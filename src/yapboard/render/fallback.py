"""Plain-HTML fallback renderer.

Used when rich messages are disabled by config or rejected by the API (older
clients). Produces ``(text, InlineKeyboardMarkup | None)`` and matches the rich
view's information content as closely as a monospace block allows.
"""

from __future__ import annotations

import unicodedata
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .views import Keyboard, View

MAX_TEXT = 4096
PAGE_SEPARATOR = "──────────────────────"


def _width(text: str) -> int:
    total = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def _pad(text: str, width: int, align: str) -> str:
    padding = max(0, width - _width(text))
    if align == "right":
        return " " * padding + text
    if align == "center":
        left = padding // 2
        return " " * left + text + " " * (padding - left)
    return text + " " * padding


def render_table(view: View) -> str:
    assert view.table is not None
    table = view.table
    aligns = table.aligns or ["left"] * len(table.headers)
    all_rows = [table.headers, *table.rows]
    widths = [
        max(_width(str(row[i])) for row in all_rows)
        for i in range(len(table.headers))
    ]
    lines = []
    for row in all_rows:
        cells = [_pad(str(row[i]), widths[i], aligns[i]) for i in range(len(row))]
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)


def render_keyboard(keyboard: Keyboard) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for row in keyboard:
        if not row:
            continue
        buttons = []
        for button in row:
            if button.url:
                buttons.append(InlineKeyboardButton(text=button.text, url=button.url))
            else:
                buttons.append(
                    InlineKeyboardButton(
                        text=button.text,
                        callback_data=button.callback_data or "n",
                    )
                )
        rows.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def render(view: View) -> tuple[str, InlineKeyboardMarkup | None]:
    parts: list[str] = [f"<b>{escape(view.heading)}</b>"]

    for paragraph in view.paragraphs:
        parts.append(escape(paragraph))

    if view.table is not None and view.table.rows:
        parts.append(PAGE_SEPARATOR)
        parts.append("<pre>" + escape(render_table(view)) + "</pre>")
    elif view.empty_text:
        parts.append(escape(view.empty_text))

    if view.footer:
        parts.append(PAGE_SEPARATOR)
        parts.append(f"<i>{escape(view.footer)}</i>")

    text = "\n\n".join(parts)
    if len(text) > MAX_TEXT:
        text = text[: MAX_TEXT - 1] + "…"
    return text, render_keyboard(view.keyboard)
