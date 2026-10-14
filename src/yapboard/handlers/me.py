"""``/me`` — the personal activity card."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from .. import stats
from ..context import AppContext
from ..i18n import translate
from ..periods import ALL, period_buttons
from ..periods import resolve as resolve_period
from ..render import MeStat, me_view
from .util import is_group

SPARK_DAYS = 14


def setup(router: Router, ctx: AppContext) -> None:
    @router.message(Command("me"))
    async def on_me(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return

        user = message.from_user
        chat = await ctx.chats.get_or_create(message.chat.id, message.chat.title)

        rows: list[MeStat] = []
        for code, label in period_buttons():
            period = resolve_period(code, chat.tz)
            stat = await stats.user_period_stat(ctx.db, chat.chat_id, user.id, period, "m")
            rows.append(
                MeStat(
                    label=label,
                    messages=stat.value,
                    rank=stat.rank,
                    total_users=stat.total_users,
                )
            )

        all_period = resolve_period(ALL, chat.tz)
        histogram = await stats.hours_histogram(ctx.db, chat.chat_id, all_period, chat.tz)
        favourite = stats.favourite_hour(histogram)

        series = await stats.daily_series(
            ctx.db, chat.chat_id, all_period, chat.tz, user_id=user.id, days=SPARK_DAYS
        )
        spark_values = [value for _, value in series]

        view = me_view(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            stats=rows,
            favourite_hour=favourite,
            spark_values=spark_values,
            requester_id=user.id,
            spark_days=SPARK_DAYS,
        )
        await ctx.messenger.reply(message, view)
