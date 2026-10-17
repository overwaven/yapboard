"""Passive message counter.

Implemented as an *outer middleware* so it observes every group message
(including commands) without ever replying or consuming updates.

Activity counters are always stored. When word stats are enabled, normalized
word frequencies are stored too — never message text, word order or a link to
the original message.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Router
from aiogram.enums import ContentType
from aiogram.types import Message

from ..context import AppContext
from ..words import WordNormalizer
from .util import GROUP_TYPES

log = logging.getLogger(__name__)

MEDIA_TYPES = frozenset(
    {
        ContentType.PHOTO,
        ContentType.VIDEO,
        ContentType.VOICE,
        ContentType.VIDEO_NOTE,
        ContentType.STICKER,
        ContentType.ANIMATION,
        ContentType.DOCUMENT,
        ContentType.AUDIO,
    }
)


class ActivityMiddleware(BaseMiddleware):
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self.words = WordNormalizer()

    async def __call__(  # type: ignore[override]
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        try:
            await self.record(event)
        except Exception:  # noqa: BLE001 - counting must never break updates
            log.exception("activity counting failed")
        return await handler(event, data)

    async def record(self, message: Message) -> None:
        chat = message.chat
        if chat.type not in GROUP_TYPES:
            return
        user = message.from_user
        if user is None or user.is_bot:
            return
        if message.sender_chat is not None:  # anonymous admin / linked channel
            return
        if message.is_automatic_forward:
            return

        ctx = self.ctx
        chat_settings = await ctx.chats.get(chat.id)
        if chat_settings is None:
            chat_settings = await ctx.chats.ensure(chat.id, chat.title)
        if not chat_settings.collecting:
            return
        if await ctx.optouts.is_opted_out(chat.id, user.id):
            return

        text = message.text or message.caption or ""
        content = message.content_type
        media = 1 if content in MEDIA_TYPES else 0
        replies = 1 if message.reply_to_message is not None else 0

        ctx.collector.add(
            chat.id,
            user.id,
            message.date,
            username=user.username,
            first_name=user.first_name,
            msgs=1,
            chars=len(text),
            media=media,
            replies=replies,
        )

        if ctx.settings.word_stats_enabled and text and not text.lstrip().startswith("/"):
            words = self.words.extract(text)
            if words:
                day = message.date.astimezone(chat_settings.zone).date()
                ctx.collector.add_words(chat.id, user.id, day, words)


def setup(router: Router, ctx: AppContext) -> None:
    middleware = ActivityMiddleware(ctx)
    router.message.outer_middleware(middleware)
