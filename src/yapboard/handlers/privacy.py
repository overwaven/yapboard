"""Privacy controls: ``/optout``, ``/optin``, ``/forgetme``, ``/pause``, ``/resume``."""

from __future__ import annotations

import contextlib
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import callbacks
from ..context import AppContext
from ..i18n import translate
from ..render import forget_confirm_view
from ..state import wipe_user
from .util import is_group

log = logging.getLogger(__name__)


async def _delete_quietly(message: Message) -> None:
    with contextlib.suppress(Exception):
        await message.delete()


def setup(router: Router, ctx: AppContext) -> None:
    @router.message(Command("optout"))
    async def on_optout(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        await ctx.chats.get_or_create(message.chat.id, message.chat.title)
        await ctx.optouts.set(message.chat.id, message.from_user.id, True)
        await message.reply(translate("privacy.optout.done"))

    @router.message(Command("optin"))
    async def on_optin(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        await ctx.chats.get_or_create(message.chat.id, message.chat.title)
        await ctx.optouts.set(message.chat.id, message.from_user.id, False)
        await message.reply(translate("privacy.optin.done"))

    @router.message(Command("forgetme"))
    async def on_forgetme(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        await ctx.chats.get_or_create(message.chat.id, message.chat.title)
        await ctx.messenger.reply(message, forget_confirm_view(requester_id=message.from_user.id))

    @router.callback_query(F.data.startswith("f:"))
    async def on_forget_callback(callback: CallbackQuery) -> None:
        data = callbacks.decode(callback.data)
        if data is None or data.kind != callbacks.FORGET or data.user_id is None:
            await callback.answer()
            return
        if data.user_id != callback.from_user.id:
            await callback.answer("Only you can confirm this.", show_alert=False)
            return

        message = callback.message
        if message is None or not isinstance(message, Message):
            await callback.answer()
            return
        chat_id = message.chat.id
        await _delete_quietly(message)

        if data.value == "yes":
            rows = await wipe_user(ctx.db, chat_id, callback.from_user.id)
            text = translate("privacy.forget.done", rows=rows)
        else:
            text = translate("privacy.forget.cancelled")

        await callback.answer(text, show_alert=True)
        await message.answer(text)

    @router.message(Command("pause"))
    async def on_pause(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        if not await ctx.admins.is_admin(message.chat.id, message.from_user.id):
            await message.reply(translate("admin.denied"))
            return
        await ctx.chats.get_or_create(message.chat.id, message.chat.title)
        await ctx.chats.set_collecting(message.chat.id, False)
        await message.reply(translate("admin.paused"))

    @router.message(Command("resume"))
    async def on_resume(message: Message) -> None:
        if not is_group(message) or message.from_user is None:
            await message.reply(translate("not.group"))
            return
        if not await ctx.admins.is_admin(message.chat.id, message.from_user.id):
            await message.reply(translate("admin.denied"))
            return
        await ctx.chats.get_or_create(message.chat.id, message.chat.title)
        await ctx.chats.set_collecting(message.chat.id, True)
        await message.reply(translate("admin.resumed"))
