# -*- coding: utf-8 -*-
"""Encoding, decoding and escaping tools."""

from __future__ import annotations

import base64
import codecs
import html
import json
import quopri
import re
import urllib.parse

from .common import err, ok, split_pipe
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# Base64
# --------------------------------------------------------------------------

def b64_encode(item: Input) -> Output:
    return ok(base64.b64encode(item.require_text().encode("utf-8")).decode("ascii"), title="Base64 Encode")


def b64_decode(item: Input) -> Output:
    raw = re.sub(r"\s+", "", item.require_text()).replace("-", "+").replace("_", "/")
    raw += "=" * (-len(raw) % 4)
    try:
        data = base64.b64decode(raw)
    except Exception as exc:
        raise ToolError(f"Invalid Base64: {exc}") from exc
    return ok(data.decode("utf-8", "replace"), title="Base64 Decode")


def b64url_encode(item: Input) -> Output:
    value = base64.urlsafe_b64encode(item.require_text().encode("utf-8")).decode("ascii")
    return ok(value.rstrip("="), title="Base64 URL-safe Encode")


_register(make_tool("base64", b64_encode, title="Base64 Encode", hint="clipboard text"))
_register(make_tool("base64", b64_decode, id="base64-decode", title="Base64 Decode", hint="clipboard text"))
_register(make_tool("base64", b64url_encode, id="base64-url-encode", title="Base64 URL-safe Encode", hint="clipboard text"))
_register(make_tool("base64", b64_decode, id="base64-url-decode", title="Base64 URL-safe Decode", hint="clipboard text"))


# --------------------------------------------------------------------------
# URL encoding
# --------------------------------------------------------------------------

_COMPONENT_SAFE = "-_.!~*'()"


def url_encode_component(item: Input) -> Output:
    return ok(urllib.parse.quote(item.require_text(), safe=_COMPONENT_SAFE), title="URL Component Encode")


def url_decode_component(item: Input) -> Output:
    return ok(urllib.parse.unquote(item.require_text()), title="URL Component Decode")


def url_encode_full(item: Input) -> Output:
    return ok(
        urllib.parse.quote(item.require_text(), safe=";,/?:@&=+$#-_.!~*'()"),
        title="URL Encode",
    )


_register(make_tool("url-encode", url_encode_component, title="URL Component Encode", hint="clipboard text"))
_register(make_tool("url-encode", url_decode_component, id="url-decode", title="URL Component Decode", hint="clipboard text"))
_register(make_tool("url-encode", url_encode_full, id="url-encode-full", title="URL Encode (full)", hint="clipboard text"))
_register(make_tool("url-encode", url_decode_component, id="url-decode-full", title="URL Decode (full)", hint="clipboard text"))


# --------------------------------------------------------------------------
# HTML entities
# --------------------------------------------------------------------------

def html_encode(item: Input) -> Output:
    value = html.escape(item.require_text(), quote=True).replace("&#x27;", "&#39;")
    return ok(value, title="HTML Entities Encode")


def html_decode(item: Input) -> Output:
    return ok(html.unescape(item.require_text()), title="HTML Entities Decode")


_register(make_tool("html-entities", html_encode, title="HTML Entities Encode", hint="clipboard text"))
_register(make_tool("html-entities", html_decode, id="html-entities-decode", title="HTML Entities Decode", hint="clipboard text"))


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------

def _b64url_decode(value: str) -> str:
    value = value.replace("-", "+").replace("_", "/")
    value += "=" * (-len(value) % 4)
    return base64.b64decode(value).decode("utf-8", "replace")


def jwt_decode(item: Input) -> Output:
    token = item.require_text().strip()
    parts = token.split(".")
    if len(parts) < 2:
        raise ToolError("That does not look like a JWT (expected header.payload.signature).")
    try:
        header = json.dumps(json.loads(_b64url_decode(parts[0])), ensure_ascii=False, indent=2)
        payload_raw = _b64url_decode(parts[1])
        payload = json.loads(payload_raw)
        payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as exc:
        raise ToolError(f"Could not decode the JWT: {exc}") from exc
    notes = []
    for key, label in [("iat", "Issued at"), ("nbf", "Not before"), ("exp", "Expires")]:
        if isinstance(payload.get(key), (int, float)):
            from datetime import datetime, timezone

            moment = datetime.fromtimestamp(payload[key], tz=timezone.utc)
            suffix = ""
            if key == "exp":
                suffix = " (expired)" if payload[key] < datetime.now(timezone.utc).timestamp() else " (valid)"
            notes.append(f"{label} ({key}): {moment.isoformat()}{suffix}")
    body = "\n".join(
        [
            "Header:",
            header,
            "",
            "Payload:",
            payload_text,
            "",
            f"Signature: {parts[2] if len(parts) > 2 else ''}",
        ]
    )
    if notes:
        body = "\n".join(notes) + "\n\n" + body
    return ok(body, title="JWT Decoder")


