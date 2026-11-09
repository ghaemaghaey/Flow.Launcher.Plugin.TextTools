# -*- coding: utf-8 -*-
"""Validators and checkers."""

from __future__ import annotations

import json
import os
import re
import urllib.parse

from .common import ok, parse_int, to_ascii_digits
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_ROOT, "banks_meta.json"), encoding="utf-8") as _fh:
    _BANKS = json.load(_fh)
_SHEBA_BANKS = _BANKS.get("sheba", {})
_CARD_BINS = _BANKS.get("cards", {})


def _digits(value: str) -> str:
    return re.sub(r"\D", "", to_ascii_digits(value or ""))


def _verdict(name: str, valid: bool, *details: str) -> Output:
    lines = [f"{name}: {'VALID' if valid else 'INVALID'}"]
    lines.extend(detail for detail in details if detail)
    return ok("\n".join(lines), title=name)


# --------------------------------------------------------------------------
# Luhn
# --------------------------------------------------------------------------

def luhn_valid(value: str) -> bool:
    digits = _digits(value)
    if len(digits) < 2:
        return False
    total = 0
    alternate = False
    for char in reversed(digits):
        digit = int(char)
        if alternate:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        alternate = not alternate
    return total % 10 == 0


def luhn_checker(item: Input) -> Output:
    value = _digits(item.require_text())
    if not value:
        raise ToolError("Clipboard does not contain digits.")
    return _verdict("Luhn", luhn_valid(value), f"Digits: {len(value)}")


def luhn_generate(item: Input) -> Output:
    value = _digits(item.require_text())
    if not value:
        raise ToolError("Clipboard does not contain digits.")
    total = 0
    double = True
    for char in reversed(value):
        digit = int(char)
        if double:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        double = not double
    check = (10 - (total % 10)) % 10
    return ok(f"Check digit: {check}\nFull number: {value}{check}", title="Luhn Generate")


_register(make_tool("luhn-checker", luhn_checker, title="Luhn Checker", hint="clipboard number"))
_register(make_tool("luhn-checker", luhn_generate, id="luhn-generate", title="Luhn Check Digit", hint="number without check digit"))


# --------------------------------------------------------------------------
# Iranian national IDs
# --------------------------------------------------------------------------

def national_code(item: Input) -> Output:
    code = _digits(item.require_text())
    if not code:
        raise ToolError("Clipboard does not contain digits.")
    valid = False
    if 8 <= len(code) <= 10:
        code = code.zfill(10)
        if not re.fullmatch(r"(\d)\1{9}", code):
            total = sum(int(code[i]) * (10 - i) for i in range(9))
            remainder = total % 11
            check = int(code[9])
            valid = check == remainder if remainder < 2 else check == 11 - remainder
    return _verdict("Iranian National Code", valid, f"Normalized: {code}")


_register(make_tool("national-code", national_code, title="Iranian National Code", hint="clipboard code"))


def legal_id(item: Input) -> Output:
    code = _digits(item.require_text())
    valid = False
    if re.fullmatch(r"\d{11}", code):
        digits = [int(char) for char in code]
        base = digits[9] + 2
        coefficients = [29, 27, 23, 19, 17, 29, 27, 23, 19, 17]
        total = sum((digits[i] + base) * coefficients[i] for i in range(10))
        remainder = total % 11
        if remainder == 10:
            remainder = 0
        valid = remainder == digits[10]
    return _verdict("Iranian Legal Entity ID", valid)


_register(make_tool("legal-national-id", legal_id, title="Legal Entity National ID", hint="clipboard 11-digit ID"))


# --------------------------------------------------------------------------
# IBAN / SHEBA
# --------------------------------------------------------------------------

def iban_mod97(value: str) -> int:
    rearranged = value[4:] + value[:4]
    remainder = 0
    for char in rearranged:
        part = char if char.isdigit() else str(ord(char) - 55)
        for digit in part:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder


