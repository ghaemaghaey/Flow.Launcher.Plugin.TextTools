# -*- coding: utf-8 -*-
"""JSON, YAML, XML, HTML, CSV and config data tools."""

from __future__ import annotations

import csv
import html as html_lib
import io
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

from .common import json_text, ok, split_pipe, temp_path
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# JSON formatter / minifier
# --------------------------------------------------------------------------

def _sort_deep(value: Any) -> Any:
    if isinstance(value, list):
        return [_sort_deep(item) for item in value]
    if isinstance(value, dict):
        return {key: _sort_deep(value[key]) for key in sorted(value)}
    return value


def _json_format(indent: int | str, minify: bool = False, sort_keys: bool = False):
    def run(item: Input) -> Output:
        try:
            data = json.loads(item.require_text())
        except Exception as exc:
            raise ToolError(f"Invalid JSON: {exc}") from exc
        if sort_keys:
            data = _sort_deep(data)
        if minify:
            text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        else:
            text = json.dumps(data, ensure_ascii=False, indent=indent)
        return ok(text, title="JSON Formatter")

    return run


_register(make_tool("json-formatter", _json_format(2), title="JSON Formatter (2 spaces)", hint="clipboard JSON"))
_register(make_tool("json-formatter", _json_format(4), id="json-format-4", title="JSON Formatter (4 spaces)", hint="clipboard JSON"))
_register(make_tool("json-formatter", _json_format("\t"), id="json-format-tab", title="JSON Formatter (tabs)", hint="clipboard JSON"))
_register(make_tool("json-formatter", _json_format(2, minify=True), id="json-minify", title="JSON Minifier", hint="clipboard JSON"))
_register(make_tool("json-formatter", _json_format(2, sort_keys=True), id="json-sort", title="JSON Sort Keys", hint="clipboard JSON"))
_register(make_tool("json-formatter", _json_format(2, minify=True, sort_keys=True), id="json-sort-minify", title="JSON Sort + Minify", hint="clipboard JSON"))


# --------------------------------------------------------------------------
# YAML
# --------------------------------------------------------------------------

def json_to_yaml(item: Input) -> Output:
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise ToolError("PyYAML is required for YAML conversion.") from exc
    try:
        data = json.loads(item.require_text())
    except Exception as exc:
        raise ToolError(f"Invalid JSON: {exc}") from exc
    return ok(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120), title="JSON → YAML")


def yaml_to_json(item: Input) -> Output:
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise ToolError("PyYAML is required for YAML conversion.") from exc
    try:
        data = yaml.safe_load(item.require_text())
    except Exception as exc:
        raise ToolError(f"Invalid YAML: {exc}") from exc
    return ok(json_text(data), title="YAML → JSON")


_register(make_tool("json-yaml", json_to_yaml, title="JSON → YAML", hint="clipboard JSON"))
_register(make_tool("json-yaml", yaml_to_json, id="yaml-to-json", title="YAML → JSON", hint="clipboard YAML"))


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------

def _delimiter_and_payload(item: Input) -> tuple[str, str]:
    raw = item.require_text()
    if "|" in raw:
        head, tail = raw.split("|", 1)
        if head in {",", ";", "\t"}:
            return head, tail
    return ",", raw


def csv_to_json(item: Input) -> Output:
    delimiter, payload = _delimiter_and_payload(item)
    try:
        rows = list(csv.reader(io.StringIO(payload), delimiter=delimiter))
    except Exception as exc:
        raise ToolError(f"Invalid CSV: {exc}") from exc
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return ok("[]", title="CSV → JSON")
    header = rows[0]
    objects = [dict(zip(header, row + [""] * (len(header) - len(row)))) for row in rows[1:]]
    return ok(json_text(objects), title="CSV → JSON")


def json_to_csv(item: Input) -> Output:
    try:
        data = json.loads(item.require_text())
    except Exception as exc:
        raise ToolError(f"Invalid JSON: {exc}") from exc
    rows = data if isinstance(data, list) else [data]
    if not rows:
        return ok("", title="JSON → CSV")
    if not all(isinstance(row, dict) for row in rows):
        rows = [{"value": row} for row in rows]
    headers = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: (json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value) for key, value in row.items()})
    return ok(buffer.getvalue().rstrip("\r\n"), title="JSON → CSV")


