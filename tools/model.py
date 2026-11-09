# -*- coding: utf-8 -*-
"""Core data model for the Text Tools plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class ToolError(Exception):
    """A user-facing tool error."""


@dataclass
class Input:
    """Everything a tool can read from the clipboard."""

    text: str = ""
    files: list[str] = field(default_factory=list)
    image: Any = None

    def path_or_text(self) -> str:
        if self.files:
            return self.files[0]
        return self.text.strip()

    def require_text(self) -> str:
        if not self.text:
            raise ToolError("Clipboard is empty. Copy some text first.")
        return self.text


@dataclass
class Output:
    """What a tool returns. `text` is copied to the clipboard."""

    text: str = ""
    title: str = "Text Tools"
    message: str = ""
    open_path: str | None = None
    copy: bool = True
    error: bool = False


@dataclass
class Tool:
    id: str
    title: str
    title_fa: str
    description: str
    category: str
    keywords: list[str]
    run: Callable[[Input], Output]
    hint: str = ""
    base_id: str = ""

    def search_haystack(self) -> str:
        return " ".join(
            [self.id, self.title, self.title_fa, self.description, *self.keywords]
        )
