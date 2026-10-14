"""Pure-text visual helpers: bars, sparklines, number formatting."""

from __future__ import annotations

from collections.abc import Sequence

FILLED = "▰"
EMPTY = "▱"

SPARK_CHARS = "▁▂▃▄▅▆▇█"

# Characters that make display names look broken (bidi controls, zero-width).
_STRIP = dict.fromkeys(
    [
        0x200B,  # zero width space
        0x200C,
        0x200D,
        0x200E,  # LRM
        0x200F,  # RLM
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,  # bidi overrides
        0x2066,
        0x2067,
        0x2068,
        0x2069,
        0xFEFF,  # BOM
    ],
    None,
)


def bar(value: float, maximum: float, width: int = 8) -> str:
    """A ``▰▱`` bar of ``width`` cells representing ``value`` / ``maximum``."""
    if width <= 0:
        return ""
    if maximum <= 0 or value <= 0:
        return EMPTY * width
    filled = round(value / maximum * width)
    filled = max(1, min(width, filled))
    return FILLED * filled + EMPTY * (width - filled)


def sparkline(values: Sequence[float], width: int | None = None) -> str:
    """Map a series of values onto the ``▁▂▃▄▅▆▇█`` ramp."""
    if not values:
        return ""
    series = list(values)
    if width is not None and width > 0 and len(series) > width:
        # Keep the most recent `width` points.
        series = series[-width:]
    low = min(series)
    high = max(series)
    span = high - low
    top = len(SPARK_CHARS) - 1
    if span <= 0:
        return SPARK_CHARS[0] * len(series)
    out = []
    for value in series:
        index = round((value - low) / span * top)
        out.append(SPARK_CHARS[max(0, min(top, index))])
    return "".join(out)


def percent(fraction: float) -> str:
    return f"{max(0.0, fraction) * 100:.0f}%"


def human(number: int | float) -> str:
    """Thousands-separated integer, e.g. ``1842 -> "1 842"``."""
    return f"{int(number):,}".replace(",", " ")


def clean_name(name: str | None, *, limit: int = 18, fallback: str = "—") -> str:
    """Neutralise weird display names and truncate for a compact table."""
    if not name:
        return fallback
    text = name.translate(_STRIP)
    text = "".join(ch for ch in text if ch == "\n" or not (0x00 <= ord(ch) <= 0x1F))
    text = text.strip()
    if not text:
        return fallback
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def display_name(
    username: str | None, first_name: str | None, user_id: int, *, limit: int = 18
) -> str:
    if username:
        return clean_name("@" + username, limit=limit + 1, fallback=f"user {user_id}")
    if first_name:
        return clean_name(first_name, limit=limit, fallback=f"user {user_id}")
    return f"user {user_id}"


def medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, str(rank))
