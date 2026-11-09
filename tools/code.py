# -*- coding: utf-8 -*-
"""Developer/code helper tools."""

from __future__ import annotations

import datetime as _dt
import re

from .common import ok, split_pipe, to_ascii_digits
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# Cron
# --------------------------------------------------------------------------

_CRON_FIELDS = [
    (0, 59, "minute"),
    (0, 23, "hour"),
    (1, 31, "day of month"),
    (1, 12, "month"),
    (0, 6, "day of week"),
]
_WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _expand_cron(raw: str, low: int, high: int) -> list[int]:
    values = set()
    for part in raw.split(","):
        range_part, _, step_part = part.partition("/")
        step = int(step_part) if step_part else 1
        if step < 1:
            raise ToolError("Cron step must be >= 1.")
        if range_part in {"*", ""}:
            start, end = low, high
        elif "-" in range_part:
            start_text, end_text = range_part.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(range_part)
        if start < low or end > high or start > end:
            raise ToolError(f"Cron value out of range {low}-{high}: {part}")
        values.update(range(start, end + 1, step))
    return sorted(values)


def _cron_describe(raw: str, low: int, high: int, name: str, values: list[int]) -> str:
    if raw == "*":
        return f"every {name}"
    if name == "day of week":
        return "on " + ", ".join(_WEEKDAYS[value % 7] for value in values)
    if name == "month":
        return "in " + ", ".join(_MONTHS[value - 1] for value in values)
    if len(values) > 8:
        return f"{name}: {len(values)} values"
    return f"{name} {', '.join(map(str, values))}"


def cron_parser(item: Input) -> Output:
    expression = to_ascii_digits(item.require_text().strip())
    parts = re.split(r"\s+", expression)
    if len(parts) != 5:
        raise ToolError("Cron expression must have exactly 5 fields.")
    fields = []
    descriptions = []
    for part, (low, high, name) in zip(parts, _CRON_FIELDS):
        values = _expand_cron(part, low, high)
        fields.append(values)
        descriptions.append(_cron_describe(part, low, high, name, values))
    minutes, hours, days, months, weekdays = [set(values) for values in fields]
    now = _dt.datetime.now().replace(second=0, microsecond=0) + _dt.timedelta(minutes=1)
    runs = []
    guard = 0
    while len(runs) < 5 and guard < 366 * 4 * 24 * 60:
        if (
            now.minute in minutes
            and now.hour in hours
            and now.month in months
            and now.day in days
            and (now.weekday() + 1) % 7 in weekdays
        ):
            runs.append(now.strftime("%Y-%m-%d %H:%M"))
        now += _dt.timedelta(minutes=1)
        guard += 1
    body = "; ".join(descriptions)
    if runs:
        body += "\n\nNext runs:\n" + "\n".join(runs)
    else:
        body += "\n\nNo runs found in the next four years."
    return ok(body, title="Cron Parser")


_register(make_tool("cron-parser", cron_parser, title="Cron Parser", hint="cron expression"))


# --------------------------------------------------------------------------
# .env validator
# --------------------------------------------------------------------------

def dotenv_validator(item: Input) -> Output:
    text = item.require_text()
    issues: list[str] = []
    entries: list[str] = []
    seen: dict[str, int] = {}
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r")
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        if "=" not in line:
            issues.append(f"ERROR line {line_number}: missing =")
            continue
        key, raw_value = line.split("=", 1)
        key = re.sub(r"^\s*export\s+", "", key)
        key_trim = key.strip()
        if not key_trim:
            issues.append(f"ERROR line {line_number}: empty key")
        else:
            if key != key_trim:
                issues.append(f"WARN line {line_number}: whitespace around key")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_trim):
                issues.append(f"ERROR line {line_number}: invalid key")
            if key_trim != key_trim.upper():
                issues.append(f"WARN line {line_number}: key is not uppercase")
            if key_trim in seen:
                issues.append(f"ERROR line {line_number}: duplicate key (first at {seen[key_trim]})")
            seen[key_trim] = line_number
        value = raw_value.strip()
        quoted = bool(re.fullmatch(r"""(["']).*\1""", value))
        if not quoted:
            if re.search(r"\s", value):
                issues.append(f"WARN line {line_number}: unquoted value contains spaces")
            if "#" in value:
                issues.append(f"WARN line {line_number}: # starts a comment unless quoted")
        parsed = value
        match = re.fullmatch(r"""(["'])([\s\S]*)\1""", value)
        if match:
            parsed = match.group(2)
        display = parsed if parsed else '""'
        entries.append(f"{key_trim or '(empty)'} = {display}")
    lines = [f"Entries: {len(entries)}  Errors: {sum(i.startswith('ERROR') for i in issues)}  Warnings: {sum(i.startswith('WARN') for i in issues)}"]
    if issues:
        lines.append("")
        lines.extend(issues)
    if entries:
        lines.append("")
        lines.extend(entries)
    if not issues and entries:
        lines.insert(1, "No problems found.")
    return ok("\n".join(lines), title=".env Validator")


