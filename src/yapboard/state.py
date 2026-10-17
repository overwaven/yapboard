"""Small in-memory caches backed by the database.

These keep the tracker hot path free of per-message queries and give admins
immediate feedback without waiting for a cache to expire.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Hashable
from dataclasses import dataclass, replace

from .db import Database
from .periods import zone

_COLUMNS = "chat_id, title, tz, collecting, only_requester"


@dataclass(frozen=True, slots=True)
class ChatSettings:
    chat_id: int
    title: str | None
    tz: str
    collecting: bool
    only_requester: bool

    @property
    def zone(self):
        return zone(self.tz)


def _row_to_settings(row) -> ChatSettings:
    return ChatSettings(
        chat_id=row["chat_id"],
        title=row["title"],
        tz=row["tz"],
        collecting=row["collecting"],
        only_requester=row["only_requester"],
    )


class ChatStore:
    def __init__(self, db: Database, *, default_tz: str = "UTC") -> None:
        self._db = db
        self._default_tz = default_tz
        self._cache: dict[int, ChatSettings] = {}
        self._lock = asyncio.Lock()

    async def ensure(self, chat_id: int, title: str | None = None) -> ChatSettings:
        async with self._lock:
            row = await self._db.fetchrow(
                f"""
                INSERT INTO chats (chat_id, title, tz) VALUES ($1, $2, $3)
                ON CONFLICT (chat_id) DO UPDATE
                    SET title = COALESCE(EXCLUDED.title, chats.title)
                RETURNING {_COLUMNS}
                """,
                chat_id,
                title,
                self._default_tz,
            )
            settings = _row_to_settings(row)
            self._cache[chat_id] = settings
            return settings

    async def get(self, chat_id: int) -> ChatSettings | None:
        cached = self._cache.get(chat_id)
        if cached is not None:
            return cached
        row = await self._db.fetchrow(f"SELECT {_COLUMNS} FROM chats WHERE chat_id = $1", chat_id)
        if row is None:
            return None
        settings = _row_to_settings(row)
        self._cache[chat_id] = settings
        return settings

    async def get_or_create(self, chat_id: int, title: str | None = None) -> ChatSettings:
        return await self.get(chat_id) or await self.ensure(chat_id, title)

    async def is_collecting(self, chat_id: int) -> bool:
        cached = self._cache.get(chat_id)
        if cached is not None:
            return cached.collecting
        settings = await self.get(chat_id)
        return settings.collecting if settings is not None else True

    async def set_tz(self, chat_id: int, tz: str) -> ChatSettings:
        zone(tz)  # validate (falls back to UTC for unknown names)
        return await self._update(chat_id, "tz", tz)

    async def set_collecting(self, chat_id: int, value: bool) -> ChatSettings:
        return await self._update(chat_id, "collecting", value)

    async def set_only_requester(self, chat_id: int, value: bool) -> ChatSettings:
        return await self._update(chat_id, "only_requester", value)

    async def _update(self, chat_id: int, field: str, value: object) -> ChatSettings:
        if field not in ("tz", "collecting", "only_requester"):
            raise ValueError(f"unknown chat field: {field}")
        async with self._lock:
            row = await self._db.fetchrow(
                f"UPDATE chats SET {field} = $2 WHERE chat_id = $1 RETURNING {_COLUMNS}",
                chat_id,
                value,
            )
            if row is None:
                await self.ensure(chat_id)
                row = await self._db.fetchrow(
                    f"UPDATE chats SET {field} = $2 WHERE chat_id = $1 RETURNING {_COLUMNS}",
                    chat_id,
                    value,
                )
            settings = _row_to_settings(row)
            self._cache[chat_id] = settings
            return settings

    def update_cached(self, settings: ChatSettings) -> None:
        self._cache[settings.chat_id] = settings

    def invalidate(self, chat_id: int) -> None:
        self._cache.pop(chat_id, None)


class OptoutStore:
    """Per-chat set of user ids that asked not to be counted."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._cache: dict[int, set[int]] = {}
        self._loaded: set[int] = set()
        self._lock = asyncio.Lock()

    async def _load(self, chat_id: int) -> set[int]:
        rows = await self._db.fetch("SELECT user_id FROM optouts WHERE chat_id = $1", chat_id)
        users = {row["user_id"] for row in rows}
        self._cache[chat_id] = users
        self._loaded.add(chat_id)
        return users

    async def is_opted_out(self, chat_id: int, user_id: int) -> bool:
        if chat_id not in self._loaded:
            async with self._lock:
                if chat_id not in self._loaded:
                    await self._load(chat_id)
        return user_id in self._cache.get(chat_id, set())

    async def set(self, chat_id: int, user_id: int, opted_out: bool) -> None:
        if opted_out:
            await self._db.execute(
                "INSERT INTO optouts (chat_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                chat_id,
                user_id,
            )
        else:
            await self._db.execute(
                "DELETE FROM optouts WHERE chat_id = $1 AND user_id = $2", chat_id, user_id
            )
        await self._load(chat_id)

    async def count(self, chat_id: int) -> int:
        if chat_id not in self._loaded:
            await self._load(chat_id)
        return len(self._cache.get(chat_id, set()))


class Cooldown:
    """Simple per-key monotonic cooldown used to rate-limit ``/top``."""

    def __init__(self, seconds: float = 10.0) -> None:
        self.seconds = seconds
        self._last: dict[Hashable, float] = {}

    def allow(self, key: Hashable) -> bool:
        now = time.monotonic()
        last = self._last.get(key)
        if last is not None and (now - last) < self.seconds:
            return False
        self._last[key] = now
        return True

    def retry_after(self, key: Hashable) -> float:
        last = self._last.get(key)
        if last is None:
            return 0.0
        return max(0.0, self.seconds - (time.monotonic() - last))


class AdminCache:
    """Caches ``is_admin`` lookups for a few minutes."""

    def __init__(self, bot, *, ttl: float = 300.0) -> None:
        self._bot = bot
        self._ttl = ttl
        self._cache: dict[tuple[int, int], tuple[bool, float]] = {}

    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        key = (chat_id, user_id)
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached is not None and (now - cached[1]) < self._ttl:
            return cached[0]
        try:
            member = await self._bot.get_chat_member(chat_id, user_id)
            status = getattr(member, "status", None)
            value = status in ("creator", "administrator")
        except Exception:  # noqa: BLE001 - be permissive on API errors
            value = False
        self._cache[key] = (value, now)
        return value


def _affected(status: str) -> int:
    try:
        return int(str(status).split()[-1])
    except (ValueError, IndexError):
        return 0


async def wipe_user(db: Database, chat_id: int, user_id: int) -> int:
    """Delete activity counters and aggregated word counts for one member."""
    async with db.pool.acquire() as conn, conn.transaction():
        activity = await conn.execute(
            "DELETE FROM activity_hourly WHERE chat_id = $1 AND user_id = $2",
            chat_id,
            user_id,
        )
        words = await conn.execute(
            "DELETE FROM word_counts WHERE chat_id = $1 AND user_id = $2",
            chat_id,
            user_id,
        )
    return _affected(activity) + _affected(words)


def with_tz(settings: ChatSettings, tz: str) -> ChatSettings:
    return replace(settings, tz=tz)
