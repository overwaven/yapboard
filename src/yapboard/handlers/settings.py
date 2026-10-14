"""``/settings`` — admin panel (timezone, pause, requester-only)."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import callbacks
from ..context import AppContext
from ..i18n import translate
from ..render import settings_view
from ..state import ChatSettings
from .util import is_group

log = logging.getLogger(__name__)


def _view(chat: ChatSettings, requester_id: int):
    return settings_view(
        chat_title=chat.title or str(chat.chat_id),
        tz=chat.tz,
        collecting=chat.collecting,
        only_requester=chat.only_requester,
        requester_id=requester_id,
    )


def _parse_tz(args: str) -> str | None:
    stripped = args.strip()
    if not stripped:
        return None
    parts = stripped.split(maxsplit=1)
    if parts[0].lower() != "tz" or len(parts) < 2:
        return None
    return parts[1].strip()


def setup(router: Router, ctx: AppContext) -> None:
    @router.message(Command("settings"))
    async def on_settings(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        if not await ctx.admins.is_admin(message.chat.id, message.from_user.id):
            await message.reply(translate("admin.denied"))
            return
        chat = await ctx.chats.get_or_create(message.chat.id, message.chat.title)

        args = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else ""
        tz_value = _parse_tz(args)
        if tz_value is not None:
            try:
                ZoneInfo(tz_value)
            except (ZoneInfoNotFoundError, ValueError):
                await message.reply(translate("admin.tz_invalid", tz=tz_value))
                return
            chat = await ctx.chats.set_tz(message.chat.id, tz_value)
            await message.reply(translate("admin.tz_set", tz=tz_value))

        await ctx.messenger.reply(message, _view(chat, message.from_user.id))

    @router.callback_query(F.data.startswith("s:"))
    async def on_setting_callback(callback: CallbackQuery) -> None:
        data = callbacks.decode(callback.data)
        message = callback.message
        if data is None or data.kind != callbacks.SETTING or message is None:
            await callback.answer()
            return
        if not await ctx.admins.is_admin(message.chat.id, callback.from_user.id):
            await callback.answer(translate("admin.denied"), show_alert=True)
            return
        if data.field not in callbacks.FIELDS:
            await callback.answer()
            return

        chat = await ctx.chats.get_or_create(message.chat.id, getattr(message.chat, "title", None))
        truthy = data.truthy_value
        if data.field == callbacks.FIELD_COLLECTING:
            chat = await ctx.chats.set_collecting(chat.chat_id, truthy)
        else:
            chat = await ctx.chats.set_only_requester(chat.chat_id, truthy)

        view = _view(chat, data.user_id or callback.from_user.id)
        await ctx.messenger.edit(
            message.chat.id,
            message.message_id,
            view,
            cache_key=f"set:{data.field}:{truthy}",
            force=True,
        )
        await callback.answer()
