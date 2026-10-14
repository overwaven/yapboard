"""Passive message counter.

Implemented as an *outer middleware* so it observes every group message
(including commands) without ever replying or consuming updates.

Nothing about the message content is stored — only counters, never text.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Router
from aiogram.enums import ContentType
from aiogram.types import Message

from ..context import AppContext
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
        if await ctx.chats.get(chat.id) is None:
            await ctx.chats.ensure(chat.id, chat.title)
        if not await ctx.chats.is_collecting(chat.id):
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


def setup(router: Router, ctx: AppContext) -> None:
    middleware = ActivityMiddleware(ctx)
    router.message.outer_middleware(middleware)
