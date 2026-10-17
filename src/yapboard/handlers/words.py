"""``/words`` — most used meaningful words, in total and by member."""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import callbacks, wordstats
from ..context import AppContext
from ..i18n import translate
from ..messenger import EDIT_FAILED
from ..periods import resolve as resolve_period
from ..render import View, words_by_member_view, words_total_view
from ..state import ChatSettings
from .util import is_group, parse_top_args

log = logging.getLogger(__name__)

PER_MEMBER = 5


async def build_view(
    ctx: AppContext,
    chat: ChatSettings,
    period_code: str,
    mode: str,
    page: int,
    requester_id: int,
) -> View:
    period = resolve_period(period_code, chat.tz)
    updated_at = datetime.now(chat.zone)

    if mode == callbacks.WORDS_BY_MEMBER:
        member_result = await wordstats.words_by_member(
            ctx.db,
            chat.chat_id,
            period,
            chat.tz,
            max(0, page),
            ctx.page_size,
            per_member=PER_MEMBER,
        )
        return words_by_member_view(
            members=member_result.members,
            total_uses=member_result.total_uses,
            total_members=member_result.total_members,
            period_code=period.code,
            period_label=period.label,
            page=member_result.page,
            pages=member_result.pages,
            requester_id=requester_id,
            updated_at=updated_at,
            page_size=ctx.page_size,
            per_member=PER_MEMBER,
        )

    total_result = await wordstats.top_words(
        ctx.db, chat.chat_id, period, chat.tz, max(0, page), ctx.page_size
    )
    return words_total_view(
        entries=total_result.entries,
        total_uses=total_result.total_uses,
        unique_words=total_result.unique_words,
        active_users=total_result.active_users,
        period_code=period.code,
        period_label=period.label,
        page=total_result.page,
        pages=total_result.pages,
        requester_id=requester_id,
        updated_at=updated_at,
        page_size=ctx.page_size,
    )


def setup(router: Router, ctx: AppContext) -> None:
    @router.message(Command("words"))
    async def on_words(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        if not ctx.settings.word_stats_enabled:
            await message.reply(translate("words.disabled"))
            return
        if not ctx.cooldown.allow((message.chat.id, message.from_user.id)):
            seconds = int(ctx.cooldown.retry_after((message.chat.id, message.from_user.id)))
            await message.reply(translate("top.cooldown", seconds=max(1, seconds)))
            return

        chat = await ctx.chats.get_or_create(message.chat.id, message.chat.title)
        args = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else ""
        period_code, _metric = parse_top_args(args, chat.tz)
        view = await build_view(
            ctx, chat, period_code, callbacks.WORDS_TOTAL, 0, message.from_user.id
        )
        await ctx.messenger.reply(message, view)

    @router.callback_query(F.data.startswith("w:"))
    async def on_words_callback(callback: CallbackQuery) -> None:
        message = callback.message
        if message is None:
            await callback.answer()
            return
        data = callbacks.decode(callback.data)
        if data is None or data.kind != callbacks.WORDS or data.period is None:
            await callback.answer()
            return
        if not ctx.settings.word_stats_enabled:
            await callback.answer(translate("words.disabled"), show_alert=True)
            return

        chat = await ctx.chats.get_or_create(message.chat.id, getattr(message.chat, "title", None))
        if chat.only_requester and data.user_id != callback.from_user.id:
            await callback.answer("Only the person who opened this board can use it.", show_alert=False)
            return

        mode = data.mode if data.mode in callbacks.WORD_MODES else callbacks.WORDS_TOTAL
        try:
            view = await build_view(
                ctx,
                chat,
                data.period,
                mode,
                data.page,
                data.user_id or callback.from_user.id,
            )
        except Exception:  # noqa: BLE001
            log.exception("failed to build word board")
            await callback.answer(translate("error.generic"), show_alert=True)
            return

        cache_key = f"words:{mode}:{data.period}:{data.page}"
        outcome = await ctx.messenger.edit(
            message.chat.id, message.message_id, view, cache_key=cache_key
        )
        if outcome == EDIT_FAILED:
            await ctx.messenger.send(message.chat.id, view)
        await callback.answer()
