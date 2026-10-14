"""``/start``, ``/help`` and bot membership events."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import ChatMemberUpdated, Message

from ..context import AppContext
from ..i18n import translate
from ..render import help_view
from .util import is_group

log = logging.getLogger(__name__)

_ACTIVE_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.RESTRICTED,
}
_INACTIVE_STATUSES = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


def setup(router: Router, ctx: AppContext) -> None:
    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        admin = is_group(message) and message.from_user is not None and await ctx.admins.is_admin(
            message.chat.id, message.from_user.id
        )
        await ctx.messenger.reply(message, help_view(is_admin=admin))

    @router.message(Command("help"))
    async def on_help(message: Message) -> None:
        admin = is_group(message) and message.from_user is not None and await ctx.admins.is_admin(
            message.chat.id, message.from_user.id
        )
        await ctx.messenger.reply(message, help_view(is_admin=admin))

    @router.my_chat_member()
    async def on_member_update(update: ChatMemberUpdated) -> None:
        new_status = update.new_chat_member.status
        old_status = update.old_chat_member.status
        if update.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        if new_status in _ACTIVE_STATUSES and old_status in _INACTIVE_STATUSES:
            await ctx.chats.ensure(update.chat.id, update.chat.title)
            try:
                await ctx.messenger.send(update.chat.id, help_view(is_admin=False))
            except Exception:  # noqa: BLE001 - joining may lack send rights
                log.warning("could not send welcome to chat %s", update.chat.id, exc_info=True)
        elif new_status in _INACTIVE_STATUSES:
            log.info("bot removed from chat %s", update.chat.id)

    @router.message(F.chat.type == ChatType.PRIVATE, ~F.text.startswith("/"))
    async def on_private(message: Message) -> None:
        # Any non-command private message gets a gentle pointer to /help.
        await message.reply(translate("not.group"))
