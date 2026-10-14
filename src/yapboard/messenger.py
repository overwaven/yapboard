"""Send/edit a :class:`View` as a rich message, falling back to HTML text.

Rich Messages are a young Bot API feature: older clients and some chat types
may reject them. The messenger therefore tries the rich path first (when
enabled) and transparently retries with the HTML fallback, remembering chats
where rich messages failed so it does not retry on every update.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from .render import render_fallback, render_rich
from .render.views import View

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import Message

log = logging.getLogger(__name__)

# Outcomes of :meth:`Messenger.edit`.
EDIT_EDITED = "edited"
EDIT_UNCHANGED = "unchanged"
EDIT_FAILED = "failed"


class Messenger:
    def __init__(
        self,
        bot: Bot,
        *,
        rich_enabled: bool = True,
        cache_ttl: float = 10.0,
        cache_max: int = 4096,
    ) -> None:
        self.bot = bot
        self.rich_enabled = rich_enabled
        self.cache_ttl = cache_ttl
        self.cache_max = cache_max
        self._rich_failed: set[int] = set()
        self._cache: dict[tuple[int, int], tuple[str, float]] = {}

    # -- capability ----------------------------------------------------------
    def rich_available(self) -> bool:
        return self.rich_enabled and hasattr(self.bot, "send_rich_message")

    def use_rich(self, chat_id: int) -> bool:
        return self.rich_available() and chat_id not in self._rich_failed

    def disable_rich_for(self, chat_id: int, error: Exception) -> None:
        if chat_id not in self._rich_failed:
            log.warning("rich messages rejected in chat %s (%s); using fallback", chat_id, error)
        self._rich_failed.add(chat_id)

    def forget(self, chat_id: int) -> None:
        self._rich_failed.discard(chat_id)

    # -- cache ---------------------------------------------------------------
    def _is_fresh(self, chat_id: int, message_id: int, cache_key: str) -> bool:
        cached = self._cache.get((chat_id, message_id))
        if cached is None:
            return False
        key, stamp = cached
        return key == cache_key and (time.monotonic() - stamp) < self.cache_ttl

    def _remember(self, chat_id: int, message_id: int, cache_key: str) -> None:
        self._cache[(chat_id, message_id)] = (cache_key, time.monotonic())
        if len(self._cache) > self.cache_max:
            self._evict()

    def _evict(self) -> None:
        now = time.monotonic()
        for key in [k for k, (_, stamp) in self._cache.items() if now - stamp >= self.cache_ttl]:
            self._cache.pop(key, None)
        while len(self._cache) > self.cache_max:
            self._cache.pop(next(iter(self._cache)))

    def invalidate(self, chat_id: int, message_id: int) -> None:
        self._cache.pop((chat_id, message_id), None)

    # -- sending -------------------------------------------------------------
    async def send(
        self,
        chat_id: int,
        view: View,
        *,
        message_thread_id: int | None = None,
    ) -> Message | None:
        if self.use_rich(chat_id):
            try:
                return await self.bot.send_rich_message(
                    chat_id=chat_id,
                    rich_message=render_rich(view),
                    message_thread_id=message_thread_id,
                )
            except TelegramAPIError as error:
                self.disable_rich_for(chat_id, error)

        text, markup = render_fallback(view)
        return await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
            message_thread_id=message_thread_id,
        )

    async def reply(self, message: Message, view: View) -> Message | None:
        return await self.send(
            message.chat.id,
            view,
            message_thread_id=message.message_thread_id if message.is_topic_message else None,
        )

    # -- editing -------------------------------------------------------------
    async def edit(
        self,
        chat_id: int,
        message_id: int,
        view: View,
        *,
        cache_key: str | None = None,
        force: bool = False,
    ) -> str:
        """Edit in place; returns one of :data:`EDIT_EDITED`, ``UNCHANGED``, ``FAILED``."""
        if not force and cache_key and self._is_fresh(chat_id, message_id, cache_key):
            return EDIT_UNCHANGED

        if self.use_rich(chat_id):
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    rich_message=render_rich(view),
                )
                if cache_key:
                    self._remember(chat_id, message_id, cache_key)
                return EDIT_EDITED
            except TelegramBadRequest as error:
                if _is_not_modified(error):
                    if cache_key:
                        self._remember(chat_id, message_id, cache_key)
                    return EDIT_UNCHANGED
                if _rich_unsupported(error):
                    self.disable_rich_for(chat_id, error)
                else:
                    log.warning("rich edit failed in chat %s: %s", chat_id, error)
            except TelegramAPIError as error:
                self.disable_rich_for(chat_id, error)

        text, markup = render_fallback(view)
        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
            )
        except TelegramBadRequest as error:
            if _is_not_modified(error):
                if cache_key:
                    self._remember(chat_id, message_id, cache_key)
                return EDIT_UNCHANGED
            log.warning("fallback edit failed in chat %s: %s", chat_id, error)
            return EDIT_FAILED
        except TelegramAPIError as error:
            log.warning("fallback edit failed in chat %s: %s", chat_id, error)
            return EDIT_FAILED
        if cache_key:
            self._remember(chat_id, message_id, cache_key)
        return EDIT_EDITED


def _is_not_modified(error: TelegramBadRequest) -> bool:
    return "not modified" in str(error).lower()


def _rich_unsupported(error: TelegramBadRequest) -> bool:
    text = str(error).lower()
    markers = (
        "rich",
        "unknown method",
        "method not found",
        "not implemented",
        "unsupported",
        "can't parse",
    )
    return any(marker in text for marker in markers)
