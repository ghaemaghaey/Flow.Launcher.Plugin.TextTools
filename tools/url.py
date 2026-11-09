# -*- coding: utf-8 -*-
"""URL, query string and link tools."""

from __future__ import annotations

import posixpath
import re
import unicodedata
import urllib.parse

from .common import ok, split_pipe
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# Cookies
# --------------------------------------------------------------------------

_ATTR_DESCRIPTIONS = {
    "Domain": "Which domain receives the cookie.",
    "Path": "URL path the cookie applies to.",
    "Expires": "Expiry date/time.",
    "Max-Age": "Lifetime in seconds.",
    "Secure": "Sent only over HTTPS.",
    "HttpOnly": "Not accessible to JavaScript.",
    "SameSite": "Cross-site sending policy (Lax/Strict/None).",
    "Priority": "Cookie priority hint.",
    "Partitioned": "Partitioned storage (CHIPS).",
}


def _norm_attr(value: str) -> str:
    mapping = {
        "domain": "Domain", "path": "Path", "expires": "Expires",
        "max-age": "Max-Age", "secure": "Secure", "httponly": "HttpOnly",
        "samesite": "SameSite", "priority": "Priority", "partitioned": "Partitioned",
    }
    return mapping.get(value.strip().lower(), value.strip())


def cookie_parse_set(item: Input) -> Output:
    lines = [line.strip() for line in item.require_text().splitlines() if line.strip()]
    blocks = []
    for line in lines:
        line = re.sub(r"^set-cookie:\s*", "", line, flags=re.IGNORECASE).strip()
        parts = [part.strip() for part in line.split(";") if part.strip()]
        if not parts or "=" not in parts[0]:
            continue
        name, value = parts[0].split("=", 1)
        block = [f"{name.strip()} = {value.strip()}"]
        for attribute in parts[1:]:
            key, _, val = attribute.partition("=")
            key = _norm_attr(key)
            description = _ATTR_DESCRIPTIONS.get(key, "")
            block.append(f"  {key}: {val.strip() or '-'}{('  (' + description + ')') if description else ''}")
        blocks.append("\n".join(block))
    if not blocks:
        raise ToolError("No Set-Cookie lines found.")
    return ok("\n\n".join(blocks), title="Set-Cookie Parser")


def cookie_parse_header(item: Input) -> Output:
    raw = item.require_text().strip()
    raw = raw.replace("Cookie:", "").replace("cookie:", "").strip()
    pairs = [part.strip() for part in raw.split(";") if part.strip()]
    lines = []
    for pair in pairs:
        if "=" in pair:
            key, value = pair.split("=", 1)
            lines.append(f"{key.strip()} = {value.strip()}")
    if not lines:
        raise ToolError("No name=value cookie pairs found.")
    return ok("\n".join(lines), title="Cookie Parser")


_register(make_tool("cookie-parser", cookie_parse_set, title="Set-Cookie Parser", hint="Set-Cookie lines"))
_register(make_tool("cookie-parser", cookie_parse_header, id="cookie-parse-header", title="Cookie Header Parser", hint="Cookie header"))


# --------------------------------------------------------------------------
# Link generator
# --------------------------------------------------------------------------

def link_mailto(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 5, from_right=False, strip=True)
    to, cc, bcc, subject, body = parts
    params = []
    for key, value in [("cc", cc), ("bcc", bcc), ("subject", subject), ("body", body)]:
        if value:
            params.append(f"{key}={urllib.parse.quote(value)}")
    if not to and not params:
        raise ToolError("Use to|cc|bcc|subject|body in the clipboard.")
    return ok(f"mailto:{to}" + (("?" + "&".join(params)) if params else ""), title="mailto Link")


def link_tel(item: Input) -> Output:
    number = item.require_text().strip().replace(" ", "")
    return ok(f"tel:{number}", title="tel Link")


def link_sms(item: Input) -> Output:
    number, body = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    number = number.replace(" ", "")
    return ok(f"sms:{number}" + (("?body=" + urllib.parse.quote(body)) if body else ""), title="sms Link")


def link_geo(item: Input) -> Output:
    lat, lon, zoom = split_pipe(item.require_text(), 3, from_right=False, strip=True)
    return ok(f"geo:{lat or '0'},{lon or '0'}" + (("?z=" + zoom) if zoom else ""), title="geo Link")


_register(make_tool("link-generator", link_mailto, title="mailto Link Generator", hint="to|cc|bcc|subject|body"))
_register(make_tool("link-generator", link_tel, id="link-tel", title="tel Link Generator", hint="phone number"))
_register(make_tool("link-generator", link_sms, id="link-sms", title="sms Link Generator", hint="number|body"))
_register(make_tool("link-generator", link_geo, id="link-geo", title="geo Link Generator", hint="lat|lon|zoom"))


# --------------------------------------------------------------------------
# Query string
# --------------------------------------------------------------------------