_register(make_tool("dotenv-validator", dotenv_validator, title=".env Validator", hint="clipboard .env"))


# --------------------------------------------------------------------------
# .gitignore / glob
# --------------------------------------------------------------------------

def _glob_to_regex(glob: str) -> re.Pattern:
    output = ""
    index = 0
    while index < len(glob):
        char = glob[index]
        if char == "*":
            if index + 1 < len(glob) and glob[index + 1] == "*":
                output += ".*"
                index += 2
                if index < len(glob) and glob[index] == "/":
                    index += 1
                continue
            output += "[^/]*"
            index += 1
        elif char == "?":
            output += "[^/]"
            index += 1
        elif char == "[":
            end = glob.find("]", index)
            if end == -1:
                raise ToolError("Unclosed [ in glob.")
            output += glob[index : end + 1]
            index = end + 1
        elif char == "{":
            end = glob.find("}", index)
            if end == -1:
                raise ToolError("Unclosed { in glob.")
            options = glob[index + 1 : end].split(",")
            output += "(?:" + "|".join(re.escape(option) for option in options) + ")"
            index = end + 1
        else:
            output += re.escape(char)
            index += 1
    return re.compile("^" + output + "$")


def glob_tester(item: Input) -> Output:
    pattern, paths = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not pattern.strip():
        pattern, paths = "*", item.require_text()
    regex = _glob_to_regex(pattern.strip())
    rows = []
    for path in [line.strip() for line in paths.splitlines() if line.strip()]:
        rows.append(f"{'MATCH ' if regex.match(path) else 'no    '} {path}")
    matched = sum(1 for row in rows if row.startswith("MATCH"))
    return ok("\n".join(rows), title="Glob Tester", message=f"{matched}/{len(rows)} matched")


_register(make_tool("glob-tester", glob_tester, title="Glob Tester", hint="pattern|paths"))


def _gitignore_regex(pattern: str) -> tuple[re.Pattern, bool]:
    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern[:-1]
    anchored = "/" in pattern
    if pattern.startswith("/"):
        pattern = pattern[1:]
    output = ""
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                if index + 2 < len(pattern) and pattern[index + 2] == "/":
                    output += "(?:.*/)?"
                    index += 3
                else:
                    output += ".*"
                    index += 2
                continue
            output += "[^/]*"
            index += 1
        elif char == "?":
            output += "[^/]"
            index += 1
        elif char == "[":
            end = pattern.find("]", index)
            if end == -1:
                output += r"\["
                index += 1
            else:
                output += pattern[index : end + 1]
                index = end + 1
        else:
            output += re.escape(char)
            index += 1
    body = ("^" + output) if anchored else ("(?:^|.*/)" + output)
    return re.compile(body + "(?:/.*)?$"), dir_only


