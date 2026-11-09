# -*- coding: utf-8 -*-
"""Log, ANSI and tracing tools."""

from __future__ import annotations

import html as html_lib
import json
import re

from .common import json_text, ok, split_pipe, temp_path
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-_]")


def ansi_strip(item: Input) -> Output:
    return ok(_ANSI_RE.sub("", item.require_text()), title="ANSI Stripper")


_FG = {
    30: "#1e1e1e", 31: "#e74c3c", 32: "#2ecc71", 33: "#d4ac0d",
    34: "#3498db", 35: "#9b59b6", 36: "#17a2b8", 37: "#d0d0d0",
    90: "#7f8c8d", 91: "#ff6b6b", 92: "#5cf28b", 93: "#f1c40f",
    94: "#5dade2", 95: "#bb8fce", 96: "#48dbfb", 97: "#ffffff",
}
_BG = {
    40: "#1e1e1e", 41: "#e74c3c", 42: "#2ecc71", 43: "#d4ac0d",
    44: "#3498db", 45: "#9b59b6", 46: "#17a2b8", 47: "#d0d0d0",
    100: "#7f8c8d", 101: "#ff6b6b", 102: "#5cf28b", 103: "#f1c40f",
    104: "#5dade2", 105: "#bb8fce", 106: "#48dbfb", 107: "#ffffff",
}


def _render_ansi(text: str) -> str:
    sgr = re.compile(r"\x1b\[([0-9;]*)m")
    output = []
    style = {}
    last = 0

    def emit(value: str):
        if not value:
            return
        css = []
        if style.get("fg"):
            css.append(f"color:{style['fg']}")
        if style.get("bg"):
            css.append(f"background:{style['bg']}")
        if style.get("bold"):
            css.append("font-weight:700")
        if style.get("italic"):
            css.append("font-style:italic")
        if style.get("underline"):
            css.append("text-decoration:underline")
        safe = html_lib.escape(value)
        output.append(f'<span style="{";".join(css)}">{safe}</span>' if css else safe)

    for match in sgr.finditer(text):
        emit(text[last : match.start()])
        codes = [0] if match.group(1) == "" else [int(part or 0) for part in match.group(1).split(";")]
        index = 0
        while index < len(codes):
            code = codes[index]
            if code == 0:
                style.clear()
            elif code == 1:
                style["bold"] = True
            elif code == 3:
                style["italic"] = True
            elif code == 4:
                style["underline"] = True
            elif code == 22:
                style.pop("bold", None)
            elif code == 23:
                style.pop("italic", None)
            elif code == 24:
                style.pop("underline", None)
            elif code == 39:
                style.pop("fg", None)
            elif code == 49:
                style.pop("bg", None)
            elif code in _FG:
                style["fg"] = _FG[code]
            elif code in _BG:
                style["bg"] = _BG[code]
            elif code in (38, 48):
                target = "fg" if code == 38 else "bg"
                if index + 1 < len(codes) and codes[index + 1] == 2 and index + 4 < len(codes):
                    style[target] = f"rgb({codes[index + 2]},{codes[index + 3]},{codes[index + 4]})"
                    index += 4
                elif index + 1 < len(codes) and codes[index + 1] == 5:
                    index += 2
            index += 1
        last = match.end()
    emit(text[last:])
    return _ANSI_RE.sub("", "".join(output))


