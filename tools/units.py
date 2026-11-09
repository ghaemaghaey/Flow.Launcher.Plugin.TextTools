# -*- coding: utf-8 -*-
"""Unit, number and math converter tools."""

from __future__ import annotations

import json
import math
import os
import re

from .common import ok, parse_float, split_pipe, to_ascii_digits
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_ROOT, "number_words_meta.json"), encoding="utf-8") as _fh:
    _WORDS = json.load(_fh)


# --------------------------------------------------------------------------
# Number bases
# --------------------------------------------------------------------------

_BASE_LABELS = [(2, "Binary"), (8, "Octal"), (10, "Decimal"), (16, "Hex"), (36, "Base36")]
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def number_base(item: Input) -> Output:
    parts = item.require_text().strip().rsplit("|", 1)
    if len(parts) == 2 and parts[0].strip().isdigit():
        base = int(parts[0].strip())
        value = parts[1].strip().lower().replace(" ", "")
    else:
        base = 10
        value = item.require_text().strip().lower().replace(" ", "")
        if value.startswith("0x"):
            base, value = 16, value[2:]
        elif value.startswith("0b"):
            base, value = 2, value[2:]
        elif value.startswith("0o"):
            base, value = 8, value[2:]
    negative = value.startswith("-")
    if negative:
        value = value[1:]
    if not value:
        raise ToolError("A number is required.")
    try:
        number = int(value, base)
    except ValueError as exc:
        raise ToolError(f"Invalid base-{base} number.") from exc
    if negative:
        number = -number
    lines = []
    for radix, label in _BASE_LABELS:
        digits = _DIGITS
        if number == 0:
            encoded = "0"
        else:
            n = abs(number)
            encoded = ""
            while n:
                n, remainder = divmod(n, radix)
                encoded = digits[remainder] + encoded
            if number < 0:
                encoded = "-" + encoded
        lines.append(f"{label}: {encoded}")
    return ok("\n".join(lines), title="Number Base Converter")


_register(make_tool("number-base", number_base, title="Number Base Converter", hint="base|number"))


# --------------------------------------------------------------------------
# Unit converter
# --------------------------------------------------------------------------

_UNITS = {
    "length": {
        "mm": ("Millimeter", 0.001), "cm": ("Centimeter", 0.01), "m": ("Meter", 1),
        "km": ("Kilometer", 1000), "in": ("Inch", 0.0254), "ft": ("Foot", 0.3048),
        "yd": ("Yard", 0.9144), "mi": ("Mile", 1609.344),
    },
    "mass": {
        "mg": ("Milligram", 0.000001), "g": ("Gram", 0.001), "kg": ("Kilogram", 1),
        "t": ("Tonne", 1000), "oz": ("Ounce", 0.0283495), "lb": ("Pound", 0.453592),
    },
    "area": {
        "cm2": ("cm²", 0.0001), "m2": ("m²", 1), "ha": ("Hectare", 10000),
        "km2": ("km²", 1000000), "ft2": ("ft²", 0.092903), "acre": ("Acre", 4046.86),
    },
    "volume": {
        "ml": ("Milliliter", 0.001), "l": ("Liter", 1), "m3": ("m³", 1000),
        "gal": ("Gallon (US)", 3.78541), "qt": ("Quart (US)", 0.946353),
    },
    "speed": {
        "ms": ("m/s", 1), "kmh": ("km/h", 0.277778), "mph": ("mph", 0.44704), "kn": ("Knot", 0.514444),
    },
    "data": {
        "B": ("Byte", 1), "KB": ("KB (1000)", 1000), "KiB": ("KiB (1024)", 1024),
        "MB": ("MB (10^6)", 1e6), "MiB": ("MiB (1024²)", 1024 ** 2),
        "GB": ("GB (10^9)", 1e9), "GiB": ("GiB (1024³)", 1024 ** 3),
    },
    "time": {
        "ms": ("Millisecond", 0.001), "s": ("Second", 1), "min": ("Minute", 60),
        "h": ("Hour", 3600), "d": ("Day", 86400), "wk": ("Week", 604800),
    },
}
_TEMPERATURE = {"c": "Celsius", "f": "Fahrenheit", "k": "Kelvin"}


