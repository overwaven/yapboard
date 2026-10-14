"""``/stats`` — chat summary with an hour heatmap."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from .. import stats
from ..context import AppContext
from ..i18n import translate
from ..periods import resolve as resolve_period
from ..render import stats_view
from .util import is_group, parse_top_args


def setup(router: Router, ctx: AppContext) -> None:
    @router.message(Command("stats"))
    async def on_stats(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        chat = await ctx.chats.get_or_create(message.chat.id, message.chat.title)
        args = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else ""
        period_code, _metric = parse_top_args(args, chat.tz)
        period = resolve_period(period_code, chat.tz)

        summary = await stats.chat_summary(ctx.db, chat.chat_id, period, chat.tz)
        await ctx.messenger.reply(
            message,
            stats_view(
                total_messages=summary.total_messages,
                active_users=summary.active_users,
                busiest_day=summary.busiest_day,
                busiest_hour=summary.busiest_hour,
                histogram=summary.histogram,
                period_label=period.label,
            ),
        )
