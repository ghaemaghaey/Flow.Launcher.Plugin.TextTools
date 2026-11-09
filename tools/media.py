# -*- coding: utf-8 -*-
"""Image and SVG tools (Pillow based)."""

from __future__ import annotations

import base64
import io
import os
import random

from .common import format_bytes, ok, parse_float, require_image, require_path, split_pipe, temp_path
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


def _pillow():
    try:
        from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps  # type: ignore
        return Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
    except Exception as exc:
        raise ToolError("The 'Pillow' package is required for image tools.") from exc


def _load(item: Input):
    return require_image(item)


def _save(image, extension: str, stem: str) -> str:
    path = temp_path(extension, stem)
    if extension.lower() in {"jpg", "jpeg"} and image.mode in {"RGBA", "LA", "P"}:
        background = _pillow()[0].new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        background.paste(image, mask=image.split()[-1] if image.mode in {"RGBA", "LA"} else None)
        image = background
    image.save(path)
    return path


def image_compressor(item: Input) -> Output:
    quality_text, format_text = split_pipe(item.text if not item.files and item.image is None else "", 2, from_right=False, strip=True)
    quality = int(parse_float(quality_text or "70"))
    quality = max(1, min(100, quality))
    fmt = (format_text or "jpeg").lower()
    extension = "webp" if fmt in {"webp"} else "jpg"
    image = _load(item)
    original_size = len(image.tobytes())
    path = _save(image, extension, "compressed")
    size = os.path.getsize(path)
    return Output(
        title="Image Compressor",
        message=f"{format_bytes(original_size)} → {format_bytes(size)} (quality {quality}%)",
        open_path=path,
        copy=False,
    )


_register(make_tool("image-compressor", image_compressor, title="Image Compressor", hint="quality|format"))


def image_convert(item: Input) -> Output:
    fmt = (item.text.strip() if not item.files and item.image is None else "png").lower() or "png"
    extension = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp", "bmp": "bmp", "gif": "gif", "tiff": "tiff"}.get(fmt, "png")
    image = _load(item)
    path = _save(image, extension, "converted")
    return Output(title="Image Converter", message=f"Converted to {extension.upper()} ({format_bytes(os.path.getsize(path))})", open_path=path, copy=False)


_register(make_tool("image-convert", image_convert, title="Image Converter", hint="png/jpeg/webp"))


def image_crop(item: Input) -> Output:
    params = item.text if not item.files and item.image is None else ""
    x_text, y_text, w_text, h_text = split_pipe(params, 4, from_right=False, strip=True)
    image = _load(item)
    x = int(parse_float(x_text or "0"))
    y = int(parse_float(y_text or "0"))
    width = int(parse_float(w_text or str(image.width)))
    height = int(parse_float(h_text or str(image.height)))
    box = (max(0, x), max(0, y), min(image.width, max(0, x) + width), min(image.height, max(0, y) + height))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ToolError("Crop rectangle is outside the image.")
    path = _save(image.crop(box), "png", "cropped")
    return Output(title="Image Crop", message=f"Cropped to {box[2]-box[0]}×{box[3]-box[1]}", open_path=path, copy=False)


_register(make_tool("image-crop", image_crop, title="Image Crop", hint="x|y|width|height"))


def image_filters(item: Input) -> Output:
    params = item.text if not item.files and item.image is None else ""
    grayscale_text, invert_text, brightness_text, contrast_text, sepia_text = split_pipe(params, 5, from_right=False, strip=True)
    Image, _draw, ImageEnhance, _filter, ImageOps = _pillow()
    image = _load(item).convert("RGB")
    grayscale = max(0, min(100, int(parse_float(grayscale_text or "0"))))
    invert = max(0, min(100, int(parse_float(invert_text or "0"))))
    brightness = max(0, min(200, int(parse_float(brightness_text or "100"))))
    contrast = max(0, min(200, int(parse_float(contrast_text or "100"))))
    sepia = max(0, min(100, int(parse_float(sepia_text or "0"))))
    if grayscale:
        image = Image.blend(image, ImageOps.grayscale(image).convert("RGB"), grayscale / 100)
    if invert:
        image = Image.blend(image, ImageOps.invert(image), invert / 100)
    if brightness != 100:
        image = ImageEnhance.Brightness(image).enhance(brightness / 100)
    if contrast != 100:
        image = ImageEnhance.Contrast(image).enhance(contrast / 100)
    if sepia:
        sepia_image = ImageOps.colorize(ImageOps.grayscale(image), "#704214", "#fff5e1")
        image = Image.blend(image, sepia_image, sepia / 100)
    path = _save(image, "png", "filtered")
    return Output(title="Image Filters", message="Filters applied", open_path=path, copy=False)


_register(make_tool("image-filters", image_filters, title="Image Filters", hint="grayscale|invert|brightness|contrast|sepia"))


