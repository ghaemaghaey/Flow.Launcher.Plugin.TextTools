# -*- coding: utf-8 -*-
"""Diagram / tree tools."""

from __future__ import annotations

import re

from .common import ok
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


def _indent_level(raw: str, spaces: int) -> int:
    leading = re.match(r"^[\t ]*", raw).group(0)
    if "\t" in leading:
        return leading.count("\t")
    return len(leading) // spaces


def _build_tree(lines: list[str], spaces: int):
    root = {"name": "", "depth": -1, "children": []}
    stack = [root]
    for line in lines:
        if not line.strip():
            continue
        depth = _indent_level(line, spaces)
        node = {"name": line.strip(), "depth": depth, "children": []}
        while len(stack) > 1 and stack[-1]["depth"] >= depth:
            stack.pop()
        stack[-1]["children"].append(node)
        stack.append(node)
    return root["children"]


def _render(nodes, prefix: str) -> str:
    output = []
    for index, node in enumerate(nodes):
        last = index == len(nodes) - 1
        output.append(f"{prefix}{'└── ' if last else '├── '}{node['name']}")
        if node["children"]:
            output.append(_render(node["children"], prefix + ("    " if last else "│   ")))
    return "\n".join(output)


def _tree(spaces: int):
    def run(item: Input) -> Output:
        lines = item.require_text().replace("\r", "").split("\n")
        tree = _build_tree(lines, spaces)
        if not tree:
            raise ToolError("No tree lines found.")
        blocks = []
        for node in tree:
            blocks.append(node["name"])
            if node["children"]:
                blocks.append(_render(node["children"], ""))
        return ok("\n".join(blocks), title="Folder Tree")

    return run


_register(make_tool("tree-generator", _tree(2), title="Folder Tree (2 spaces)", hint="indented lines"))
_register(make_tool("tree-generator", _tree(4), id="tree-4", title="Folder Tree (4 spaces)", hint="indented lines"))
_register(make_tool("tree-generator", _tree(1), id="tree-tab", title="Folder Tree (tabs)", hint="indented lines"))
