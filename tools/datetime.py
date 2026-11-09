# -*- coding: utf-8 -*-
"""Date, time and timestamp tools."""

from __future__ import annotations

import datetime as _dt
import re

from .common import ok, parse_float, split_pipe, to_ascii_digits
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


def _parse_datetime(value: str) -> _dt.datetime:
    raw = to_ascii_digits(value.strip())
    if not raw:
        raise ToolError("A date/time is required.")
    for parser in (
        lambda s: _dt.datetime.fromisoformat(s),
        lambda s: _dt.datetime.strptime(s, "%Y/%m/%d %H:%M"),
        lambda s: _dt.datetime.strptime(s, "%Y/%m/%d"),
        lambda s: _dt.datetime.strptime(s, "%Y-%m-%d"),
        lambda s: _dt.datetime.strptime(s, "%d/%m/%Y"),
    ):
        try:
            return parser(raw)
        except ValueError:
            continue
    raise ToolError(f"Could not parse date/time: {value!r}")


def _fmt(value: _dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Timestamp
# --------------------------------------------------------------------------

def _relative(value: _dt.datetime) -> str:
    now = _dt.datetime.now()
    delta = value - now
    seconds = delta.total_seconds()
    units = [(60, "second"), (3600, "minute"), (86400, "hour"), (2592000, "day"), (31536000, "month")]
    previous = 1
    for limit, unit in units:
        if abs(seconds) < limit:
            amount = round(seconds / previous)
            return f"{amount} {unit}{'' if abs(amount) == 1 else 's'}"
        previous = limit
    return f"{round(seconds / 31536000)} years"


def timestamp(item: Input) -> Output:
    raw = to_ascii_digits(item.text.strip())
    if not raw:
        now = _dt.datetime.now()
        return ok(
            f"Now (Unix seconds): {int(now.timestamp())}\nNow (ms): {int(now.timestamp() * 1000)}\nLocal: {_fmt(now)}",
            title="Timestamp",
        )
    try:
        number = float(raw)
    except ValueError:
        value = _parse_datetime(raw)
        return ok(
            f"Unix seconds: {int(value.timestamp())}\nUnix milliseconds: {int(value.timestamp() * 1000)}\nLocal: {_fmt(value)}\nISO: {value.isoformat()}",
            title="Date → Timestamp",
        )
    milliseconds = number if abs(number) >= 1e12 else number * 1000
    value = _dt.datetime.fromtimestamp(milliseconds / 1000)
    utc = _dt.datetime.fromtimestamp(milliseconds / 1000, tz=_dt.timezone.utc)
    return ok(
        "\n".join(
            [
                f"Local: {_fmt(value)}",
                f"UTC: {utc.strftime('%a, %d %b %Y %H:%M:%S GMT')}",
                f"ISO 8601: {utc.isoformat().replace('+00:00', 'Z')}",
                f"Relative: {_relative(value)}",
                f"Unix seconds: {int(milliseconds / 1000)}",
                f"Unix milliseconds: {int(milliseconds)}",
            ]
        ),
        title="Timestamp",
    )


_register(make_tool("timestamp", timestamp, title="Unix Timestamp Converter", hint="timestamp or date"))


# --------------------------------------------------------------------------
# Date diff / shift / info
# --------------------------------------------------------------------------

def date_diff(item: Input) -> Output:
    a, b = split_pipe(item.require_text(), 2, from_right=False, strip=False)
    first = _parse_datetime(a)
    second = _parse_datetime(b)
    seconds = abs((second - first).total_seconds())
    days = seconds / 86400
    months = (second.year - first.year) * 12 + (second.month - first.month)
    if second.day < first.day:
        months -= 1
    months = abs(months)
    return ok(
        "\n".join(
            [
                f"Days: {days:.2f}",
                f"Weeks: {days / 7:.2f}",
                f"Months: {months}",
                f"Years: {months / 12:.2f}",
                f"Hours: {seconds / 3600:.2f}",
            ]
        ),
        title="Date Difference",
    )


_register(make_tool("date-diff", date_diff, title="Date Difference", hint="date1|date2"))


def date_shift(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 4, from_right=False, strip=True)
    base, operation, amount_text, unit = parts
    value = _parse_datetime(base)
    amount = int(parse_float(amount_text or "0"))
    if operation.lower() in {"sub", "subtract", "-"}:
        amount = -amount
    if unit.lower().startswith("month"):
        month = value.month - 1 + amount
        year = value.year + month // 12
        month = month % 12 + 1
        day = min(value.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        value = value.replace(year=year, month=month, day=day)
    else:
        value += _dt.timedelta(days=amount)
    return ok(_fmt(value), title="Add/Subtract Date")


_register(make_tool("date-diff", date_shift, id="date-shift", title="Add/Subtract Date", hint="base|add/sub|amount|days/months"))


def date_info(item: Input) -> Output:
    value = _parse_datetime(item.require_text()).date()
    iso = value.isocalendar()
    leap = value.year % 4 == 0 and (value.year % 100 != 0 or value.year % 400 == 0)
    return ok(
        "\n".join(
            [
                f"Weekday: {value.strftime('%A')}",
                f"Month: {value.strftime('%B')}",
                f"ISO week: {iso.week}",
                f"Day of year: {value.timetuple().tm_yday}",
                f"Quarter: Q{(value.month - 1) // 3 + 1}",
                f"Leap year: {'yes' if leap else 'no'}",
            ]
        ),
        title="Date Info",
    )


_register(make_tool("date-info", date_info, title="Date Info", hint="date"))


# --------------------------------------------------------------------------
# Duration
# --------------------------------------------------------------------------

def _breakdown(seconds: int) -> tuple[int, int, int, int]:
    days, remainder = divmod(max(0, seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    return days, hours, minutes, secs


def _human(seconds: int) -> str:
    days, hours, minutes, secs = _breakdown(seconds)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _iso_duration(seconds: int) -> str:
    days, hours, minutes, secs = _breakdown(seconds)
    result = "P"
    if days:
        result += f"{days}D"
    if hours or minutes or secs:
        result += "T"
        if hours:
            result += f"{hours}H"
        if minutes:
            result += f"{minutes}M"
        if secs or (not hours and not minutes):
            result += f"{secs}S"
    return result if result != "P" else "PT0S"


def duration_format(item: Input) -> Output:
    raw = to_ascii_digits(item.require_text().strip())
    value = parse_float(raw)
    if value < 0:
        raise ToolError("Duration must be non-negative.")
    seconds = int(value)
    return ok(f"{_human(seconds)}\n{_iso_duration(seconds)}", title="Duration Formatter")


def duration_parse(item: Input) -> Output:
    text = to_ascii_digits(item.require_text().strip().lower())
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(d|h|m|s)", text)
    if not matches:
        raise ToolError("Could not parse duration (example: 1h2m).")
    total = 0.0
    for amount, unit in matches:
        factor = {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
        total += float(amount) * factor
    seconds = int(total)
    return ok(
        f"Seconds: {seconds}\nMilliseconds: {seconds * 1000}\nHuman: {_human(seconds)}\nISO 8601: {_iso_duration(seconds)}",
        title="Duration Parser",
    )


_register(make_tool("duration-formatter", duration_format, title="Duration Formatter", hint="seconds"))
_register(make_tool("duration-formatter", duration_parse, id="duration-parse", title="Duration Parser", hint="1h2m3s"))


# --------------------------------------------------------------------------
# Jalali
# --------------------------------------------------------------------------

_BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]


def _div(a: int, b: int) -> int:
    return int(a / b)


def _mod(a: int, b: int) -> int:
    return a - _div(a, b) * b


def _jal_cal(jy: int) -> dict:
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for index in range(1, len(_BREAKS)):
        jm = _BREAKS[index]
        jump = jm - jp
        if jy < jm:
            break
        leap_j = leap_j + _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j = leap_j + _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return {"leap": leap, "gy": gy, "march": march}


def _g2d(gy: int, gm: int, gd: int) -> int:
    d = _div((gy + _div(gm - 8, 6) + 100100) * 1461, 4) + _div(153 * _mod(gm + 9, 12) + 2, 5) + gd - 34840408
    return d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752


def _d2g(jdn: int) -> tuple[int, int, int]:
    j = 4 * jdn + 139361631
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div(_mod(j, 1461), 4) * 5 + 308
    gd = _div(_mod(i, 153), 5) + 1
    gm = _mod(_div(i, 153), 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return gy, gm, gd


def _j2d(jy: int, jm: int, jd: int) -> int:
    cal = _jal_cal(jy)
    return _g2d(cal["gy"], 3, cal["march"]) + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1


def _d2j(jdn: int) -> tuple[int, int, int]:
    gy = _d2g(jdn)[0]
    jy = gy - 621
    cal = _jal_cal(jy)
    jdn1f = _g2d(gy, 3, cal["march"])
    k = jdn - jdn1f
    if k >= 0:
        if k <= 185:
            return jy, 1 + _div(k, 31), _mod(k, 31) + 1
        k -= 186
    else:
        jy -= 1
        k += 179
        if cal["leap"] == 1:
            k += 1
    return jy, 7 + _div(k, 30), _mod(k, 30) + 1


def _to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    return _d2j(_g2d(gy, gm, gd))


def _to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    return _d2g(_j2d(jy, jm, jd))


def _j_len(jy: int, jm: int) -> int:
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if _jal_cal(jy)["leap"] == 0 else 29


def _valid_j(jy: int, jm: int, jd: int) -> bool:
    return 1 <= jm <= 12 and 1 <= jd <= _j_len(jy, jm)


def _jalali_result(gy: int, gm: int, gd: int) -> Output:
    jy, jm, jd = _to_jalali(gy, gm, gd)
    weekday = _dt.date(gy, gm, gd).strftime("%A")
    return ok(
        f"Jalali: {jy}/{jm:02d}/{jd:02d}\nGregorian: {gy}/{gm:02d}/{gd:02d}\nWeekday: {weekday}",
        title="Jalali Converter",
    )


def _gregorian_result(jy: int, jm: int, jd: int) -> Output:
    gy, gm, gd = _to_gregorian(jy, jm, jd)
    weekday = _dt.date(gy, gm, gd).strftime("%A")
    return ok(
        f"Jalali: {jy}/{jm:02d}/{jd:02d}\nGregorian: {gy}/{gm:02d}/{gd:02d}\nWeekday: {weekday}",
        title="Jalali Converter",
    )


def jalali_auto(item: Input) -> Output:
    numbers = [int(part) for part in re.findall(r"\d+", to_ascii_digits(item.require_text()))]
    if len(numbers) < 3:
        raise ToolError("Enter a date as YYYY/MM/DD.")
    a, b, c = numbers[:3]
    if a >= 1000:
        y, m, d = a, b, c
    elif c >= 1000:
        y, m, d = c, b, a
    else:
        raise ToolError("The year must be four digits.")
    if y >= 1700:
        try:
            _dt.date(y, m, d)
        except ValueError as exc:
            raise ToolError("Invalid Gregorian date.") from exc
        return _jalali_result(y, m, d)
    if not _valid_j(y, m, d):
        raise ToolError("Invalid Jalali date.")
    return _gregorian_result(y, m, d)


def gregorian_to_jalali(item: Input) -> Output:
    numbers = [int(part) for part in re.findall(r"\d+", to_ascii_digits(item.require_text()))]
    if len(numbers) < 3:
        raise ToolError("Enter a Gregorian date as YYYY/MM/DD.")
    y, m, d = numbers[:3]
    try:
        _dt.date(y, m, d)
    except ValueError as exc:
        raise ToolError("Invalid Gregorian date.") from exc
    return _jalali_result(y, m, d)


def jalali_to_gregorian(item: Input) -> Output:
    numbers = [int(part) for part in re.findall(r"\d+", to_ascii_digits(item.require_text()))]
    if len(numbers) < 3:
        raise ToolError("Enter a Jalali date as YYYY/MM/DD.")
    y, m, d = numbers[:3]
    if not _valid_j(y, m, d):
        raise ToolError("Invalid Jalali date.")
    return _gregorian_result(y, m, d)


_register(make_tool("jalali-converter", jalali_auto, title="Jalali ↔ Gregorian", hint="YYYY/MM/DD"))
_register(make_tool("jalali-converter", gregorian_to_jalali, id="gregorian-to-jalali", title="Gregorian → Jalali", hint="YYYY/MM/DD"))
_register(make_tool("jalali-converter", jalali_to_gregorian, id="jalali-to-gregorian", title="Jalali → Gregorian", hint="YYYY/MM/DD"))


# --------------------------------------------------------------------------
# Relative time
# --------------------------------------------------------------------------

def relative_time(item: Input) -> Output:
    value = _parse_datetime(item.require_text())
    return ok(
        f"Relative: {_relative(value)}\nAbsolute: {value.strftime('%Y-%m-%d %H:%M:%S')}",
        title="Relative Time",
    )


_register(make_tool("relative-time", relative_time, title="Relative Time", hint="date/time"))


# --------------------------------------------------------------------------
# Timezone
# --------------------------------------------------------------------------

def timezone_converter(item: Input) -> Output:
    value_text, from_zone, to_zone = split_pipe(item.require_text(), 3, from_right=False, strip=True)
    if not value_text:
        raise ToolError("Use datetime|from_zone|to_zone in the clipboard.")
    try:
        from zoneinfo import ZoneInfo
    except Exception as exc:
        raise ToolError("zoneinfo is unavailable.") from exc
    try:
        source_zone = ZoneInfo(from_zone or "UTC")
        target_zone = ZoneInfo(to_zone or "UTC")
    except Exception as exc:
        raise ToolError(f"Unknown timezone: {exc}") from exc
    naive = _parse_datetime(value_text)
    source = naive.replace(tzinfo=source_zone)
    target = source.astimezone(target_zone)
    return ok(
        "\n".join(
            [
                f"Source ({from_zone or 'UTC'}): {source.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                f"Target ({to_zone or 'UTC'}): {target.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                f"ISO 8601 (UTC): {source.astimezone(_dt.timezone.utc).isoformat().replace('+00:00', 'Z')}",
            ]
        ),
        title="Timezone Converter",
    )


_register(make_tool("timezone-converter", timezone_converter, title="Timezone Converter", hint="datetime|from_zone|to_zone"))
