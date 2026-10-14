"""Read-side analytics queries.

Metric columns are chosen from a hard whitelist — never interpolated from user
input. Period boundaries are always bound parameters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .db import Database
from .periods import Period, zone
from .render import TopEntry

METRIC_COLUMNS: dict[str, str] = {
    "m": "msgs",
    "c": "chars",
    "v": "media",
}


@dataclass(slots=True)
class TopResult:
    entries: list[TopEntry]
    total_activity: int
    active_users: int
    page: int
    pages: int
    page_size: int


@dataclass(slots=True)
class UserPeriodStat:
    value: int
    rank: int | None
    total_users: int


def column_for(metric: str) -> str:
    return METRIC_COLUMNS.get(metric, METRIC_COLUMNS["m"])


def _bounds(period: Period, start_index: int = 2) -> tuple[str, list[object]]:
    """Build the ``bucket`` predicate and its bound parameters."""
    conditions: list[str] = []
    params: list[object] = []
    index = start_index
    if period.start is not None:
        conditions.append(f"a.bucket >= ${index}")
        params.append(period.start)
        index += 1
    if period.end is not None:
        conditions.append(f"a.bucket < ${index}")
        params.append(period.end)
        index += 1
    return (" AND ".join(conditions) if conditions else "TRUE", params)


async def top(
    db: Database,
    chat_id: int,
    period: Period,
    metric: str,
    page: int,
    page_size: int,
) -> TopResult:
    column = column_for(metric)
    bounds_sql, bounds_params = _bounds(period)

    stats_row = await db.fetchrow(
        f"""
        SELECT COALESCE(SUM(v), 0)::bigint AS total,
               COUNT(*)::int            AS users
        FROM (
            SELECT a.user_id, SUM(a.{column}) AS v
            FROM activity_hourly a
            WHERE a.chat_id = $1 AND {bounds_sql}
            GROUP BY a.user_id
        ) t
        WHERE t.v > 0
        """,
        chat_id,
        *bounds_params,
    )
    total_activity = int(stats_row["total"]) if stats_row else 0
    active_users = int(stats_row["users"]) if stats_row else 0
    pages = max(1, math.ceil(active_users / page_size)) if page_size > 0 else 1
    page = max(0, min(page, pages - 1))

    limit_index = 2 + len(bounds_params)
    offset_index = limit_index + 1
    rows = await db.fetch(
        f"""
        SELECT a.user_id, u.username, u.first_name,
               SUM(a.{column})::bigint AS value
        FROM activity_hourly a
        LEFT JOIN users u ON u.user_id = a.user_id
        WHERE a.chat_id = $1 AND {bounds_sql}
        GROUP BY a.user_id, u.username, u.first_name
        HAVING SUM(a.{column}) > 0
        ORDER BY value DESC, a.user_id ASC
        LIMIT ${limit_index} OFFSET ${offset_index}
        """,
        chat_id,
        *bounds_params,
        page_size,
        page * page_size,
    )

    entries = [
        TopEntry(
            user_id=row["user_id"],
            username=row["username"],
            first_name=row["first_name"],
            value=int(row["value"]),
        )
        for row in rows
    ]
    return TopResult(
        entries=entries,
        total_activity=total_activity,
        active_users=active_users,
        page=page,
        pages=pages,
        page_size=page_size,
    )


async def user_period_stat(
    db: Database, chat_id: int, user_id: int, period: Period, metric: str
) -> UserPeriodStat:
    column = column_for(metric)
    bounds_sql, bounds_params = _bounds(period)
    my_index = 2 + len(bounds_params)
    row = await db.fetchrow(
        f"""
        WITH agg AS (
            SELECT a.user_id, SUM(a.{column}) AS v
            FROM activity_hourly a
            WHERE a.chat_id = $1 AND {bounds_sql}
            GROUP BY a.user_id
        )
        SELECT
            COALESCE((SELECT v FROM agg WHERE user_id = ${my_index}), 0)::bigint AS value,
            (SELECT COUNT(*) FROM agg
              WHERE v > COALESCE((SELECT v FROM agg WHERE user_id = ${my_index}), 0))::int
                + 1 AS rank,
            (SELECT COUNT(*) FROM agg WHERE v > 0)::int AS total_users
        """,
        chat_id,
        *bounds_params,
        user_id,
    )
    if row is None:
        return UserPeriodStat(value=0, rank=None, total_users=0)
    value = int(row["value"])
    total_users = int(row["total_users"])
    rank = int(row["rank"]) if value > 0 and total_users > 0 else None
    return UserPeriodStat(value=value, rank=rank, total_users=total_users)


async def hours_histogram(
    db: Database, chat_id: int, period: Period, tz_name: str
) -> list[int]:
    """Messages per local hour (index 0..23)."""
    bounds_sql, bounds_params = _bounds(period)
    tz_index = 2 + len(bounds_params)
    rows = await db.fetch(
        f"""
        SELECT EXTRACT(HOUR FROM a.bucket AT TIME ZONE ${tz_index})::int AS hour,
               SUM(a.msgs)::bigint AS value
        FROM activity_hourly a
        WHERE a.chat_id = $1 AND {bounds_sql}
        GROUP BY 1
        """,
        chat_id,
        *bounds_params,
        tz_name,
    )
    histogram = [0] * 24
    for row in rows:
        hour = int(row["hour"])
        if 0 <= hour < 24:
            histogram[hour] = int(row["value"])
    return histogram


def favourite_hour(histogram: list[int]) -> int | None:
    best_value = max(histogram, default=0)
    if best_value <= 0:
        return None
    return histogram.index(best_value)


async def daily_series(
    db: Database,
    chat_id: int,
    period: Period,
    tz_name: str,
    *,
    user_id: int | None = None,
    days: int = 14,
    now: datetime | None = None,
) -> list[tuple[date, int]]:
    """Per-local-day message counts for the last ``days`` days (oldest first)."""
    tz = zone(tz_name)
    today = (now or datetime.now(UTC)).astimezone(tz).date()
    first_day = today - timedelta(days=days - 1)

    bounds_sql, bounds_params = _bounds(period)
    tz_index = 2 + len(bounds_params)
    user_index = tz_index + 1
    user_clause = f"AND a.user_id = ${user_index}" if user_id is not None else ""
    params: list[object] = [chat_id, *bounds_params, tz_name]
    if user_id is not None:
        params.append(user_id)

    rows = await db.fetch(
        f"""
        SELECT (a.bucket AT TIME ZONE ${tz_index})::date AS day,
               SUM(a.msgs)::bigint AS value
        FROM activity_hourly a
        WHERE a.chat_id = $1 AND {bounds_sql} {user_clause}
        GROUP BY 1
        """,
        *params,
    )
    by_day = {row["day"]: int(row["value"]) for row in rows}
    return [
        (first_day + timedelta(days=offset), by_day.get(first_day + timedelta(days=offset), 0))
        for offset in range(days)
    ]


@dataclass(slots=True)
class ChatSummary:
    total_messages: int
    active_users: int
    busiest_day: date | None
    busiest_day_messages: int
    busiest_hour: int | None
    histogram: list[int]


async def chat_summary(
    db: Database, chat_id: int, period: Period, tz_name: str
) -> ChatSummary:
    bounds_sql, bounds_params = _bounds(period)
    row = await db.fetchrow(
        f"""
        SELECT COALESCE(SUM(a.msgs), 0)::bigint          AS total,
               COUNT(DISTINCT a.user_id)::int            AS users
        FROM activity_hourly a
        WHERE a.chat_id = $1 AND {bounds_sql}
        """,
        chat_id,
        *bounds_params,
    )
    total_messages = int(row["total"]) if row else 0
    active_users = int(row["users"]) if row else 0

    histogram = await hours_histogram(db, chat_id, period, tz_name)

    busiest_day = None
    busiest_day_messages = 0
    if total_messages:
        day_rows = await db.fetch(
            f"""
            SELECT (a.bucket AT TIME ZONE ${2 + len(bounds_params)})::date AS day,
                   SUM(a.msgs)::bigint AS value
            FROM activity_hourly a
            WHERE a.chat_id = $1 AND {bounds_sql}
            GROUP BY 1 ORDER BY value DESC LIMIT 1
            """,
            chat_id,
            *bounds_params,
            tz_name,
        )
        if day_rows:
            busiest_day = day_rows[0]["day"]
            busiest_day_messages = int(day_rows[0]["value"])
    return ChatSummary(
        total_messages=total_messages,
        active_users=active_users,
        busiest_day=busiest_day,
        busiest_day_messages=busiest_day_messages,
        busiest_hour=favourite_hour(histogram),
        histogram=histogram,
    )
