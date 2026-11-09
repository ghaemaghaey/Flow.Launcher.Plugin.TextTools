# -*- coding: utf-8 -*-
"""Generators: IDs, tokens, fake data, QR and identicons."""

from __future__ import annotations

import colorsys
import hashlib
import json
import os
import random
import re
import secrets
import string
import time
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone

from .common import err, json_text, ok, parse_int, split_pipe, temp_path
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_ROOT, "generators_meta.json"), encoding="utf-8") as _fh:
    _GEN = json.load(_fh)
with open(os.path.join(_ROOT, "lorem_meta.json"), encoding="utf-8") as _fh:
    _LOREM = json.load(_fh)


# --------------------------------------------------------------------------
# UUID / ULID / NanoID
# --------------------------------------------------------------------------

def _uuid_options(item: Input) -> tuple[int, bool, bool]:
    parts = split_pipe(item.text, 3, from_right=False, strip=True)
    count = 1
    if parts[0].isdigit():
        count = max(1, min(200, int(parts[0])))
    dashes = parts[1].lower() not in {"0", "false", "no"}
    upper = parts[2].lower() in {"1", "true", "yes"}
    return count, dashes, upper


def _format_uuid(value: uuid_lib.UUID, dashes: bool, upper: bool) -> str:
    text = str(value)
    if not dashes:
        text = text.replace("-", "")
    return text.upper() if upper else text


def uuid4_tool(item: Input) -> Output:
    count, dashes, upper = _uuid_options(item)
    values = [_format_uuid(uuid_lib.uuid4(), dashes, upper) for _ in range(count)]
    return ok("\n".join(values), title=f"UUID v4 ({count})")


def uuid1_tool(item: Input) -> Output:
    count, dashes, upper = _uuid_options(item)
    values = [_format_uuid(uuid_lib.uuid1(), dashes, upper) for _ in range(count)]
    return ok("\n".join(values), title=f"UUID v1 ({count})")


