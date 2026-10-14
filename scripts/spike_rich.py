#!/usr/bin/env python
"""Milestone 0 spike: prove Rich Messages work in a real chat.

Sends a table with a button row, waits a couple of seconds, then edits the
message in place. Run it once in a throwaway test group before a release.

Usage::

    BOT_TOKEN=123:abc python scripts/spike_rich.py <chat_id>

The bot must be a member of the chat (privacy mode disabled / admin) to send.
"""

from __future__ import annotations

import asyncio
import os
import sys

from aiogram import Bot
from aiogram.types import (
    DisabledButton,
    InputRichBlockButtons,
    InputRichBlockFooter,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichMessageButton,
)


def cell(text: str, *, align: str = "left", header: bool = False) -> RichBlockTableCell:
    return RichBlockTableCell(align=align, valign="middle", text=text, is_header=header or None)


def board(nonce: str) -> InputRichMessage:
    table = InputRichBlockTable(
        cells=[
            [cell("#", align="right", header=True), cell("Member", header=True), cell("Msgs", align="right", header=True)],
            [cell("🥇", align="right"), cell("@alex"), cell("1 842", align="right")],
            [cell("🥈", align="right"), cell("@masha"), cell("977", align="right")],
            [cell("🥉", align="right"), cell("@dan"), cell("640", align="right")],
        ],
        is_striped=True,
        is_compact=True,
    )
    return InputRichMessage(
        blocks=[
            InputRichBlockSectionHeading(text=f"🏆 Spike · {nonce}", size=2),
            table,
            InputRichBlockFooter(text="5 912 messages · 38 active members"),
            InputRichBlockButtons(
                buttons=[
                    RichMessageButton(text="Today", callback_data="spike:today"),
                    RichMessageButton(text="7d", style="primary", callback_data="spike:7d"),
                    RichMessageButton(text="Next ›", disabled=DisabledButton()),
                ],
                align="center",
            ),
        ]
    )


async def main(chat_id: int) -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN is not set")
    bot = Bot(token)
    try:
        sent = await bot.send_rich_message(chat_id=chat_id, rich_message=board("first"))
        print(f"sent message_id={sent.message_id}")
        await asyncio.sleep(2)
        await bot.edit_message_text(
            chat_id=chat_id, message_id=sent.message_id, rich_message=board("edited in place")
        )
        print("edited in place — check the chat")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: BOT_TOKEN=... python scripts/spike_rich.py <chat_id>")
    asyncio.run(main(int(sys.argv[1])))
