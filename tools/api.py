# -*- coding: utf-8 -*-
"""API and HTTP request helper tools."""

from __future__ import annotations

import base64
import json
import re

from .common import ok, split_pipe
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# Authorization header
# --------------------------------------------------------------------------

def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def auth_basic(item: Input) -> Output:
    user, password = split_pipe(item.require_text(), 2, from_right=False, strip=False)
    return ok(f"Authorization: Basic {_b64(f'{user}:{password}')}", title="Basic Auth Header")


def auth_bearer(item: Input) -> Output:
    return ok("Authorization: Bearer " + item.require_text().strip(), title="Bearer Auth Header")


def _b64url_decode(value: str) -> str:
    value = value.replace("-", "+").replace("_", "/")
    value += "=" * (-len(value) % 4)
    return base64.b64decode(value).decode("utf-8", "replace")


def auth_parse(item: Input) -> Output:
    raw = re.sub(r"^\s*Authorization:\s*", "", item.require_text(), flags=re.IGNORECASE).strip()
    match = re.match(r"^(\w+)\s+([\s\S]*)$", raw)
    if not match:
        raise ToolError("Expected <scheme> <credentials>.")
    scheme = match.group(1).lower()
    credentials = match.group(2).strip()
    if scheme == "basic":
        try:
            decoded = base64.b64decode(credentials + "=" * (-len(credentials) % 4)).decode("utf-8", "replace")
        except Exception as exc:
            raise ToolError(f"Invalid Basic credentials: {exc}") from exc
        if ":" not in decoded:
            raise ToolError("Decoded Basic credentials have no colon.")
        user, password = decoded.split(":", 1)
        return ok(f"Username: {user}\nPassword: {password}", title="Parse Authorization")
    if scheme == "bearer":
        parts = credentials.split(".")
        if len(parts) >= 2:
            try:
                header = json.dumps(json.loads(_b64url_decode(parts[0])), ensure_ascii=False, indent=2)
                payload = json.dumps(json.loads(_b64url_decode(parts[1])), ensure_ascii=False, indent=2)
            except Exception as exc:
                raise ToolError(f"Could not decode JWT: {exc}") from exc
            return ok(f"Bearer JWT\n\nHeader:\n{header}\n\nPayload:\n{payload}", title="Parse Authorization")
        return ok(f"Bearer token:\n{credentials}", title="Parse Authorization")
    return ok(f"{match.group(1)} token:\n{credentials}", title="Parse Authorization")


_register(make_tool("auth-header", auth_basic, title="Basic Auth Header", hint="username|password"))
_register(make_tool("auth-header", auth_bearer, id="auth-header-bearer", title="Bearer Auth Header", hint="token"))
_register(make_tool("auth-header", auth_parse, id="auth-header-parse", title="Parse Authorization Header", hint="Authorization header"))


# --------------------------------------------------------------------------
# Cache-Control
# --------------------------------------------------------------------------

_CACHE_DESCRIPTIONS = {
    "no-cache": "Cache may store the response but must revalidate before reuse.",
    "no-store": "Do not store the response anywhere.",
    "public": "Response may be stored by any cache, including CDNs.",
    "private": "Response is for a single user and must not be stored by shared caches.",
    "must-revalidate": "Stale responses must not be used without revalidation.",
    "proxy-revalidate": "Like must-revalidate for shared caches.",
    "immutable": "The response will not change while fresh.",
    "no-transform": "Intermediaries must not transform the response.",
}


def _describe_directive(token: str) -> str:
    name, _, value = token.partition("=")
    name = name.strip().lower()
    if name == "max-age":
        return f"Fresh for {value or '?'} seconds."
    if name == "s-maxage":
        return f"Shared cache fresh for {value or '?'} seconds."
    if name == "stale-while-revalidate":
        return f"May serve stale for {value or '?'} seconds while revalidating."
    if name == "max-stale":
        return f"Client accepts stale responses up to {value or '?'} seconds."
    if name == "min-fresh":
        return f"Client wants a response fresh for at least {value or '?'} seconds."
    return _CACHE_DESCRIPTIONS.get(name, "Unknown directive.")


def cache_control_parse(item: Input) -> Output:
    raw = re.sub(r"^\s*Cache-Control:\s*", "", item.require_text(), flags=re.IGNORECASE).strip()
    directives = [part.strip() for part in raw.split(",") if part.strip()]
    if not directives:
        raise ToolError("No Cache-Control directives found.")
    return ok(
        "\n".join(f"{directive} - {_describe_directive(directive)}" for directive in directives),
        title="Cache-Control Parser",
    )


def cache_control_build(item: Input) -> Output:
    max_age, s_maxage, flags = split_pipe(item.require_text(), 3, from_right=False, strip=True)
    directives = []
    for flag in [part.strip() for part in flags.split(",") if part.strip()]:
        directives.append(flag)
    if max_age.isdigit():
        directives.append(f"max-age={max_age}")
    if s_maxage.isdigit():
        directives.append(f"s-maxage={s_maxage}")
    if not directives:
        raise ToolError("Use max_age|s_maxage|flags in the clipboard.")
    return ok("Cache-Control: " + ", ".join(directives), title="Cache-Control Builder")


_register(make_tool("cache-control", cache_control_parse, title="Cache-Control Parser", hint="Cache-Control header"))
_register(make_tool("cache-control", cache_control_build, id="cache-control-build", title="Cache-Control Builder", hint="max_age|s_maxage|flags"))