def image_resizer(item: Input) -> Output:
    params = item.text if not item.files and item.image is None else ""
    width_text, height_text = split_pipe(params, 2, from_right=False, strip=True)
    image = _load(item)
    width = int(parse_float(width_text)) if width_text else 0
    height = int(parse_float(height_text)) if height_text else 0
    if width <= 0 and height <= 0:
        width = 800
    if width <= 0:
        width = max(1, round(image.width * height / image.height))
    if height <= 0:
        height = max(1, round(image.height * width / image.width))
    path = _save(image.resize((width, height), _pillow()[0].LANCZOS), "png", "resized")
    return Output(title="Image Resizer", message=f"Resized to {width}×{height}", open_path=path, copy=False)


_register(make_tool("image-resizer", image_resizer, title="Image Resizer", hint="width|height"))


def image_rotate_flip(item: Input) -> Output:
    params = item.text if not item.files and item.image is None else ""
    angle_text, flip_h_text, flip_v_text = split_pipe(params, 3, from_right=False, strip=True)
    angle = parse_float(angle_text or "0")
    flip_h = flip_h_text.lower() in {"1", "true", "yes", "h"}
    flip_v = flip_v_text.lower() in {"1", "true", "yes", "v"}
    image = _load(item)
    if angle:
        image = image.rotate(-angle, expand=True)
    if flip_h:
        image = image.transpose(_pillow()[0].FLIP_LEFT_RIGHT)
    if flip_v:
        image = image.transpose(_pillow()[0].FLIP_TOP_BOTTOM)
    path = _save(image, "png", "rotated")
    return Output(title="Rotate & Flip", message=f"Angle {angle}°", open_path=path, copy=False)


_register(make_tool("image-rotate-flip", image_rotate_flip, title="Rotate & Flip", hint="angle|flip_h|flip_v"))


def image_to_base64(item: Input) -> Output:
    try:
        path = require_path(item)
        with open(path, "rb") as fh:
            data = fh.read()
        extension = os.path.splitext(path)[1].lstrip(".").lower() or "png"
        mime = {
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
            "svg": "image/svg+xml",
        }.get(extension, "application/octet-stream")
    except ToolError:
        image = _load(item)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data = buffer.getvalue()
        mime = "image/png"
    encoded = base64.b64encode(data).decode("ascii")
    return ok(f"data:{mime};base64,{encoded}", title="Image to Base64", message=f"{format_bytes(len(data))}")


_register(make_tool("image-to-base64", image_to_base64, title="Image to Base64", hint="clipboard image/file"))


def image_to_scan(item: Input) -> Output:
    params = item.text if not item.files and item.image is None else ""
    angle_text, noise_text, contrast_text, gray_text = split_pipe(params, 4, from_right=False, strip=True)
    angle = parse_float(angle_text or "2")
    noise = max(0, min(50, int(parse_float(noise_text or "14"))))
    contrast = max(80, min(160, int(parse_float(contrast_text or "108"))))
    gray = gray_text.lower() in {"1", "true", "yes"}
    Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps = _pillow()
    image = _load(item).convert("RGB")
    if gray:
        image = ImageOps.grayscale(image).convert("RGB")
    image = image.rotate(-angle, expand=True, fillcolor=(250, 250, 250))
    image = ImageEnhance.Contrast(image).enhance(contrast / 100)
    if noise:
        pixels = image.load()
        random.seed(1234)
        for y in range(image.height):
            for x in range(image.width):
                n = int((random.random() - 0.5) * 2 * noise)
                r, g, b = pixels[x, y]
                pixels[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    path = _save(image, "jpg", "scan")
    return Output(title="Image to Scan", message="Scan effect applied", open_path=path, copy=False)


_register(make_tool("image-to-scan", image_to_scan, title="Image to Scan", hint="angle|noise|contrast|gray"))


def svg_to_png(item: Input) -> Output:
    scale_text, svg_text = split_pipe(item.text, 2, from_right=True, strip=False)
    scale = parse_float(scale_text) if scale_text.strip() and scale_text.strip().replace(".", "", 1).isdigit() else 2.0
    svg_text = svg_text if svg_text.strip().startswith("<") else item.text
    if not svg_text.strip().startswith("<"):
        path = require_path(item)
        with open(path, encoding="utf-8") as fh:
            svg_text = fh.read()
    try:
        from reportlab.graphics import renderPM  # type: ignore
        from svglib.svglib import svg2rlg  # type: ignore
    except Exception as exc:
        raise ToolError("The 'svglib' and 'reportlab' packages are required for SVG rendering.") from exc
    import tempfile

    source = tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8")
    source.write(svg_text)
    source.close()
    try:
        drawing = svg2rlg(source.name)
        if drawing is None:
            raise ToolError("Could not parse SVG.")
        drawing.width *= scale
        drawing.height *= scale
        drawing.scale(scale, scale)
        output = temp_path("png", "svg")
        renderPM.drawToFile(drawing, output, fmt="PNG")
    finally:
        os.unlink(source.name)
    return Output(title="SVG → PNG", message="PNG generated", open_path=output, copy=False)


_register(make_tool("svg-to-png", svg_to_png, title="SVG to PNG", hint="scale|SVG"))
