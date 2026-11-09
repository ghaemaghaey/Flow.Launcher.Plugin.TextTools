# -*- coding: utf-8 -*-
"""CSV, Markdown table and SQL insert tools."""

from __future__ import annotations

import csv
import html as html_lib
import io
import re

from .common import ok, split_pipe
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


def _delimiter_and_payload(text: str) -> tuple[str, str]:
    if "|" in text:
        head, tail = text.split("|", 1)
        if head in {",", ";", "\t"}:
            return head, tail
    return ",", text


def _parse_csv(text: str, delimiter: str) -> list[list[str]]:
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    except Exception as exc:
        raise ToolError(f"Invalid CSV: {exc}") from exc
    return [row for row in rows if any(cell.strip() for cell in row)]


def _to_csv(rows: list[list[str]], delimiter: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue().rstrip("\n")


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


# --------------------------------------------------------------------------
# CSV → HTML / Markdown
# --------------------------------------------------------------------------

def _csv_to_html(no_header: bool = False):
    def run(item: Input) -> Output:
        delimiter, payload = _delimiter_and_payload(item.require_text())
        rows = _parse_csv(payload, delimiter)
        if not rows:
            return ok("", title="CSV → HTML")
        lines = ["<table>"]
        body = rows
        if not no_header:
            lines.append("  <thead>")
            lines.append("    <tr>" + "".join(f"<th>{html_lib.escape(cell)}</th>" for cell in rows[0]) + "</tr>")
            lines.append("  </thead>")
            body = rows[1:]
        lines.append("  <tbody>")
        for row in body:
            lines.append("    <tr>" + "".join(f"<td>{html_lib.escape(cell)}</td>" for cell in row) + "</tr>")
        lines.append("  </tbody>")
        lines.append("</table>")
        return ok("\n".join(lines), title="CSV → HTML")

    return run


def _csv_to_markdown(no_header: bool = False):
    def run(item: Input) -> Output:
        delimiter, payload = _delimiter_and_payload(item.require_text())
        rows = _parse_csv(payload, delimiter)
        if not rows:
            return ok("", title="CSV → Markdown")
        columns = max(len(row) for row in rows)

        def pad(row):
            return [_escape_md(row[index] if index < len(row) else "") for index in range(columns)]

        header = pad(rows[0]) if not no_header else [f"Column {index + 1}" for index in range(columns)]
        body = rows[1:] if not no_header else rows
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        lines.extend("| " + " | ".join(pad(row)) + " |" for row in body)
        return ok("\n".join(lines), title="CSV → Markdown")

    return run


_register(make_tool("csv-to-html", _csv_to_html(), title="CSV → HTML Table", hint="CSV (or ,|CSV)"))
_register(make_tool("csv-to-html", _csv_to_html(no_header=True), id="csv-to-html-no-header", title="CSV → HTML (no header)", hint="CSV"))
_register(make_tool("csv-to-markdown", _csv_to_markdown(), title="CSV → Markdown Table", hint="CSV (or ,|CSV)"))
_register(make_tool("csv-to-markdown", _csv_to_markdown(no_header=True), id="csv-to-markdown-no-header", title="CSV → Markdown (no header)", hint="CSV"))


# --------------------------------------------------------------------------
# CSV tools
# --------------------------------------------------------------------------

def _csv_sort(default_column: str = "0", default_desc: bool = False, default_numeric: bool = False):
    def run(item: Input) -> Output:
        parts = item.require_text().rsplit("|", 3)
        if len(parts) == 1:
            column, order, kind, payload = "0", "", "", parts[0]
        elif len(parts) == 2:
            column, order, kind, payload = parts[0], "", "", parts[1]
        elif len(parts) == 3:
            column, order, kind, payload = parts[0], parts[1], "", parts[2]
        else:
            column, order, kind, payload = parts
        delimiter, payload = _delimiter_and_payload(payload)
        rows = _parse_csv(payload, delimiter)
        if not rows:
            return ok("", title="CSV Sort")
        header = rows[0]
        body = rows[1:]
        try:
            index = int(column) if column.strip() else int(default_column)
        except ValueError:
            index = header.index(column.strip()) if column.strip() in header else 0
        numeric = kind.strip().lower() in {"num", "numeric", "number"} or default_numeric
        desc = order.strip().lower() in {"desc", "d", "descending"} or default_desc

        def key(row):
            value = row[index] if index < len(row) else ""
            if numeric:
                try:
                    return float(value)
                except ValueError:
                    return 0.0
            return value.lower()

        body = sorted(body, key=key, reverse=desc)
        return ok(_to_csv([header] + body, delimiter), title="CSV Sort")

    return run


def csv_dedupe(item: Input) -> Output:
    delimiter, payload = _delimiter_and_payload(item.require_text())
    rows = _parse_csv(payload, delimiter)
    if not rows:
        return ok("", title="CSV Deduplicate")
    header, body = rows[0], rows[1:]
    seen = set()
    unique = []
    for row in body:
        key = tuple(row)
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return ok(_to_csv([header] + unique, delimiter), title="CSV Deduplicate")


def csv_transpose(item: Input) -> Output:
    delimiter, payload = _delimiter_and_payload(item.require_text())
    rows = _parse_csv(payload, delimiter)
    if not rows:
        return ok("", title="CSV Transpose")
    columns = max(len(row) for row in rows)
    transposed = [[row[index] if index < len(row) else "" for row in rows] for index in range(columns)]
    return ok(_to_csv(transposed, delimiter), title="CSV Transpose")


def csv_filter(item: Input) -> Output:
    query, payload = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not payload.strip():
        query, payload = "", item.require_text()
    delimiter, payload = _delimiter_and_payload(payload)
    rows = _parse_csv(payload, delimiter)
    if not rows:
        return ok("", title="CSV Filter")
    header, body = rows[0], rows[1:]
    needle = query.strip().lower()
    matched = [row for row in body if not needle or any(needle in cell.lower() for cell in row)]
    return ok(_to_csv([header] + matched, delimiter), title="CSV Filter", message=f"{len(matched)} row(s)")


_register(make_tool("csv-tools", _csv_sort(), title="CSV Sort", hint="column|order|type|CSV"))
_register(make_tool("csv-tools", csv_dedupe, id="csv-dedupe", title="CSV Deduplicate", hint="CSV"))
_register(make_tool("csv-tools", csv_transpose, id="csv-transpose", title="CSV Transpose", hint="CSV"))
_register(make_tool("csv-tools", csv_filter, id="csv-filter", title="CSV Filter", hint="query|CSV"))


# --------------------------------------------------------------------------
# Markdown tables
# --------------------------------------------------------------------------

def _split_md_row(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    cells = []
    current = ""
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value) and value[index + 1] == "|":
            current += "|"
            index += 2
            continue
        if char == "|":
            cells.append(current.strip())
            current = ""
        else:
            current += char
        index += 1
    cells.append(current.strip())
    return cells


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", line)) and "-" in line


def markdown_table_csv(item: Input) -> Output:
    delimiter, payload = _delimiter_and_payload(item.require_text())
    lines = [line for line in payload.splitlines() if "|" in line]
    if not lines:
        raise ToolError("No Markdown table found.")
    rows = [_split_md_row(line) for line in lines if not _is_separator(line)]
    if not rows:
        raise ToolError("No Markdown table rows found.")
    return ok(_to_csv(rows, delimiter), title="Markdown Table → CSV")


_register(make_tool("markdown-table-csv", markdown_table_csv, title="Markdown Table → CSV", hint="Markdown table"))


def markdown_table_generator(item: Input) -> Output:
    parts = split_pipe(item.text, 2, from_right=False, strip=True)
    columns = int(parts[0]) if parts[0].isdigit() else 3
    rows = int(parts[1]) if parts[1].isdigit() else 2
    columns = max(1, min(12, columns))
    rows = max(1, min(30, rows))
    header = [f"Column {index + 1}" for index in range(columns)]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join("" for _ in header) + " |" for _ in range(rows))
    return ok("\n".join(lines), title="Markdown Table Generator")


