"""Neutral view models.

Handlers and stats code build these plain data structures; the rich and the
HTML-fallback renderers turn the *same* view into Telegram payloads. Keeping
presentation decisions here makes both renderers trivial and unit-testable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from ..callbacks import (
    FIELD_COLLECTING,
    FIELD_ONLY_REQUESTER,
    WORDS_BY_MEMBER,
    WORDS_TOTAL,
    encode_forget,
    encode_noop,
    encode_setting,
    encode_top,
    encode_words,
)
from ..periods import (
    METRIC_LABELS,
    METRIC_ORDER,
    PERIOD_LABELS,
    PERIOD_ORDER,
    metric_buttons,
    period_buttons,
)
from .bars import bar, display_name, human, medal, percent, sparkline


@dataclass(frozen=True, slots=True)
class Button:
    text: str
    callback_data: str | None = None
    url: str | None = None
    style: str | None = None  # 'primary' | 'success' | 'danger' | 'link'
    disabled: bool = False


Keyboard = list[list[Button]]


@dataclass(frozen=True, slots=True)
class Table:
    headers: list[str]
    rows: list[list[str]]
    aligns: list[str]  # 'left' | 'center' | 'right'


@dataclass(frozen=True, slots=True)
class View:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    table: Table | None = None
    empty_text: str | None = None
    footer: str | None = None
    keyboard: Keyboard = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TopEntry:
    user_id: int
    username: str | None
    first_name: str | None
    value: int


@dataclass(frozen=True, slots=True)
class MeStat:
    label: str
    messages: int
    rank: int | None
    total_users: int


@dataclass(frozen=True, slots=True)
class WordEntry:
    stem: str
    word: str
    uses: int
    members: int = 0


@dataclass(frozen=True, slots=True)
class MemberWord:
    stem: str
    word: str
    uses: int


@dataclass(slots=True)
class MemberWords:
    user_id: int
    username: str | None
    first_name: str | None
    words: list[MemberWord] = field(default_factory=list)
    total_uses: int = 0
    unique_words: int = 0


def _period_row(uid: int, period: str, metric: str) -> list[Button]:
    row = []
    for code, label in period_buttons():
        row.append(
            Button(
                text=label,
                callback_data=encode_top(uid, code, metric, 0),
                style="primary" if code == period else None,
            )
        )
    return row


def _metric_row(uid: int, period: str, metric: str) -> list[Button]:
    row = []
    for code, label in metric_buttons():
        row.append(
            Button(
                text=label,
                callback_data=encode_top(uid, period, code, 0),
                style="primary" if code == metric else None,
            )
        )
    return row


def _pager_row(uid: int, period: str, metric: str, page: int, pages: int) -> list[Button]:
    return [
        Button(
            text="‹ Prev",
            callback_data=encode_top(uid, period, metric, page - 1),
            disabled=page <= 0,
        ),
        Button(text=f"{page + 1} / {max(1, pages)}", callback_data=encode_noop()),
        Button(
            text="Next ›",
            callback_data=encode_top(uid, period, metric, page + 1),
            disabled=page >= pages - 1,
        ),
    ]


def leaderboard_view(
    *,
    entries: list[TopEntry],
    total_activity: int,
    active_users: int,
    period_code: str,
    period_label: str,
    metric: str,
    page: int,
    pages: int,
    requester_id: int,
    updated_at: datetime | None = None,
    page_size: int = 10,
) -> View:
    metric_label = METRIC_LABELS.get(metric, metric)
    heading = f"🏆 Leaderboard · {period_label} · {metric_label}"

    keyboard: Keyboard = [
        _period_row(requester_id, period_code, metric),
        _metric_row(requester_id, period_code, metric),
    ]
    if pages > 1:
        keyboard.append(_pager_row(requester_id, period_code, metric, page, pages))

    footer_bits = [
        f"{human(total_activity)} {metric_label.lower()}",
        f"{human(active_users)} active members",
    ]
    if updated_at is not None:
        footer_bits.append(f"updated {updated_at.strftime('%H:%M')}")
    footer = " · ".join(footer_bits)

    if not entries:
        return View(
            heading=heading,
            empty_text="No activity in this period yet — start chatting!",
            footer=footer,
            keyboard=keyboard,
        )

    maximum = max(entry.value for entry in entries)
    rows: list[list[str]] = []
    for index, entry in enumerate(entries):
        rank = page * page_size + index + 1
        share = entry.value / total_activity if total_activity > 0 else 0.0
        name = display_name(entry.username, entry.first_name, entry.user_id)
        rows.append(
            [
                medal(rank),
                name,
                human(entry.value),
                f"{bar(entry.value, maximum)}  {percent(share)}",
            ]
        )

    table = Table(
        headers=["#", "Member", metric_label, "Share"],
        rows=rows,
        aligns=["right", "left", "right", "left"],
    )
    return View(heading=heading, table=table, footer=footer, keyboard=keyboard)


def _words_period_row(uid: int, period: str, mode: str) -> list[Button]:
    return [
        Button(
            text=label,
            callback_data=encode_words(uid, code, mode, 0),
            style="primary" if code == period else None,
        )
        for code, label in period_buttons()
    ]


def _words_mode_row(uid: int, period: str, mode: str) -> list[Button]:
    options = (
        (WORDS_TOTAL, "Everyone"),
        (WORDS_BY_MEMBER, "By member"),
    )
    return [
        Button(
            text=label,
            callback_data=encode_words(uid, period, code, 0),
            style="primary" if code == mode else None,
        )
        for code, label in options
    ]


def _words_pager_row(uid: int, period: str, mode: str, page: int, pages: int) -> list[Button]:
    return [
        Button(
            text="‹ Prev",
            callback_data=encode_words(uid, period, mode, page - 1),
            disabled=page <= 0,
        ),
        Button(text=f"{page + 1} / {max(1, pages)}", callback_data=encode_noop()),
        Button(
            text="Next ›",
            callback_data=encode_words(uid, period, mode, page + 1),
            disabled=page >= pages - 1,
        ),
    ]


def _words_keyboard(
    uid: int, period: str, mode: str, page: int, pages: int
) -> Keyboard:
    keyboard: Keyboard = [
        _words_period_row(uid, period, mode),
        _words_mode_row(uid, period, mode),
    ]
    if pages > 1:
        keyboard.append(_words_pager_row(uid, period, mode, page, pages))
    return keyboard


def _short_word(word: str, limit: int = 24) -> str:
    return word if len(word) <= limit else word[: limit - 1] + "…"


def words_total_view(
    *,
    entries: list[WordEntry],
    total_uses: int,
    unique_words: int,
    active_users: int,
    period_code: str,
    period_label: str,
    page: int,
    pages: int,
    requester_id: int,
    updated_at: datetime | None = None,
    page_size: int = 10,
) -> View:
    heading = f"🗣 Words · {period_label} · Everyone"
    keyboard = _words_keyboard(requester_id, period_code, WORDS_TOTAL, page, pages)

    footer_bits = [
        f"{human(total_uses)} word uses",
        f"{human(unique_words)} unique words",
        f"{human(active_users)} members",
    ]
    if updated_at is not None:
        footer_bits.append(f"updated {updated_at.strftime('%H:%M')}")
    footer = " · ".join(footer_bits)

    if not entries:
        return View(
            heading=heading,
            empty_text="No meaningful words in this period yet — start chatting!",
            footer=footer,
            keyboard=keyboard,
        )

    maximum = max(entry.uses for entry in entries)
    rows: list[list[str]] = []
    for index, entry in enumerate(entries):
        rank = page * page_size + index + 1
        share = entry.uses / total_uses if total_uses > 0 else 0.0
        rows.append(
            [
                medal(rank),
                _short_word(entry.word),
                human(entry.uses),
                f"{bar(entry.uses, maximum)}  {percent(share)}",
            ]
        )

    table = Table(
        headers=["#", "Word", "Uses", "Share"],
        rows=rows,
        aligns=["right", "left", "right", "left"],
    )
    return View(heading=heading, table=table, footer=footer, keyboard=keyboard)


def words_by_member_view(
    *,
    members: list[MemberWords],
    total_uses: int,
    total_members: int,
    period_code: str,
    period_label: str,
    page: int,
    pages: int,
    requester_id: int,
    updated_at: datetime | None = None,
    page_size: int = 10,
    per_member: int = 5,
) -> View:
    heading = f"🗣 Words · {period_label} · By member"
    keyboard = _words_keyboard(requester_id, period_code, WORDS_BY_MEMBER, page, pages)

    footer_bits = [
        f"{human(total_members)} members",
        f"{human(total_uses)} word uses",
        f"top {per_member} words each",
    ]
    if updated_at is not None:
        footer_bits.append(f"updated {updated_at.strftime('%H:%M')}")
    footer = " · ".join(footer_bits)

    if not members:
        return View(
            heading=heading,
            empty_text="No meaningful words in this period yet — start chatting!",
            footer=footer,
            keyboard=keyboard,
        )

    rows: list[list[str]] = []
    for member in members:
        name = display_name(member.username, member.first_name, member.user_id)
        words = " · ".join(
            f"«{_short_word(word.word)}» ×{human(word.uses)}"
            for word in member.words[:per_member]
        )
        rows.append([name, words or "—", human(member.total_uses)])

    table = Table(
        headers=["Member", "Most used words", "Uses"],
        rows=rows,
        aligns=["left", "left", "right"],
    )
    return View(heading=heading, table=table, footer=footer, keyboard=keyboard)


def me_view(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    stats: list[MeStat],
    favourite_hour: int | None,
    spark_values: Sequence[float],
    requester_id: int,
    spark_days: int = 14,
) -> View:
    name = display_name(username, first_name, user_id)
    heading = f"👤 {name}"

    rows = []
    for stat in stats:
        rank = f"#{stat.rank} / {stat.total_users}" if stat.rank else "—"
        rows.append([stat.label, human(stat.messages), rank])
    table = Table(headers=["Period", "Messages", "Rank"], rows=rows, aligns=["left", "right", "right"])

    paragraphs: list[str] = []
    if favourite_hour is not None:
        paragraphs.append(f"🕐 Peak hour: {favourite_hour:02d}:00")

    spark = sparkline(spark_values)
    if spark:
        paragraphs.append(f"📈 Last {spark_days} days: {spark}")

    keyboard: Keyboard = [[Button(text="🏆 Leaderboard", callback_data=encode_top(requester_id, "7d", "m", 0))]]
    return View(heading=heading, paragraphs=paragraphs, table=table, keyboard=keyboard)


def settings_view(
    *,
    chat_title: str,
    tz: str,
    collecting: bool,
    only_requester: bool,
    requester_id: int,
) -> View:
    heading = f"⚙️ Settings · {chat_title}"
    paragraphs = [
        f"🧭 Timezone: {tz}",
        f"📥 Collection: {'active' if collecting else 'paused'}",
        f"🔒 Only requester can use buttons: {'on' if only_requester else 'off'}",
    ]
    keyboard: Keyboard = [
        [
            Button(
                text="▶️ Resume" if not collecting else "⏸ Pause",
                callback_data=encode_setting(requester_id, FIELD_COLLECTING, "0" if collecting else "1"),
                style="danger" if collecting else "success",
            )
        ],
        [
            Button(
                text="🔓 Allow everyone" if only_requester else "🔒 Only requester",
                callback_data=encode_setting(
                    requester_id, FIELD_ONLY_REQUESTER, "0" if only_requester else "1"
                ),
            )
        ],
    ]
    footer = "Admins only. Timezone can be changed with /settings tz <Zone/Name>."
    return View(heading=heading, paragraphs=paragraphs, footer=footer, keyboard=keyboard)


def help_view(*, is_admin: bool = False) -> View:
    heading = "❓ Yapboard — chat activity leaderboard"
    paragraphs = [
        "I silently count messages in this chat and show a leaderboard when asked. "
        "I never store message text — only aggregated counters and word "
        "frequencies.",
        "• /top — leaderboard (period & metric buttons)\n"
        "• /words — most used meaningful words (total / by member)\n"
        "• /me — your personal card\n"
        "• /hours — time-of-day board\n"
        "• /stats — chat summary\n"
        "• /optout · /optin — stop or resume counting you\n"
        "• /forgetme — wipe your data in this chat",
    ]
    if is_admin:
        paragraphs.append("Admin: /settings, /pause, /resume, and /settings tz <Zone/Name>.")
    return View(heading=heading, paragraphs=paragraphs)


def forget_confirm_view(*, requester_id: int) -> View:
    return View(
        heading="🧹 Forget me",
        paragraphs=[
            "This deletes all counters collected about you in this chat. "
            "This cannot be undone."
        ],
        keyboard=[
            [
                Button(text="✅ Delete my data", callback_data=encode_forget(requester_id, True), style="danger"),
                Button(text="Cancel", callback_data=encode_forget(requester_id, False)),
            ]
        ],
    )


def error_view(message: str) -> View:
    return View(heading="⚠️ Oops", paragraphs=[message])


HOUR_BUCKETS: list[tuple[str, range]] = [
    ("🌙 Night 00–05", range(0, 6)),
    ("☀️ Morning 06–11", range(6, 12)),
    ("🌤 Afternoon 12–17", range(12, 18)),
    ("🌆 Evening 18–23", range(18, 24)),
]


def hours_view(*, histogram: Sequence[int], period_label: str, peak_hour: int | None) -> View:
    heading = f"🕐 Time of day · {period_label}"
    total = sum(histogram)
    values = [(label, sum(histogram[hour] for hour in hours)) for label, hours in HOUR_BUCKETS]
    maximum = max((value for _, value in values), default=0)
    rows = [
        [label, human(value), f"{bar(value, maximum)}  {percent(value / total if total else 0)}"]
        for label, value in values
    ]
    table = Table(headers=["Part of day", "Messages", "Share"], rows=rows, aligns=["left", "right", "left"])
    if peak_hour is not None and total > 0:
        footer = f"Peak hour: {peak_hour:02d}:00 · {human(total)} messages"
    else:
        footer = "Not enough data yet."
    return View(heading=heading, table=table, footer=footer)


def stats_view(
    *,
    total_messages: int,
    active_users: int,
    busiest_day: date | None,
    busiest_hour: int | None,
    histogram: Sequence[int],
    period_label: str,
) -> View:
    heading = f"📊 Chat summary · {period_label}"
    paragraphs = [
        f"Total messages: {human(total_messages)}",
        f"Active members: {human(active_users)}",
    ]
    if busiest_day is not None:
        paragraphs.append(f"Busiest day: {busiest_day.isoformat()}")
    if busiest_hour is not None:
        paragraphs.append(f"Busiest hour: {busiest_hour:02d}:00")

    maximum = max(histogram, default=0)
    ranked = sorted(
        ((hour, value) for hour, value in enumerate(histogram) if value > 0),
        key=lambda item: item[1],
        reverse=True,
    )[:8]
    rows = [
        [f"{hour:02d}:00", human(value), bar(value, maximum)]
        for hour, value in ranked
    ]
    table = Table(headers=["Hour", "Messages", "Bar"], rows=rows, aligns=["left", "right", "left"]) if rows else None
    return View(
        heading=heading,
        paragraphs=paragraphs,
        table=table,
        empty_text=None if rows else "No activity in this period yet.",
        footer="Aggregated counters and word frequencies only — no message text is stored.",
    )


__all__ = [
    "Button",
    "Keyboard",
    "Table",
    "View",
    "TopEntry",
    "MeStat",
    "WordEntry",
    "MemberWord",
    "MemberWords",
    "leaderboard_view",
    "words_total_view",
    "words_by_member_view",
    "me_view",
    "settings_view",
    "help_view",
    "forget_confirm_view",
    "error_view",
    "hours_view",
    "stats_view",
    "HOUR_BUCKETS",
    "PERIOD_LABELS",
    "METRIC_LABELS",
    "PERIOD_ORDER",
    "METRIC_ORDER",
]