# --------------------------------------------------------------------------
# cURL builder / converter
# --------------------------------------------------------------------------

def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def curl_builder(item: Input) -> Output:
    parts = item.require_text().rsplit("|", 3)
    if len(parts) == 1:
        method, url, headers_text, body = "GET", parts[0], "", ""
    elif len(parts) == 2:
        method, url, headers_text, body = parts[0], parts[1], "", ""
    elif len(parts) == 3:
        method, url, headers_text, body = parts[0], parts[1], parts[2], ""
    else:
        method, url, headers_text, body = parts
    method = (method or "GET").strip().upper()
    url = url.strip()
    if not url:
        raise ToolError("A URL is required.")
    pieces = ["curl"]
    if method != "GET":
        pieces.append(f"-X {method}")
    pieces.append(_shell_quote(url))
    for header in headers_text.split(";"):
        header = header.strip()
        if not header:
            continue
        if ":" not in header:
            raise ToolError(f"Invalid header: {header}")
        pieces.append(f"-H {_shell_quote(header)}")
    if body.strip():
        pieces.append(f"-d {_shell_quote(body)}")
    return ok(" \\\n  ".join(pieces), title="cURL Builder")


_register(make_tool("curl-builder", curl_builder, title="cURL Builder", hint="method|url|headers|body"))


def _tokenize_curl(command: str) -> list[str]:
    text = re.sub(r"\\\r?\n", " ", command)
    tokens = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        token = ""
        while index < len(text) and not text[index].isspace():
            char = text[index]
            if char == "'":
                index += 1
                while index < len(text) and text[index] != "'":
                    token += text[index]
                    index += 1
                index += 1
            elif char == '"':
                index += 1
                while index < len(text) and text[index] != '"':
                    if text[index] == "\\" and index + 1 < len(text):
                        token += text[index + 1]
                        index += 2
                    else:
                        token += text[index]
                        index += 1
                index += 1
            else:
                token += char
                index += 1
        tokens.append(token)
    return tokens


def _parse_curl(command: str) -> dict:
    tokens = _tokenize_curl(command.strip())
    if not tokens or tokens[0] != "curl":
        raise ToolError("Not a curl command.")
    parsed = {"method": "", "url": "", "headers": [], "body": "", "auth": None}
    index = 1
    while index < len(tokens):
        token = tokens[index]

        def next_value():
            nonlocal index
            index += 1
            return tokens[index] if index < len(tokens) else ""

        if token in {"-X", "--request"}:
            parsed["method"] = next_value().upper()
        elif token in {"-H", "--header"}:
            header = next_value()
            if ":" in header:
                key, value = header.split(":", 1)
                parsed["headers"].append((key.strip(), value.strip()))
        elif token in {"-d", "--data", "--data-raw", "--data-binary"}:
            parsed["body"] += ("&" if parsed["body"] else "") + next_value()
        elif token in {"-u", "--user"}:
            value = next_value()
            user, _, password = value.partition(":")
            parsed["auth"] = (user, password)
        elif token == "--url":
            parsed["url"] = next_value()
        elif not token.startswith("-") and not parsed["url"]:
            parsed["url"] = token
        index += 1
    if not parsed["url"]:
        raise ToolError("No URL found in the curl command.")
    if not parsed["method"]:
        parsed["method"] = "POST" if parsed["body"] else "GET"
    return parsed


def curl_to_code(item: Input) -> Output:
    parsed = _parse_curl(item.require_text())
    headers = [
        f"    {json.dumps(key)}: {json.dumps(value)}," for key, value in parsed["headers"]
    ]
    if parsed["auth"]:
        headers.append(
            f'    "Authorization": "Basic " + btoa({json.dumps(parsed["auth"][0] + ":" + parsed["auth"][1])}),'
        )
    fetch_lines = [f"const res = await fetch({json.dumps(parsed['url'])}, {{"]
    fetch_lines.append(f"  method: {json.dumps(parsed['method'])},")
    if headers:
        fetch_lines.extend(["  headers: {", *headers, "  },"])
    if parsed["body"]:
        fetch_lines.append(f"  body: {json.dumps(parsed['body'])},")
    fetch_lines.extend(["});", "const data = await res.json();"])
    fetch_code = "\n".join(fetch_lines)

    axios_lines = [
        "const res = await axios({",
        f"  method: {json.dumps(parsed['method'].lower())},",
        f"  url: {json.dumps(parsed['url'])},",
    ]
    if parsed["headers"]:
        axios_lines.append("  headers: {")
        axios_lines.extend(f"    {json.dumps(key)}: {json.dumps(value)}," for key, value in parsed["headers"])
        axios_lines.append("  },")
    if parsed["auth"]:
        axios_lines.append(
            f"  auth: {{ username: {json.dumps(parsed['auth'][0])}, password: {json.dumps(parsed['auth'][1])} }},"
        )
    if parsed["body"]:
        axios_lines.append(f"  data: {json.dumps(parsed['body'])},")
    axios_lines.append("});")
    axios_code = "\n".join(axios_lines)
    return ok(f"fetch():\n{fetch_code}\n\naxios:\n{axios_code}", title="cURL → Code")


_register(make_tool("curl-to-code", curl_to_code, title="cURL → Code", hint="clipboard curl command"))