def uuid7_tool(item: Input) -> Output:
    count, dashes, upper = _uuid_options(item)
    values = []
    for _ in range(count):
        timestamp = int(time.time() * 1000) & ((1 << 48) - 1)
        rand_a = secrets.randbits(12)
        rand_b = secrets.randbits(62)
        value = (timestamp << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
        values.append(_format_uuid(uuid_lib.UUID(int=value), dashes, upper))
    return ok("\n".join(values), title=f"UUID v7 ({count})")


_register(make_tool("uuid", uuid4_tool, title="UUID v4", hint="count|dashes|upper"))
_register(make_tool("uuid", uuid1_tool, id="uuid-v1", title="UUID v1", hint="count|dashes|upper"))
_register(make_tool("uuid", uuid7_tool, id="uuid-v7", title="UUID v7", hint="count|dashes|upper"))


_ULID_ENC = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid_encode_time(ms: int) -> str:
    output = ""
    for _ in range(10):
        remainder = ms % 32
        output = _ULID_ENC[remainder] + output
        ms = (ms - remainder) // 32
    return output


def _ulid() -> str:
    timestamp = _ulid_encode_time(int(time.time() * 1000))
    bits = secrets.randbits(80)
    random_part = "".join(
        _ULID_ENC[(bits >> (75 - 5 * index)) & 31] for index in range(16)
    )
    return timestamp + random_part


def ulid_tool(item: Input) -> Output:
    count_text = item.text.strip()
    count = max(1, min(500, int(count_text))) if count_text.isdigit() else 1
    return ok("\n".join(_ulid() for _ in range(count)), title=f"ULID ({count})")


_register(make_tool("ulid", ulid_tool, title="ULID", hint="count"))


_NANOID_ALPHABET = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict"


def nanoid_tool(item: Input) -> Output:
    parts = split_pipe(item.text, 2, from_right=False, strip=True)
    size = int(parts[0]) if parts[0].isdigit() else 21
    count = int(parts[1]) if parts[1].isdigit() else 1
    size = max(2, min(256, size))
    count = max(1, min(500, count))
    values = [
        "".join(secrets.choice(_NANOID_ALPHABET) for _ in range(size))
        for _ in range(count)
    ]
    return ok("\n".join(values), title=f"NanoID ({count})")


_register(make_tool("nanoid", nanoid_tool, title="NanoID", hint="size|count"))


# --------------------------------------------------------------------------
# Random strings / passwords / PINs / tokens
# --------------------------------------------------------------------------

_SETS = {
    "lower": string.ascii_lowercase,
    "upper": string.ascii_uppercase,
    "digits": string.digits,
    "symbols": "!@#$%^&*()-_=+[]{};:,.<>?",
}


def random_string(item: Input) -> Output:
    parts = split_pipe(item.text, 6, from_right=False, strip=True)
    length = int(parts[0]) if parts[0].isdigit() else 24
    count = int(parts[1]) if parts[1].isdigit() else 1
    flags = [part.lower() not in {"0", "false", "no"} if part else default for part, default in zip(parts[2:6], [True, True, True, False])]
    pool = "".join(_SETS[name] for name, enabled in zip(["lower", "upper", "digits", "symbols"], flags) if enabled)
    if not pool:
        raise ToolError("Select at least one character set.")
    length = max(1, min(256, length))
    count = max(1, min(500, count))
    values = ["".join(secrets.choice(pool) for _ in range(length)) for _ in range(count)]
    return ok("\n".join(values), title=f"Random Strings ({count})")


_register(make_tool("random-string", random_string, title="Random String", hint="length|count|lower|upper|digits|symbols"))


def password_generator(item: Input) -> Output:
    parts = split_pipe(item.text, 6, from_right=False, strip=True)
    length = int(parts[0]) if parts[0].isdigit() else 16
    flags = [part.lower() not in {"0", "false", "no"} if part else default for part, default in zip(parts[1:6], [True, True, True, True, False])]
    pool = "".join(_SETS[name] for name, enabled in zip(["lower", "upper", "digits", "symbols"], flags[:4]) if enabled)
    if flags[4]:
        pool = re.sub(r"[Il1O0o]", "", pool)
    if not pool:
        raise ToolError("Select at least one character set.")
    length = max(4, min(64, length))
    return ok("".join(secrets.choice(pool) for _ in range(length)), title="Password Generator")


_register(make_tool("password-generator", password_generator, title="Password Generator", hint="length|lower|upper|digits|symbols|no_ambiguous"))


def pin_generator(item: Input) -> Output:
    parts = split_pipe(item.text, 3, from_right=False, strip=True)
    length = int(parts[0]) if parts[0].isdigit() else 6
    count = int(parts[1]) if parts[1].isdigit() else 1
    leading_zero = parts[2].lower() not in {"0", "false", "no"} if parts[2] else True
    length = max(1, min(32, length))
    count = max(1, min(500, count))
    values = []
    for _ in range(count):
        digits = []
        for index in range(length):
            if index == 0 and not leading_zero:
                digits.append(str(secrets.randbelow(9) + 1))
            else:
                digits.append(str(secrets.randbelow(10)))
        values.append("".join(digits))
    return ok("\n".join(values), title=f"PINs ({count})")


_register(make_tool("pin-generator", pin_generator, title="PIN Generator", hint="length|count|leading_zero"))


def token_generator(item: Input) -> Output:
    parts = split_pipe(item.text, 3, from_right=False, strip=True)
    fmt = (parts[0] or "hex").lower()
    byte_len = int(parts[1]) if parts[1].isdigit() else 32
    count = int(parts[2]) if parts[2].isdigit() else 1
    byte_len = max(1, min(256, byte_len))
    count = max(1, min(500, count))
    values = []
    for _ in range(count):
        data = secrets.token_bytes(byte_len)
        if fmt in {"base64url", "base64"}:
            import base64

            values.append(base64.urlsafe_b64encode(data).decode("ascii").rstrip("="))
        else:
            values.append(data.hex())
    return ok("\n".join(values), title=f"Tokens ({count})")


_register(make_tool("token-generator", token_generator, title="Token Generator", hint="format|bytes|count"))


# --------------------------------------------------------------------------
# Fake data
# --------------------------------------------------------------------------

_EN_FIRST = ["James", "Mary", "John", "Patricia", "Robert", "Linda", "Michael", "Sarah", "David", "Emma", "Daniel", "Olivia", "Noah", "Sophia", "Liam", "Ava", "Lucas", "Mia", "Henry", "Isabella"]
_EN_LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White"]
_EN_CITY = ["New York", "London", "Toronto", "Berlin", "Sydney", "Paris", "Madrid", "Tokyo", "Dubai", "Amsterdam"]
_COMPANY = ["Rasmio", "Acme", "Globex", "Initech", "Umbrella", "Soylent", "Hooli", "Pied Piper", "Stark", "Wayne", "Cyberdyne", "Wonka"]
_COMPANY_SUFFIX = ["Inc", "LLC", "Group", "Co", "Tech", "Labs"]
_DOMAINS = ["example.com", "mail.com", "test.org", "demo.net", "inbox.io", "sample.co"]


def _pick(values):
    return secrets.choice(values)


def _randint(low: int, high: int) -> int:
    return low + secrets.randbelow(high - low + 1)


def _person(fa: bool) -> dict:
    first = _pick(_GEN["fa_first"] if fa else _EN_FIRST)
    last = _pick(_GEN["fa_last"] if fa else _EN_LAST)
    if fa:
        slug_first = f"user{_randint(100, 999)}"
        slug_last = str(_randint(10, 99))
        city = _pick(_GEN["fa_city"])
        phone = f"+989{_randint(10, 39)}{_randint(0, 9999999):07d}"
    else:
        slug_first = first.lower()
        slug_last = last.lower()
        city = _pick(_EN_CITY)
        phone = f"+1{_randint(200, 989)}{_randint(0, 9999999):07d}"
    return {
        "name": f"{first} {last}",
        "email": f"{slug_first}.{slug_last}@{_pick(_DOMAINS)}",
        "phone": phone,
        "city": city,
        "company": f"{_pick(_COMPANY)} {_pick(_COMPANY_SUFFIX)}",
    }


def fake_data(item: Input) -> Output:
    parts = split_pipe(item.text, 3, from_right=False, strip=True)
    count = int(parts[0]) if parts[0].isdigit() else 1
    count = max(1, min(200, count))
    fa = parts[1].lower() not in {"en", "english", "0", "false", "no"}
    as_json = parts[2].lower() in {"json", "1", "true", "yes"}
    people = [_person(fa) for _ in range(count)]
    if as_json:
        return ok(json_text(people), title=f"Fake Data ({count})")
    lines = []
    for person in people:
        lines.append(
            f"{person['name']} | {person['email']} | {person['phone']} | {person['city']} | {person['company']}"
        )
    return ok("\n".join(lines), title=f"Fake Data ({count})")


_register(make_tool("fake-data", fake_data, title="Fake Data Generator", hint="count|lang|view"))


_ROLES = ["admin", "editor", "viewer", "member", "guest"]
_COUNTRIES = ["IR", "US", "GB", "DE", "FR", "CA", "AU", "JP"]


def _dummy_record(index: int) -> dict:
    first = _pick(_EN_FIRST)
    last = _pick(_EN_LAST)
    username = f"{first.lower()}_{last.lower()}{_randint(1, 99)}"
    created = datetime.now(timezone.utc) - timedelta(
        days=_randint(0, 730), seconds=_randint(0, 86399)
    )
    return {
        "id": index,
        "uuid": str(uuid_lib.uuid4()),
        "name": f"{first} {last}",
        "username": username,
        "email": f"{username}@{_pick(_DOMAINS)}",
        "age": _randint(18, 70),
        "role": _pick(_ROLES),
        "country": _pick(_COUNTRIES),
        "active": bool(_randint(0, 1)),
        "balance": round(_randint(0, 1000000) / 100, 2),
        "createdAt": created.isoformat().replace("+00:00", "Z"),
    }


def dummy_json(item: Input) -> Output:
    count_text = item.text.strip()
    count = max(1, min(500, int(count_text))) if count_text.isdigit() else 1
    return ok(json_text([_dummy_record(index + 1) for index in range(count)]), title=f"Dummy JSON ({count})")


_register(make_tool("dummy-json", dummy_json, title="Dummy JSON", hint="count"))


# --------------------------------------------------------------------------
# Lorem ipsum
# --------------------------------------------------------------------------

def _sentence(words: list[str], length: int) -> str:
    text = " ".join(_pick(words) for _ in range(length))
    return text[:1].upper() + text[1:] + "."


def _paragraph(words: list[str]) -> str:
    return " ".join(_sentence(words, _randint(6, 13)) for _ in range(_randint(4, 7)))


def lorem_ipsum(item: Input) -> Output:
    parts = split_pipe(item.text, 3, from_right=False, strip=True)
    unit = (parts[0] or "para").lower()
    count = int(parts[1]) if parts[1].isdigit() else 1
    lang = (parts[2] or "latin").lower()
    count = max(1, min(100, count))
    words = _LOREM["fa"] if lang in {"fa", "persian", "فارسی"} else _LOREM["latin"]
    if unit in {"word", "words"}:
        output = " ".join(_pick(words) for _ in range(count))
    elif unit in {"sentence", "sentences"}:
        output = " ".join(_sentence(words, _randint(8, 13)) for _ in range(count))
    else:
        output = "\n\n".join(_paragraph(words) for _ in range(count))
    return ok(output, title="Lorem Ipsum")


_register(make_tool("lorem-ipsum", lorem_ipsum, title="Lorem Ipsum", hint="unit|count|lang"))


# --------------------------------------------------------------------------
# QR / identicon
# --------------------------------------------------------------------------

def qr_code(item: Input) -> Output:
    size_text, ec_text, text = split_pipe(item.text, 3, from_right=True, strip=True)
    text = text if text else item.text
    if not text:
        raise ToolError("Copy the text to encode first.")
    size = int(size_text) if size_text.isdigit() else 280
    size = max(64, min(1024, size))
    ec = (ec_text or "M").upper()[:1]
    levels = {"L": 1, "M": 0, "Q": 3, "H": 2}
    try:
        import qrcode  # type: ignore
        from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q  # type: ignore
    except Exception as exc:
        raise ToolError("The 'qrcode' package is required for QR generation.") from exc
    constants = {
        "L": ERROR_CORRECT_L,
        "M": ERROR_CORRECT_M,
        "Q": ERROR_CORRECT_Q,
        "H": ERROR_CORRECT_H,
    }
    code = qrcode.QRCode(error_correction=constants.get(ec, ERROR_CORRECT_M), box_size=10, border=2)
    code.add_data(text)
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white")
    path = temp_path("png", "qrcode")
    image.save(path)
    return Output(title="QR Code", open_path=path, message=f"QR saved ({size}px requested)", copy=False)


_register(make_tool("qr-code", qr_code, title="QR Code Generator", hint="size|ec|text"))


def identicon(item: Input) -> Output:
    value = item.require_text().strip()
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception as exc:
        raise ToolError("The 'Pillow' package is required for identicons.") from exc
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    hue = digest[-1] * 360 / 256
    saturation = (55 + digest[-2] % 30) / 100
    lightness = (45 + digest[-3] % 15) / 100
    red, green, blue = colorsys.hls_to_rgb(hue / 360, lightness, saturation)
    foreground = (int(red * 255), int(green * 255), int(blue * 255))
    grid, cell, pad = 5, 64, 64
    size = grid * cell + pad * 2
    image = Image.new("RGB", (size, size), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    half = (grid + 1) // 2
    for column in range(half):
        for row in range(grid):
            index = column * grid + row
            if digest[index] & 1:
                continue
            x = pad + column * cell
            y = pad + row * cell
            draw.rectangle([x, y, x + cell, y + cell], fill=foreground)
            mirror = grid - 1 - column
            if mirror != column:
                draw.rectangle([pad + mirror * cell, y, pad + mirror * cell + cell, y + cell], fill=foreground)
    path = temp_path("png", "identicon")
    image.save(path)
    return Output(title="Identicon", open_path=path, message="Identicon saved", copy=False)


_register(make_tool("identicon", identicon, title="Identicon Generator", hint="clipboard text"))