_register(make_tool("csv-json", csv_to_json, title="CSV → JSON", hint="clipboard CSV (or ,|CSV)"))
_register(make_tool("csv-json", json_to_csv, id="json-to-csv", title="JSON → CSV", hint="clipboard JSON"))


# --------------------------------------------------------------------------
# XML
# --------------------------------------------------------------------------

def _element_to_json(element: ET.Element) -> Any:
    obj: dict[str, Any] = {}
    for key, value in element.attrib.items():
        obj[f"@{key}"] = value
    text = (element.text or "").strip()
    children = list(element)
    if not children:
        if not obj:
            return text
        if text:
            obj["#text"] = text
        return obj
    if text:
        obj["#text"] = text
    for child in children:
        value = _element_to_json(child)
        if child.tag in obj:
            previous = obj[child.tag]
            if isinstance(previous, list):
                previous.append(value)
            else:
                obj[child.tag] = [previous, value]
        else:
            obj[child.tag] = value
    return obj


def xml_to_json(item: Input) -> Output:
    try:
        root = ET.fromstring(item.require_text())
    except Exception as exc:
        raise ToolError(f"Invalid XML: {exc}") from exc
    return ok(json_text({root.tag: _element_to_json(root)}), title="XML → JSON")


def _escape_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(value: str) -> str:
    return _escape_text(value).replace('"', "&quot;")


def _build_xml(tag: str, value: Any, indent: str) -> str:
    if isinstance(value, list):
        return "\n".join(_build_xml(tag, item, indent) for item in value)
    if isinstance(value, dict):
        attributes = []
        children = []
        text = ""
        for key, child in value.items():
            if key.startswith("@"):
                attributes.append(f'{key[1:]}="{_escape_attr(str(child))}"')
            elif key == "#text":
                text = str(child)
            else:
                children.append(_build_xml(key, child, indent + "  "))
        attr_text = (" " + " ".join(attributes)) if attributes else ""
        if not children and not text:
            return f"{indent}<{tag}{attr_text}/>"
        if not children:
            return f"{indent}<{tag}{attr_text}>{_escape_text(text)}</{tag}>"
        return f"{indent}<{tag}{attr_text}>\n" + "\n".join(children) + f"\n{indent}</{tag}>"
    if value is None:
        return f"{indent}<{tag}/>"
    return f"{indent}<{tag}>{_escape_text(str(value))}</{tag}>"


def json_to_xml(item: Input) -> Output:
    try:
        data = json.loads(item.require_text())
    except Exception as exc:
        raise ToolError(f"Invalid JSON: {exc}") from exc
    keys = list(data) if isinstance(data, dict) else []
    root = keys[0] if len(keys) == 1 else "root"
    body = data[root] if len(keys) == 1 else data
    return ok(_build_xml(root, body, ""), title="JSON → XML")


_register(make_tool("xml-json", xml_to_json, title="XML → JSON", hint="clipboard XML"))
_register(make_tool("xml-json", json_to_xml, id="json-to-xml", title="JSON → XML", hint="clipboard JSON"))


def xml_format(item: Input) -> Output:
    raw = item.require_text()
    try:
        root = ET.fromstring(raw)
    except Exception as exc:
        raise ToolError(f"Invalid XML: {exc}") from exc
    try:
        ET.indent(root, space="  ")
        return ok(ET.tostring(root, encoding="unicode"), title="XML Formatter")
    except Exception:
        normalized = re.sub(r">\s*<", "><", raw).replace("><", ">\n<")
        depth = 0
        lines = []
        for line in normalized.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("</"):
                depth = max(0, depth - 1)
            lines.append("  " * depth + line)
            if re.match(r"^<[^/!?]", line) and not line.endswith("/>") and not re.search(r"</[^>]+>$", line):
                depth += 1
        return ok("\n".join(lines), title="XML Formatter")


def xml_minify(item: Input) -> Output:
    raw = item.require_text()
    try:
        ET.fromstring(raw)
    except Exception as exc:
        raise ToolError(f"Invalid XML: {exc}") from exc
    return ok(re.sub(r">\s+<", "><", raw).strip(), title="XML Minifier")


