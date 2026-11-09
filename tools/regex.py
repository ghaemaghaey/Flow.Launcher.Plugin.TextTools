# -*- coding: utf-8 -*-
"""Regex testing and reference tools."""

from __future__ import annotations

import re

from .common import ok
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


def _flags(value: str) -> int:
    flags = 0
    for char in value or "":
        if char == "i":
            flags |= re.IGNORECASE
        elif char == "m":
            flags |= re.MULTILINE
        elif char == "s":
            flags |= re.DOTALL
        elif char == "x":
            flags |= re.VERBOSE
    return flags


def _js_replacement(value: str) -> str:
    value = value.replace("$$", "\x00")
    value = value.replace("$&", r"\g<0>")
    value = re.sub(r"\$(\d+)", r"\\\1", value)
    return value.replace("\x00", "$")


def regex_tester(item: Input) -> Output:
    parts = item.require_text().rsplit("|", 3)
    if len(parts) == 2:
        pattern, flags, replacement, text = parts[0], "g", "", parts[1]
    elif len(parts) == 3:
        pattern, flags, text = parts
        replacement = ""
    elif len(parts) == 4:
        pattern, flags, replacement, text = parts
    else:
        raise ToolError("Use pattern|flags|text (or pattern|flags|replacement|text).")
    try:
        compiled = re.compile(pattern, _flags(flags))
    except re.error as exc:
        raise ToolError(f"Invalid regex: {exc}") from exc
    matches = list(compiled.finditer(text)) if "g" in flags or not flags else [compiled.search(text)] if compiled.search(text) else []
    lines = [f"Matches: {len(matches)}"]
    for index, match in enumerate(matches[:200], 1):
        line = f"{index}: {match.group(0)!r} at {match.start()}"
        if match.groups():
            line += " groups=" + repr(match.groups())
        lines.append(line)
    if replacement:
        try:
            replaced = compiled.sub(_js_replacement(replacement), text)
            lines.extend(["", "Replaced:", replaced])
        except Exception as exc:
            lines.append(f"Replacement error: {exc}")
    return ok("\n".join(lines), title="Regex Tester")


_register(make_tool("regex-tester", regex_tester, title="Regex Tester", hint="pattern|flags|replacement|text"))


def regex_replace(item: Input) -> Output:
    parts = item.require_text().rsplit("|", 3)
    if len(parts) == 2:
        pattern, text = parts
        flags, replacement = "g", ""
    elif len(parts) == 3:
        pattern, flags, text = parts
        replacement = ""
    elif len(parts) == 4:
        pattern, flags, replacement, text = parts
    else:
        raise ToolError("Use pattern|flags|replacement|text.")
    try:
        compiled = re.compile(pattern, _flags(flags))
    except re.error as exc:
        raise ToolError(f"Invalid regex: {exc}") from exc
    count = len(compiled.findall(text))
    try:
        result = compiled.sub(_js_replacement(replacement), text)
    except Exception as exc:
        raise ToolError(f"Replacement failed: {exc}") from exc
    return ok(result, title="Regex Replace", message=f"{count} replacement(s)")


_register(make_tool("regex-replace", regex_replace, title="Regex Replace", hint="pattern|flags|replacement|text"))