def _parse_query(text: str) -> tuple[str, list[tuple[str, str]]]:
    value = text.strip()
    if not value:
        return "", []
    if "#" in value:
        value = value.split("#", 1)[0]
    base = ""
    if "?" in value:
        base, value = value.split("?", 1)
    elif value.startswith("/") or urllib.parse.urlparse(value).scheme:
        base, value = value, ""
    pairs = urllib.parse.parse_qsl(value, keep_blank_values=True)
    return base, pairs


def query_string(item: Input) -> Output:
    base, pairs = _parse_query(item.require_text())
    if not pairs and not base:
        raise ToolError("No query string found.")
    sorted_pairs = sorted(pairs, key=lambda pair: pair[0])
    lines = []
    if base:
        lines.append(f"Base: {base}")
    lines.append("Parameters:")
    lines.extend(f"  {key} = {value}" for key, value in sorted_pairs)
    built = urllib.parse.urlencode(sorted_pairs)
    lines.append("")
    lines.append("Rebuilt: " + ((base + "?" + built) if base else built))
    return ok("\n".join(lines), title="Query String")


_register(make_tool("query-string", query_string, title="Query String Parser", hint="URL or query string"))


# --------------------------------------------------------------------------
# URL normalizer
# --------------------------------------------------------------------------

_DEFAULT_PORTS = {"http": 80, "https": 443, "ftp": 21, "ws": 80, "wss": 443}


def url_normalizer(item: Input) -> Output:
    raw = item.require_text().strip()
    parsed = urllib.parse.urlsplit(raw)
    if not parsed.scheme:
        raise ToolError("URL must include a scheme (e.g. https://).")
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    if port and _DEFAULT_PORTS.get(scheme) == port:
        port = None
    netloc = hostname
    if port:
        netloc += f":{port}"
    path = posixpath.normpath(parsed.path or "/")
    if parsed.path.endswith("/") and path != "/":
        path += "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    pairs = sorted(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True), key=lambda pair: pair[0])
    query = urllib.parse.urlencode(pairs)
    normalized = urllib.parse.urlunsplit((scheme, netloc, path, query, parsed.fragment))
    return ok(normalized, title="URL Normalizer")


_register(make_tool("url-normalizer", url_normalizer, title="URL Normalizer", hint="clipboard URL"))


# --------------------------------------------------------------------------
# URL parser / slug
# --------------------------------------------------------------------------

def url_parser(item: Input) -> Output:
    raw = item.require_text().strip()
    parsed = urllib.parse.urlsplit(raw)
    if not parsed.scheme:
        raise ToolError("URL must include a scheme (e.g. https://).")
    port = parsed.port or "-"
    origin = f"{parsed.scheme}://{parsed.netloc}"
    params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    lines = [
        f"Protocol: {parsed.scheme}",
        f"Host: {parsed.netloc}",
        f"Hostname: {parsed.hostname or '-'}",
        f"Port: {port}",
        f"Pathname: {parsed.path or '/'}",
        f"Hash: {parsed.fragment or '-'}",
        f"Origin: {origin}",
        "",
        f"Query parameters ({len(params)}):",
    ]
    lines.extend(f"  {key} = {value}" for key, value in params)
    return ok("\n".join(lines), title="URL Parser")


def slug(item: Input) -> Output:
    text = unicodedata.normalize("NFKC", item.require_text()).strip().lower()
    text = re.sub(r"[\s\-_]+", " ", text)
    text = re.sub(r"[^a-z0-9\u0600-\u06ff ]", "", text)
    return ok(text.strip().replace(" ", "-"), title="Slug Generator")


_register(make_tool("url-parser", url_parser, title="URL Parser", hint="clipboard URL"))
_register(make_tool("slug", slug, title="Slug Generator", hint="clipboard text"))


# --------------------------------------------------------------------------
# UTM
# --------------------------------------------------------------------------

_UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]


def utm_build(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 6, from_right=False, strip=True)
    base, *values = parts
    if not base:
        raise ToolError("Use base_url|source|medium|campaign|term|content in the clipboard.")
    parsed = urllib.parse.urlsplit(base)
    pairs = [(key, value) for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if key not in _UTM_KEYS]
    pairs.extend((key, value) for key, value in zip(_UTM_KEYS, values) if value)
    query = urllib.parse.urlencode(pairs)
    return ok(urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)), title="UTM Builder")


def utm_parse(item: Input) -> Output:
    parsed = urllib.parse.urlsplit(item.require_text().strip())
    values = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    lines = [f"{key}: {values.get(key, '-')}" for key in _UTM_KEYS]
    return ok("\n".join(lines), title="UTM Parser")


_register(make_tool("utm-builder", utm_build, title="UTM Builder", hint="base_url|source|medium|campaign|term|content"))
_register(make_tool("utm-builder", utm_parse, id="utm-parse", title="UTM Parser", hint="clipboard URL"))