_register(make_tool("xml-formatter", xml_format, title="XML Formatter", hint="clipboard XML"))
_register(make_tool("xml-formatter", xml_minify, id="xml-minify", title="XML Minifier", hint="clipboard XML"))


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_RAW_TAGS = {"pre", "textarea", "script", "style"}


def html_format(item: Input) -> Output:
    text = item.require_text()
    tokens = re.findall(r"<[^>]+>|[^<]+", text)
    depth = 0
    raw_depth = 0
    output = []
    for token in tokens:
        if not token.startswith("<"):
            value = re.sub(r"\s+", " ", token).strip()
            if value:
                output.append("  " * depth + value)
            continue
        is_comment = token.startswith("<!--")
        is_decl = token.startswith("<!") or token.startswith("<?")
        is_close = token.startswith("</")
        match = re.match(r"^</?\s*([a-zA-Z0-9-]+)", token)
        name = match.group(1).lower() if match else ""
        self_close = token.rstrip().endswith("/>") or name in _VOID_TAGS or is_comment or is_decl
        if raw_depth > 0:
            if is_close and name in _RAW_TAGS:
                raw_depth -= 1
                depth = max(0, depth - 1)
                output.append("  " * depth + token)
            else:
                output.append(token)
            continue
        if is_close:
            depth = max(0, depth - 1)
            output.append("  " * depth + token)
        else:
            output.append("  " * depth + token)
            if not self_close:
                depth += 1
                if name in _RAW_TAGS:
                    raw_depth += 1
    return ok("\n".join(output), title="HTML Formatter")


def html_minify(item: Input) -> Output:
    text = re.sub(r">\s+<", "><", item.require_text())
    text = re.sub(r"\s{2,}", " ", text).strip()
    return ok(text, title="HTML Minifier")


_register(make_tool("html-formatter", html_format, title="HTML Formatter", hint="clipboard HTML"))
_register(make_tool("html-formatter", html_minify, id="html-minify", title="HTML Minifier", hint="clipboard HTML"))


# --------------------------------------------------------------------------
# JSON diff / flatten / path / TypeScript
# --------------------------------------------------------------------------

def _json_diff(a: Any, b: Any, path: str, out: list[str]) -> None:
    if a == b:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            child = f"{path}.{key}" if path else key
            if key not in a:
                out.append(f"+ {child} = {json.dumps(b[key], ensure_ascii=False)}")
            elif key not in b:
                out.append(f"- {child} = {json.dumps(a[key], ensure_ascii=False)}")
            else:
                _json_diff(a[key], b[key], child, out)
        return
    if isinstance(a, list) and isinstance(b, list):
        for index in range(max(len(a), len(b))):
            child = f"{path}[{index}]"
            if index >= len(a):
                out.append(f"+ {child} = {json.dumps(b[index], ensure_ascii=False)}")
            elif index >= len(b):
                out.append(f"- {child} = {json.dumps(a[index], ensure_ascii=False)}")
            else:
                _json_diff(a[index], b[index], child, out)
        return
    out.append(
        f"~ {path or '$'}: {json.dumps(a, ensure_ascii=False)} → {json.dumps(b, ensure_ascii=False)}"
    )


def json_diff(item: Input) -> Output:
    left, right = split_pipe(item.require_text(), 2, from_right=False, strip=False)
    try:
        a = json.loads(left)
        b = json.loads(right)
    except Exception as exc:
        raise ToolError(f"Invalid JSON: {exc}") from exc
    changes: list[str] = []
    _json_diff(a, b, "", changes)
    if not changes:
        return ok("No differences.", title="JSON Diff")
    return ok("\n".join(changes), title="JSON Diff", message=f"{len(changes)} change(s)")


_register(make_tool("json-diff", json_diff, title="JSON Diff", hint="left JSON|right JSON"))


