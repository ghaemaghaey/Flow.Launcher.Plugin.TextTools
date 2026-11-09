# -*- coding: utf-8 -*-
"""Shared helpers: clipboard, pipe inputs, output, files and HTTP."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
import webbrowser
from typing import Any

import pyperclip

from .model import Input, Output, ToolError

try:  # Flow Launcher API is optional during tests
    from flowlauncher import FlowLauncherAPI
except Exception:  # pragma: no cover
    FlowLauncherAPI = None  # type: ignore

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_DIGIT_MAP = {ch: str(i) for i, ch in enumerate(_PERSIAN_DIGITS)}
_DIGIT_MAP.update({ch: str(i) for i, ch in enumerate(_ARABIC_DIGITS)})


# --------------------------------------------------------------------------
# Clipboard
# --------------------------------------------------------------------------

def _clipboard_retry(callback, attempts: int = 6):
    last_error = None
    for _ in range(attempts):
        try:
            return callback()
        except Exception as exc:  # clipboard can be briefly locked by another app
            last_error = exc
            time.sleep(0.15)
    raise last_error


def read_clipboard() -> Input:
    override = os.environ.get("TEXTTOOLS_CLIPBOARD_FILE")
    if override:
        try:
            with open(override, encoding="utf-8") as fh:
                text = fh.read()
        except Exception:
            text = ""
        files = [text.strip()] if text.strip() and os.path.isfile(text.strip()) else []
        return Input(text=text, files=files)

    text = ""
    try:
        text = _clipboard_retry(lambda: pyperclip.paste() or "")
    except Exception:
        text = ""

    files: list[str] = []
    image: Any = None
    try:
        from PIL import ImageGrab  # type: ignore

        data = ImageGrab.grabclipboard()
        if isinstance(data, list):
            files = [str(item) for item in data]
        elif data is not None:
            image = data
    except Exception:
        pass

    if not files and text.strip():
        candidate = text.strip().strip('"').strip("'")
        if os.path.isfile(candidate):
            files = [candidate]

    return Input(text=text, files=files, image=image)


def copy_text(value: str) -> None:
    override = os.environ.get("TEXTTOOLS_CLIPBOARD_FILE")
    if override:
        with open(override, "w", encoding="utf-8", newline="") as fh:
            fh.write(value)
        return
    _clipboard_retry(lambda: pyperclip.copy(value))


def toast(title: str, message: str) -> None:
    if FlowLauncherAPI is None:
        return
    try:
        FlowLauncherAPI.show_msg(title or "Text Tools", message or "")
    except Exception:
        pass


def _preview(value: str, limit: int = 240) -> str:
    value = (value or "").strip()
    if len(value) > limit:
        value = value[:limit].rstrip() + " …"
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " · ")


def finish(output: Output) -> Output:
    if output.error:
        toast(output.title or "Text Tools", output.message or output.text or "Error")
        return output

    if output.open_path and not os.environ.get("TEXTTOOLS_NO_OPEN"):
        try:
            os.startfile(output.open_path)  # type: ignore[attr-defined]
        except Exception as exc:
            toast("Text Tools", f"Could not open file: {exc}")

    if output.copy and output.text:
        try:
            copy_text(output.text)
        except Exception as exc:
            toast("Text Tools", f"Could not copy to clipboard: {exc}")
            return output

    message = output.message or (
        _preview(output.text) if output.text else "Done."
    )
    toast(output.title or "Text Tools", message)
    return output


# --------------------------------------------------------------------------
# Input parsing
# --------------------------------------------------------------------------

def to_ascii_digits(value: str) -> str:
    return (value or "").translate(_DIGIT_MAP)


def parse_float(value: str, default: float | None = None) -> float:
    raw = to_ascii_digits(str(value or "")).strip()
    raw = raw.replace(",", "").replace(" ", "")
    if not raw:
        if default is None:
            raise ToolError("A number is required.")
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ToolError(f"Not a number: {value!r}") from exc


def parse_int(value: str, default: int | None = None) -> int:
    number = parse_float(value, None if default is None else float(default))
    return int(number)


def split_pipe(
    text: str,
    count: int,
    *,
    from_right: bool = False,
    strip: bool = True,
) -> list[str]:
    """Split a clipboard payload into `count` pipe-separated parts.

    Missing trailing/leading parts are filled with empty strings so callers can
    provide sensible defaults.
    """
    if count <= 1:
        return [text]
    if from_right:
        parts = text.rsplit("|", count - 1)
    else:
        parts = text.split("|", count - 1)
    if len(parts) < count:
        pad = [""] * (count - len(parts))
        parts = pad + parts if from_right else parts + pad
    if strip:
        return [part.strip() for part in parts]
    return parts


def require_path(item: Input) -> str:
    if item.files:
        return item.files[0]
    candidate = item.text.strip().strip('"').strip("'")
    if candidate and os.path.isfile(candidate):
        return candidate
    raise ToolError("Copy a file in Explorer (or put its full path on the clipboard).")


def require_image(item: Input):
    if item.image is not None:
        return item.image
    path = None
    if item.files:
        path = item.files[0]
    elif item.text.strip():
        candidate = item.text.strip().strip('"').strip("'")
        if os.path.isfile(candidate):
            path = candidate
    if path:
        try:
            from PIL import Image  # type: ignore

            return Image.open(path)
        except Exception as exc:
            raise ToolError(f"Could not open image: {exc}") from exc
    raise ToolError("Copy an image (or an image file) to the clipboard first.")


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------

def ok(text: str, *, title: str = "Text Tools", message: str = "") -> Output:
    return Output(text=text, title=title, message=message)


def err(message: str, *, title: str = "Text Tools") -> Output:
    return Output(title=title, message=message, error=True)


def json_text(value: Any, *, indent: int = 2) -> str:
    return json.dumps(value, ensure_ascii=False, indent=indent, default=str)


def format_bytes(size: int, digits: int = 2) -> str:
    if size == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    return f"{value:.{digits}f} {units[index]}"


def temp_path(extension: str, stem: str = "texttools") -> str:
    folder = os.path.join(tempfile.gettempdir(), "TextTools")
    os.makedirs(folder, exist_ok=True)
    name = f"{stem}-{uuid.uuid4().hex[:10]}.{extension.lstrip('.')}"
    return os.path.join(folder, name)


def save_image(image, extension: str = "png", stem: str = "image") -> str:
    path = temp_path(extension, stem)
    image.save(path)
    return path


def open_url(url: str) -> None:
    webbrowser.open(url)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

_USER_AGENT = "TextTools-FlowLauncher/2.0 (+https://github.com/ghaemaghaey)"


def http_get(url: str, *, timeout: int = 12, headers: dict | None = None) -> str:
    merged = {"User-Agent": _USER_AGENT, "Accept": "*/*"}
    if headers:
        merged.update(headers)
    try:
        import requests  # type: ignore

        response = requests.get(url, timeout=timeout, headers=merged)
        response.raise_for_status()
        return response.text
    except Exception:
        import urllib.request

        request = urllib.request.Request(url, headers=merged)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")


def http_json(url: str, *, timeout: int = 12, headers: dict | None = None) -> Any:
    merged = {"Accept": "application/json"}
    if headers:
        merged.update(headers)
    return json.loads(http_get(url, timeout=timeout, headers=merged))


def http_head(url: str, *, timeout: int = 12) -> tuple[int, dict, str]:
    try:
        import requests  # type: ignore

        response = requests.head(
            url, timeout=timeout, allow_redirects=True, headers={"User-Agent": _USER_AGENT}
        )
        return response.status_code, dict(response.headers), response.url
    except Exception:
        import urllib.request

        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.geturl()


def read_text_file(path: str) -> str:
    with open(path, "rb") as fh:
        raw = fh.read()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1256", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def write_text_file(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def unique_preserve(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def natural_lines(text: str) -> list[str]:
    return re.split(r"\r\n|\r|\n", text)