_register(make_tool("markdown-table-generator", markdown_table_generator, title="Markdown Table Generator", hint="cols|rows"))


# --------------------------------------------------------------------------
# SQL INSERT
# --------------------------------------------------------------------------

def sql_insert_generator(item: Input) -> Output:
    parts = item.require_text().rsplit("|", 3)
    if len(parts) == 1:
        table, empty_null, multi_row, payload = "my_table", "", "", parts[0]
    elif len(parts) == 2:
        table, empty_null, multi_row, payload = parts[0], "", "", parts[1]
    elif len(parts) == 3:
        table, empty_null, multi_row, payload = parts[0], parts[1], "", parts[2]
    else:
        table, empty_null, multi_row, payload = parts
    table = table.strip() or "my_table"
    null_for_empty = empty_null.strip().lower() not in {"0", "false", "no"}
    multi = multi_row.strip().lower() in {"1", "true", "yes"}
    delimiter, payload = _delimiter_and_payload(payload)
    rows = _parse_csv(payload, delimiter)
    if len(rows) < 2:
        raise ToolError("CSV needs a header row and at least one data row.")
    header, body = rows[0], rows[1:]
    columns = ", ".join(f"`{column.replace('`', '``')}`" for column in header)
    table_name = f"`{table.replace('`', '``')}`"

    def fmt(value: str) -> str:
        if value.strip() == "":
            return "NULL" if null_for_empty else "''"
        if re.fullmatch(r"-?\d+(\.\d+)?", value.strip()):
            return value.strip()
        return "'" + value.replace("'", "''") + "'"

    if multi:
        values = [f"  ({', '.join(fmt(row[index] if index < len(row) else '') for index in range(len(header)))})" for row in body]
        return ok(f"INSERT INTO {table_name} ({columns}) VALUES\n" + ",\n".join(values) + ";", title="SQL INSERT")
    lines = [
        f"INSERT INTO {table_name} ({columns}) VALUES ({', '.join(fmt(row[index] if index < len(row) else '') for index in range(len(header)))});"
        for row in body
    ]
    return ok("\n".join(lines), title="SQL INSERT")


_register(make_tool("sql-insert-generator", sql_insert_generator, title="SQL INSERT Generator", hint="table|empty_null|multi_row|CSV"))
