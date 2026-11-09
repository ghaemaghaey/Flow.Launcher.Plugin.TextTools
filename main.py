# -*- coding: utf-8 -*-
"""Text Tools for Flow Launcher.

Every tool reads the clipboard, transforms it and copies the result back.
Type `tt` to list/search tools, then press Enter to run the selected tool.
"""

import os
import re
import sys
import traceback

parent_folder_path = os.path.abspath(os.path.dirname(__file__))
sys.path.append(parent_folder_path)
sys.path.append(os.path.join(parent_folder_path, "lib"))
sys.path.append(os.path.join(parent_folder_path, "plugin"))

from flowlauncher import FlowLauncher

from tools.common import err, finish, read_clipboard, toast
from tools.model import Input, ToolError
from tools.registry import TOOL_BY_ID, search


def _extract_args(query: str, tool) -> str:
    """Return the part of the Flow query after the tool name.

    `tt uuid v7 1|1|0` -> `1|1|0`, `tt uuid v7 4` -> `4`.
    """
    if not query:
        return ""
    text = query.strip()
    for candidate in (tool.title, tool.id, tool.title_fa):
        if candidate and text.lower().startswith(candidate.lower()):
            return text[len(candidate):].strip()
    words = set()
    for value in (tool.title, tool.id):
        expanded = re.sub(r"([a-z])([A-Z])", r"\1 \2", value).lower()
        words.update(re.findall(r"[a-z0-9]+", expanded))
    tokens = text.split()
    return " ".join(token for token in tokens if token.lower() not in words).strip()


class TextTools(FlowLauncher):

    def query(self, query):
        tools = search(query or "")
        # Allow generator arguments in the query, e.g. `uuid v7 4` or
        # `uuid v7 1|1|0`: if the full query has no match, drop trailing
        # tokens until the tool is found.
        if not tools and query and query.strip():
            parts = query.split()
            while len(parts) > 1 and not tools:
                parts.pop()
                tools = search(" ".join(parts))
        results = []
        for tool in tools:
            # Keep the subtitle useful: when a tool has an input format, show
            # only that usage instead of repeating the (self-explanatory) name
            # and the long Persian description.
            if tool.hint:
                subtitle = f"in: {tool.hint}"
            else:
                subtitle = tool.description
            results.append(
                {
                    "Title": tool.title,
                    "SubTitle": subtitle,
                    "IcoPath": "Images/app.png",
                    "JsonRPCAction": {
                        "method": "run_tool",
                        "parameters": [tool.id, query or ""],
                    },
                }
            )
        return results

    def run_tool(self, tool_id, query=""):
        tool = TOOL_BY_ID.get(tool_id)
        if tool is None:
            toast("Text Tools", f"Unknown tool: {tool_id}")
            return
        try:
            args = _extract_args(query, tool)
            if args and (tool.category == "generators" or tool.id == "diceware"):
                item = Input(text=args)
            else:
                item = read_clipboard()
            output = tool.run(item)
            finish(output)
        except ToolError as exc:
            finish(err(str(exc), title=tool.title))
        except Exception:
            finish(err(f"{tool.title} failed:\n{traceback.format_exc(limit=3)}", title=tool.title))


if __name__ == "__main__":
    TextTools()