def iban_valid(value: str) -> bool:
    value = re.sub(r"\s+", "", value).upper()
    return bool(re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", value)) and iban_mod97(value) == 1


def _normalize_sheba(value: str) -> str:
    value = re.sub(r"\s+", "", value).upper()
    if re.fullmatch(r"\d{24}", value):
        value = "IR" + value
    return value


def sheba_valid(value: str) -> bool:
    value = _normalize_sheba(value)
    return bool(re.fullmatch(r"IR\d{24}", value)) and iban_mod97(value) == 1


def sheba_validator(item: Input) -> Output:
    value = item.require_text()
    normalized = _normalize_sheba(value)
    valid = sheba_valid(value)
    bank = _SHEBA_BANKS.get(normalized[4:7]) if re.fullmatch(r"IR\d{24}", normalized) else None
    formatted = " ".join(normalized[i : i + 4] for i in range(0, len(normalized), 4))
    return _verdict("SHEBA / IBAN", valid, f"Bank: {bank}" if bank else "", f"Formatted: {formatted}")


_register(make_tool("sheba-validator", sheba_validator, title="SHEBA (Iranian IBAN)", hint="clipboard SHEBA"))


_IBAN_COUNTRIES = {
    "IR": (26, "Iran"), "DE": (22, "Germany"), "GB": (22, "United Kingdom"),
    "FR": (27, "France"), "IT": (27, "Italy"), "ES": (24, "Spain"),
    "NL": (18, "Netherlands"), "BE": (16, "Belgium"), "CH": (21, "Switzerland"),
    "AT": (20, "Austria"), "SE": (24, "Sweden"), "NO": (15, "Norway"),
    "DK": (18, "Denmark"), "FI": (18, "Finland"), "PL": (28, "Poland"),
    "PT": (25, "Portugal"), "IE": (22, "Ireland"), "TR": (26, "Turkey"),
    "AE": (23, "UAE"), "SA": (24, "Saudi Arabia"), "QA": (29, "Qatar"),
    "KW": (30, "Kuwait"), "LU": (20, "Luxembourg"), "GR": (27, "Greece"),
}


def iban_validator(item: Input) -> Output:
    value = re.sub(r"\s+", "", item.require_text()).upper()
    if not re.fullmatch(r"[A-Z0-9]+", value):
        raise ToolError("IBAN may only contain letters and digits.")
    if not re.fullmatch(r"[A-Z]{2}\d{2}", value[:4]):
        raise ToolError("IBAN must start with a two-letter country code and two check digits.")
    country = value[:2]
    info = _IBAN_COUNTRIES.get(country)
    if info and len(value) != info[0]:
        return _verdict(
            "IBAN",
            False,
            f"{info[1]} IBANs have {info[0]} characters; got {len(value)}.",
        )
    if not 15 <= len(value) <= 34:
        raise ToolError("IBAN length must be 15–34 characters.")
    valid = iban_mod97(value) == 1
    formatted = " ".join(value[i : i + 4] for i in range(0, len(value), 4))
    return _verdict("IBAN", valid, f"Country: {info[1] if info else country}", f"Formatted: {formatted}")


_register(make_tool("iban-validator", iban_validator, title="IBAN Validator", hint="clipboard IBAN"))


# --------------------------------------------------------------------------
# Bank card
# --------------------------------------------------------------------------

def card_valid(value: str) -> bool:
    digits = _digits(value)
    return bool(re.fullmatch(r"\d{16}", digits)) and luhn_valid(digits)


def card_bank(value: str) -> str | None:
    digits = _digits(value)
    return _CARD_BINS.get(digits[:6]) if len(digits) >= 6 else None


def bank_card(item: Input) -> Output:
    value = item.require_text()
    digits = _digits(value)
    if not digits:
        raise ToolError("Clipboard does not contain digits.")
    valid = card_valid(value)
    bank = card_bank(value)
    formatted = "-".join(digits[i : i + 4] for i in range(0, len(digits), 4))
    return _verdict(
        "Iranian Bank Card",
        valid,
        f"Bank: {bank or 'unknown'}",
        f"Formatted: {formatted}",
    )


_register(make_tool("bank-card", bank_card, title="Iranian Bank Card", hint="clipboard card number"))


# --------------------------------------------------------------------------
# Credit card / barcode / IMEI / ISIN / ISBN
# --------------------------------------------------------------------------

def _brand(number: str) -> str:
    if re.fullmatch(r"4\d{12}(\d{3})?(\d{3})?", number):
        return "Visa"
    if re.fullmatch(r"(5[1-5]\d{14}|2(2[2-9]\d|[3-6]\d{2}|7[01]\d|720)\d{12})", number):
        return "Mastercard"
    if re.fullmatch(r"3[47]\d{13}", number):
        return "American Express"
    if re.fullmatch(r"(6011\d{12}|65\d{14}|64[4-9]\d{13}|622\d{13})", number):
        return "Discover"
    if re.fullmatch(r"3(0[0-5]|[68]\d)\d{11}", number):
        return "Diners Club"
    if re.fullmatch(r"35(2[89]|[3-8]\d)\d{12}", number):
        return "JCB"
    if re.fullmatch(r"(50|5[6-9]|6\d)\d{10,17}", number):
        return "Maestro"
    if re.fullmatch(r"62\d{14,17}", number):
        return "UnionPay"
    return "Unknown"


def credit_card(item: Input) -> Output:
    number = re.sub(r"[\s-]", "", to_ascii_digits(item.require_text()))
    if not number:
        raise ToolError("Clipboard does not contain digits.")
    if not re.fullmatch(r"\d+", number):
        raise ToolError("Card number must contain digits only.")
    valid = 12 <= len(number) <= 19 and luhn_valid(number)
    grouped = " ".join(number[i : i + 4] for i in range(0, len(number), 4))
    return _verdict(
        "Credit Card",
        valid,
        f"Brand: {_brand(number)}",
        f"Length: {len(number)}",
        f"Number: {grouped}",
    )


_register(make_tool("credit-card-validator", credit_card, title="Credit Card Validator", hint="clipboard card number"))


def barcode_valid(value: str) -> bool:
    digits = _digits(value)
    if len(digits) not in (8, 12, 13):
        return False
    numbers = [int(char) for char in digits]
    check = numbers.pop()
    total = 0
    for index, digit in enumerate(numbers):
        from_right = len(numbers) - 1 - index
        total += digit * (3 if from_right % 2 == 0 else 1)
    return (10 - (total % 10)) % 10 == check


def barcode_validator(item: Input) -> Output:
    value = item.require_text()
    digits = _digits(value)
    if not digits:
        raise ToolError("Clipboard does not contain digits.")
    kind = {8: "EAN-8", 12: "UPC-A", 13: "EAN-13"}.get(len(digits), "unknown")
    return _verdict("Barcode", barcode_valid(value), f"Type: {kind}", f"Length: {len(digits)}")


_register(make_tool("barcode-validator", barcode_validator, title="Barcode (EAN/UPC)", hint="clipboard barcode"))


def imei_validator(item: Input) -> Output:
    digits = _digits(item.require_text())
    valid = bool(re.fullmatch(r"\d{15}", digits)) and luhn_valid(digits)
    return _verdict("IMEI", valid)


_register(make_tool("imei-validator", imei_validator, title="IMEI Validator", hint="clipboard IMEI"))


def isin_valid(value: str) -> bool:
    value = re.sub(r"\s+", "", value).upper()
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", value):
        return False
    digits = "".join(char if char.isdigit() else str(ord(char) - 55) for char in value)
    return luhn_valid(digits)


def isin_validator(item: Input) -> Output:
    return _verdict("ISIN", isin_valid(item.require_text()))


_register(make_tool("isin-validator", isin_validator, title="ISIN Validator", hint="clipboard ISIN"))


def _isbn10_valid(value: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", value):
        return False
    total = sum((10 if char == "X" else int(char)) * (10 - index) for index, char in enumerate(value))
    return total % 11 == 0


def _isbn13_valid(value: str) -> bool:
    if not re.fullmatch(r"\d{13}", value):
        return False
    total = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(value))
    return total % 10 == 0


def _check13(twelve: str) -> str:
    total = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(twelve))
    return str((10 - total % 10) % 10)