_register(make_tool("jwt-decoder", jwt_decode, title="JWT Decoder", hint="clipboard token"))


# --------------------------------------------------------------------------
# Hex / binary / ASCII
# --------------------------------------------------------------------------

def hex_encode(item: Input) -> Output:
    return ok(" ".join(f"{byte:02x}" for byte in item.require_text().encode("utf-8")), title="Text → Hex")


def hex_encode_compact(item: Input) -> Output:
    return ok(item.require_text().encode("utf-8").hex(), title="Text → Hex (compact)")


def hex_decode(item: Input) -> Output:
    raw = re.sub(r"0x", "", item.require_text(), flags=re.IGNORECASE)
    raw = re.sub(r"[^0-9a-fA-F]", "", raw)
    if len(raw) % 2:
        raise ToolError("Hex input must have an even number of digits.")
    try:
        data = bytes.fromhex(raw)
    except ValueError as exc:
        raise ToolError(f"Invalid hex: {exc}") from exc
    return ok(data.decode("utf-8", "replace"), title="Hex → Text")


_register(make_tool("hex-text", hex_encode, title="Text → Hex", hint="clipboard text"))
_register(make_tool("hex-text", hex_encode_compact, id="hex-encode-compact", title="Text → Hex (compact)", hint="clipboard text"))
_register(make_tool("hex-text", hex_decode, id="hex-decode", title="Hex → Text", hint="clipboard hex"))


def binary_encode(item: Input) -> Output:
    return ok(" ".join(f"{byte:08b}" for byte in item.require_text().encode("utf-8")), title="Text → Binary")


def binary_decode(item: Input) -> Output:
    tokens = [token for token in item.require_text().split() if token]
    data = bytearray()
    for token in tokens:
        if not re.fullmatch(r"[01]{1,8}", token):
            raise ToolError(f"Invalid binary group: {token!r}")
        data.append(int(token, 2))
    return ok(bytes(data).decode("utf-8", "replace"), title="Binary → Text")


_register(make_tool("binary-text", binary_encode, title="Text → Binary", hint="clipboard text"))
_register(make_tool("binary-text", binary_decode, id="binary-decode", title="Binary → Text", hint="clipboard binary"))


def ascii_to_codes(item: Input) -> Output:
    rows = []
    for char in item.require_text():
        for byte in char.encode("utf-8"):
            label = repr(char) if byte == ord(char) else ""
            rows.append(f"{label}\t{byte}\t0x{byte:02X}\t{byte:08b}")
    return ok("\n".join(rows), title="Text → ASCII Codes")


def codes_to_ascii(item: Input) -> Output:
    tokens = [token for token in re.split(r"[\s,]+", item.require_text().strip()) if token]
    chars = []
    for token in tokens:
        try:
            value = int(token, 16) if token.lower().startswith("0x") else int(token, 10)
        except ValueError as exc:
            raise ToolError(f"Invalid code: {token!r}") from exc
        if value < 0 or value > 0x10FFFF:
            raise ToolError(f"Code out of range: {token!r}")
        chars.append(chr(value))
    return ok("".join(chars), title="ASCII Codes → Text")


_register(make_tool("ascii-converter", ascii_to_codes, title="Text → ASCII Codes", hint="clipboard text"))
_register(make_tool("ascii-converter", codes_to_ascii, id="ascii-decode", title="ASCII Codes → Text", hint="codes separated by spaces/commas"))


# --------------------------------------------------------------------------
# Base32 / Base58 / Base85
# --------------------------------------------------------------------------

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_encode(data: bytes) -> str:
    if not data:
        return ""
    number = int.from_bytes(data, "big")
    output = ""
    while number:
        number, remainder = divmod(number, 58)
        output = _B58[remainder] + output
    zeros = len(data) - len(data.lstrip(b"\x00"))
    return _B58[0] * zeros + output


