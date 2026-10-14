from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from yapboard import stats
from yapboard.collector import Collector, hour_bucket
from yapboard.periods import resolve
from yapboard.state import ChatStore, Cooldown, OptoutStore, wipe_user

NOW = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
CHAT = -100


def bucket(day: int, hour: int = 10) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=UTC)


async def seed_chat(db, chat_id: int = CHAT) -> None:
    await db.execute(
        "INSERT INTO chats (chat_id, title) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        chat_id,
        "Testers",
    )


async def add_activity(db, user_id: int, moment: datetime, *, msgs=0, chars=0, media=0, username=None):
    await db.execute(
        "INSERT INTO users (user_id, username) VALUES ($1, $2) "
        "ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username",
        user_id,
        username,
    )
    await db.execute(
        "INSERT INTO activity_hourly (chat_id, user_id, bucket, msgs, chars, media) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        CHAT,
        user_id,
        moment,
        msgs,
        chars,
        media,
    )


async def test_chat_store_optouts_and_wipe(db):
    store = ChatStore(db, default_tz="Europe/Berlin")
    assert await store.get(CHAT) is None

    created = await store.ensure(CHAT, "Testers")
    assert (created.tz, created.collecting, created.only_requester) == ("Europe/Berlin", True, False)
    assert (await store.set_tz(CHAT, "Europe/Moscow")).tz == "Europe/Moscow"
    assert (await store.set_collecting(CHAT, False)).collecting is False
    assert await store.is_collecting(CHAT) is False
    assert (await store.set_only_requester(CHAT, True)).only_requester is True
    assert await ChatStore(db).is_collecting(-999) is True  # unknown chat counts

    optouts = OptoutStore(db)
    assert await optouts.is_opted_out(CHAT, 7) is False
    await optouts.set(CHAT, 7, True)
    assert await optouts.is_opted_out(CHAT, 7) is True
    await optouts.set(CHAT, 7, False)
    assert await optouts.count(CHAT) == 0

    await db.execute(
        "INSERT INTO activity_hourly (chat_id, user_id, bucket, msgs) VALUES ($1, 7, $2, 5)",
        CHAT,
        bucket(5),
    )
    await db.execute(
        "INSERT INTO activity_hourly (chat_id, user_id, bucket, msgs) VALUES ($1, 8, $2, 9)",
        CHAT,
        bucket(5),
    )
    assert await wipe_user(db, CHAT, 7) == 1
    assert (await db.fetchval("SELECT count(*) FROM activity_hourly")) == 1


async def test_collector_accumulates_flushes_and_preserves_on_error(db):
    await seed_chat(db)
    assert hour_bucket(datetime(2026, 1, 10, 15, 59, tzinfo=UTC)) == datetime(2026, 1, 10, 15, tzinfo=UTC)

    collector = Collector(profile_refresh_sec=0)
    collector.add(CHAT, 7, bucket(5, 15), username="alex", first_name="Alex", msgs=1, chars=5, replies=1)
    collector.add(CHAT, 7, bucket(5, 15), username="alex", msgs=1, chars=3, media=1)
    assert collector.pending_keys == 1  # same hour merged

    assert await collector.flush(db) == 1
    row = await db.fetchrow("SELECT msgs, chars, media, replies FROM activity_hourly")
    assert (row["msgs"], row["chars"], row["media"], row["replies"]) == (2, 8, 1, 1)
    assert (await db.fetchrow("SELECT username FROM users WHERE user_id = 7"))["username"] == "alex"

    collector.add(CHAT, 7, bucket(5, 15), msgs=1)
    await collector.flush(db)
    assert (await db.fetchval("SELECT msgs FROM activity_hourly")) == 3

    class BoomPool:
        def acquire(self):
            raise RuntimeError("db down")

    failing = Collector()
    failing.add(CHAT, 7, bucket(5), msgs=3)
    with contextlib.suppress(RuntimeError):
        await failing.flush(type("DB", (), {"pool": BoomPool()})())
    assert failing.pending_keys == 1 and failing.snapshot()[0][3] == 3


async def test_top_ordering_pagination_and_metrics(db):
    await seed_chat(db)
    await add_activity(db, 1, bucket(5), msgs=5, username="a")
    await add_activity(db, 2, bucket(5), msgs=5, username="b")
    await add_activity(db, 3, bucket(5), msgs=1)
    await add_activity(db, 1, datetime(2025, 12, 1, 10, tzinfo=UTC), msgs=100)  # outside 7d

    period = resolve("7d", "UTC", now=NOW)
    result = await stats.top(db, CHAT, period, "m", 0, 10)
    assert [e.user_id for e in result.entries] == [1, 2, 3]  # ties broken by user_id
    assert result.total_activity == 11 and result.active_users == 3 and result.pages == 1

    for user_id in range(4, 27):
        await add_activity(db, user_id, bucket(5), msgs=user_id)
    paged = await stats.top(db, CHAT, period, "m", 0, 10)
    assert paged.pages == 3 and paged.entries[0].user_id == 26
    assert len((await stats.top(db, CHAT, period, "m", 2, 10)).entries) == 6
    assert (await stats.top(db, CHAT, period, "m", 99, 10)).page == 2  # clamped

    await db.execute("UPDATE activity_hourly SET media = msgs, chars = msgs * 10")
    media = await stats.top(db, CHAT, period, "v", 0, 10)
    chars = await stats.top(db, CHAT, period, "c", 0, 10)
    assert media.total_activity == chars.total_activity // 10


async def test_user_stat_hours_and_summary(db):
    await seed_chat(db)
    await add_activity(db, 1, bucket(5), msgs=10)
    await add_activity(db, 2, bucket(5, 22), msgs=20)
    await add_activity(db, 3, bucket(6), msgs=5)
    await add_activity(db, 1, bucket(9), msgs=7)

    period = resolve("7d", "UTC", now=NOW)
    assert (await stats.user_period_stat(db, CHAT, 2, period, "m")).rank == 1
    assert (await stats.user_period_stat(db, CHAT, 3, period, "m")).rank == 3
    assert (await stats.user_period_stat(db, CHAT, 999, period, "m")).rank is None

    histogram = await stats.hours_histogram(db, CHAT, period, "UTC")
    moscow = await stats.hours_histogram(db, CHAT, period, "Europe/Moscow")
    assert histogram[10] == 22 and histogram[22] == 20 and moscow[1] == 20
    assert stats.favourite_hour(histogram) == 10 and stats.favourite_hour([0] * 24) is None

    series = await stats.daily_series(db, CHAT, period, "UTC", user_id=1, days=3, now=NOW)
    assert [value for _, value in series] == [0, 7, 0]

    summary = await stats.chat_summary(db, CHAT, period, "UTC")
    assert summary.total_messages == 42 and summary.active_users == 3
    assert summary.busiest_hour == 10


def test_cooldown():
    cooldown = Cooldown(seconds=10)
    assert cooldown.allow("k") is True
    assert cooldown.allow("k") is False
    assert cooldown.retry_after("k") > 0
    assert cooldown.allow("other") is True
