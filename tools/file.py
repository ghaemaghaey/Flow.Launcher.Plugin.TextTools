# -*- coding: utf-8 -*-
"""File, archive and byte tools."""

from __future__ import annotations

import base64
import gzip
import hashlib
import os
import re
import zlib

from .common import format_bytes, ok, parse_float, require_path, split_pipe, temp_path, to_ascii_digits
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


def _read_file(item: Input) -> tuple[str, bytes]:
    path = require_path(item)
    with open(path, "rb") as fh:
        return path, fh.read()


def _mime_for(path: str) -> str:
    extension = os.path.splitext(path)[1].lstrip(".").lower()
    return {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
        "webp": "image/webp", "svg": "image/svg+xml", "pdf": "application/pdf",
        "zip": "application/zip", "gz": "application/gzip", "txt": "text/plain",
        "json": "application/json", "html": "text/html", "css": "text/css",
        "js": "text/javascript", "xml": "application/xml",
    }.get(extension, "application/octet-stream")


# --------------------------------------------------------------------------
# Base64 file
# --------------------------------------------------------------------------

def file_to_base64(item: Input) -> Output:
    path, data = _read_file(item)
    encoded = base64.b64encode(data).decode("ascii")
    mime = _mime_for(path)
    return ok(
        f"Base64:\n{encoded}\n\nData URI:\ndata:{mime};base64,{encoded}",
        title="File → Base64",
        message=f"{os.path.basename(path)} ({format_bytes(len(data))})",
    )


def base64_to_file(item: Input) -> Output:
    value = item.require_text().strip()
    match = re.match(r"^data:([^;,]*)(;base64)?,(.*)$", value, re.DOTALL)
    if match:
        mime = match.group(1) or "application/octet-stream"
        payload = match.group(3)
        data = base64.b64decode(payload + "=" * (-len(payload) % 4)) if match.group(2) else payload.encode("utf-8")
        extension = (mime.split("/")[-1] or "bin").split("+")[0]
    else:
        data = base64.b64decode(re.sub(r"\s+", "", value) + "=" * (-len(re.sub(r"\s+", "", value)) % 4))
        extension = "bin"
    path = temp_path(extension, "decoded")
    with open(path, "wb") as fh:
        fh.write(data)
    return Output(title="Base64 → File", message=f"{format_bytes(len(data))} decoded", open_path=path, copy=False)


_register(make_tool("base64-file", file_to_base64, title="File → Base64", hint="file path or clipboard file"))
_register(make_tool("base64-file", base64_to_file, id="base64-to-file", title="Base64 → File", hint="base64 or data URI"))


# --------------------------------------------------------------------------
# File hash
# --------------------------------------------------------------------------

def file_hash(item: Input) -> Output:
    try:
        path, data = _read_file(item)
    except ToolError:
        image = item.image
        if image is None:
            raise
        import io

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data = buffer.getvalue()
        path = "clipboard-image.png"
    lines = [
        f"File: {os.path.basename(path)}",
        f"Size: {format_bytes(len(data))}",
        f"MD5: {hashlib.md5(data).hexdigest()}",
        f"SHA-1: {hashlib.sha1(data).hexdigest()}",
        f"SHA-256: {hashlib.sha256(data).hexdigest()}",
        f"SHA-512: {hashlib.sha512(data).hexdigest()}",
    ]
    return ok("\n".join(lines), title="File Hash")


_register(make_tool("file-hash", file_hash, title="File Hash", hint="file path or clipboard file"))


# --------------------------------------------------------------------------
# File size
# --------------------------------------------------------------------------

_DEC = ["B", "KB", "MB", "GB", "TB", "PB"]
_BIN = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]


def _fmt_size(size: float, units: list[str], base: int) -> str:
    if size == 0:
        return f"0 {units[0]}"
    index = min(int(__import__("math").log(size, base)), len(units) - 1)
    return f"{size / (base ** index):.3f} {units[index]}"


def bytes_to_human(item: Input) -> Output:
    size = parse_float(to_ascii_digits(item.require_text().strip().replace(",", "")))
    if size < 0:
        raise ToolError("Size must be non-negative.")
    return ok(
        f"Decimal: {_fmt_size(size, _DEC, 1000)}\nBinary: {_fmt_size(size, _BIN, 1024)}",
        title="Bytes → Human",
    )


def human_to_bytes(item: Input) -> Output:
    amount_text, unit = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    amount = parse_float(to_ascii_digits(amount_text.strip().replace(",", "")))
    unit = (unit or "MB").strip()
    if unit in _DEC:
        size = amount * (1000 ** _DEC.index(unit))
    elif unit in _BIN:
        size = amount * (1024 ** _BIN.index(unit))
    else:
        raise ToolError(f"Unknown unit: {unit}")
    return ok(f"{round(size):,} bytes", title="Human → Bytes")


