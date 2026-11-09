# -*- coding: utf-8 -*-
"""Color and CSS design tools."""

from __future__ import annotations

import colorsys
import math
import re

from .common import ok, parse_float, split_pipe, temp_path
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# Color parsing / conversion
# --------------------------------------------------------------------------

def _clamp(value: float) -> int:
    return max(0, min(255, round(value)))


def parse_color(value: str) -> tuple[int, int, int]:
    text = value.strip().lower()
    if text.startswith("#"):
        hex_value = text[1:]
        if len(hex_value) == 3:
            hex_value = "".join(char * 2 for char in hex_value)
        if len(hex_value) == 6 and re.fullmatch(r"[0-9a-f]{6}", hex_value):
            return tuple(int(hex_value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    if text.startswith("rgb"):
        numbers = [int(number) for number in re.findall(r"\d+", text)]
        if len(numbers) >= 3:
            return _clamp(numbers[0]), _clamp(numbers[1]), _clamp(numbers[2])
    if text.startswith("hsl"):
        numbers = [float(number) for number in re.findall(r"-?\d+(?:\.\d+)?", text)]
        if len(numbers) >= 3:
            return hsl_to_rgb(numbers[0], numbers[1], numbers[2])
    if re.fullmatch(r"[0-9a-f]{6}", text):
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    raise ToolError(f"Invalid color: {value!r}")


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in rgb)


def rgb_to_hsl(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = [channel / 255 for channel in rgb]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s * 100, l * 100


def rgb_to_hsv(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = [channel / 255 for channel in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360, s * 100, v * 100


def hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l / 100, s / 100)
    return _clamp(r * 255), _clamp(g * 255), _clamp(b * 255)


def _luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for value in rgb:
        value /= 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    first, second = _luminance(a), _luminance(b)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def color_converter(item: Input) -> Output:
    rgb = parse_color(item.require_text())
    h, s, l = rgb_to_hsl(rgb)
    hsv_h, hsv_s, hsv_v = rgb_to_hsv(rgb)
    return ok(
        "\n".join(
            [
                f"HEX: {to_hex(rgb)}",
                f"RGB: rgb({rgb[0]}, {rgb[1]}, {rgb[2]})",
                f"HSL: hsl({round(h)}, {round(s)}%, {round(l)}%)",
                f"HSV: hsv({round(hsv_h)}, {round(hsv_s)}%, {round(hsv_v)}%)",
            ]
        ),
        title="Color Converter",
    )


_register(make_tool("color-converter", color_converter, title="Color Converter", hint="hex, rgb() or hsl()"))


def contrast_checker(item: Input) -> Output:
    fg_text, bg_text = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    foreground = parse_color(fg_text)
    background = parse_color(bg_text)
    ratio = _contrast(foreground, background)
    return ok(
        "\n".join(
            [
                f"Contrast: {ratio:.2f}:1",
                f"AA normal text (4.5): {'PASS' if ratio >= 4.5 else 'FAIL'}",
                f"AA large text (3.0): {'PASS' if ratio >= 3 else 'FAIL'}",
                f"AAA normal text (7.0): {'PASS' if ratio >= 7 else 'FAIL'}",
                f"AAA large text (4.5): {'PASS' if ratio >= 4.5 else 'FAIL'}",
            ]
        ),
        title="Contrast Checker",
    )


_register(make_tool("contrast-checker", contrast_checker, title="Contrast Checker", hint="foreground|background"))


# --------------------------------------------------------------------------
# Palette / gradient / previews
# --------------------------------------------------------------------------

def _mix(rgb: tuple[int, int, int], target: int, ratio: float) -> tuple[int, int, int]:
    return tuple(_clamp(channel + (target - channel) * ratio) for channel in rgb)  # type: ignore[return-value]


def _rotate(rgb: tuple[int, int, int], degrees: float) -> tuple[int, int, int]:
    h, s, l = rgb_to_hsl(rgb)
    return hsl_to_rgb(h + degrees, s, l)


def _save_palette(colors: list[tuple[str, str]]) -> str:
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception as exc:
        raise ToolError("Pillow is required for palette previews.") from exc
    cell = 110
    image = Image.new("RGB", (cell * len(colors), cell + 24), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    for index, (label, hex_value) in enumerate(colors):
        rgb = parse_color(hex_value)
        draw.rectangle([index * cell, 0, (index + 1) * cell - 1, cell], fill=rgb)
        draw.text((index * cell + 6, cell + 5), hex_value, fill=(30, 30, 30))
    path = temp_path("png", "palette")
    image.save(path)
    return path


def color_palette(item: Input) -> Output:
    rgb = parse_color(item.require_text())
    rows = {
        "Tints": [to_hex(_mix(rgb, 255, ratio)) for ratio in (0.15, 0.3, 0.45, 0.6, 0.78)],
        "Shades": [to_hex(_mix(rgb, 0, ratio)) for ratio in (0.15, 0.3, 0.45, 0.6, 0.78)],
        "Complementary": [to_hex(rgb), to_hex(_rotate(rgb, 180))],
        "Analogous": [to_hex(_rotate(rgb, -30)), to_hex(rgb), to_hex(_rotate(rgb, 30))],
        "Triadic": [to_hex(rgb), to_hex(_rotate(rgb, 120)), to_hex(_rotate(rgb, 240))],
    }
    lines = []
    colors = []
    for title, values in rows.items():
        lines.append(f"{title}: " + ", ".join(values))
        colors.extend((title, value) for value in values)
    path = _save_palette(colors[:10])
    return Output(text="\n".join(lines), title="Color Palette", open_path=path, message="Palette preview opened")


_register(make_tool("color-palette", color_palette, title="Color Palette Generator", hint="hex color"))


def _save_gradient(css: str, stops: list[tuple[float, tuple[int, int, int]]], kind: str, angle: float) -> str:
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:
        raise ToolError("Pillow is required for gradient previews.") from exc
    width, height = 480, 240
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    stops = sorted(stops, key=lambda pair: pair[0])
    for y in range(height):
        for x in range(width):
            if kind == "radial":
                distance = math.hypot(x - width / 2, y - height / 2) / math.hypot(width / 2, height / 2)
                position = min(1.0, distance)
            else:
                radians = math.radians(angle)
                position = ((x - width / 2) * math.cos(radians) + (y - height / 2) * math.sin(radians)) / max(width, height) + 0.5
                position = max(0.0, min(1.0, position))
            previous = stops[0]
            following = stops[-1]
            for index, stop in enumerate(stops):
                if stop[0] <= position:
                    previous = stop
                if stop[0] >= position:
                    following = stop
                    break
            span = following[0] - previous[0] or 1
            ratio = (position - previous[0]) / span
            color = tuple(
                _clamp(previous[1][channel] + (following[1][channel] - previous[1][channel]) * ratio)
                for channel in range(3)
            )
            pixels[x, y] = color
    path = temp_path("png", "gradient")
    image.save(path)
    return path


def gradient_generator(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 3, from_right=False, strip=False)
    kind = (parts[0] or "linear").strip().lower()
    angle_text = (parts[1] or "90").strip()
    angle = float(angle_text) if re.fullmatch(r"-?\d+(?:\.\d+)?", angle_text) else 90.0
    stop_text = parts[2] if len(parts) > 2 else ""
    stop_values = []
    for part in stop_text.split(","):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"(.+?)\s+(-?\d+(?:\.\d+)?)%?$", part)
        if match:
            color = parse_color(match.group(1).strip())
            position = max(0.0, min(100.0, float(match.group(2))))
        else:
            color = parse_color(part)
            position = 0.0 if not stop_values else 100.0
        stop_values.append((position, color))
    if len(stop_values) < 2:
        raise ToolError("Provide at least two color stops, e.g. #2dd4c4,#7c3aed.")
    stop_values.sort(key=lambda pair: pair[0])
    stop_string = ", ".join(f"{to_hex(color)} {position:g}%" for position, color in stop_values)
    css = f"linear-gradient({angle:g}deg, {stop_string})" if kind != "radial" else f"radial-gradient(circle, {stop_string})"
    path = _save_gradient(css, stop_values, kind, angle)
    return Output(text=f"background: {css};", title="Gradient Generator", open_path=path, message="Gradient preview opened")


_register(make_tool("gradient-generator", gradient_generator, title="Gradient Generator", hint="linear|angle|color pos%,..."))


def shadow_generator(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 7, from_right=False, strip=True)
    x, y, blur, spread, color_text, opacity_text, inset_text = parts
    x_value = int(parse_float(x or "0"))
    y_value = int(parse_float(y or "10"))
    blur_value = max(0, int(parse_float(blur or "25")))
    spread_value = int(parse_float(spread or "-5"))
    color = parse_color(color_text or "#0a0f14")
    opacity = max(0, min(100, int(parse_float(opacity_text or "35"))))
    inset = inset_text.lower() in {"1", "true", "yes", "inset"}
    rgba = f"rgba({color[0]}, {color[1]}, {color[2]}, {opacity / 100:.2f})"
    shadow = f"{'inset ' if inset else ''}{x_value}px {y_value}px {blur_value}px {spread_value}px {rgba}"
    path = _save_shadow(x_value, y_value, blur_value, spread_value, color, opacity, inset)
    return Output(text=f"box-shadow: {shadow};", title="Box Shadow", open_path=path, message="Shadow preview opened")


def _save_shadow(x, y, blur, spread, color, opacity, inset):
    try:
        from PIL import Image, ImageDraw, ImageFilter  # type: ignore
    except Exception as exc:
        raise ToolError("Pillow is required for shadow previews.") from exc
    canvas = Image.new("RGBA", (480, 320), (240, 240, 240, 255))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    box = [140, 90, 340, 230]
    draw.rounded_rectangle(
        [box[0] + x - spread, box[1] + y - spread, box[2] + x + spread, box[3] + y + spread],
        radius=24,
        fill=(color[0], color[1], color[2], int(opacity * 2.55)),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(max(0, blur / 2)))
    canvas = Image.alpha_composite(canvas, layer)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=24, fill=(255, 255, 255, 255))
    path = temp_path("png", "shadow")
    canvas.convert("RGB").save(path)
    return path


_register(make_tool("shadow-generator", shadow_generator, title="Box Shadow Generator", hint="x|y|blur|spread|color|opacity|inset"))


def border_radius_generator(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 4, from_right=False, strip=True)
    values = [max(0, min(150, int(parse_float(part or "24")))) for part in parts]
    tl, tr, br, bl = values
    radius = f"{tl}px" if tl == tr == br == bl else f"{tl}px {tr}px {br}px {bl}px"
    path = _save_border_radius(max(values))
    return Output(text=f"border-radius: {radius};", title="Border Radius", open_path=path, message="Preview opened")


def _save_border_radius(radius: int) -> str:
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception as exc:
        raise ToolError("Pillow is required for previews.") from exc
    image = Image.new("RGB", (360, 300), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([80, 70, 280, 230], radius=max(1, radius), outline=(45, 212, 196), width=3, fill=(220, 250, 247))
    path = temp_path("png", "border-radius")
    image.save(path)
    return path


_register(make_tool("border-radius-generator", border_radius_generator, title="Border Radius Generator", hint="tl|tr|br|bl"))


def css_filter_generator(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 8, from_right=False, strip=True)
    defaults = [0, 100, 100, 0, 100, 0, 0, 0]
    values = []
    for index, part in enumerate(parts):
        try:
            values.append(float(part) if part else float(defaults[index]))
        except ValueError:
            values.append(float(defaults[index]))
    blur, brightness, contrast, grayscale, saturate, sepia, hue, invert = values
    definitions = [
        ("blur", blur, "px", 0), ("brightness", brightness, "%", 100), ("contrast", contrast, "%", 100),
        ("grayscale", grayscale, "%", 0), ("saturate", saturate, "%", 100), ("sepia", sepia, "%", 0),
        ("hue-rotate", hue, "deg", 0), ("invert", invert, "%", 0),
    ]
    filter_text = " ".join(f"{name}({value:g}{unit})" for name, value, unit, default in definitions if value != default)
    applied = filter_text or "none"
    path = _save_filter(values)
    return Output(text=f"filter: {applied};", title="CSS Filter", open_path=path, message="Filter preview opened")


def _save_filter(values):
    try:
        from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps  # type: ignore
    except Exception as exc:
        raise ToolError("Pillow is required for previews.") from exc
    blur, brightness, contrast, grayscale, saturate, sepia, hue, invert = values
    image = Image.new("RGB", (320, 240), (45, 212, 196))
    draw = ImageDraw.Draw(image)
    for index in range(6):
        draw.rectangle([index * 53, 0, index * 53 + 52, 240], fill=[(45, 212, 196), (124, 58, 237), (245, 158, 11), (239, 68, 68), (59, 130, 246), (16, 185, 129)][index])
    if blur > 0:
        image = image.filter(ImageFilter.GaussianBlur(blur / 2))
    if brightness != 100:
        image = ImageEnhance.Brightness(image).enhance(brightness / 100)
    if contrast != 100:
        image = ImageEnhance.Contrast(image).enhance(contrast / 100)
    if grayscale:
        gray = ImageOps.grayscale(image).convert("RGB")
        image = Image.blend(image, gray, grayscale / 100)
    if saturate != 100:
        image = ImageEnhance.Color(image).enhance(saturate / 100)
    if sepia:
        sepia_image = ImageOps.colorize(ImageOps.grayscale(image), "#704214", "#fff5e1")
        image = Image.blend(image, sepia_image, sepia / 100)
    if hue:
        hsv = image.convert("HSV")
        pixels = list(hsv.getdata())
        shifted = [(int((h + hue * 255 / 360) % 255), s, v) for h, s, v in pixels]
        hsv.putdata(shifted)
        image = hsv.convert("RGB")
    if invert:
        inverted = ImageOps.invert(image)
        image = Image.blend(image, inverted, invert / 100)
    path = temp_path("png", "css-filter")
    image.save(path)
    return path


_register(make_tool("css-filter-generator", css_filter_generator, title="CSS Filter Generator", hint="blur|brightness|contrast|grayscale|saturate|sepia|hue|invert"))
