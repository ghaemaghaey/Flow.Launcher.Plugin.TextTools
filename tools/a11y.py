# -*- coding: utf-8 -*-
"""Accessibility tools."""

from __future__ import annotations

import re

from .common import ok, parse_float, split_pipe
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# ARIA reference
# --------------------------------------------------------------------------

_ARIA = [
    ("button", "role", "A clickable button."),
    ("link", "role", "A hyperlink."),
    ("checkbox", "role", "A checkable input."),
    ("radio", "role", "One option in a radio group."),
    ("switch", "role", "An on/off toggle."),
    ("tab", "role", "A tab in a tab list."),
    ("tablist", "role", "A list of tabs."),
    ("tabpanel", "role", "The panel for a tab."),
    ("dialog", "role", "A modal or non-modal dialog."),
    ("alertdialog", "role", "A dialog requiring a response."),
    ("alert", "role", "An important live message."),
    ("status", "role", "A status message."),
    ("menu", "role", "A menu of actions."),
    ("menuitem", "role", "An item in a menu."),
    ("navigation", "role", "A navigation landmark."),
    ("banner", "role", "The page header landmark."),
    ("main", "role", "The main content landmark."),
    ("contentinfo", "role", "The page footer landmark."),
    ("complementary", "role", "A supporting landmark (aside)."),
    ("search", "role", "A search landmark."),
    ("region", "role", "A named landmark region."),
    ("list / listitem", "role", "A list and its items."),
    ("table / row / cell", "role", "A table and its parts."),
    ("progressbar", "role", "A progress indicator."),
    ("tooltip", "role", "A tooltip."),
    ("aria-label", "state", "An accessible name."),
    ("aria-labelledby", "state", "References the element that labels this one."),
    ("aria-describedby", "state", "References a description."),
    ("aria-hidden", "state", "Hides the element from assistive tech."),
    ("aria-expanded", "state", "Whether a control is expanded."),
    ("aria-selected", "state", "Whether an item is selected."),
    ("aria-checked", "state", "Whether a checkbox/radio/switch is checked."),
    ("aria-disabled", "state", "Whether a control is disabled."),
    ("aria-current", "state", "The current item in a set."),
    ("aria-live", "state", "Live-region politeness (polite/assertive)."),
    ("aria-controls", "state", "References the element this control affects."),
    ("aria-haspopup", "state", "Whether the element opens a popup."),
    ("aria-required", "state", "Whether input is required."),
    ("aria-invalid", "state", "Whether the value is invalid."),
    ("role", "state", "The element's ARIA role."),
]


def aria_reference(item: Input) -> Output:
    query = item.text.strip().lower()
    rows = [
        f"{name:<28} {kind:<6} {description}"
        for name, kind, description in _ARIA
        if not query or query in name.lower() or query in description.lower() or query == kind
    ]
    if not rows:
        return ok("No matching ARIA entry.", title="ARIA Reference")
    return ok("\n".join(rows), title="ARIA Reference")


_register(make_tool("aria-reference", aria_reference, title="ARIA Reference", hint="query (optional)"))


# --------------------------------------------------------------------------
# Subtitle converter
# --------------------------------------------------------------------------

def srt_to_vtt(item: Input) -> Output:
    body = re.sub(r"\r+", "", item.require_text()).strip()
    body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", body)
    return ok("WEBVTT\n\n" + body + "\n", title="SRT → VTT")


def vtt_to_srt(item: Input) -> Output:
    text = re.sub(r"\r+", "", item.require_text())
    text = re.sub(r"^WEBVTT.*\n", "", text)
    text = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", text)
    blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
    output = []
    number = 1
    for block in blocks:
        lines = block.split("\n")
        if lines and "-->" not in lines[0] and len(lines) > 1 and "-->" in lines[1]:
            lines = lines[1:]
        if not any("-->" in line for line in lines):
            continue
        cleaned = [
            re.sub(r"\s+(align|line|position|size|vertical):\S+", "", line).strip() if "-->" in line else line
            for line in lines
        ]
        output.append(f"{number}\n" + "\n".join(cleaned))
        number += 1
    if not output:
        raise ToolError("No VTT cues found.")
    return ok("\n\n".join(output) + "\n", title="VTT → SRT")


_register(make_tool("subtitle-converter", srt_to_vtt, title="SRT → VTT", hint="clipboard SRT"))
_register(make_tool("subtitle-converter", vtt_to_srt, id="vtt-to-srt", title="VTT → SRT", hint="clipboard VTT"))


# --------------------------------------------------------------------------
# Touch target
# --------------------------------------------------------------------------

def touch_target(item: Input) -> Output:
    width_text, height_text = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    width = max(0, parse_float(width_text or "44"))
    height = max(0, parse_float(height_text or "44"))
    smallest = min(width, height)
    return ok(
        "\n".join(
            [
                f"Size: {width:g} × {height:g} px",
                f"Smallest side: {smallest:g} px",
                f"WCAG 2.5.8 AA (24×24): {'PASS' if smallest >= 24 else 'FAIL'}",
                f"WCAG 2.5.5 AAA (44×44): {'PASS' if smallest >= 44 else 'FAIL'}",
            ]
        ),
        title="Touch Target Size",
    )


_register(make_tool("touch-target", touch_target, title="Touch Target Size", hint="width|height"))