def _fmt_number(value: float) -> str:
    if not math.isfinite(value):
        return "-"
    return f"{value:.8g}"


def unit_converter(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 3, from_right=False, strip=True)
    category, value_text, unit = parts
    category = (category or "length").lower()
    value = parse_float(value_text or "1")
    if category in {"temperature", "temp"}:
        unit = (unit or "c").lower()
        if unit == "c":
            celsius = value
        elif unit == "f":
            celsius = (value - 32) * 5 / 9
        elif unit == "k":
            celsius = value - 273.15
        else:
            raise ToolError("Temperature unit must be c, f or k.")
        return ok(
            "\n".join(
                [
                    f"Celsius: {_fmt_number(celsius)}",
                    f"Fahrenheit: {_fmt_number(celsius * 9 / 5 + 32)}",
                    f"Kelvin: {_fmt_number(celsius + 273.15)}",
                ]
            ),
            title="Unit Converter",
        )
    if category not in _UNITS:
        raise ToolError(f"Unknown category: {category}")
    units = _UNITS[category]
    if unit not in units:
        unit = next(iter(units))
    base_value = value * units[unit][1]
    lines = [f"{units[unit][0]}: {_fmt_number(value)}"]
    for key, (label, factor) in units.items():
        lines.append(f"{label}: {_fmt_number(base_value / factor)}")
    return ok("\n".join(lines), title="Unit Converter")


_register(make_tool("unit-converter", unit_converter, title="Unit Converter", hint="category|value|from_unit"))


# --------------------------------------------------------------------------
# Fractions / percentages / ratios
# --------------------------------------------------------------------------

def _gcd(a: int, b: int) -> int:
    return math.gcd(abs(a), abs(b)) or 1


