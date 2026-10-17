from __future__ import annotations

import contextlib
from datetime import UTC, date, datetime

from yapboard import stats, wordstats
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


async def add_word(
    db,
    user_id: int,
    day: date,
    stem: str,
    word: str,
    n: int,
    *,
    chat_id: int = CHAT,
) -> None:
    await db.execute(
        "INSERT INTO word_counts (chat_id, user_id, day, stem, word, n) "
        "VALUES ($1, $2, $3, $4, $5, $6) "
        "ON CONFLICT (chat_id, user_id, day, stem, word) DO UPDATE "
        "SET n = word_counts.n + EXCLUDED.n",
        chat_id,
        user_id,
        day,
        stem,
        word,
        n,
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
    await add_word(db, 7, date(2026, 1, 5), "кот", "кот", 3)
    await add_word(db, 8, date(2026, 1, 5), "код", "код", 2)
    assert await wipe_user(db, CHAT, 7) == 2
    assert (await db.fetchval("SELECT count(*) FROM activity_hourly")) == 1
    assert (await db.fetchval("SELECT count(*) FROM word_counts")) == 1


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


async def test_collector_flushes_word_counts_and_preserves_on_error(db):
    await seed_chat(db)
    collector = Collector()
    collector.add_words(
        CHAT,
        7,
        date(2026, 1, 5),
        {("кот", "кот"): 2, ("кот", "кота"): 1, ("код", "код"): 4},
    )
    assert collector.pending_words == 3

    await collector.flush(db)
    assert collector.pending_words == 0 and collector.word_rows_flushed == 3
    rows = await db.fetch(
        "SELECT stem, word, n FROM word_counts ORDER BY stem, word"
    )
    assert [(row["stem"], row["word"], row["n"]) for row in rows] == [
        ("код", "код", 4),
        ("кот", "кот", 2),
        ("кот", "кота", 1),
    ]

    collector.add_words(CHAT, 7, date(2026, 1, 5), {("кот", "кот"): 3})
    await collector.flush(db)
    assert (await db.fetchval("SELECT n FROM word_counts WHERE word = 'кот'")) == 5

    class BoomPool:
        def acquire(self):
            raise RuntimeError("db down")

    failing = Collector()
    failing.add_words(CHAT, 7, date(2026, 1, 5), {("кот", "кот"): 3})
    with contextlib.suppress(RuntimeError):
        await failing.flush(type("DB", (), {"pool": BoomPool()})())
    assert failing.pending_words == 1
    assert failing.snapshot_words()[0][5] == 3


async def test_word_stats_total_by_member_and_periods(db):
    await seed_chat(db)
    period = resolve("7d", "UTC", now=NOW)
    assert wordstats.local_day_bounds(period, "UTC") == (date(2026, 1, 4), date(2026, 1, 11))

    today = resolve("d", "Europe/Moscow", now=NOW)
    assert wordstats.local_day_bounds(today, "Europe/Moscow") == (
        date(2026, 1, 10),
        date(2026, 1, 11),
    )

    await add_word(db, 1, date(2026, 1, 5), "кот", "кот", 3)
    await add_word(db, 1, date(2026, 1, 5), "кот", "кота", 2)
    await add_word(db, 1, date(2026, 1, 6), "код", "код", 1)
    await add_word(db, 2, date(2026, 1, 5), "кот", "кот", 1)
    await add_word(db, 2, date(2026, 1, 6), "код", "код", 4)
    await add_word(db, 1, date(2026, 1, 1), "старое", "старое", 100)
    await add_word(db, 1, date(2026, 1, 12), "новое", "новое", 100)

    total = await wordstats.top_words(db, CHAT, period, "UTC", 0, 10)
    assert [(e.word, e.uses, e.members) for e in total.entries] == [
        ("кот", 6, 2),
        ("код", 5, 2),
    ]
    assert (total.total_uses, total.unique_words, total.active_users) == (11, 2, 2)
    assert total.pages == 1

    paged = await wordstats.top_words(db, CHAT, period, "UTC", 0, 1)
    assert paged.pages == 2 and paged.entries[0].word == "кот"
    assert (await wordstats.top_words(db, CHAT, period, "UTC", 99, 1)).page == 1

    by_member = await wordstats.words_by_member(
        db, CHAT, period, "UTC", 0, 10, per_member=1
    )
    assert (by_member.total_members, by_member.total_uses) == (2, 11)
    assert [member.user_id for member in by_member.members] == [1, 2]
    first = by_member.members[0]
    assert first.total_uses == 6 and first.unique_words == 2
    assert [(word.word, word.uses) for word in first.words] == [("кот", 5)]

    member_page = await wordstats.words_by_member(
        db, CHAT, period, "UTC", 1, 1, per_member=1
    )
    assert member_page.page == 1 and member_page.pages == 2
    assert [member.user_id for member in member_page.members] == [2]

    all_time = resolve("all", "UTC", now=NOW)
    everything = await wordstats.top_words(db, CHAT, all_time, "UTC", 0, 10)
    assert everything.total_uses == 211
    assert everything.unique_words == 4


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
