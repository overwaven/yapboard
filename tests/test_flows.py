"""End-to-end flow tests: updates go through the real aiogram Dispatcher.

The bot session is faked, so no network is involved — but the router,
middleware, handlers, stats queries and both renderers all run for real.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendMessage,
    SendRichMessage,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, ChatMemberMember, Message, Update, User

from yapboard import callbacks
from yapboard.collector import Collector
from yapboard.config import Settings
from yapboard.context import AppContext
from yapboard.handlers import build_router
from yapboard.messenger import Messenger
from yapboard.state import AdminCache, ChatStore, Cooldown, OptoutStore

NOW = datetime(2026, 1, 10, 15, 30, tzinfo=UTC)
CHAT_ID = -100
USER_ID = 7

USER = User(id=USER_ID, is_bot=False, first_name="Alex", username="alex")
CHAT = Chat(id=CHAT_ID, type="supergroup", title="Testers")


def make_message(text: str, message_id: int = 1) -> Message:
    return Message(message_id=message_id, date=NOW, chat=CHAT, from_user=USER, text=text)


class CapturingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.methods: list[TelegramMethod[Any]] = []

    async def close(self) -> None:  # pragma: no cover - nothing to close
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes]:
        yield b""

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.methods.append(method)
        if type(method).__name__ in ("SendMessage", "SendRichMessage", "EditMessageText"):
            return Message(message_id=99, date=NOW, chat=CHAT)
        if type(method).__name__ == "GetChatMember":
            return ChatMemberMember(status="member", user=USER)
        return True

    def of(self, method_type: type) -> list:
        return [m for m in self.methods if isinstance(m, method_type)]


def setup(db):
    session = CapturingSession()
    bot = Bot(token="123456:TEST", session=session)
    ctx = AppContext(
        settings=Settings(bot_token="123456:TEST", page_size=10),
        db=db,
        collector=Collector(),
        messenger=Messenger(bot, rich_enabled=True),
        chats=ChatStore(db),
        optouts=OptoutStore(db),
        cooldown=Cooldown(0),
        admins=AdminCache(bot),
    )
    dp = Dispatcher()
    dp.include_router(build_router(ctx))
    return session, bot, ctx, dp


async def test_top_command_and_args(db):
    session, bot, ctx, dp = setup(db)

    await dp.feed_update(bot, Update(update_id=1, message=make_message("/top")))
    await dp.feed_update(bot, Update(update_id=2, message=make_message("/top 30d media", message_id=2)))

    headings = [m.rich_message.blocks[0].text for m in session.of(SendRichMessage)]
    assert not session.of(SendMessage)  # rich path, no fallback
    assert "Leaderboard" in headings[0] and "Last 7 days" in headings[0] and "Messages" in headings[0]
    assert "Last 30 days" in headings[1] and "Media" in headings[1]
    assert sum(row[3] for row in ctx.collector.snapshot()) == 2  # commands are counted too


async def test_callback_edits_the_same_message(db):
    session, bot, _ctx, dp = setup(db)

    callback = CallbackQuery(
        id="1",
        from_user=USER,
        chat_instance="ci",
        message=make_message("/top", message_id=55),
        data=callbacks.encode_top(USER_ID, "30d", "c", 0),
    )
    await dp.feed_update(bot, Update(update_id=2, callback_query=callback))

    edits = session.of(EditMessageText)
    assert len(edits) == 1 and edits[0].message_id == 55
    heading = edits[0].rich_message.blocks[0].text
    assert "Last 30 days" in heading and "Characters" in heading


async def test_hours_and_stats_commands(db):
    session, bot, _ctx, dp = setup(db)

    await dp.feed_update(bot, Update(update_id=1, message=make_message("/hours")))
    await dp.feed_update(bot, Update(update_id=2, message=make_message("/stats", message_id=2)))

    headings = [m.rich_message.blocks[0].text for m in session.of(SendRichMessage)]
    assert any("Time of day" in h for h in headings)
    assert any("Chat summary" in h for h in headings)


async def test_privacy_optout_and_forgetme(db):
    session, bot, ctx, dp = setup(db)
    await ctx.chats.ensure(CHAT_ID, "Testers")
    ctx.collector.add(CHAT_ID, USER_ID, NOW, msgs=3)
    await ctx.collector.flush(db)

    await dp.feed_update(bot, Update(update_id=1, message=make_message("/optout")))
    assert await ctx.optouts.is_opted_out(CHAT_ID, USER_ID) is True

    await dp.feed_update(bot, Update(update_id=2, message=make_message("/forgetme", message_id=2)))
    assert session.of(SendRichMessage)

    callback = CallbackQuery(
        id="2",
        from_user=USER,
        chat_instance="ci",
        message=make_message("/forgetme", message_id=60),
        data=callbacks.encode_forget(USER_ID, True),
    )
    await dp.feed_update(bot, Update(update_id=3, callback_query=callback))
    assert (await db.fetchval("SELECT count(*) FROM activity_hourly")) == 0
    assert session.of(AnswerCallbackQuery)