def _check10(nine: str) -> str:
    total = sum(int(char) * (10 - index) for index, char in enumerate(nine))
    remainder = (11 - total % 11) % 11
    return "X" if remainder == 10 else str(remainder)


def isbn_validator(item: Input) -> Output:
    value = re.sub(r"[\s-]", "", to_ascii_digits(item.require_text())).upper()
    if len(value) == 10:
        valid = _isbn10_valid(value)
        converted = "978" + value[:9] + _check13("978" + value[:9]) if valid else None
        return _verdict("ISBN-10", valid, f"ISBN-13: {converted}" if converted else "")
    if len(value) == 13:
        valid = _isbn13_valid(value)
        converted = None
        if valid and value.startswith("978"):
            core = value[3:12]
            converted = core + _check10(core)
        return _verdict("ISBN-13", valid, f"ISBN-10: {converted}" if converted else "")
    raise ToolError("ISBN must have 10 or 13 characters.")


_register(make_tool("isbn-validator", isbn_validator, title="ISBN Validator", hint="clipboard ISBN"))


# --------------------------------------------------------------------------
# Regex / generic suite
# --------------------------------------------------------------------------

_FLAG_NAMES = {
    "i": "ignore case",
    "m": "multiline",
    "s": "dot all",
    "x": "verbose",
    "u": "unicode",
}


