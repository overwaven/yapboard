"""Small helpers shared by the command handlers."""

from __future__ import annotations

from aiogram.enums import ChatType
from aiogram.types import Message

GROUP_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}


def is_group(message: Message) -> bool:
    return message.chat.type in GROUP_TYPES


def chat_title(message: Message) -> str | None:
    return message.chat.title or message.chat.full_name


_PERIOD_ALIASES = {
    "today": "d",
    "d": "d",
    "day": "d",
    "7d": "7d",
    "week": "7d",
    "w": "7d",
    "30d": "30d",
    "month": "30d",
    "m30": "30d",
    "all": "all",
    "total": "all",
}

_METRIC_ALIASES = {
    "messages": "m",
    "message": "m",
    "msg": "m",
    "msgs": "m",
    "chars": "c",
    "characters": "c",
    "media": "v",
    "mediafiles": "v",
    "files": "v",
}


def parse_top_args(text: str | None, tz_name: str) -> tuple[str, str]:
    """Parse ``/top`` arguments into ``(period_code, metric_code)``.

    Supports ``/top 7d``, ``/top 30d media`` and ``/top 2026-09-01 2026-09-30``.
    """
    from ..periods import DEFAULT_METRIC, DEFAULT_PERIOD, encode_range

    period_code = DEFAULT_PERIOD
    metric = DEFAULT_METRIC
    if not text:
        return period_code, metric

    tokens = text.split()
    dates: list = []
    for token in tokens:
        alias = token.lower()
        if alias in _PERIOD_ALIASES:
            period_code = _PERIOD_ALIASES[alias]
        elif alias in _METRIC_ALIASES:
            metric = _METRIC_ALIASES[alias]
        elif alias.startswith("r") and "-" in alias:
            period_code = alias
        else:
            from datetime import date

            try:
                dates.append(date.fromisoformat(token))
            except ValueError:
                continue

    if len(dates) >= 2:
        first, last = min(dates[:2]), max(dates[:2])
        period_code = encode_range(first, last)
    return period_code, metric