def _decimal_string(numerator: int, denominator: int) -> str:
    sign = "-" if numerator * denominator < 0 else ""
    numerator, denominator = abs(numerator), abs(denominator)
    integer, remainder = divmod(numerator, denominator)
    if remainder == 0:
        return f"{sign}{integer}"
    digits = []
    seen = {}
    while remainder and remainder not in seen:
        seen[remainder] = len(digits)
        remainder *= 10
        digits.append(str(remainder // denominator))
        remainder %= denominator
    if remainder == 0:
        return f"{sign}{integer}.{''.join(digits)}"
    start = seen[remainder]
    return f"{sign}{integer}.{''.join(digits[:start])}({''.join(digits[start:])})"


def fraction_to_decimal(item: Input) -> Output:
    match = re.fullmatch(r"\s*(-?\d+)\s*/\s*(-?\d+)\s*", to_ascii_digits(item.require_text()))
    if not match:
        raise ToolError("Use a fraction like 3/4.")
    numerator, denominator = int(match.group(1)), int(match.group(2))
    if denominator == 0:
        raise ToolError("Denominator cannot be zero.")
    gcd = _gcd(numerator, denominator)
    sn, sd = numerator // gcd, denominator // gcd
    if sd < 0:
        sn, sd = -sn, -sd
    return ok(
        f"Simplified: {sn}/{sd}\nDecimal: {_decimal_string(numerator, denominator)}\nApprox: {numerator / denominator:.10g}",
        title="Fraction → Decimal",
    )


def decimal_to_fraction(item: Input) -> Output:
    raw = to_ascii_digits(item.require_text().strip())
    if not re.fullmatch(r"-?\d*\.?\d+", raw):
        raise ToolError("Enter a decimal number.")
    sign = -1 if raw.startswith("-") else 1
    raw = raw.lstrip("-")
    integer, _, fraction = raw.partition(".")
    denominator = 10 ** len(fraction)
    numerator = int(integer or "0") * denominator + (int(fraction) if fraction else 0)
    numerator *= sign
    gcd = _gcd(numerator, denominator)
    return ok(f"{numerator // gcd}/{denominator // gcd}", title="Decimal → Fraction")


_register(make_tool("fraction-decimal", fraction_to_decimal, title="Fraction → Decimal", hint="a/b"))
_register(make_tool("fraction-decimal", decimal_to_fraction, id="decimal-to-fraction", title="Decimal → Fraction", hint="decimal"))


def percent_of(item: Input) -> Output:
    x, y = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    return ok(_fmt_number(parse_float(x) / 100 * parse_float(y)), title="Percentage")


def percent_what(item: Input) -> Output:
    x, y = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    y_value = parse_float(y)
    if y_value == 0:
        raise ToolError("Cannot divide by zero.")
    return ok(f"{_fmt_number(parse_float(x) / y_value * 100)}%", title="Percentage")


def percent_change(item: Input) -> Output:
    a, b = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    a_value, b_value = parse_float(a), parse_float(b)
    if a_value == 0:
        raise ToolError("The starting value cannot be zero.")
    change = (b_value - a_value) / abs(a_value) * 100
    return ok(f"Change: {'+' if change >= 0 else ''}{_fmt_number(change)}%\nDifference: {_fmt_number(b_value - a_value)}", title="Percentage Change")


def percent_adjust(item: Input) -> Output:
    y, x = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    y_value, x_value = parse_float(y), parse_float(x)
    return ok(
        f"Increase by {x}%: {_fmt_number(y_value * (1 + x_value / 100))}\nDecrease by {x}%: {_fmt_number(y_value * (1 - x_value / 100))}",
        title="Percentage Adjust",
    )


_register(make_tool("percentage-calculator", percent_of, title="X% of Y", hint="x|y"))
_register(make_tool("percentage-calculator", percent_what, id="percent-what", title="X is what % of Y", hint="x|y"))
_register(make_tool("percentage-calculator", percent_change, id="percent-change", title="Percentage Change", hint="a|b"))
_register(make_tool("percentage-calculator", percent_adjust, id="percent-adjust", title="Increase / Decrease by %", hint="y|x"))


def ratio_simplify(item: Input) -> Output:
    a, b = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    a_value, b_value = int(parse_float(a)), int(parse_float(b))
    if b_value == 0:
        raise ToolError("Second value cannot be zero.")
    gcd = _gcd(a_value, b_value)
    return ok(f"{a_value // gcd} : {b_value // gcd}\nDecimal: {_fmt_number(a_value / b_value)}", title="Ratio")


def ratio_proportion(item: Input) -> Output:
    a, b, c = split_pipe(item.require_text(), 3, from_right=False, strip=True)
    a_value, b_value, c_value = parse_float(a), parse_float(b), parse_float(c)
    if a_value == 0:
        raise ToolError("First value cannot be zero.")
    return ok(_fmt_number(b_value * c_value / a_value), title="Ratio Proportion")


_register(make_tool("ratio-calculator", ratio_simplify, title="Ratio Simplify", hint="a|b"))
_register(make_tool("ratio-calculator", ratio_proportion, id="ratio-proportion", title="Ratio Proportion (a:b = c:?)", hint="a|b|c"))


# --------------------------------------------------------------------------
# Persian numbers
# --------------------------------------------------------------------------

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def _map_digits(value: str, target: str) -> str:
    result = []
    for char in value:
        if char.isdigit():
            index = int(char)
        elif char in _FA_DIGITS:
            index = _FA_DIGITS.index(char)
        elif char in _AR_DIGITS:
            index = _AR_DIGITS.index(char)
        else:
            result.append(char)
            continue
        result.append(_FA_DIGITS[index] if target == "fa" else _AR_DIGITS[index] if target == "ar" else str(index))
    return "".join(result)


def _three_to_words(number: int) -> str:
    words = []
    hundreds, remainder = divmod(number, 100)
    if hundreds:
        words.append(_WORDS["hundreds"][hundreds])
    if 0 < remainder < 10:
        words.append(_WORDS["ones"][remainder])
    elif 10 <= remainder < 20:
        words.append(_WORDS["teens"][remainder - 10])
    elif remainder >= 20:
        tens, ones = divmod(remainder, 10)
        words.append(_WORDS["tens"][tens] + ((" و " + _WORDS["ones"][ones]) if ones else ""))
    return " و ".join(words)


def _int_to_words(digits: str) -> str:
    digits = digits.lstrip("0")
    if not digits:
        return _WORDS["ones"][0] or "صفر"
    if len(digits) > 18:
        raise ToolError("Number is too large.")
    groups = []
    for index in range(len(digits), 0, -3):
        groups.insert(0, digits[max(0, index - 3) : index])
    words = []
    for position, group in enumerate(groups):
        value = int(group)
        if value:
            scale = _WORDS["scales"][len(groups) - 1 - position]
            words.append(_three_to_words(value) + ((" " + scale) if scale else ""))
    return " و ".join(words)


def _num_to_words(value: str) -> str:
    raw = to_ascii_digits(value).strip().replace(",", "").replace(" ", "")
    if not raw:
        return ""
    negative = raw.startswith("-")
    raw = raw.lstrip("-")
    raw = re.sub(r"[^\d.]", "", raw)
    if not raw or raw == ".":
        return ""
    integer, _, fraction = raw.partition(".")
    result = _int_to_words(integer or "0")
    if fraction and re.search(r"[1-9]", fraction) and len(fraction) < len(_WORDS["dec"]):
        result += " و " + _int_to_words(fraction) + " " + _WORDS["dec"][len(fraction)]
    return ("منفی " if negative else "") + result


def persian_number(item: Input) -> Output:
    text = item.require_text()
    lines = [
        f"English digits: {_map_digits(text, 'en')}",
        f"Persian digits: {_map_digits(text, 'fa')}",
        f"Arabic digits: {_map_digits(text, 'ar')}",
    ]
    if re.fullmatch(r"[\d۰-۹٠-٩,.\-\s]+", text.strip()):
        try:
            lines.append(f"Words: {_num_to_words(text)}")
        except ToolError:
            pass
    return ok("\n".join(lines), title="Persian Numbers")


_register(make_tool("persian-number", persian_number, title="Persian ↔ English Numbers", hint="text or number"))


# --------------------------------------------------------------------------
# Roman numerals
# --------------------------------------------------------------------------

_ROMAN_TABLE = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
_ROMAN_RE = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def number_to_roman(item: Input) -> Output:
    number = int(parse_float(item.require_text()))
    if not 1 <= number <= 3999:
        raise ToolError("Number must be between 1 and 3999.")
    output = ""
    for value, symbol in _ROMAN_TABLE:
        while number >= value:
            output += symbol
            number -= value
    return ok(output, title="Number → Roman")


def roman_to_number(item: Input) -> Output:
    value = item.require_text().strip().upper()
    if not _ROMAN_RE.fullmatch(value):
        raise ToolError("Invalid Roman numeral.")
    mapping = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for index, char in enumerate(value):
        current = mapping[char]
        following = mapping.get(value[index + 1], 0) if index + 1 < len(value) else 0
        total += -current if current < following else current
    return ok(str(total), title="Roman → Number")


_register(make_tool("roman-numeral", number_to_roman, title="Number → Roman", hint="1-3999"))
_register(make_tool("roman-numeral", roman_to_number, id="roman-to-number", title="Roman → Number", hint="Roman numeral"))


# --------------------------------------------------------------------------
# Scientific notation
# --------------------------------------------------------------------------

def scientific_notation(item: Input) -> Output:
    raw = to_ascii_digits(item.require_text().strip()).replace(" ", "")
    number = parse_float(raw)
    if not math.isfinite(number):
        raise ToolError("Not a finite number.")
    if number == 0:
        scientific = engineering = "0e+0"
    else:
        scientific = f"{number:e}"
        mantissa, exponent = scientific.split("e")
        mantissa = mantissa.rstrip("0").rstrip(".")
        scientific = f"{mantissa}e{int(exponent):+d}"
        exponent_int = int(math.floor(math.log10(abs(number))))
        exponent_int -= (exponent_int % 3 + 3) % 3
        engineering_mantissa = number / (10 ** exponent_int)
        engineering = f"{engineering_mantissa:.7g}e{exponent_int:+d}"
    return ok(
        "\n".join(
            [
                f"Scientific: {scientific}",
                f"Engineering: {engineering}",
                f"Plain: {number:.20g}",
            ]
        ),
        title="Scientific Notation",
    )


_register(make_tool("scientific-notation", scientific_notation, title="Scientific Notation", hint="number"))
