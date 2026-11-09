# -*- coding: utf-8 -*-
"""Tool registry: collects every category module and builds the search index."""

from __future__ import annotations

from . import (
    a11y,
    api,
    code,
    color,
    crypto,
    data,
    datetime,
    diagram,
    encoding,
    file,
    finance,
    generators,
    geo,
    logs,
    media,
    network,
    reference,
    regex,
    seo,
    table,
    text,
    units,
    url,
    validators,
)
from .meta import META_BY_ID, normalize
from .model import Tool

_MODULES = [
    a11y, api, code, color, crypto, data, datetime, diagram, encoding, file,
    finance, generators, geo, logs, media, network, reference, regex, seo,
    table, text, units, url, validators,
]

# Tools that are browser/UI features and do not make sense in a launcher.
SKIPPED = {
    "screen-info",
    "feature-detector",
    "user-agent",
    "keycode-inspector",
    "websocket-tester",
    "cors-tester",
    "stopwatch",
    "countdown-timer",
}

ALL_TOOLS: list[Tool] = []
_seen: set[str] = set()
for module in _MODULES:
    for tool in module.TOOLS:
        if tool.id in _seen:
            continue
        _seen.add(tool.id)
        ALL_TOOLS.append(tool)

# Keep a stable, pleasant default order: category then English title.
ALL_TOOLS.sort(key=lambda tool: (tool.category, tool.title.lower()))

TOOL_BY_ID: dict[str, Tool] = {tool.id: tool for tool in ALL_TOOLS}


def missing_metadata_ids() -> list[str]:
    """Metadata ids that have no implemented tool (excluding skipped ones)."""
    covered = {tool.base_id or tool.id for tool in ALL_TOOLS}
    return sorted(
        tool_id
        for tool_id in META_BY_ID
        if tool_id not in covered and tool_id not in SKIPPED
    )


def extra_tool_ids() -> list[str]:
    """Implemented ids that are not in the metadata (synthetic variants / old tools)."""
    return sorted(tool_id for tool_id in TOOL_BY_ID if tool_id not in META_BY_ID)


def search(query: str, limit: int = 300) -> list[Tool]:
    from .meta import search_tools

    return search_tools(ALL_TOOLS, query, limit=limit)