def base58_decode(value: str) -> bytes:
    value = value.strip()
    if not value:
        return b""
    number = 0
    for char in value:
        if char not in _B58:
            raise ToolError(f"Invalid Base58 character: {char!r}")
        number = number * 58 + _B58.index(char)
    data = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    zeros = len(value) - len(value.lstrip(_B58[0]))
    return b"\x00" * zeros + data


def base32_encode(item: Input) -> Output:
    return ok(base64.b32encode(item.require_text().encode("utf-8")).decode("ascii"), title="Base32 Encode")


def base32_decode(item: Input) -> Output:
    raw = re.sub(r"\s+", "", item.require_text()).upper().rstrip("=")
    raw += "=" * (-len(raw) % 8)
    try:
        data = base64.b32decode(raw, casefold=True)
    except Exception as exc:
        raise ToolError(f"Invalid Base32: {exc}") from exc
    return ok(data.decode("utf-8", "replace"), title="Base32 Decode")


def base58_encode_tool(item: Input) -> Output:
    return ok(base58_encode(item.require_text().encode("utf-8")), title="Base58 Encode")


def base58_decode_tool(item: Input) -> Output:
    try:
        data = base58_decode(item.require_text())
    except ToolError:
        raise
    return ok(data.decode("utf-8", "replace"), title="Base58 Decode")


def base85_encode(item: Input) -> Output:
    return ok(base64.a85encode(item.require_text().encode("utf-8")).decode("ascii"), title="Base85 Encode")


def base85_decode(item: Input) -> Output:
    raw = item.require_text().strip()
    raw = re.sub(r"^<~|~>$", "", raw)
    try:
        data = base64.a85decode(raw)
    except Exception as exc:
        raise ToolError(f"Invalid Base85: {exc}") from exc
    return ok(data.decode("utf-8", "replace"), title="Base85 Decode")


_register(make_tool("base-encoder", base58_encode_tool, title="Base58 Encode", hint="clipboard text"))
_register(make_tool("base-encoder", base58_decode_tool, id="base58-decode", title="Base58 Decode", hint="clipboard text"))
_register(make_tool("base-encoder", base32_encode, id="base32-encode", title="Base32 Encode", hint="clipboard text"))
_register(make_tool("base-encoder", base32_decode, id="base32-decode", title="Base32 Decode", hint="clipboard text"))
_register(make_tool("base-encoder", base85_encode, id="base85-encode", title="Base85 Encode", hint="clipboard text"))
_register(make_tool("base-encoder", base85_decode, id="base85-decode", title="Base85 Decode", hint="clipboard text"))


# --------------------------------------------------------------------------
# Basic auth
# --------------------------------------------------------------------------

def basic_auth_encode(item: Input) -> Output:
    user, password = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return ok(f"Authorization: Basic {token}", title="Basic Auth Header")


def basic_auth_decode(item: Input) -> Output:
    value = item.require_text().strip()
    value = re.sub(r"^\s*Authorization:\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^Basic\s+", "", value, flags=re.IGNORECASE).strip()
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4)).decode("utf-8", "replace")
    except Exception as exc:
        raise ToolError(f"Invalid Basic auth value: {exc}") from exc
    if ":" not in raw:
        raise ToolError("Decoded value has no colon.")
    user, password = raw.split(":", 1)
    return ok(f"Username: {user}\nPassword: {password}", title="Basic Auth Decode")


_register(make_tool("basic-auth", basic_auth_encode, title="Basic Auth Header", hint="username|password"))
_register(make_tool("basic-auth", basic_auth_decode, id="basic-auth-decode", title="Basic Auth Decode", hint="Authorization header"))


# --------------------------------------------------------------------------
# Morse
# --------------------------------------------------------------------------

_MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-", "_": "..--.-",
    '"': ".-..-.", "@": ".--.-.",
}
_MORSE_REVERSE = {value: key for key, value in _MORSE.items()}


def morse_encode(item: Input) -> Output:
    words = item.require_text().upper().split()
    encoded = [
        " ".join(_MORSE.get(char, "") for char in word if _MORSE.get(char, ""))
        for word in words
    ]
    return ok(" / ".join(encoded), title="Morse Encode")


def morse_decode(item: Input) -> Output:
    words = re.split(r"\s*/\s*", item.require_text().strip())
    decoded = [
        "".join(_MORSE_REVERSE.get(code, "") for code in word.split())
        for word in words
    ]
    return ok(" ".join(decoded), title="Morse Decode")


