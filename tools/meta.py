# -*- coding: utf-8 -*-
"""Tool metadata, Persian-aware normalisation and search."""

from __future__ import annotations

import json
import os
import re

from .model import Tool

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _load(name: str):
    with open(os.path.join(_ROOT, name), encoding="utf-8") as fh:
        return json.load(fh)


TOOLS_META: list[dict] = _load("tools_meta.json")
CATEGORIES: list[dict] = _load("categories_meta.json")

META_BY_ID: dict[str, dict] = {item["id"]: item for item in TOOLS_META}
CATEGORY_BY_ID: dict[str, dict] = {item["id"]: item for item in CATEGORIES}

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"

_TRANSLATE = str.maketrans(
    {
        "\u064a": "\u06cc",  # Arabic yeh -> Persian yeh
        "\u0649": "\u06cc",  # Alef maksura -> Persian yeh
        "\u0643": "\u06a9",  # Arabic kaf -> Persian kaf
        "\u0629": "\u0647",  # Teh marbuta -> heh
        "\u0623": "\u0627",
        "\u0625": "\u0627",
        "\u0622": "\u0627",
        **{ch: str(i) for i, ch in enumerate(_PERSIAN_DIGITS)},
        **{ch: str(i) for i, ch in enumerate(_ARABIC_DIGITS)},
    }
)

_DIACRITICS = re.compile(r"[\u064b-\u0652\u0670\u0640]")


def normalize(value: str) -> str:
    """Fold Persian/Arabic variants so a forgiving search works."""
    text = (value or "").lower()
    text = text.replace("\u200c", " ").replace("\u200d", " ").replace("\ufeff", "")
    text = text.translate(_TRANSLATE)
    text = _DIACRITICS.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_tool(
    base_id: str,
    run,
    *,
    id: str | None = None,
    title: str | None = None,
    keywords: list[str] | None = None,
    hint: str = "",
) -> Tool:
    meta = META_BY_ID.get(base_id)
    if meta is None:
        raise KeyError(f"unknown tool metadata id: {base_id}")
    extra_keywords = list(keywords or [])
    if title:
        extra_keywords.append(title)
    return Tool(
        id=id or base_id,
        title=title or meta.get("titleEn") or base_id,
        title_fa=meta.get("title") or "",
        description=meta.get("description") or "",
        category=meta.get("category") or "",
        keywords=list(meta.get("keywords") or []) + extra_keywords,
        run=run,
        hint=hint,
        base_id=base_id,
    )


def make_custom_tool(
    *,
    id: str,
    title: str,
    title_fa: str,
    description: str,
    category: str,
    keywords: list[str],
    run,
    hint: str = "",
) -> Tool:
    return Tool(
        id=id,
        title=title,
        title_fa=title_fa,
        description=description,
        category=category,
        keywords=keywords,
        run=run,
        hint=hint,
        base_id=id,
    )


def category_names(category_id: str) -> tuple[str, str]:
    cat = CATEGORY_BY_ID.get(category_id) or {}
    return cat.get("titleEn", ""), cat.get("title", "")


def score_tool(tool: Tool, terms: list[str]) -> int:
    title = normalize(f"{tool.title} {tool.title_fa}")
    haystack = normalize(tool.search_haystack())
    cat_en, cat_fa = category_names(tool.category)
    haystack += " " + normalize(f"{cat_en} {cat_fa}")
    score = 0
    for term in terms:
        if term not in haystack:
            return -1
        if title.startswith(term):
            score += 12
        elif term in title:
            score += 6
        else:
            score += 2
    return score


def search_tools(tools: list[Tool], query: str, limit: int = 60) -> list[Tool]:
    q = normalize(query)
    if not q:
        return tools
    terms = [term for term in q.split(" ") if term]
    scored: list[tuple[int, Tool]] = []
    for tool in tools:
        value = score_tool(tool, terms)
        if value >= 0:
            scored.append((value, tool))
    scored.sort(key=lambda pair: (-pair[0], pair[1].title.lower()))
    return [tool for _, tool in scored[:limit]]