def regex_validator(item: Input) -> Output:
    raw = item.require_text().strip()
    match = re.fullmatch(r"/((?:\\.|[^/\\])*)/([a-z]*)", raw)
    source, flags = (match.group(1), match.group(2)) if match else (raw, "")
    seen = set()
    for flag in flags:
        if flag not in _FLAG_NAMES:
            return _verdict("Regex", False, f"Unsupported flag: {flag}")
        if flag in seen:
            return _verdict("Regex", False, f"Duplicate flag: {flag}")
        seen.add(flag)
    python_flags = 0
    if "i" in flags:
        python_flags |= re.IGNORECASE
    if "m" in flags:
        python_flags |= re.MULTILINE
    if "s" in flags:
        python_flags |= re.DOTALL
    if "x" in flags:
        python_flags |= re.VERBOSE
    try:
        re.compile(source, python_flags)
    except re.error as exc:
        return _verdict("Regex", False, f"Error: {exc}")
    return _verdict(
        "Regex",
        True,
        f"Source: {source}",
        f"Flags: {flags or '(none)'}",
        *[f"  {flag}: {_FLAG_NAMES[flag]}" for flag in flags],
    )


_register(make_tool("regex-validator", regex_validator, title="Regex Validator", hint="pattern or /pattern/flags"))


def _ipv4(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(
        re.fullmatch(r"\d{1,3}", part)
        and (len(part) == 1 or part[0] != "0")
        and int(part) <= 255
        for part in parts
    )


def _ipv6(value: str) -> bool:
    try:
        import ipaddress

        ipaddress.IPv6Address(value)
        return True
    except Exception:
        return False


def _suite_check(kind: str, value: str) -> tuple[bool, str]:
    kind = kind.lower()
    if kind == "email":
        return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", value)), "name@example.com"
    if kind == "url":
        parsed = urllib.parse.urlparse(value)
        return bool(parsed.scheme and parsed.netloc), f"scheme: {parsed.scheme or '-'}"
    if kind == "domain":
        return bool(re.fullmatch(r"(?=.{1,253}$)(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))+", value)), "example.com"
    if kind == "ipv4":
        return _ipv4(value), "IPv4 address"
    if kind == "ipv6":
        return _ipv6(value), "IPv6 address"
    if kind == "mac":
        return bool(re.fullmatch(r"([0-9A-Fa-f]{2}([:-])){5}[0-9A-Fa-f]{2}|[0-9A-Fa-f]{4}(\.[0-9A-Fa-f]{4}){2}", value)), "00:1A:2B:3C:4D:5E"
    if kind == "uuid":
        return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}", value)), "UUID"
    if kind == "hex color":
        return bool(re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", value)), "#1e90ff"
    if kind == "base64":
        import base64

        if not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value) or len(value) % 4 != 0:
            return False, "Base64"
        try:
            base64.b64decode(value)
            return True, "Base64"
        except Exception:
            return False, "Base64"
    if kind == "json":
        try:
            parsed = json.loads(value)
            return True, type(parsed).__name__
        except Exception as exc:
            return False, str(exc)
    if kind == "slug":
        return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value)), "lowercase-with-hyphens"
    if kind == "phone":
        digits = re.sub(r"[\s().-]", "", value)
        return bool(re.fullmatch(r"\+?\d{7,15}", digits)), "E.164"
    return False, f"Unknown kind: {kind}"


def _suite(kind: str):
    def run(item: Input) -> Output:
        value = item.require_text().strip()
        valid, detail = _suite_check(kind, value)
        return _verdict(kind.title(), valid, detail)

    return run


for _kind, _slug in [
    ("Email", "validate-email"),
    ("URL", "validate-url"),
    ("Domain", "validate-domain"),
    ("IPv4", "validate-ipv4"),
    ("IPv6", "validate-ipv6"),
    ("MAC", "validate-mac"),
    ("UUID", "validate-uuid"),
    ("Hex Color", "validate-hex-color"),
    ("Base64", "validate-base64"),
    ("JSON", "validate-json"),
    ("Slug", "validate-slug"),
    ("Phone", "validate-phone"),
]:
    _register(
        make_tool(
            "validator-suite",
            _suite(_kind),
            id=_slug,
            title=f"Validate {_kind}",
            keywords=[_kind.lower(), "validate"],
            hint="clipboard value",
        )
    )

_register(make_tool("validator-suite", _suite("Email"), title="Validator Suite (Email)", hint="clipboard value"))
