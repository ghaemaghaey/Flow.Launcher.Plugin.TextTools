# -*- coding: utf-8 -*-
"""Text, string and document tools."""

from __future__ import annotations

import re
import unicodedata

from .common import (
    err,
    natural_lines,
    ok,
    split_pipe,
    unique_preserve,
)
from .meta import make_custom_tool, make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


def _lines(text: str) -> list[str]:
    return re.split(r"\r\n|\r|\n", text)


def _words(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"[_\-./]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return [part for part in value.split(" ") if part]


def _cap(word: str) -> str:
    return word[:1].upper() + word[1:].lower()


# --------------------------------------------------------------------------
# Text counter
# --------------------------------------------------------------------------

def text_counter(item: Input) -> Output:
    text = item.require_text()
    chars = len(text)
    chars_no_space = len(re.sub(r"\s", "", text))
    words = len(text.strip().split()) if text.strip() else 0
    lines = len(_lines(text)) if text else 0
    sentences = len([part for part in re.split(r"[.!?؟。]+", text) if part.strip()])
    paragraphs = len([part for part in re.split(r"\n\s*\n", text) if part.strip()])
    size = len(text.encode("utf-8"))
    minutes = words / 200
    if words == 0:
        read_time = "0 seconds"
    elif minutes < 1:
        read_time = f"{max(1, round(minutes * 60))} seconds"
    else:
        read_time = f"{max(1, round(minutes))} minutes"
    return ok(
        "\n".join(
            [
                f"Characters: {chars}",
                f"Characters (no spaces): {chars_no_space}",
                f"Words: {words}",
                f"Lines: {lines}",
                f"Sentences: {sentences}",
                f"Paragraphs: {paragraphs}",
                f"UTF-8 bytes: {size}",
                f"Reading time: {read_time}",
            ]
        ),
        title="Text Counter",
    )


# --------------------------------------------------------------------------
# Case conversion
# --------------------------------------------------------------------------

def _case_values(text: str) -> list[tuple[str, str]]:
    parts = _words(text)
    lower = [part.lower() for part in parts]
    camel = "".join((part if i == 0 else _cap(part)) for i, part in enumerate(lower))
    pascal = "".join(_cap(part) for part in parts)
    sentence = ""
    if lower:
        sentence = _cap(lower[0])
        if len(lower) > 1:
            sentence += " " + " ".join(lower[1:])
    alternating = "".join(
        char.upper() if index % 2 else char.lower()
        for index, char in enumerate(text)
    )
    return [
        ("camelCase", camel),
        ("PascalCase", pascal),
        ("snake_case", "_".join(lower)),
        ("kebab-case", "-".join(lower)),
        ("CONSTANT_CASE", "_".join(lower).upper()),
        ("Title Case", " ".join(_cap(part) for part in parts)),
        ("Sentence case", sentence),
        ("lowercase", text.lower()),
        ("UPPERCASE", text.upper()),
        ("aLtErNaTiNg", alternating),
    ]


def case_all(item: Input) -> Output:
    text = item.require_text()
    return ok(
        "\n".join(f"{label}: {value}" for label, value in _case_values(text)),
        title="Case Converter",
    )


def _case_variant(label: str):
    def run(item: Input) -> Output:
        text = item.require_text()
        values = dict(_case_values(text))
        return ok(values[label], title=f"Case: {label}")

    return run


for _label, _slug in [
    ("camelCase", "case-camel"),
    ("PascalCase", "case-pascal"),
    ("snake_case", "case-snake"),
    ("kebab-case", "case-kebab"),
    ("CONSTANT_CASE", "case-constant"),
    ("Title Case", "case-title"),
    ("Sentence case", "case-sentence"),
    ("lowercase", "case-lower"),
    ("UPPERCASE", "case-upper"),
    ("aLtErNaTiNg", "case-alternating"),
]:
    _register(
        make_tool(
            "case-converter",
            _case_variant(_label),
            id=_slug,
            title=f"Case: {_label}",
            keywords=["case", _label.lower()],
            hint="clipboard text",
        )
    )

_register(
    make_tool(
        "case-converter",
        case_all,
        title="Case Converter (all cases)",
        keywords=["case", "all"],
        hint="clipboard text",
    )
)


# --------------------------------------------------------------------------
# Line tools
# --------------------------------------------------------------------------

def _seeded_shuffle(lines: list[str]) -> list[str]:
    result = list(lines)
    seed = (len(result) * 2654435761) & 0xFFFFFFFF
    for index in range(len(result) - 1, 0, -1):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        target = int((seed / 0x7FFFFFFF) * (index + 1))
        result[index], result[target] = result[target], result[index]
    return result


def _line_apply(text: str, *, trim=False, remove_empty=False, unique=False,
                sort=None, number=False) -> str:
    lines = _lines(text)
    if trim:
        lines = [line.strip() for line in lines]
    if remove_empty:
        lines = [line for line in lines if line.strip()]
    if unique:
        lines = unique_preserve(lines)
    if sort == "asc":
        lines = sorted(lines, key=lambda value: value.lower())
    elif sort == "desc":
        lines = sorted(lines, key=lambda value: value.lower(), reverse=True)
    elif sort == "reverse":
        lines = list(reversed(lines))
    elif sort == "shuffle":
        lines = _seeded_shuffle(lines)
    if number:
        width = len(str(len(lines)))
        lines = [f"{index + 1:>{width}}. {line}" for index, line in enumerate(lines)]
    return "\n".join(lines)


def line_all(item: Input) -> Output:
    text = item.require_text()
    return ok(_line_apply(text, trim=True, remove_empty=True, unique=True), title="Line Tools")


def _line_variant(**options):
    def run(item: Input) -> Output:
        return ok(_line_apply(item.require_text(), **options), title="Line Tools")

    return run


for _slug, _title, _opts in [
    ("line-sort-asc", "Sort Lines A→Z", {"sort": "asc"}),
    ("line-sort-desc", "Sort Lines Z→A", {"sort": "desc"}),
    ("line-reverse", "Reverse Lines", {"sort": "reverse"}),
    ("line-shuffle", "Shuffle Lines", {"sort": "shuffle"}),
    ("line-unique", "Remove Duplicate Lines", {"unique": True}),
    ("line-remove-empty", "Remove Empty Lines", {"remove_empty": True}),
    ("line-trim", "Trim Lines", {"trim": True}),
    ("line-number", "Number Lines", {"number": True}),
]:
    _register(
        make_tool(
            "line-tools",
            _line_variant(**_opts),
            id=_slug,
            title=_title,
            keywords=["line", "lines", _title.lower()],
            hint="clipboard text",
        )
    )


def line_prefix(item: Input) -> Output:
    prefix, text = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    return ok("\n".join(prefix + line for line in _lines(text)), title="Prefix Lines")


def line_suffix(item: Input) -> Output:
    suffix, text = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    return ok("\n".join(line + suffix for line in _lines(text)), title="Suffix Lines")


_register(
    make_tool(
        "line-tools",
        line_prefix,
        id="line-prefix",
        title="Prefix Lines",
        hint="prefix|text",
    )
)
_register(
    make_tool(
        "line-tools",
        line_suffix,
        id="line-suffix",
        title="Suffix Lines",
        hint="suffix|text",
    )
)
_register(
    make_tool(
        "line-tools",
        line_all,
        title="Line Tools (trim + dedupe)",
        hint="clipboard text",
    )
)


# --------------------------------------------------------------------------
# Find and replace
# --------------------------------------------------------------------------

def _replace_literal(item: Input, *, ignore_case: bool) -> Output:
    find, replacement, text = split_pipe(item.require_text(), 3, from_right=True, strip=False)
    if not find:
        raise ToolError("Use find|replace|text in the clipboard.")
    flags = re.IGNORECASE if ignore_case else 0
    pattern = re.compile(re.escape(find), flags)
    count = len(pattern.findall(text))
    result = pattern.sub(lambda _m: replacement, text)
    return ok(result, title="Find & Replace", message=f"{count} replacement(s)")


def _replace_regex(item: Input, *, ignore_case: bool) -> Output:
    parts = item.require_text().rsplit("|", 3)
    if len(parts) == 3:
        pattern_text, replacement, text = parts
        flags_text = ""
    elif len(parts) == 4:
        pattern_text, replacement, flags_text, text = parts
    else:
        raise ToolError("Use pattern|replacement|flags|text in the clipboard.")
    flags = 0
    if ignore_case or "i" in flags_text.lower():
        flags |= re.IGNORECASE
    if "m" in flags_text.lower():
        flags |= re.MULTILINE
    if "s" in flags_text.lower():
        flags |= re.DOTALL
    try:
        pattern = re.compile(pattern_text, flags)
    except re.error as exc:
        raise ToolError(f"Invalid regex: {exc}") from exc
    count = len(pattern.findall(text))
    result = pattern.sub(replacement, text)
    return ok(result, title="Regex Replace", message=f"{count} replacement(s)")


_register(
    make_tool(
        "find-replace",
        lambda item: _replace_literal(item, ignore_case=False),
        title="Find & Replace",
        hint="find|replace|text",
    )
)
_register(
    make_tool(
        "find-replace",
        lambda item: _replace_literal(item, ignore_case=True),
        id="find-replace-ci",
        title="Find & Replace (ignore case)",
        keywords=["case insensitive"],
        hint="find|replace|text",
    )
)
_register(
    make_tool(
        "find-replace",
        lambda item: _replace_regex(item, ignore_case=False),
        id="find-replace-regex",
        title="Regex Replace",
        hint="pattern|replacement|flags|text",
    )
)
_register(
    make_tool(
        "find-replace",
        lambda item: _replace_regex(item, ignore_case=True),
        id="find-replace-regex-ci",
        title="Regex Replace (ignore case)",
        keywords=["case insensitive"],
        hint="pattern|replacement|flags|text",
    )
)


# --------------------------------------------------------------------------
# Diff and similarity
# --------------------------------------------------------------------------

_register(make_tool("text-counter", text_counter, title="Text Counter", hint="clipboard text"))


def _diff_lines(left: list[str], right: list[str]) -> list[tuple[str, str]]:
    n, m = len(left), len(right)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            table[i][j] = (
                table[i + 1][j + 1] + 1
                if left[i] == right[j]
                else max(table[i + 1][j], table[i][j + 1])
            )
    ops: list[tuple[str, str]] = []
    i = j = 0
    while i < n and j < m:
        if left[i] == right[j]:
            ops.append(("eq", left[i]))
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            ops.append(("del", left[i]))
            i += 1
        else:
            ops.append(("add", right[j]))
            j += 1
    while i < n:
        ops.append(("del", left[i]))
        i += 1
    while j < m:
        ops.append(("add", right[j]))
        j += 1
    return ops


def text_diff(item: Input) -> Output:
    left, right = split_pipe(item.require_text(), 2, from_right=False, strip=False)
    ops = _diff_lines(_lines(left), _lines(right))
    added = sum(1 for kind, _ in ops if kind == "add")
    removed = sum(1 for kind, _ in ops if kind == "del")
    body = "\n".join(
        ("+" if kind == "add" else "-" if kind == "del" else " ") + line
        for kind, line in ops
    )
    return ok(
        f"Added: {added}  Removed: {removed}\n\n{body}",
        title="Text Diff",
    )


_register(make_tool("text-diff", text_diff, title="Text Diff", hint="left|right"))


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def _word_set(value: str) -> set[str]:
    return set(value.lower().strip().split())


def text_similarity(item: Input) -> Output:
    a, b = split_pipe(item.require_text(), 2, from_right=False, strip=False)
    distance = _levenshtein(a, b)
    longest = max(len(a), len(b))
    similarity = 100.0 if longest == 0 else (1 - distance / longest) * 100
    set_a, set_b = _word_set(a), _word_set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    jaccard = 0.0 if union == 0 else intersection / union * 100
    dice = 0.0 if not set_a and not set_b else 2 * intersection / (len(set_a) + len(set_b)) * 100
    return ok(
        "\n".join(
            [
                f"Levenshtein distance: {distance}",
                f"Character similarity: {similarity:.1f}%",
                f"Jaccard (words): {jaccard:.1f}%",
                f"Dice (words): {dice:.1f}%",
            ]
        ),
        title="Text Similarity",
    )


_register(make_tool("text-similarity", text_similarity, title="Text Similarity", hint="a|b"))


def string_checker(item: Input) -> Output:
    a, b = split_pipe(item.require_text(), 2, from_right=False, strip=False)
    clean = re.sub(r"[\s\W_]", "", a.lower(), flags=re.UNICODE)
    palindrome = bool(clean) and clean == clean[::-1]
    anagram = None
    if a.strip() and b.strip():
        anagram = sorted(re.sub(r"\s+", "", a.lower())) == sorted(
            re.sub(r"\s+", "", b.lower())
        )
    return ok(
        "\n".join(
            [
                f"Palindrome (first text): {'yes' if palindrome else 'no'}",
                f"Anagram (first vs second): {'yes' if anagram else 'no' if anagram is not None else '-'}",
            ]
        ),
        title="String Checker",
    )


_register(make_tool("string-checker", string_checker, title="String Checker", hint="a|b"))


# --------------------------------------------------------------------------
# Extract
# --------------------------------------------------------------------------

_EXTRACT_PATTERNS = {
    "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "url": r"\bhttps?://[^\s<>\"')]+",
    "ip": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "domain": r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b",
    "number": r"-?\d+(?:\.\d+)?",
    "hashtag": r"#[\w\d_]+",
    "phone": r"(?:\+?98|0)?9\d{9}|0\d{2,3}[- ]?\d{7,8}",
    "quoted": r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'",
}


def _extract(kind: str):
    def run(item: Input) -> Output:
        text = item.require_text()
        pattern = _EXTRACT_PATTERNS[kind]
        flags = re.IGNORECASE if kind in {"url", "domain"} else 0
        matches = re.findall(pattern, text, flags)
        values = unique_preserve(matches)
        return ok(
            "\n".join(values),
            title=f"Extract {kind.title()}",
            message=f"{len(values)} unique match(es)",
        )

    return run


for _kind, _slug in [
    ("email", "extract-email"),
    ("url", "extract-url"),
    ("ip", "extract-ip"),
    ("domain", "extract-domain"),
    ("number", "extract-number"),
    ("hashtag", "extract-hashtag"),
    ("phone", "extract-phone"),
    ("quoted", "extract-quoted"),
]:
    _register(
        make_tool(
            "extract-text",
            _extract(_kind),
            id=_slug,
            title=f"Extract {_kind.title()}",
            keywords=[_kind, "extract"],
            hint="clipboard text",
        )
    )

_register(
    make_tool(
        "extract-text",
        _extract("email"),
        title="Extract Emails",
        hint="clipboard text",
    )
)


# --------------------------------------------------------------------------
# Frequency
# --------------------------------------------------------------------------

def _frequency(items: list[str]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0].lower()))


