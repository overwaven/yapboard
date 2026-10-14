"""In-memory activity buffer with periodic batched flush.

Counters live in a dict keyed by ``(chat_id, user_id, utc_hour)``. A background
task swaps the buffer out every ``flush_interval`` seconds (or sooner when it
grows past ``flush_max_keys``) and upserts it in a single transaction.

Crash exposure is bounded by the flush interval; nothing is ever lost from the
database that has already been flushed.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from .db import Database

log = logging.getLogger(__name__)

UPSERT_ACTIVITY = """
INSERT INTO activity_hourly (chat_id, user_id, bucket, msgs, chars, media, replies)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (chat_id, user_id, bucket) DO UPDATE SET
    msgs    = activity_hourly.msgs    + EXCLUDED.msgs,
    chars   = activity_hourly.chars   + EXCLUDED.chars,
    media   = activity_hourly.media   + EXCLUDED.media,
    replies = activity_hourly.replies + EXCLUDED.replies
"""

UPSERT_USER = """
INSERT INTO users (user_id, username, first_name, updated_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (user_id) DO UPDATE SET
    username   = COALESCE(EXCLUDED.username, users.username),
    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
    updated_at = now()
"""


def hour_bucket(moment: datetime) -> datetime:
    """Truncate an aware datetime to its UTC hour."""
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


@dataclass(slots=True)
class Counter:
    msgs: int = 0
    chars: int = 0
    media: int = 0
    replies: int = 0


class Collector:
    def __init__(
        self,
        *,
        flush_interval: float = 5.0,
        max_keys: int = 500,
        profile_refresh_sec: float = 600.0,
    ) -> None:
        self.flush_interval = flush_interval
        self.max_keys = max_keys
        self.profile_refresh_sec = profile_refresh_sec

        self._buffer: dict[tuple[int, int, datetime], Counter] = {}
        self._profiles: dict[int, tuple[str | None, str | None]] = {}
        self._profile_seen: dict[int, float] = {}
        self._wake = asyncio.Event()

        # Stats for logging.
        self.rows_flushed = 0
        self.flushes = 0
        self.last_flush_ms = 0.0

    @property
    def pending_keys(self) -> int:
        return len(self._buffer)

    @property
    def pending_profiles(self) -> int:
        return len(self._profiles)

    def add(
        self,
        chat_id: int,
        user_id: int,
        moment: datetime,
        *,
        username: str | None = None,
        first_name: str | None = None,
        msgs: int = 1,
        chars: int = 0,
        media: int = 0,
        replies: int = 0,
    ) -> None:
        key = (chat_id, user_id, hour_bucket(moment))
        counter = self._buffer.get(key)
        if counter is None:
            counter = Counter()
            self._buffer[key] = counter
        counter.msgs += msgs
        counter.chars += chars
        counter.media += media
        counter.replies += replies

        now = time.monotonic()
        last = self._profile_seen.get(user_id)
        if last is None or (now - last) >= self.profile_refresh_sec:
            self._profile_seen[user_id] = now
            previous = self._profiles.get(user_id)
            if previous is not None:
                username = username or previous[0]
                first_name = first_name or previous[1]
            self._profiles[user_id] = (username, first_name)

        if len(self._buffer) >= self.max_keys:
            self._wake.set()

    def snapshot(self) -> list[tuple[int, int, datetime, int, int, int, int]]:
        """Return already-accumulated rows without disturbing the buffer."""
        rows: list[tuple[int, int, datetime, int, int, int, int]] = []
        for (chat_id, user_id, bucket), counter in self._buffer.items():
            rows.append(
                (chat_id, user_id, bucket, counter.msgs, counter.chars, counter.media, counter.replies)
            )
        return rows

    async def flush(self, db: Database) -> int:
        buffer, self._buffer = self._buffer, {}
        profiles, self._profiles = self._profiles, {}
        if not buffer and not profiles:
            return 0

        started = time.monotonic()
        rows = [
            (chat_id, user_id, bucket, counter.msgs, counter.chars, counter.media, counter.replies)
            for (chat_id, user_id, bucket), counter in buffer.items()
        ]
        profile_rows = [(uid, username, first_name) for uid, (username, first_name) in profiles.items()]

        try:
            async with db.pool.acquire() as conn, conn.transaction():
                if rows:
                    await conn.executemany(UPSERT_ACTIVITY, rows, timeout=30)
                if profile_rows:
                    await conn.executemany(UPSERT_USER, profile_rows, timeout=30)
        except Exception:
            # A transient DB error must not drop counters collected while we were
            # attempting the write; merge the batch back for the next flush.
            self._merge_back(buffer)
            raise

        self.last_flush_ms = (time.monotonic() - started) * 1000
        self.rows_flushed += len(rows)
        self.flushes += 1
        return len(rows)

    def _merge_back(self, buffer: dict[tuple[int, int, datetime], Counter]) -> None:
        for key, counter in buffer.items():
            existing = self._buffer.get(key)
            if existing is None:
                self._buffer[key] = counter
                continue
            existing.msgs += counter.msgs
            existing.chars += counter.chars
            existing.media += counter.media
            existing.replies += counter.replies

    async def run(self, db: Database, stop_event: asyncio.Event) -> None:
        """Background loop; flushes on interval, on wake, and once on shutdown."""
        while not stop_event.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self.flush_interval)
            self._wake.clear()
            try:
                flushed = await self.flush(db)
            except Exception:  # noqa: BLE001 - keep the loop alive
                log.exception("activity flush failed")
                continue
            if flushed:
                log.debug(
                    "flushed %d rows in %.1f ms (pending=%d)",
                    flushed,
                    self.last_flush_ms,
                    self.pending_keys,
                )
        # Graceful shutdown flush.
        try:
            await self.flush(db)
        except Exception:  # noqa: BLE001
            log.exception("final flush failed")