_COMMON = [
    ("Email", r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "g", "user.name@example.com"),
    ("URL", r"https?:\/\/[^\s/$.?#].[^\s]*", "gi", "https://rasm.io/path?x=1"),
    ("IPv4", r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b", "g", "192.168.1.1"),
    ("Date (YYYY-MM-DD)", r"\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b", "g", "2026-06-06"),
    ("Time (HH:MM[:SS])", r"\b([01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\b", "g", "14:30:00"),
    ("Iranian mobile", r"\b(?:\+98|0)?9\d{9}\b", "g", "09123456789"),
    ("Hex color", r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", "g", "#2dd4bf"),
    ("Slug", r"^[a-z0-9]+(?:-[a-z0-9]+)*$", "", "my-cool-post-1"),
    ("UUID", r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b", "g", "550e8400-e29b-41d4-a716-446655440000"),
    ("IPv6 (full)", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b", "g", "2001:0db8:85a3:0000:0000:8a2e:0370:7334"),
    ("Credit card", r"\b(?:\d[ -]?){16}\b", "g", "1234 5678 9012 3456"),
    ("Username", r"^[a-zA-Z0-9_]{3,20}$", "", "rasm_user"),
]


def common_regex(item: Input) -> Output:
    text = item.text
    if not text.strip():
        return ok(
            "\n".join(f"{name}: /{pattern}/{flags}  e.g. {sample}" for name, pattern, flags, sample in _COMMON),
            title="Common Regex Patterns",
        )
    lines = []
    for name, pattern, flags, _sample in _COMMON:
        try:
            matches = re.findall(pattern, text, _flags(flags))
        except re.error:
            continue
        if matches:
            lines.append(f"{name}: {len(matches)} match(es)")
            lines.extend(f"  {match}" for match in matches[:20])
    if not lines:
        return ok("No common patterns matched.", title="Common Regex Patterns")
    return ok("\n".join(lines), title="Common Regex Patterns")


_register(make_tool("common-regex", common_regex, title="Common Regex Patterns", hint="clipboard text (optional)"))


_CHEATSHEET = [
    ("Anchors", [
        ("^", "start of string (or line with m)"),
        ("$", "end of string (or line with m)"),
        (r"\b", "word boundary"),
        (r"\B", "not a word boundary"),
    ]),
    ("Character classes", [
        (".", "any character except newline (unless s)"),
        (r"\d  \D", "digit / non-digit"),
        (r"\w  \W", "word character / non-word"),
        (r"\s  \S", "whitespace / non-whitespace"),
        ("[abc]", "a, b or c"),
        ("[^abc]", "not a, b or c"),
        ("[a-z]", "range a to z"),
    ]),
    ("Quantifiers", [
        ("*", "zero or more"),
        ("+", "one or more"),
        ("?", "zero or one"),
        ("{n}", "exactly n"),
        ("{n,}", "n or more"),
        ("{n,m}", "between n and m"),
        ("*?  +?  ??", "lazy versions"),
    ]),
    ("Groups", [
        ("(...)", "capturing group"),
        ("(?:...)", "non-capturing group"),
        ("(?<name>...)", "named group"),
        (r"\1  \k<name>", "backreference"),
        ("a|b", "a or b"),
    ]),
    ("Lookaround", [
        ("(?=...)", "positive lookahead"),
        ("(?!...)", "negative lookahead"),
        ("(?<=...)", "positive lookbehind"),
        ("(?<!...)", "negative lookbehind"),
    ]),
    ("Flags", [
        ("g", "global"),
        ("i", "ignore case"),
        ("m", "multiline"),
        ("s", "dotAll"),
        ("u", "unicode"),
        ("y", "sticky"),
    ]),
    ("Escapes", [
        (r"\n  \t  \r", "newline, tab, carriage return"),
        (r"\.  \*  \\", "escape special characters"),
        (r"\uXXXX", "unicode code point"),
    ]),
]


def regex_cheatsheet(item: Input) -> Output:
    query = item.text.strip().lower()
    lines = []
    for title, rows in _CHEATSHEET:
        selected = [row for row in rows if not query or query in row[0].lower() or query in row[1].lower() or query in title.lower()]
        if selected:
            lines.append(title + ":")
            lines.extend(f"  {token:<18} {description}" for token, description in selected)
            lines.append("")
    if not lines:
        return ok("No matching cheatsheet entries.", title="Regex Cheatsheet")
    return ok("\n".join(lines).strip(), title="Regex Cheatsheet")


_register(make_tool("regex-cheatsheet", regex_cheatsheet, title="Regex Cheatsheet", hint="query (optional)"))
