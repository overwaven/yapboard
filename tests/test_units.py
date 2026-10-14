from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from yapboard import callbacks, periods
from yapboard.render.bars import bar, clean_name, display_name, human, medal, percent, sparkline


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_periods_timezones_and_dst():
    period = periods.resolve("d", "UTC", now=utc(2026, 1, 10, 15, 30))
    assert (period.start, period.end) == (utc(2026, 1, 10), utc(2026, 1, 11))

    week = periods.resolve("7d", "UTC", now=utc(2026, 1, 10, 15, 30))
    assert week.start == utc(2026, 1, 4) and week.end == utc(2026, 1, 11) and week.days == 7

    # 01:00 UTC is 04:00 in Moscow, so the local day already started.
    moscow = periods.resolve("d", "Europe/Moscow", now=utc(2026, 1, 10, 1))
    assert (moscow.start, moscow.end) == (utc(2026, 1, 9, 21), utc(2026, 1, 10, 21))

    spring = periods.resolve("d", "Europe/Berlin", now=utc(2026, 3, 29, 12))
    fall = periods.resolve("d", "Europe/Berlin", now=utc(2026, 10, 25, 12))
    assert spring.end - spring.start == timedelta(hours=23)
    assert fall.end - fall.start == timedelta(hours=25)


def test_periods_ranges_and_fallbacks():
    assert periods.resolve("all", "UTC").start is None

    code = periods.encode_range(date(2026, 9, 1), date(2026, 9, 30))
    assert periods.parse_range(code) == (date(2026, 9, 1), date(2026, 9, 30))
    rng = periods.resolve(code, "UTC", now=utc(2026, 10, 1))
    assert (rng.start, rng.end) == (utc(2026, 9, 1), utc(2026, 10, 1))

    assert periods.resolve("banana", "UTC", now=utc(2026, 1, 10)).code == periods.DEFAULT_PERIOD
    assert periods.resolve("rXX", "UTC", now=utc(2026, 1, 10)).code == periods.DEFAULT_PERIOD

    previous = periods.previous(periods.resolve("d", "UTC", now=utc(2026, 1, 10, 9)), "UTC")
    assert (previous.start, previous.end) == (utc(2026, 1, 9), utc(2026, 1, 10))


def test_callbacks_roundtrip_and_size():
    parsed = callbacks.decode(callbacks.encode_top(42, "7d", "m", 2))
    assert parsed is not None
    assert (parsed.kind, parsed.user_id, parsed.period, parsed.metric, parsed.page) == (
        callbacks.TOP,
        42,
        "7d",
        "m",
        2,
    )
    assert callbacks.decode(callbacks.encode_setting(7, callbacks.FIELD_COLLECTING, "1")).truthy_value
    assert callbacks.decode(callbacks.encode_forget(5, True)).value == "yes"
    assert callbacks.decode(callbacks.encode_noop()).kind == callbacks.NOOP

    payload = callbacks.encode_top(999999999999, "rb3a-3zz", "v", 99)
    assert len(payload.encode()) <= callbacks.MAX_CALLBACK_BYTES


def test_callbacks_reject_malformed():
    for data in (
        None,
        "",
        "x",
        "t:1:7d:m",
        "t:x:7d:m:0",
        "t:1:7d:m:-1",
        "s:1",
        "f:1:maybe",
        "t:" + "1" * 100,
    ):
        assert callbacks.decode(data) is None, data


def test_bars_and_numbers():
    assert bar(0, 10) == "▱" * 8
    assert bar(10, 10) == "▰" * 8
    assert bar(5, 10) == "▰▰▰▰▱▱▱▱"
    assert bar(1, 1000).startswith("▰")
    assert bar(5, 0) == "▱" * 8

    assert sparkline([]) == ""
    assert sparkline([3, 3, 3]) == "▁▁▁"
    assert sparkline([0, 1, 2, 3, 4, 5, 6, 7]) == "▁▂▃▄▅▆▇█"
    assert len(sparkline(list(range(30)), width=14)) == 14

    assert percent(0.314) == "31%"
    assert human(1842) == "1 842"
    assert medal(1) == "🥇" and medal(4) == "4"


def test_display_names():
    assert clean_name("\u202eabc\u200f") == "abc"
    truncated = clean_name("a" * 50, limit=18)
    assert len(truncated) == 18 and truncated.endswith("…")
    assert display_name("alex", "Alex", 1) == "@alex"
    assert display_name(None, "Alex", 1) == "Alex"
    assert display_name(None, None, 77) == "user 77"