def gitignore_tester(item: Input) -> Output:
    rules_text, path = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not path.strip():
        rules_text, path = item.require_text(), ""
    if not path.strip():
        raise ToolError("Use rules|path in the clipboard.")
    rules = []
    for raw in rules_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        if negate:
            line = line[1:]
        regex, dir_only = _gitignore_regex(line)
        rules.append((regex, negate, dir_only, raw.strip()))
    clean = path.strip().replace("./", "", 1).rstrip("/")
    is_dir = path.strip().endswith("/")
    ignored = False
    matched_rule = ""
    for regex, negate, dir_only, source in rules:
        if dir_only and not is_dir and "/" not in clean and regex.match(clean):
            continue
        if regex.match(clean):
            ignored = not negate
            matched_rule = source
    state = "IGNORED" if ignored else "TRACKED"
    return ok(
        f"{state}\nMatched rule: {matched_rule or '(none)'}",
        title=".gitignore Tester",
    )


_register(make_tool("gitignore-tester", gitignore_tester, title=".gitignore Tester", hint="rules|path"))


# --------------------------------------------------------------------------
# MIME lookup
# --------------------------------------------------------------------------

_MIME = {
    "html": "text/html", "htm": "text/html", "css": "text/css", "js": "text/javascript",
    "mjs": "text/javascript", "json": "application/json", "jsonld": "application/ld+json",
    "xml": "application/xml", "csv": "text/csv", "txt": "text/plain", "md": "text/markdown",
    "ics": "text/calendar", "rtf": "application/rtf", "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "zip": "application/zip", "gz": "application/gzip", "tar": "application/x-tar",
    "rar": "application/vnd.rar", "7z": "application/x-7z-compressed",
    "bz2": "application/x-bzip2", "bin": "application/octet-stream",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
    "webp": "image/webp", "svg": "image/svg+xml", "bmp": "image/bmp", "ico": "image/vnd.microsoft.icon",
    "tif": "image/tiff", "tiff": "image/tiff", "avif": "image/avif", "heic": "image/heic",
    "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg", "oga": "audio/ogg",
    "weba": "audio/webm", "aac": "audio/aac", "flac": "audio/flac", "mid": "audio/midi",
    "m4a": "audio/mp4", "opus": "audio/opus",
    "mp4": "video/mp4", "webm": "video/webm", "ogv": "video/ogg", "avi": "video/x-msvideo",
    "mov": "video/quicktime", "mkv": "video/x-matroska", "mpeg": "video/mpeg",
    "ts": "video/mp2t", "3gp": "video/3gpp", "flv": "video/x-flv",
    "ttf": "font/ttf", "otf": "font/otf", "woff": "font/woff", "woff2": "font/woff2",
    "eot": "application/vnd.ms-fontobject", "wasm": "application/wasm",
    "apk": "application/vnd.android.package-archive", "jar": "application/java-archive",
    "sh": "application/x-sh", "php": "application/x-httpd-php", "csh": "application/x-csh",
    "epub": "application/epub+zip", "azw": "application/vnd.amazon.ebook",
    "abw": "application/x-abiword", "arc": "application/x-freearc",
    "yaml": "application/yaml", "yml": "application/yaml", "toml": "application/toml",
    "form": "application/x-www-form-urlencoded",
}


def mime_lookup(item: Input) -> Output:
    query = item.require_text().strip().lower().lstrip(".")
    if not query:
        pairs = sorted(_MIME.items())
    else:
        pairs = sorted((ext, mime) for ext, mime in _MIME.items() if query in ext or query in mime.lower())
    if not pairs:
        return ok("No matching MIME type.", title="MIME Lookup")
    return ok("\n".join(f".{ext}\t{mime}" for ext, mime in pairs), title="MIME Lookup")


_register(make_tool("mime-lookup", mime_lookup, title="MIME Type Lookup", hint="extension or MIME"))


# --------------------------------------------------------------------------
# SemVer
# --------------------------------------------------------------------------

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def _semver(value: str):
    match = _SEMVER_RE.match(value.strip())
    if not match:
        return None
    return {
        "major": int(match.group(1)),
        "minor": int(match.group(2)),
        "patch": int(match.group(3)),
        "pre": match.group(4).split(".") if match.group(4) else [],
    }