_register(make_tool("morse-code", morse_encode, title="Morse Encode", hint="clipboard text"))
_register(make_tool("morse-code", morse_decode, id="morse-decode", title="Morse Decode", hint="clipboard morse"))


# --------------------------------------------------------------------------
# Caesar / ROT13
# --------------------------------------------------------------------------

def _caesar(text: str, shift: int) -> str:
    shift %= 26

    def rotate(match: re.Match) -> str:
        char = match.group(0)
        base = ord("a") if char.islower() else ord("A")
        return chr((ord(char) - base + shift) % 26 + base)

    return re.sub(r"[a-zA-Z]", rotate, text)


def caesar_encode(item: Input) -> Output:
    shift_text, text = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    shift = int(shift_text.strip()) if shift_text.strip().lstrip("-").isdigit() else 3
    return ok(_caesar(text, shift), title="Caesar Encode")


def caesar_decode(item: Input) -> Output:
    shift_text, text = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    shift = int(shift_text.strip()) if shift_text.strip().lstrip("-").isdigit() else 3
    return ok(_caesar(text, -shift), title="Caesar Decode")


def rot13(item: Input) -> Output:
    return ok(codecs.encode(item.require_text(), "rot_13"), title="ROT13")


_register(make_tool("caesar-cipher", caesar_encode, title="Caesar Encode", hint="shift|text"))
_register(make_tool("caesar-cipher", caesar_decode, id="caesar-decode", title="Caesar Decode", hint="shift|text"))
_register(make_tool("caesar-cipher", rot13, id="rot13", title="ROT13", hint="clipboard text"))


# --------------------------------------------------------------------------
# Braille
# --------------------------------------------------------------------------

_BRAILLE_LETTERS = {
    "a": 1, "b": 3, "c": 9, "d": 25, "e": 17, "f": 11, "g": 27, "h": 19,
    "i": 10, "j": 26, "k": 5, "l": 7, "m": 13, "n": 29, "o": 21, "p": 15,
    "q": 31, "r": 23, "s": 14, "t": 30, "u": 37, "v": 39, "w": 58, "x": 45,
    "y": 61, "z": 53,
}
_BRAILLE_PUNCT = {
    ",": 2, ";": 6, ":": 18, ".": 50, "?": 38, "!": 22, "'": 3, "-": 36,
    "(": 38, ")": 38, "/": 52, " ": 0,
}
_BRAILLE_DIGITS = "1234567890"
_NUMBER_SIGN = 60


def _braille_cell(dots: int) -> str:
    return chr(0x2800 + dots)


def braille_encode(item: Input) -> Output:
    output = []
    in_number = False
    for char in item.require_text():
        lower = char.lower()
        if lower.isdigit():
            if not in_number:
                output.append(_braille_cell(_NUMBER_SIGN))
                in_number = True
            digit_letter = "abcdefghij"[int(lower) - 1] if lower != "0" else "j"
            output.append(_braille_cell(_BRAILLE_LETTERS[digit_letter]))
        elif lower in _BRAILLE_LETTERS:
            in_number = False
            output.append(_braille_cell(_BRAILLE_LETTERS[lower]))
        elif lower in _BRAILLE_PUNCT:
            in_number = False
            output.append(_braille_cell(_BRAILLE_PUNCT[lower]))
        else:
            in_number = False
            output.append(char)
    return ok("".join(output), title="Braille Encode")


def braille_decode(item: Input) -> Output:
    reverse = {dots: letter for letter, dots in _BRAILLE_LETTERS.items()}
    output = []
    in_number = False
    for char in item.require_text():
        dots = ord(char) - 0x2800
        if 0 <= dots <= 0x3F:
            if dots == _NUMBER_SIGN:
                in_number = True
                continue
            if dots == 0:
                in_number = False
                output.append(" ")
                continue
            letter = reverse.get(dots)
            if letter:
                if in_number:
                    output.append(str(_BRAILLE_DIGITS.index(letter) + 1) if letter in _BRAILLE_DIGITS[:9] else "0")
                else:
                    output.append(letter)
                continue
            punct = next((key for key, value in _BRAILLE_PUNCT.items() if value == dots), None)
            if punct:
                in_number = False
                output.append(punct)
            else:
                output.append(char)
        else:
            output.append(char)
    return ok("".join(output), title="Braille Decode")


