"""Render a neutral :class:`~yapboard.render.views.View` into rich blocks.

The output is a fully typed :class:`aiogram.types.InputRichMessage` built from
``blocks`` (never from markdown/html strings), so there is nothing to escape
and the result is trivial to snapshot-test.
"""

from __future__ import annotations

from aiogram.types import (
    DisabledButton,
    InputRichBlockButtons,
    InputRichBlockFooter,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichMessageButton,
)

from .views import Button, Keyboard, View

HEADING_SIZE = 2
MAX_BUTTONS_PER_ROW = 8


def _button(button: Button) -> RichMessageButton:
    kwargs: dict[str, object] = {"text": button.text}
    if button.disabled:
        kwargs["disabled"] = DisabledButton()
    elif button.url:
        kwargs["url"] = button.url
    else:
        # Telegram requires exactly one action; a noop callback is the safest
        # default for otherwise inert buttons (e.g. the page indicator).
        kwargs["callback_data"] = button.callback_data or "n"
    if button.style:
        kwargs["style"] = button.style
    return RichMessageButton(**kwargs)  # type: ignore[arg-type]


def _cell(text: str, align: str, *, header: bool) -> RichBlockTableCell:
    return RichBlockTableCell(
        align=align,
        valign="middle",
        text=text,
        is_header=header or None,
    )


def _table_block(view: View) -> InputRichBlockTable:
    assert view.table is not None
    table = view.table
    aligns = table.aligns or ["left"] * len(table.headers)
    rows: list[list[RichBlockTableCell]] = [
        [_cell(head, aligns[i], header=True) for i, head in enumerate(table.headers)]
    ]
    for row in table.rows:
        rows.append([_cell(str(value), aligns[i], header=False) for i, value in enumerate(row)])
    return InputRichBlockTable(
        cells=rows,
        is_striped=True,
        is_bordered=False,
        is_compact=True,
    )


def _keyboard_blocks(keyboard: Keyboard) -> list[InputRichBlockButtons]:
    blocks: list[InputRichBlockButtons] = []
    for row in keyboard:
        if not row:
            continue
        buttons = [_button(button) for button in row[:MAX_BUTTONS_PER_ROW]]
        blocks.append(InputRichBlockButtons(buttons=buttons, align="center"))
    return blocks


def render(view: View) -> InputRichMessage:
    blocks: list[object] = [InputRichBlockSectionHeading(text=view.heading, size=HEADING_SIZE)]

    for paragraph in view.paragraphs:
        blocks.append(InputRichBlockParagraph(text=paragraph))

    if view.table is not None and view.table.rows:
        blocks.append(_table_block(view))
    elif view.empty_text:
        blocks.append(InputRichBlockParagraph(text=view.empty_text))

    if view.footer:
        blocks.append(InputRichBlockFooter(text=view.footer))

    blocks.extend(_keyboard_blocks(view.keyboard))

    return InputRichMessage(blocks=blocks)  # type: ignore[arg-type]
