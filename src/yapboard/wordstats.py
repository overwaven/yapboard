"""Read-side queries for the word-frequency board.

Words are bucketed by the chat-local calendar day, so a :class:`Period` can be
resolved to a half-open local date range and used with simple ``day >= / <``
predicates. Every user-controlled value is bound; only fixed SQL fragments are
interpolated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .db import Database
from .periods import Period, zone
from .render import MemberWord, MemberWords, WordEntry


@dataclass(slots=True)
class WordsTotalResult:
    entries: list[WordEntry]
    total_uses: int
    unique_words: int
    active_users: int
    page: int
    pages: int
    page_size: int


@dataclass(slots=True)
class WordsByMemberResult:
    members: list[MemberWords]
    total_uses: int
    total_members: int
    page: int
    pages: int
    page_size: int


def local_day_bounds(period: Period, tz_name: str) -> tuple[date | None, date | None]:
    """Half-open local-day bounds for a resolved period."""
    tz = zone(tz_name)
    first = period.start.astimezone(tz).date() if period.start is not None else None
    last = period.end.astimezone(tz).date() if period.end is not None else None
    return first, last


def _bounds(period: Period, tz_name: str, start_index: int = 2) -> tuple[str, list[object]]:
    first, last = local_day_bounds(period, tz_name)
    conditions: list[str] = []
    params: list[object] = []
    index = start_index
    if first is not None:
        conditions.append(f"w.day >= ${index}")
        params.append(first)
        index += 1
    if last is not None:
        conditions.append(f"w.day < ${index}")
        params.append(last)
    return (" AND ".join(conditions) if conditions else "TRUE", params)


async def top_words(
    db: Database,
    chat_id: int,
    period: Period,
    tz_name: str,
    page: int,
    page_size: int,
) -> WordsTotalResult:
    bounds_sql, bounds_params = _bounds(period, tz_name)

    stats_row = await db.fetchrow(
        f"""
        WITH base AS (
            SELECT w.user_id, w.stem, SUM(w.n)::bigint AS n
            FROM word_counts w
            WHERE w.chat_id = $1 AND {bounds_sql}
            GROUP BY w.user_id, w.stem
        )
        SELECT COALESCE(SUM(n), 0)::bigint       AS total_uses,
               COUNT(DISTINCT stem)::int          AS unique_words,
               COUNT(DISTINCT user_id)::int       AS active_users
        FROM base
        """,
        chat_id,
        *bounds_params,
    )
    total_uses = int(stats_row["total_uses"]) if stats_row else 0
    unique_words = int(stats_row["unique_words"]) if stats_row else 0
    active_users = int(stats_row["active_users"]) if stats_row else 0
    pages = max(1, math.ceil(unique_words / page_size)) if page_size > 0 else 1
    page = max(0, min(page, pages - 1))

    limit_index = 2 + len(bounds_params)
    offset_index = limit_index + 1
    rows = await db.fetch(
        f"""
        WITH base AS (
            SELECT w.user_id, w.stem, w.word, SUM(w.n)::bigint AS n
            FROM word_counts w
            WHERE w.chat_id = $1 AND {bounds_sql}
            GROUP BY w.user_id, w.stem, w.word
        ),
        per_word AS (
            SELECT stem, word, SUM(n)::bigint AS word_uses
            FROM base
            GROUP BY stem, word
        ),
        per_stem AS (
            SELECT stem,
                   SUM(word_uses)::bigint AS uses,
                   (array_agg(
                       word ORDER BY word_uses DESC, length(word) ASC, word ASC
                   ))[1] AS word
            FROM per_word
            GROUP BY stem
        ),
        members AS (
            SELECT stem, COUNT(DISTINCT user_id)::int AS members
            FROM base
            GROUP BY stem
        )
        SELECT s.stem, s.word, s.uses, m.members
        FROM per_stem s
        JOIN members m USING (stem)
        ORDER BY s.uses DESC, s.word ASC
        LIMIT ${limit_index} OFFSET ${offset_index}
        """,
        chat_id,
        *bounds_params,
        page_size,
        page * page_size,
    )

    entries = [
        WordEntry(
            stem=row["stem"],
            word=row["word"],
            uses=int(row["uses"]),
            members=int(row["members"]),
        )
        for row in rows
    ]
    return WordsTotalResult(
        entries=entries,
        total_uses=total_uses,
        unique_words=unique_words,
        active_users=active_users,
        page=page,
        pages=pages,
        page_size=page_size,
    )


async def words_by_member(
    db: Database,
    chat_id: int,
    period: Period,
    tz_name: str,
    page: int,
    page_size: int,
    *,
    per_member: int = 5,
) -> WordsByMemberResult:
    bounds_sql, bounds_params = _bounds(period, tz_name)

    stats_row = await db.fetchrow(
        f"""
        SELECT COUNT(DISTINCT w.user_id)::int AS members,
               COALESCE(SUM(w.n), 0)::bigint  AS total_uses
        FROM word_counts w
        WHERE w.chat_id = $1 AND {bounds_sql}
        """,
        chat_id,
        *bounds_params,
    )
    total_members = int(stats_row["members"]) if stats_row else 0
    total_uses = int(stats_row["total_uses"]) if stats_row else 0
    pages = max(1, math.ceil(total_members / page_size)) if page_size > 0 else 1
    page = max(0, min(page, pages - 1))

    per_member_index = 2 + len(bounds_params)
    limit_index = per_member_index + 1
    offset_index = limit_index + 1
    rows = await db.fetch(
        f"""
        WITH base AS (
            SELECT w.user_id, w.stem, w.word, SUM(w.n)::bigint AS n
            FROM word_counts w
            WHERE w.chat_id = $1 AND {bounds_sql}
            GROUP BY w.user_id, w.stem, w.word
        ),
        per_stem AS (
            SELECT user_id, stem,
                   SUM(n)::bigint AS uses,
                   (array_agg(
                       word ORDER BY n DESC, length(word) ASC, word ASC
                   ))[1] AS word
            FROM base
            GROUP BY user_id, stem
        ),
        ranked AS (
            SELECT user_id, stem, word, uses,
                   SUM(uses) OVER (PARTITION BY user_id)::bigint AS total_uses,
                   COUNT(*) OVER (PARTITION BY user_id)::int       AS unique_words,
                   ROW_NUMBER() OVER (
                       PARTITION BY user_id
                       ORDER BY uses DESC, length(word) ASC, word ASC
                   ) AS rn
            FROM per_stem
        )
        SELECT r.user_id, u.username, u.first_name,
               r.total_uses, r.unique_words,
               array_agg(r.stem ORDER BY r.uses DESC, length(r.word) ASC, r.word ASC)
                   FILTER (WHERE r.rn <= ${per_member_index}) AS stems,
               array_agg(r.word ORDER BY r.uses DESC, length(r.word) ASC, r.word ASC)
                   FILTER (WHERE r.rn <= ${per_member_index}) AS words,
               array_agg(r.uses ORDER BY r.uses DESC, length(r.word) ASC, r.word ASC)
                   FILTER (WHERE r.rn <= ${per_member_index}) AS uses
        FROM ranked r
        LEFT JOIN users u ON u.user_id = r.user_id
        GROUP BY r.user_id, u.username, u.first_name, r.total_uses, r.unique_words
        ORDER BY r.total_uses DESC, r.user_id ASC
        LIMIT ${limit_index} OFFSET ${offset_index}
        """,
        chat_id,
        *bounds_params,
        per_member,
        page_size,
        page * page_size,
    )

    members: list[MemberWords] = []
    for row in rows:
        stems = row["stems"] or []
        words = row["words"] or []
        uses = row["uses"] or []
        members.append(
            MemberWords(
                user_id=row["user_id"],
                username=row["username"],
                first_name=row["first_name"],
                words=[
                    MemberWord(stem=stems[i], word=words[i], uses=int(uses[i]))
                    for i in range(min(len(stems), len(words), len(uses)))
                ],
                total_uses=int(row["total_uses"]),
                unique_words=int(row["unique_words"]),
            )
        )
    return WordsByMemberResult(
        members=members,
        total_uses=total_uses,
        total_members=total_members,
        page=page,
        pages=pages,
        page_size=page_size,
    )


__all__ = [
    "MemberWord",
    "MemberWords",
    "WordEntry",
    "WordsByMemberResult",
    "WordsTotalResult",
    "local_day_bounds",
    "top_words",
    "words_by_member",
]