_register(make_tool("braille", braille_encode, title="Braille Encode", hint="clipboard text"))
_register(make_tool("braille", braille_decode, id="braille-decode", title="Braille Decode", hint="clipboard braille"))


# --------------------------------------------------------------------------
# Data URI
# --------------------------------------------------------------------------

def data_uri_encode(item: Input) -> Output:
    mime, text = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not mime or "/" not in mime:
        mime, text = "text/plain", item.require_text()
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return ok(f"data:{mime};base64,{encoded}", title="Data URI Encode")


def data_uri_decode(item: Input) -> Output:
    value = item.require_text().strip()
    match = re.match(r"^data:([^;,]*)(;base64)?,(.*)$", value, re.DOTALL)
    if not match:
        raise ToolError("Invalid data URI.")
    mime = match.group(1) or "text/plain"
    is_base64 = bool(match.group(2))
    payload = match.group(3)
    if is_base64:
        data = base64.b64decode(payload + "=" * (-len(payload) % 4))
    else:
        data = urllib.parse.unquote_to_bytes(payload)
    if mime.startswith("text/") or mime in {"application/json", "application/xml", "application/javascript"}:
        return ok(data.decode("utf-8", "replace"), title="Data URI Decode")
    extension = (mime.split("/")[-1] or "bin").split("+")[0]
    path = __import__("os").path.join(
        __import__("tempfile").gettempdir(), "TextTools", f"data-uri-{__import__('uuid').uuid4().hex[:8]}.{extension}"
    )
    __import__("os").makedirs(__import__("os").path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return Output(
        title="Data URI Decode",
        message=f"{len(data)} bytes decoded; opening {mime}",
        open_path=path,
        copy=False,
    )


_register(make_tool("data-uri", data_uri_encode, title="Data URI Encode", hint="mime|text"))
_register(make_tool("data-uri", data_uri_decode, id="data-uri-decode", title="Data URI Decode", hint="clipboard data URI"))


# --------------------------------------------------------------------------
# NATO
# --------------------------------------------------------------------------

_NATO = {
    "A": "Alpha", "B": "Bravo", "C": "Charlie", "D": "Delta", "E": "Echo",
    "F": "Foxtrot", "G": "Golf", "H": "Hotel", "I": "India", "J": "Juliett",
    "K": "Kilo", "L": "Lima", "M": "Mike", "N": "November", "O": "Oscar",
    "P": "Papa", "Q": "Quebec", "R": "Romeo", "S": "Sierra", "T": "Tango",
    "U": "Uniform", "V": "Victor", "W": "Whiskey", "X": "X-ray", "Y": "Yankee",
    "Z": "Zulu",
    "0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
    "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine",
    ".": "Stop", "-": "Dash", "@": "At",
}


def nato(item: Input) -> Output:
    values = []
    for char in item.require_text().upper():
        if char == " ":
            values.append("(Space)")
        else:
            values.append(_NATO.get(char, char))
    return ok(" ".join(values), title="NATO Phonetic")


_register(make_tool("nato-phonetic", nato, title="NATO Phonetic", hint="clipboard text"))


# --------------------------------------------------------------------------
# Punycode
# --------------------------------------------------------------------------

def punycode_encode(item: Input) -> Output:
    labels = []
    for label in item.require_text().strip().split("."):
        if any(ord(char) > 127 for char in label):
            labels.append("xn--" + codecs.encode(label, "punycode").decode("ascii"))
        else:
            labels.append(label)
    return ok(".".join(labels), title="Punycode Encode")


def punycode_decode(item: Input) -> Output:
    labels = []
    for label in item.require_text().strip().split("."):
        if label.lower().startswith("xn--"):
            try:
                labels.append(codecs.decode(label[4:].encode("ascii"), "punycode"))
            except Exception as exc:
                raise ToolError(f"Invalid Punycode label: {label!r}") from exc
        else:
            labels.append(label)
    return ok(".".join(labels), title="Punycode Decode")


_register(make_tool("punycode", punycode_encode, title="Punycode Encode", hint="clipboard domain"))
_register(make_tool("punycode", punycode_decode, id="punycode-decode", title="Punycode Decode", hint="clipboard domain"))


# --------------------------------------------------------------------------
# Quoted-printable
# --------------------------------------------------------------------------

def qp_encode(item: Input) -> Output:
    return ok(quopri.encodestring(item.require_text().encode("utf-8")).decode("ascii"), title="Quoted-Printable Encode")


def qp_decode(item: Input) -> Output:
    try:
        data = quopri.decodestring(item.require_text().encode("ascii", "replace"))
    except Exception as exc:
        raise ToolError(f"Invalid quoted-printable: {exc}") from exc
    return ok(data.decode("utf-8", "replace"), title="Quoted-Printable Decode")


_register(make_tool("quoted-printable", qp_encode, title="Quoted-Printable Encode", hint="clipboard text"))
_register(make_tool("quoted-printable", qp_decode, id="qp-decode", title="Quoted-Printable Decode", hint="clipboard text"))


# --------------------------------------------------------------------------
# String escaping
# --------------------------------------------------------------------------

def _escape(text: str, target: str) -> str:
    if target == "xml":
        return html.escape(text, quote=True).replace("&#x27;", "&apos;")
    if target == "json":
        return json.dumps(text)[1:-1]
    if target == "js":
        return (
            text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
            .replace("`", "\\`").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        )
    if target == "css":
        return re.sub(r"[^a-zA-Z0-9_-]", lambda m: "\\%x " % ord(m.group(0)), text)
    if target == "sql":
        return text.replace("'", "''")
    if target == "shell":
        return "'" + text.replace("'", "'\\''") + "'"
    if target == "markdown":
        return re.sub(r"([\\`*_{}\[\]()#+\-.!>|~])", r"\\\1", text)
    if target == "regexp":
        return re.escape(text)
    return text


def _unescape(text: str, target: str) -> str:
    if target == "xml":
        return html.unescape(text)
    if target == "json":
        return json.loads('"' + text + '"')
    if target == "js":
        return (
            text.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
            .replace("\\`", "`").replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
        )
    if target == "css":
        return re.sub(r"\\([0-9a-fA-F]{1,6}) ?", lambda m: chr(int(m.group(1), 16)), text)
    if target == "sql":
        return text.replace("''", "'")
    if target == "shell":
        return re.sub(r"^'|'$", "", text).replace("'\\''", "'")
    if target in {"markdown", "regexp"}:
        return re.sub(r"\\(.)", r"\1", text)
    return text


for _target, _slug in [
    ("xml", "escape-xml"),
    ("json", "escape-json"),
    ("js", "escape-js"),
    ("css", "escape-css"),
    ("sql", "escape-sql"),
    ("shell", "escape-shell"),
    ("markdown", "escape-markdown"),
    ("regexp", "escape-regex"),
]:
    def _make_escape(target=_target):
        def run(item: Input) -> Output:
            return ok(_escape(item.require_text(), target), title=f"Escape {target.upper()}")

        return run

    def _make_unescape(target=_target):
        def run(item: Input) -> Output:
            try:
                return ok(_unescape(item.require_text(), target), title=f"Unescape {target.upper()}")
            except Exception as exc:
                raise ToolError(f"Could not unescape: {exc}") from exc

        return run

    _register(make_tool("string-escape", _make_escape(), id=_slug, title=f"Escape {_target.upper()}", hint="clipboard text"))
    _register(make_tool("string-escape", _make_unescape(), id=_slug + "-decode", title=f"Unescape {_target.upper()}", hint="clipboard text"))

_register(make_tool("string-escape", _make_escape("json"), title="String Escape (JSON)", hint="clipboard text"))


# --------------------------------------------------------------------------
# Unicode
# --------------------------------------------------------------------------

def unicode_inspector(item: Input) -> Output:
    rows = []
    for char in item.require_text():
        code = ord(char)
        utf8 = " ".join(f"{byte:02X}" for byte in char.encode("utf-8"))
        label = repr(char) if char.isspace() else char
        rows.append(f"{label}\tU+{code:04X}\t{code}\t{utf8}")
    return ok("\n".join(rows), title="Unicode Inspector")


def unicode_normalize(item: Input) -> Output:
    import unicodedata

    text = item.require_text()
    lines = []
    for form in ("NFC", "NFD", "NFKC", "NFKD"):
        value = unicodedata.normalize(form, text)
        lines.append(f"{form} ({len(value)} chars):\n{value}")
    return ok("\n\n".join(lines), title="Unicode Normalizer")


_register(make_tool("unicode-inspector", unicode_inspector, title="Unicode Inspector", hint="clipboard text"))
_register(make_tool("unicode-normalize", unicode_normalize, title="Unicode Normalizer", hint="clipboard text"))