def _flatten(value: Any, prefix: str, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        if not value and prefix:
            out[prefix] = {}
        for key, child in value.items():
            _flatten(child, f"{prefix}.{key}" if prefix else key, out)
    elif isinstance(value, list):
        if not value and prefix:
            out[prefix] = []
        for index, child in enumerate(value):
            _flatten(child, f"{prefix}[{index}]", out)
    else:
        out[prefix] = value


def _parse_key(key: str) -> list[Any]:
    segments: list[Any] = []
    for part in key.split("."):
        for match in re.finditer(r"[^.[\]]+|\[(\d+)\]", part):
            segments.append(int(match.group(1)) if match.group(1) is not None else match.group(0))
    return segments


def _unflatten(flat: dict[str, Any]) -> Any:
    root: dict[Any, Any] = {}
    for key, value in flat.items():
        segments = _parse_key(key)
        current: Any = root
        for index, segment in enumerate(segments):
            last = index == len(segments) - 1
            next_is_index = (not last) and isinstance(segments[index + 1], int)
            if isinstance(current, list):
                position = int(segment)
                while len(current) <= position:
                    current.append(None)
                if last:
                    current[position] = value
                else:
                    if current[position] is None:
                        current[position] = [] if next_is_index else {}
                    current = current[position]
            else:
                if last:
                    current[segment] = value
                else:
                    if segment not in current:
                        current[segment] = [] if next_is_index else {}
                    current = current[segment]
    return root


def json_flatten(item: Input) -> Output:
    try:
        data = json.loads(item.require_text())
    except Exception as exc:
        raise ToolError(f"Invalid JSON: {exc}") from exc
    flat: dict[str, Any] = {}
    _flatten(data, "", flat)
    return ok(json_text(flat), title="JSON Flatten")


def json_unflatten(item: Input) -> Output:
    try:
        data = json.loads(item.require_text())
    except Exception as exc:
        raise ToolError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ToolError("Unflatten expects a JSON object.")
    return ok(json_text(_unflatten(data)), title="JSON Unflatten")


_register(make_tool("json-flatten", json_flatten, title="JSON Flatten", hint="clipboard JSON"))
_register(make_tool("json-flatten", json_unflatten, id="json-unflatten", title="JSON Unflatten", hint="clipboard JSON"))


def _parse_json_path(path: str) -> list[tuple[str, Any]]:
    path = path.strip()
    if not path:
        raise ToolError("JSONPath is empty.")
    if path[0] != "$":
        raise ToolError("JSONPath must start with $.")
    steps: list[tuple[str, Any]] = []
    index = 1
    while index < len(path):
        char = path[index]
        if char == ".":
            index += 1
            if index < len(path) and path[index] == "*":
                steps.append(("wildcard", None))
                index += 1
                continue
            key = ""
            while index < len(path) and path[index] not in ".[]":
                key += path[index]
                index += 1
            if not key:
                raise ToolError("Empty key in JSONPath.")
            steps.append(("key", key))
        elif char == "[":
            end = path.find("]", index)
            if end == -1:
                raise ToolError("Missing ] in JSONPath.")
            inner = path[index + 1 : end].strip()
            if inner == "*":
                steps.append(("wildcard", None))
            elif re.fullmatch(r"-?\d+", inner):
                steps.append(("index", int(inner)))
            elif re.fullmatch(r"[\"'].*[\"']", inner):
                steps.append(("key", inner[1:-1]))
            else:
                raise ToolError(f"Invalid bracket expression: {inner}")
            index = end + 1
        else:
            raise ToolError(f"Unexpected character in JSONPath: {char!r}")
    return steps


def _eval_json_path(root: Any, steps: list[tuple[str, Any]]) -> list[Any]:
    current = [root]
    for kind, value in steps:
        next_values: list[Any] = []
        for node in current:
            if node is None:
                continue
            if kind == "key":
                if isinstance(node, dict) and value in node:
                    next_values.append(node[value])
            elif kind == "index":
                if isinstance(node, list):
                    index = value if value >= 0 else len(node) + value
                    if 0 <= index < len(node):
                        next_values.append(node[index])
            else:
                if isinstance(node, list):
                    next_values.extend(node)
                elif isinstance(node, dict):
                    next_values.extend(node.values())
        current = next_values
    return current


def json_path(item: Input) -> Output:
    path, payload = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not path.strip():
        path = "$"
        payload = item.require_text()
    try:
        data = json.loads(payload)
    except Exception as exc:
        raise ToolError(f"Invalid JSON: {exc}") from exc
    matches = _eval_json_path(data, _parse_json_path(path))
    return ok(json_text(matches), title="JSONPath", message=f"{len(matches)} match(es)")


_register(make_tool("json-path", json_path, title="JSONPath Evaluator", hint="path|json"))


def _pascal(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", " ", name).strip()
    if not value:
        return "Item"
    return "".join(word[:1].upper() + word[1:] for word in value.split(" "))


def _singular(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("ses"):
        return name[:-2]
    if name.endswith("s"):
        return name[:-1]
    return name + "Item"


def _ts_type(value: Any, name: str, interfaces: dict[str, str]) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        if not value:
            return "unknown[]"
        element_name = _singular(name)
        parts = {_ts_type(item, element_name, interfaces) for item in value}
        union = " | ".join(sorted(parts))
        return f"({union})[]" if len(parts) > 1 else f"{union}[]"
    if isinstance(value, dict):
        type_name = _pascal(name)
        lines = []
        for key, child in value.items():
            optional = child is None
            safe = key if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", key) else json.dumps(key)
            lines.append(f"  {safe}{'?' if optional else ''}: {_ts_type(child, key, interfaces)};")
        body = "\n".join(lines) or "  [key: string]: unknown;"
        final = type_name
        counter = 2
        while final in interfaces and interfaces[final] != body:
            final = f"{type_name}{counter}"
            counter += 1
        interfaces[final] = body
        return final
    return {"str": "string", "int": "number", "float": "number", "bool": "boolean"}.get(type(value).__name__, "any")


def json_to_typescript(item: Input) -> Output:
    root_name, payload = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not payload.strip():
        root_name, payload = "Root", item.require_text()
    try:
        data = json.loads(payload)
    except Exception as exc:
        raise ToolError(f"Invalid JSON: {exc}") from exc
    interfaces: dict[str, str] = {}
    root = _pascal(root_name or "Root")
    root_type = _ts_type(data, root, interfaces)
    blocks = [f"export interface {name} {{\n{body}\n}}" for name, body in reversed(list(interfaces.items()))]
    if root not in interfaces:
        blocks.insert(0, f"export type {root} = {root_type};")
    return ok("\n\n".join(blocks), title="JSON → TypeScript")


_register(make_tool("json-to-typescript", json_to_typescript, title="JSON → TypeScript", hint="root|json"))


# --------------------------------------------------------------------------
# Markdown / NDJSON / config / CSS / SVG
# --------------------------------------------------------------------------

def markdown_to_html(item: Input) -> Output:
    try:
        import markdown  # type: ignore
    except Exception as exc:
        raise ToolError("The 'markdown' package is required.") from exc
    return ok(
        markdown.markdown(item.require_text(), extensions=["extra", "fenced_code", "tables"]),
        title="Markdown → HTML",
    )


def html_to_markdown(item: Input) -> Output:
    try:
        from markdownify import markdownify  # type: ignore
    except Exception as exc:
        raise ToolError("The 'markdownify' package is required.") from exc
    return ok(markdownify(item.require_text(), heading_style="ATX"), title="HTML → Markdown")


_register(make_tool("markdown-html", markdown_to_html, title="Markdown → HTML", hint="clipboard Markdown"))
_register(make_tool("markdown-html", html_to_markdown, id="html-to-markdown", title="HTML → Markdown", hint="clipboard HTML"))


def markdown_preview(item: Input) -> Output:
    try:
        import markdown  # type: ignore
    except Exception as exc:
        raise ToolError("The 'markdown' package is required.") from exc
    body = markdown.markdown(item.require_text(), extensions=["extra", "fenced_code", "tables"])
    page = f"""<!doctype html>
<html lang="fa" dir="auto"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Markdown Preview</title>
<style>
body{{font-family:Segoe UI,Tahoma,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;line-height:1.7;color:#1f2933;background:#fff}}
pre{{background:#f4f6f8;padding:1rem;overflow:auto;border-radius:8px}}code{{background:#eef1f4;padding:.1em .3em;border-radius:4px}}
table{{border-collapse:collapse}}td,th{{border:1px solid #d5dbe1;padding:.4rem .6rem}}blockquote{{border-left:4px solid #2dd4c0;margin:0;padding-left:1rem;color:#52606d}}
img{{max-width:100%}}
</style></head><body>{body}</body></html>"""
    path = temp_path("html", "markdown-preview")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return Output(title="Markdown Preview", open_path=path, message="Preview opened in your browser", copy=False)


_register(make_tool("markdown-preview", markdown_preview, title="Markdown Preview", hint="clipboard Markdown"))


def ndjson_to_json(item: Input) -> Output:
    rows = []
    bad = []
    for index, line in enumerate(item.require_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            bad.append(str(index))
    text = json_text(rows)
    if bad:
        text += f"\n\nSkipped invalid lines: {', '.join(bad)}"
    return ok(text, title="NDJSON → JSON")


def json_to_ndjson(item: Input) -> Output:
    try:
        data = json.loads(item.require_text())
    except Exception as exc:
        raise ToolError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ToolError("Expected a JSON array.")
    return ok("\n".join(json.dumps(row, ensure_ascii=False) for row in data), title="JSON → NDJSON")


_register(make_tool("ndjson", ndjson_to_json, title="NDJSON → JSON", hint="clipboard NDJSON"))
_register(make_tool("ndjson", json_to_ndjson, id="json-to-ndjson", title="JSON → NDJSON", hint="clipboard JSON array"))


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_ini(text: str) -> dict:
    root: dict[str, Any] = {}
    section = root
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        match = re.fullmatch(r"\[(.+)\]", line)
        if match:
            section = {}
            root[match.group(1).strip()] = section
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        section[key.strip()] = _unquote(value)
    return root


def _parse_env(text: str) -> dict:
    result = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = _unquote(value)
    return result


def _parse_properties(text: str) -> dict:
    result = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        match = re.match(r"^([^=:]+)[=:](.*)$", line)
        if match:
            result[match.group(1).strip()] = match.group(2).strip()
    return result


def _config_parser(fmt: str):
    def run(item: Input) -> Output:
        parser = {"ini": _parse_ini, "env": _parse_env, "properties": _parse_properties}[fmt]
        return ok(json_text(parser(item.require_text())), title=f"Parse {fmt.upper()}")

    return run


_register(make_tool("config-parser", _config_parser("ini"), title="Parse INI", hint="clipboard INI"))
_register(make_tool("config-parser", _config_parser("env"), id="parse-env", title="Parse .env", hint="clipboard .env"))
_register(make_tool("config-parser", _config_parser("properties"), id="parse-properties", title="Parse .properties", hint="clipboard properties"))


def css_selector_tester(item: Input) -> Output:
    selector, payload = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not selector.strip():
        selector, payload = "body", item.require_text()
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception as exc:
        raise ToolError("The 'beautifulsoup4' package is required.") from exc
    try:
        soup = BeautifulSoup(payload, "html.parser")
        matches = soup.select(selector)
    except Exception as exc:
        raise ToolError(f"Invalid selector or HTML: {exc}") from exc
    if not matches:
        return ok("No matches.", title="CSS Selector")
    return ok(
        f"{len(matches)} match(es):\n\n" + "\n\n".join(str(match) for match in matches),
        title="CSS Selector",
    )


_register(make_tool("css-selector-tester", css_selector_tester, title="CSS Selector Tester", hint="selector|html"))


def svg_optimizer(item: Input) -> Output:
    svg = item.require_text()
    optimized = re.sub(r"<\?xml[\s\S]*?\?>", "", svg, flags=re.IGNORECASE)
    optimized = re.sub(r"<!DOCTYPE[\s\S]*?>", "", optimized, flags=re.IGNORECASE)
    optimized = re.sub(r"<!--[\s\S]*?-->", "", optimized)
    optimized = re.sub(r"<metadata[\s\S]*?</metadata>", "", optimized, flags=re.IGNORECASE)
    optimized = re.sub(r"<\?[\s\S]*?\?>", "", optimized)
    optimized = re.sub(r">\s+<", "><", optimized)
    optimized = re.sub(r"\s{2,}", " ", optimized)
    optimized = re.sub(r"\s+/>", "/>", optimized).strip()
    before = len(svg.encode("utf-8"))
    after = len(optimized.encode("utf-8"))
    saved = round((1 - after / before) * 100) if before else 0
    return ok(optimized, title="SVG Optimizer", message=f"{before} → {after} bytes ({saved}% saved)")


_register(make_tool("svg-optimizer", svg_optimizer, title="SVG Optimizer", hint="clipboard SVG"))