_register(make_tool("file-size-formatter", bytes_to_human, title="Bytes → Human", hint="bytes"))
_register(make_tool("file-size-formatter", human_to_bytes, id="human-to-bytes", title="Human → Bytes", hint="amount|unit"))


# --------------------------------------------------------------------------
# gzip / deflate
# --------------------------------------------------------------------------

def gzip_compress(item: Input) -> Output:
    data = item.require_text().encode("utf-8")
    compressed = gzip.compress(data)
    return ok(
        base64.b64encode(compressed).decode("ascii"),
        title="Gzip Compress",
        message=f"{len(data)} → {len(compressed)} bytes",
    )


def gzip_decompress(item: Input) -> Output:
    try:
        data = gzip.decompress(base64.b64decode(re.sub(r"\s+", "", item.require_text())))
    except Exception as exc:
        raise ToolError(f"Invalid gzip data: {exc}") from exc
    return ok(data.decode("utf-8", "replace"), title="Gzip Decompress")


def deflate_compress(item: Input) -> Output:
    data = item.require_text().encode("utf-8")
    compressed = zlib.compress(data)
    return ok(
        base64.b64encode(compressed).decode("ascii"),
        title="Deflate Compress",
        message=f"{len(data)} → {len(compressed)} bytes",
    )


def deflate_decompress(item: Input) -> Output:
    try:
        data = zlib.decompress(base64.b64decode(re.sub(r"\s+", "", item.require_text())))
    except Exception as exc:
        raise ToolError(f"Invalid deflate data: {exc}") from exc
    return ok(data.decode("utf-8", "replace"), title="Deflate Decompress")


_register(make_tool("gzip-tool", gzip_compress, title="Gzip Compress", hint="clipboard text"))
_register(make_tool("gzip-tool", gzip_decompress, id="gzip-decompress", title="Gzip Decompress", hint="base64"))
_register(make_tool("gzip-tool", deflate_compress, id="deflate-compress", title="Deflate Compress", hint="clipboard text"))
_register(make_tool("gzip-tool", deflate_decompress, id="deflate-decompress", title="Deflate Decompress", hint="base64"))


# --------------------------------------------------------------------------
# Hex dump / line endings
# --------------------------------------------------------------------------

def _dump(data: bytes) -> str:
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        hex_parts = []
        ascii_part = ""
        for index in range(16):
            if index < len(chunk):
                byte = chunk[index]
                hex_parts.append(f"{byte:02x}")
                ascii_part += chr(byte) if 0x20 <= byte <= 0x7E else "."
            else:
                hex_parts.append("  ")
            if index == 7:
                hex_parts.append("")
        lines.append(f"{offset:08x}  {' '.join(hex_parts)}  |{ascii_part}|")
    return "\n".join(lines)


def hex_dump(item: Input) -> Output:
    if item.files or (item.text.strip() and os.path.isfile(item.text.strip().strip('"'))):
        path, data = _read_file(item)
        label = os.path.basename(path)
    else:
        data = item.require_text().encode("utf-8")
        label = "clipboard text"
    return ok(_dump(data), title="Hex Dump", message=f"{label} ({len(data)} bytes)")


_register(make_tool("hex-dump", hex_dump, title="Hex Dump", hint="text, file path or clipboard file"))


def _eol(value: str, target: str) -> Output:
    stats = {
        "CRLF": len(re.findall(r"\r\n", value)),
        "CR": len(re.findall(r"\r(?!\n)", value)),
        "LF": len(re.findall(r"(?<!\r)\n", value)),
    }
    kinds = sum(1 for count in stats.values() if count)
    detected = "Mixed" if kinds > 1 else next((name for name, count in stats.items() if count), "None")
    converted = value.replace("\r\n", "\n").replace("\r", "\n")
    if target == "crlf":
        converted = converted.replace("\n", "\r\n")
    elif target == "cr":
        converted = converted.replace("\n", "\r")
    return ok(
        f"Detected: {detected}\nLF: {stats['LF']}  CRLF: {stats['CRLF']}  CR: {stats['CR']}\n\n{converted}",
        title=f"Line Endings: {target.upper()}",
    )


_register(make_tool("line-ending-converter", lambda item: _eol(item.require_text(), "lf"), title="Line Endings: LF", hint="clipboard text"))
_register(make_tool("line-ending-converter", lambda item: _eol(item.require_text(), "crlf"), id="eol-crlf", title="Line Endings: CRLF", hint="clipboard text"))
_register(make_tool("line-ending-converter", lambda item: _eol(item.require_text(), "cr"), id="eol-cr", title="Line Endings: CR", hint="clipboard text"))