def _cmp_pre(a: list[str], b: list[str]) -> int:
    if not a and not b:
        return 0
    if not a:
        return 1
    if not b:
        return -1
    for left, right in zip(a, b):
        left_num = left.isdigit()
        right_num = right.isdigit()
        if left_num and right_num:
            if int(left) != int(right):
                return -1 if int(left) < int(right) else 1
        elif left_num:
            return -1
        elif right_num:
            return 1
        elif left != right:
            return -1 if left < right else 1
    return (len(a) > len(b)) - (len(a) < len(b))


def _semver_compare(a, b) -> int:
    for key in ("major", "minor", "patch"):
        if a[key] != b[key]:
            return -1 if a[key] < b[key] else 1
    return _cmp_pre(a["pre"], b["pre"])


def _semver_satisfies_one(version, range_text: str) -> bool:
    range_text = range_text.strip()
    if not range_text or range_text in {"*", "x"}:
        return True
    match = re.match(r"^(>=|<=|>|<|=)", range_text)
    if match:
        target = _semver(range_text[len(match.group(0)) :])
        if not target:
            return False
        comparison = _semver_compare(version, target)
        return {
            ">": comparison > 0,
            "<": comparison < 0,
            ">=": comparison >= 0,
            "<=": comparison <= 0,
            "=": comparison == 0,
        }[match.group(1)]
    if range_text[0] in "^~":
        target = _semver(range_text[1:])
        if not target or _semver_compare(version, target) < 0:
            return False
        if range_text[0] == "^":
            if target["major"] > 0:
                return version["major"] == target["major"]
            if target["minor"] > 0:
                return version["major"] == 0 and version["minor"] == target["minor"]
            return version["major"] == 0 and version["minor"] == 0 and version["patch"] == target["patch"]
        return version["major"] == target["major"] and version["minor"] == target["minor"]
    parts = range_text.split(".")
    numbers = [version["major"], version["minor"], version["patch"]]
    for index, part in enumerate(parts):
        if part in {"x", "X", "*"}:
            continue
        if int(part) != numbers[index]:
            return False
    return True


def _semver_satisfies(version, range_text: str) -> bool:
    return any(
        all(_semver_satisfies_one(version, comparator) for comparator in group.split() if comparator)
        for group in range_text.split("||")
    )


def semver_validate(item: Input) -> Output:
    value = item.require_text().strip()
    parsed = _semver(value)
    if not parsed:
        raise ToolError("Invalid SemVer (expected X.Y.Z).")
    return ok(
        f"Valid SemVer\nMajor: {parsed['major']}\nMinor: {parsed['minor']}\nPatch: {parsed['patch']}\nPrerelease: {'.'.join(parsed['pre']) or '-'}",
        title="SemVer Validate",
    )


def semver_compare(item: Input) -> Output:
    a, b = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    pa, pb = _semver(a), _semver(b)
    if not pa or not pb:
        raise ToolError("Both values must be valid SemVer (X.Y.Z).")
    comparison = _semver_compare(pa, pb)
    symbol = "A = B" if comparison == 0 else "A < B" if comparison < 0 else "A > B"
    return ok(f"Comparison: {comparison}\nResult: {symbol}", title="SemVer Compare")


def semver_range(item: Input) -> Output:
    version_text, range_text = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    version = _semver(version_text)
    if not version:
        raise ToolError("Invalid version.")
    if not range_text:
        raise ToolError("Use version|range in the clipboard.")
    return ok(
        f"{'SATISFIES' if _semver_satisfies(version, range_text) else 'DOES NOT SATISFY'} {range_text}",
        title="SemVer Range",
    )


_register(make_tool("semver-checker", semver_validate, title="SemVer Validate", hint="version"))
_register(make_tool("semver-checker", semver_compare, id="semver-compare", title="SemVer Compare", hint="a|b"))
_register(make_tool("semver-checker", semver_range, id="semver-range", title="SemVer Range", hint="version|range"))


# --------------------------------------------------------------------------
# SQL formatter
# --------------------------------------------------------------------------

_SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "INSERT", "INTO", "VALUES",
    "UPDATE", "SET", "DELETE", "CREATE", "TABLE", "ALTER", "DROP", "INDEX",
    "VIEW", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS", "ON",
    "GROUP", "BY", "ORDER", "HAVING", "LIMIT", "OFFSET", "UNION", "ALL", "AS",
    "DISTINCT", "COUNT", "SUM", "AVG", "MIN", "MAX", "BETWEEN", "LIKE", "IN",
    "IS", "NULL", "ASC", "DESC", "CASE", "WHEN", "THEN", "ELSE", "END", "EXISTS",
    "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "DEFAULT", "WITH",
}
_SQL_NEWLINE = [
    "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "FULL JOIN", "CROSS JOIN",
    "OUTER JOIN", "GROUP BY", "ORDER BY", "SELECT", "FROM", "WHERE", "JOIN",
    "HAVING", "LIMIT", "OFFSET", "UNION", "VALUES", "SET", "INSERT", "UPDATE",
    "DELETE", "AND", "OR",
]


def _sql_tokens(sql: str) -> list[str]:
    return re.findall(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`]|``)*`|[A-Za-z_][\w$]*|\d+(?:\.\d+)?|[(),;]|[<>=!]+|\S", sql)


def _sql_norm(token: str) -> str:
    if token and token[0] in "'\"`":
        return token
    upper = token.upper()
    return upper if upper in _SQL_KEYWORDS else token


def sql_format(item: Input) -> Output:
    tokens = [_sql_norm(token) for token in _sql_tokens(item.require_text())]
    lines: list[str] = []
    current = ""

    def push():
        nonlocal current
        if current.strip():
            lines.append(current.rstrip())
        current = ""

    index = 0
    while index < len(tokens):
        phrase = ""
        length = 0
        for candidate in _SQL_NEWLINE:
            parts = candidate.split(" ")
            if all((tokens[index + offset] if index + offset < len(tokens) else "").upper() == part for offset, part in enumerate(parts)):
                phrase = candidate
                length = len(parts)
                break
        if length:
            push()
            current = ("  " if phrase in {"AND", "OR"} else "") + phrase + " "
            index += length
            continue
        token = tokens[index]
        if token == ",":
            current = current.rstrip() + ",\n  "
        elif token == ";":
            current = current.rstrip() + ";"
            push()
        elif token == "(":
            current += "("
        elif token == ")":
            current = current.rstrip() + ") "
        else:
            current += token + " "
        index += 1
    push()
    return ok("\n".join(lines), title="SQL Formatter")


def sql_minify(item: Input) -> Output:
    tokens = [_sql_norm(token) for token in _sql_tokens(item.require_text())]
    output = ""
    for token in tokens:
        if token in {",", ";", ")"}:
            output += token
        elif token == "(":
            output += "(" if output == "" or output.endswith("(") else " ("
        else:
            output += ("" if output == "" or output.endswith("(") else " ") + token
    return ok(output.strip(), title="SQL Minifier")


_register(make_tool("sql-formatter", sql_format, title="SQL Formatter", hint="clipboard SQL"))
_register(make_tool("sql-formatter", sql_minify, id="sql-minify", title="SQL Minifier", hint="clipboard SQL"))


# --------------------------------------------------------------------------
# Stack trace
# --------------------------------------------------------------------------

def stack_trace_formatter(item: Input) -> Output:
    output = []
    for raw in item.require_text().splitlines():
        line = raw.rstrip().strip()
        if not line:
            continue
        if line.startswith("at "):
            output.append("    " + line)
            continue
        match = re.match(r'^File\s+"(.+?)",\s*line\s+(\d+)(?:,\s*in\s+(.+))?$', line)
        if match:
            suffix = f" in {match.group(3)}" if match.group(3) else ""
            output.append(f'    File "{match.group(1)}", line {match.group(2)}{suffix}')
            continue
        if re.match(r"^(Caused by:|\.\.\.\s*\d+\s*more)", line, re.IGNORECASE):
            output.append(line)
            continue
        output.append(line)
    return ok("\n".join(output), title="Stack Trace Formatter")


_register(make_tool("stack-trace-formatter", stack_trace_formatter, title="Stack Trace Formatter", hint="clipboard stack trace"))