def _freq_output(pairs: list[tuple[str, int]], label: str) -> Output:
    body = "\n".join(f"{count}\t{value!r}" for value, count in pairs[:200])
    return ok(body, title=f"Frequency: {label}", message=f"{len(pairs)} unique item(s)")


def freq_chars(item: Input) -> Output:
    text = item.require_text()
    chars = [char for char in text if not char.isspace()]
    return _freq_output(_frequency(chars), "characters")


def freq_words(item: Input) -> Output:
    text = item.require_text()
    words = text.strip().split() if text.strip() else []
    return _freq_output(_frequency(words), "words")


def freq_ngrams(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if len(parts) == 2 and parts[0].strip().isdigit():
        size = max(1, min(4, int(parts[0].strip())))
        text = parts[1]
    else:
        size = 2
        text = item.require_text()
    words = text.strip().split() if text.strip() else []
    grams = [" ".join(words[i : i + size]) for i in range(max(0, len(words) - size + 1))]
    return _freq_output(_frequency(grams), f"{size}-grams")


_register(make_tool("text-frequency", freq_chars, title="Character Frequency", hint="clipboard text"))
_register(make_tool("text-frequency", freq_words, id="frequency-words", title="Word Frequency", hint="clipboard text"))
_register(make_tool("text-frequency", freq_ngrams, id="frequency-ngrams", title="N-gram Frequency", hint="n|text"))


# --------------------------------------------------------------------------
# Whitespace
# --------------------------------------------------------------------------

def ws_normalize(item: Input) -> Output:
    text = item.require_text().replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return ok(text, title="Whitespace Normalizer")


def ws_trim(item: Input) -> Output:
    return ok(re.sub(r"[ \t]+$", "", item.require_text(), flags=re.MULTILINE), title="Trim Trailing Spaces")


def ws_trim_all(item: Input) -> Output:
    return ok("\n".join(line.strip() for line in _lines(item.require_text())), title="Trim Lines")


def ws_collapse(item: Input) -> Output:
    text = item.require_text().replace("\r\n", "\n").replace("\r", "\n")
    return ok(re.sub(r"\n{3,}", "\n\n", text), title="Collapse Blank Lines")


def ws_tabs_to_spaces(item: Input) -> Output:
    size_text, text = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    size = int(size_text.strip()) if size_text.strip().isdigit() else 4
    return ok(text.replace("\t", " " * max(1, size)), title="Tabs → Spaces")


def ws_spaces_to_tabs(item: Input) -> Output:
    size_text, text = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    size = int(size_text.strip()) if size_text.strip().isdigit() else 4
    size = max(1, size)

    def convert(match: re.Match) -> str:
        length = len(match.group(0))
        return "\t" * (length // size) + " " * (length % size)

    return ok(re.sub(r" {1,}", convert, text), title="Spaces → Tabs")


def ws_lf(item: Input) -> Output:
    return ok(item.require_text().replace("\r\n", "\n").replace("\r", "\n"), title="Line Endings: LF")


def ws_crlf(item: Input) -> Output:
    text = item.require_text().replace("\r\n", "\n").replace("\r", "\n")
    return ok(text.replace("\n", "\r\n"), title="Line Endings: CRLF")


_register(make_tool("whitespace-tool", ws_normalize, title="Whitespace Normalizer", hint="clipboard text"))
_register(make_tool("whitespace-tool", ws_trim, id="ws-trim", title="Trim Trailing Spaces", hint="clipboard text"))
_register(make_tool("whitespace-tool", ws_trim_all, id="ws-trim-all", title="Trim Each Line", hint="clipboard text"))
_register(make_tool("whitespace-tool", ws_collapse, id="ws-collapse", title="Collapse Blank Lines", hint="clipboard text"))
_register(make_tool("whitespace-tool", ws_tabs_to_spaces, id="ws-tabs-to-spaces", title="Tabs → Spaces", hint="size|text"))
_register(make_tool("whitespace-tool", ws_spaces_to_tabs, id="ws-spaces-to-tabs", title="Spaces → Tabs", hint="size|text"))
_register(make_tool("whitespace-tool", ws_lf, id="ws-lf", title="Line Endings: LF", hint="clipboard text"))
_register(make_tool("whitespace-tool", ws_crlf, id="ws-crlf", title="Line Endings: CRLF", hint="clipboard text"))


# --------------------------------------------------------------------------
# Wrap / unwrap
# --------------------------------------------------------------------------

def _wrap_line(line: str, width: int) -> str:
    if line.strip() == "":
        return line
    pieces = re.split(r"(\s+)", line)
    output: list[str] = []
    current = ""
    for piece in pieces:
        if current == "":
            current = piece.lstrip()
        elif len(current + piece) <= width:
            current += piece
        else:
            output.append(current.rstrip())
            current = piece.lstrip()
    if current.strip() != "" or not output:
        output.append(current.rstrip())
    return "\n".join(output)


def text_wrap(item: Input) -> Output:
    width_text, text = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    width = int(width_text.strip()) if width_text.strip().isdigit() else 80
    width = max(1, width)
    return ok(
        "\n".join(_wrap_line(line, width) for line in _lines(text)),
        title="Wrap Text",
    )


def text_unwrap(item: Input) -> Output:
    text = item.require_text().replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n{2,}", text)
    joined = [
        " ".join(line.strip() for line in paragraph.split("\n") if line.strip())
        for paragraph in paragraphs
    ]
    return ok("\n\n".join(joined), title="Unwrap Text")


_register(make_tool("text-wrap", text_wrap, title="Wrap Text", hint="width|text"))
_register(make_tool("text-wrap", text_unwrap, id="text-unwrap", title="Unwrap Text", hint="clipboard text"))


# --------------------------------------------------------------------------
# Cleanup
# --------------------------------------------------------------------------

def diacritics_latin(item: Input) -> Output:
    text = unicodedata.normalize("NFD", item.require_text())
    text = re.sub(r"[\u0300-\u036f]", "", text)
    return ok(unicodedata.normalize("NFC", text), title="Remove Latin Diacritics")


def diacritics_all(item: Input) -> Output:
    text = unicodedata.normalize("NFD", item.require_text())
    text = re.sub(r"[\u0300-\u036f]", "", text)
    text = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", text)
    return ok(unicodedata.normalize("NFC", text), title="Remove Diacritics")


_register(make_tool("diacritics-remover", diacritics_all, title="Remove Diacritics", hint="clipboard text"))
_register(make_tool("diacritics-remover", diacritics_latin, id="diacritics-latin", title="Remove Latin Diacritics", hint="clipboard text"))


_INVISIBLE = {
    0x00A0: "NBSP - non-breaking space",
    0x00AD: "SHY - soft hyphen",
    0x061C: "ALM - Arabic letter mark",
    0x180E: "MVS - Mongolian vowel separator",
    0x200B: "ZWSP - zero-width space",
    0x200C: "ZWNJ - zero-width non-joiner",
    0x200D: "ZWJ - zero-width joiner",
    0x200E: "LRM - left-to-right mark",
    0x200F: "RLM - right-to-left mark",
    0x202A: "LRE - left-to-right embedding",
    0x202B: "RLE - right-to-left embedding",
    0x202C: "PDF - pop directional formatting",
    0x202D: "LRO - left-to-right override",
    0x202E: "RLO - right-to-left override",
    0x2060: "WJ - word joiner",
    0x2061: "Function application",
    0x2062: "Invisible times",
    0x2063: "Invisible separator",
    0x2064: "Invisible plus",
    0x2066: "LRI - left-to-right isolate",
    0x2067: "RLI - right-to-left isolate",
    0x2068: "FSI - first strong isolate",
    0x2069: "PDI - pop directional isolate",
    0x3000: "Ideographic space",
    0xFEFF: "BOM / ZWNBSP",
}


def invisible_detect(item: Input) -> Output:
    text = item.require_text()
    found = []
    for index, char in enumerate(text):
        code = ord(char)
        if code in _INVISIBLE:
            found.append(f"#{index}  U+{code:04X}  {_INVISIBLE[code]}")
    if not found:
        return ok("No invisible characters found.", title="Invisible Characters")
    return ok("\n".join(found), title="Invisible Characters", message=f"{len(found)} found")


def invisible_strip(item: Input) -> Output:
    text = "".join(char for char in item.require_text() if ord(char) not in _INVISIBLE)
    return ok(text, title="Remove Invisible Characters")


_register(make_tool("invisible-chars", invisible_detect, title="Detect Invisible Characters", hint="clipboard text"))
_register(make_tool("invisible-chars", invisible_strip, id="invisible-strip", title="Remove Invisible Characters", hint="clipboard text"))


def smart_quotes(item: Input) -> Output:
    text = item.require_text()
    text = text.replace("---", "—").replace("--", "–")
    text = re.sub(r'(^|[\s(\[{<])"', r"\1“", text)
    text = text.replace('"', "”")
    text = re.sub(r"(^|[\s(\[{<])'", r"\1‘", text)
    text = text.replace("'", "’")
    return ok(text, title="Smart Quotes")


def straight_quotes(item: Input) -> Output:
    text = item.require_text()
    text = text.replace("“", '"').replace("”", '"').replace("„", '"')
    text = text.replace("‘", "'").replace("’", "'").replace("‚", "'")
    text = text.replace("—", "---").replace("–", "--")
    return ok(text, title="Straight Quotes")


_register(make_tool("smart-quotes", smart_quotes, title="Smart Quotes", hint="clipboard text"))
_register(make_tool("smart-quotes", straight_quotes, id="straight-quotes", title="Straight Quotes", hint="clipboard text"))


def reverse_chars(item: Input) -> Output:
    return ok(item.require_text()[::-1], title="Reverse Characters")


def reverse_words(item: Input) -> Output:
    text = item.require_text()
    return ok(
        "\n".join(
            "".join(reversed(re.split(r"(\s+)", line)))
            for line in _lines(text)
        ),
        title="Reverse Words",
    )


def reverse_lines(item: Input) -> Output:
    return ok("\n".join(reversed(_lines(item.require_text()))), title="Reverse Lines")


_register(make_tool("reverse-text", reverse_chars, title="Reverse Characters", hint="clipboard text"))
_register(make_tool("reverse-text", reverse_words, id="reverse-words", title="Reverse Words", hint="clipboard text"))
_register(make_tool("reverse-text", reverse_lines, id="reverse-lines", title="Reverse Lines", hint="clipboard text"))


# --------------------------------------------------------------------------
# Original Text Tools actions
# --------------------------------------------------------------------------

def arabic_to_persian(item: Input) -> Output:
    text = item.require_text()
    return ok(
        text.replace("ي", "ی").replace("ك", "ک").replace("ى", "ی").replace("ة", "ه"),
        title="Arabic → Persian",
    )


def add_comma(item: Input) -> Output:
    return ok("\n".join(line + "," for line in _lines(item.require_text())), title="Add Comma")


def to_upper(item: Input) -> Output:
    return ok(item.require_text().upper(), title="UPPERCASE")


def to_lower(item: Input) -> Output:
    return ok(item.require_text().lower(), title="lowercase")


def remove_empty_lines(item: Input) -> Output:
    return ok("\n".join(line for line in _lines(item.require_text()) if line.strip()), title="Remove Empty Lines")


def trim_lines(item: Input) -> Output:
    return ok("\n".join(line.strip() for line in _lines(item.require_text())), title="Trim Lines")


def remove_spaces(item: Input) -> Output:
    return ok(
        re.sub(r"[\s\u200c\u200b\u00a0\u2000-\u200a\u202f\u205f\u3000\ufeff]", "", item.require_text()),
        title="Remove Spaces",
    )


_register(
    make_custom_tool(
        id="arabic-to-persian",
        title="Arabic to Persian",
        title_fa="تبدیل حروف عربی به فارسی",
        description="جایگزینی حروف عربی ي و ك با حروف فارسی",
        category="text",
        keywords=["arabic", "persian", "عربی", "فارسی", "ي", "ك"],
        run=arabic_to_persian,
        hint="clipboard text",
    )
)
_register(
    make_custom_tool(
        id="add-comma",
        title="Add Comma to Each Line",
        title_fa="افزودن کاما به هر خط",
        description="افزودن کاما به انتهای هر خط",
        category="text",
        keywords=["comma", "line", "کاما", "خط"],
        run=add_comma,
        hint="clipboard text",
    )
)
_register(
    make_custom_tool(
        id="to-upper",
        title="UPPERCASE",
        title_fa="حروف بزرگ",
        description="تبدیل متن به حروف بزرگ",
        category="text",
        keywords=["uppercase", "upper", "بزرگ"],
        run=to_upper,
        hint="clipboard text",
    )
)
_register(
    make_custom_tool(
        id="to-lower",
        title="lowercase",
        title_fa="حروف کوچک",
        description="تبدیل متن به حروف کوچک",
        category="text",
        keywords=["lowercase", "lower", "کوچک"],
        run=to_lower,
        hint="clipboard text",
    )
)
_register(
    make_custom_tool(
        id="remove-empty-lines",
        title="Remove Empty Lines",
        title_fa="حذف خطوط خالی",
        description="حذف تمام خطوط خالی",
        category="text",
        keywords=["empty", "lines", "خالی", "خط"],
        run=remove_empty_lines,
        hint="clipboard text",
    )
)
_register(
    make_custom_tool(
        id="trim-lines",
        title="Trim Each Line",
        title_fa="حذف فاصله ابتدا و انتهای خطوط",
        description="حذف فاصله‌های ابتدا و انتهای هر خط",
        category="text",
        keywords=["trim", "lines", "فاصله", "خط"],
        run=trim_lines,
        hint="clipboard text",
    )
)
_register(
    make_custom_tool(
        id="remove-spaces",
        title="Remove All Spaces",
        title_fa="حذف تمام فاصله‌ها",
        description="حذف فاصله کامل، نیم‌فاصله و کاراکترهای بدون عرض",
        category="text",
        keywords=["spaces", "whitespace", "فاصله", "نیم‌فاصله"],
        run=remove_spaces,
        hint="clipboard text",
    )
)
