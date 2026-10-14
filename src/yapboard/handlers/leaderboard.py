"""``/top`` — the leaderboard, plus its period/metric/pager callbacks."""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import callbacks, stats
from ..context import AppContext
from ..i18n import translate
from ..messenger import EDIT_FAILED
from ..periods import (
    DEFAULT_METRIC,
    is_valid_metric,
)
from ..periods import (
    resolve as resolve_period,
)
from ..render import View, leaderboard_view
from ..state import ChatSettings
from .util import is_group, parse_top_args

log = logging.getLogger(__name__)


async def build_view(
    ctx: AppContext,
    chat: ChatSettings,
    period_code: str,
    metric: str,
    page: int,
    requester_id: int,
) -> View:
    period = resolve_period(period_code, chat.tz)
    result = await stats.top(
        ctx.db, chat.chat_id, period, metric, max(0, page), ctx.page_size
    )
    return leaderboard_view(
        entries=result.entries,
        total_activity=result.total_activity,
        active_users=result.active_users,
        period_code=period.code,
        period_label=period.label,
        metric=metric,
        page=result.page,
        pages=result.pages,
        requester_id=requester_id,
        updated_at=datetime.now(chat.zone),
        page_size=ctx.page_size,
    )


def setup(router: Router, ctx: AppContext) -> None:
    @router.message(Command("top"))
    async def on_top(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        if not ctx.cooldown.allow((message.chat.id, message.from_user.id)):
            seconds = int(ctx.cooldown.retry_after((message.chat.id, message.from_user.id)))
            await message.reply(translate("top.cooldown", seconds=max(1, seconds)))
            return

        chat = await ctx.chats.get_or_create(message.chat.id, message.chat.title)
        args = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else ""
        period_code, metric = parse_top_args(args, chat.tz)
        if not is_valid_metric(metric):
            metric = DEFAULT_METRIC
        view = await build_view(ctx, chat, period_code, metric, 0, message.from_user.id)
        await ctx.messenger.reply(message, view)

    @router.callback_query(F.data.startswith("t:"))
    async def on_top_callback(callback: CallbackQuery) -> None:
        message = callback.message
        if message is None:
            await callback.answer()
            return
        data = callbacks.decode(callback.data)
        if data is None or data.period is None or data.metric is None:
            await callback.answer()
            return

        chat = await ctx.chats.get_or_create(message.chat.id, getattr(message.chat, "title", None))
        if chat.only_requester and data.user_id != callback.from_user.id:
            await callback.answer("Only the person who opened this board can use it.", show_alert=False)
            return

        metric = data.metric if is_valid_metric(data.metric) else DEFAULT_METRIC
        try:
            view = await build_view(ctx, chat, data.period, metric, data.page, data.user_id or callback.from_user.id)
        except Exception:  # noqa: BLE001
            log.exception("failed to build leaderboard")
            await callback.answer(translate("error.generic"), show_alert=True)
            return

        cache_key = f"{data.period}:{metric}:{data.page}"
        outcome = await ctx.messenger.edit(
            message.chat.id, message.message_id, view, cache_key=cache_key
        )
        if outcome == EDIT_FAILED:
            await ctx.messenger.send(message.chat.id, view)
        await callback.answer()