def ansi_render(item: Input) -> Output:
    body = _render_ansi(item.require_text())
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>ANSI</title>
<style>body{{background:#0c0c0c;color:#d0d0d0;font-family:Consolas,monospace;padding:1rem}}
pre{{white-space:pre-wrap;word-break:break-word;line-height:1.6}}</style></head>
<body><pre>{body}</pre></body></html>"""
    path = temp_path("html", "ansi")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return Output(title="ANSI Render", open_path=path, message="Rendered ANSI opened in your browser", copy=False)


_register(make_tool("ansi-stripper", ansi_strip, title="ANSI Stripper", hint="clipboard ANSI text"))
_register(make_tool("ansi-stripper", ansi_render, id="ansi-render", title="ANSI Render", hint="clipboard ANSI text"))


# --------------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------------

_EXIT_CODES = [
    (0, "Success", "Command completed successfully."),
    (1, "General Error", "Generic error."),
    (2, "Misuse of Shell Builtins", "Shell builtin misuse."),
    (126, "Command Not Executable", "Command found but not executable."),
    (127, "Command Not Found", "Command not found."),
    (128, "Invalid Exit Argument", "Invalid exit argument."),
    (130, "SIGINT (Ctrl-C)", "Terminated by Ctrl-C."),
    (131, "SIGQUIT", "Quit signal."),
    (132, "SIGILL", "Illegal instruction."),
    (134, "SIGABRT", "Aborted."),
    (136, "SIGFPE", "Floating-point exception."),
    (137, "SIGKILL", "Killed (often OOM killer)."),
    (139, "SIGSEGV", "Segmentation fault."),
    (141, "SIGPIPE", "Broken pipe."),
    (143, "SIGTERM", "Terminated."),
    (255, "Out of Range", "Exit status out of range."),
]
_SIGNALS = [
    (1, "SIGHUP", "Hangup."),
    (2, "SIGINT", "Interrupt (Ctrl-C)."),
    (3, "SIGQUIT", "Quit with core dump."),
    (9, "SIGKILL", "Kill (cannot be caught)."),
    (11, "SIGSEGV", "Segmentation violation."),
    (13, "SIGPIPE", "Broken pipe."),
    (15, "SIGTERM", "Termination request."),
    (18, "SIGCONT", "Continue."),
    (19, "SIGSTOP", "Stop (cannot be caught)."),
    (20, "SIGTSTP", "Terminal stop (Ctrl-Z)."),
]


def exit_code_reference(item: Input) -> Output:
    query = item.text.strip().lower()
    lines = []
    codes = [row for row in _EXIT_CODES if not query or query in str(row[0]) or query in row[1].lower() or query in row[2].lower()]
    signals = [row for row in _SIGNALS if not query or query in str(row[0]) or query in row[1].lower() or query in row[2].lower()]
    if codes:
        lines.append("Exit codes:")
        lines.extend(f"  {code:>3}  {name}: {description}" for code, name, description in codes)
    if signals:
        if lines:
            lines.append("")
        lines.append("Signals:")
        lines.extend(f"  {code:>3}  {name}: {description}" for code, name, description in signals)
    if not lines:
        return ok("No matching exit code or signal.", title="Exit Codes")
    return ok("\n".join(lines), title="Exit Codes")


_register(make_tool("exit-code-reference", exit_code_reference, title="Exit Code Reference", hint="query (optional)"))


# --------------------------------------------------------------------------
# JSON logs
# --------------------------------------------------------------------------

def _parse_json_logs(text: str) -> list[dict]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
            return [row for row in data if isinstance(row, dict)]
        except Exception as exc:
            raise ToolError(f"Invalid JSON: {exc}") from exc
    rows = []
    for line in stripped.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
        except Exception:
            continue
    return rows


def json_log_viewer(item: Input) -> Output:
    query, payload = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not payload.strip():
        query, payload = "", item.require_text()
    rows = _parse_json_logs(payload)
    if not rows:
        raise ToolError("No JSON log rows found.")
    needle = query.strip().lower()
    if needle:
        rows = [row for row in rows if needle in json.dumps(row, ensure_ascii=False).lower()]
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
        if len(columns) >= 12:
            break
    columns = columns[:12]
    lines = [" | ".join(columns)]
    lines.append(" | ".join("---" for _ in columns))
    for row in rows[:200]:
        cells = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            cells.append("" if value is None else str(value))
        lines.append(" | ".join(cells))
    return ok("\n".join(lines), title="JSON Log Viewer", message=f"{len(rows)} row(s)")


_register(make_tool("json-log-viewer", json_log_viewer, title="JSON Log Viewer", hint="filter|JSON or NDJSON"))


# --------------------------------------------------------------------------
# Access logs
# --------------------------------------------------------------------------

_LOG_RE = re.compile(
    r'^(\S+)\s+\S+\s+\S+\s+\[([^\]]+)\]\s+"(\S+)\s+(.*?)\s+(\S+)"\s+(\d{3})\s+(\d+|-)(?:\s+"([^"]*)"\s+"([^"]*)")?'
)


def log_parser(item: Input) -> Output:
    rows = []
    bad = 0
    for line in item.require_text().splitlines():
        line = line.strip()
        if not line:
            continue
        match = _LOG_RE.match(line)
        if not match:
            bad += 1
            continue
        rows.append(match.groups())
    if not rows:
        raise ToolError("No Common/Combined log lines found.")
    lines = ["IP | Time | Method | Path | Status | Size | Referer | User-Agent"]
    for ip, time_value, method, path, _protocol, status, size, referer, ua in rows[:200]:
        lines.append(
            f"{ip} | {time_value} | {method} | {path} | {status} | {size} | {referer or '-'} | {ua or '-'}"
        )
    if bad:
        lines.append(f"\nSkipped {bad} unrecognized line(s).")
    return ok("\n".join(lines), title="Access Log Parser", message=f"{len(rows)} row(s)")


_register(make_tool("log-parser", log_parser, title="Access Log Parser", hint="clipboard Apache/Nginx log"))


# --------------------------------------------------------------------------
# traceparent
# --------------------------------------------------------------------------

def traceparent_parser(item: Input) -> Output:
    value = item.require_text().strip()
    parts = value.split("-")
    if len(parts) != 4:
        raise ToolError("traceparent must have 4 dash-separated parts.")
    version, trace_id, parent_id, flags = parts
    if not re.fullmatch(r"[0-9a-f]{2}", version, re.IGNORECASE):
        raise ToolError("version must be 2 hex characters.")
    if version.lower() == "ff":
        raise ToolError("version ff is invalid.")
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id, re.IGNORECASE) or trace_id == "0" * 32:
        raise ToolError("trace-id must be 32 non-zero hex characters.")
    if not re.fullmatch(r"[0-9a-f]{16}", parent_id, re.IGNORECASE) or parent_id == "0" * 16:
        raise ToolError("parent-id must be 16 non-zero hex characters.")
    if not re.fullmatch(r"[0-9a-f]{2}", flags, re.IGNORECASE):
        raise ToolError("flags must be 2 hex characters.")
    bits = int(flags, 16)
    sampled = bool(bits & 1)
    return ok(
        "\n".join(
            [
                f"version: {version.lower()}",
                f"trace-id: {trace_id.lower()}",
                f"parent-id: {parent_id.lower()}",
                f"trace-flags: {flags.lower()} (0b{bits:08b})",
                f"sampled: {'yes' if sampled else 'no'}",
            ]
        ),
        title="traceparent Parser",
    )


_register(make_tool("traceparent-parser", traceparent_parser, title="W3C traceparent Parser", hint="clipboard traceparent"))
