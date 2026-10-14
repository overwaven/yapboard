"""``/hours`` — time-of-day activity board (uses the chat's timezone)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from .. import stats
from ..context import AppContext
from ..i18n import translate
from ..periods import DEFAULT_PERIOD
from ..periods import resolve as resolve_period
from ..render import hours_view
from .util import is_group, parse_top_args


def setup(router: Router, ctx: AppContext) -> None:
    @router.message(Command("hours"))
    async def on_hours(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        chat = await ctx.chats.get_or_create(message.chat.id, message.chat.title)
        args = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else ""
        period_code, _metric = parse_top_args(args, chat.tz)
        period = resolve_period(period_code or DEFAULT_PERIOD, chat.tz)

        histogram = await stats.hours_histogram(ctx.db, chat.chat_id, period, chat.tz)
        peak = stats.favourite_hour(histogram)
        await ctx.messenger.reply(
            message,
            hours_view(histogram=histogram, period_label=period.label, peak_hour=peak),
        )
