"""Timezone-aware period parsing and UTC range resolution.

All period boundaries ("today", "last 7 days") are computed in the *chat's*
timezone and converted to half-open UTC intervals ``[start, end)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Short codes used in callback data. Kept tiny on purpose (<= 64 byte limit).
TODAY = "d"
WEEK = "7d"
MONTH = "30d"
ALL = "all"

PERIOD_LABELS: dict[str, str] = {
    TODAY: "Today",
    WEEK: "Last 7 days",
    MONTH: "Last 30 days",
    ALL: "All time",
}

# Metric codes -> display labels. The matching SQL column is whitelisted in
# :mod:`yapboard.stats` and never taken from user input.
METRIC_MSG = "m"
METRIC_CHARS = "c"
METRIC_MEDIA = "v"

METRIC_LABELS: dict[str, str] = {
    METRIC_MSG: "Messages",
    METRIC_CHARS: "Characters",
    METRIC_MEDIA: "Media",
}

DEFAULT_PERIOD = WEEK
DEFAULT_METRIC = METRIC_MSG

PERIOD_ORDER = (TODAY, WEEK, MONTH, ALL)
METRIC_ORDER = (METRIC_MSG, METRIC_CHARS, METRIC_MEDIA)

_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def zone(tz: str | None) -> ZoneInfo:
    """Return a :class:`ZoneInfo`, falling back to UTC for unknown names."""
    if not tz:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_midnight(day: date, tz: ZoneInfo) -> datetime:
    """UTC instant of the start of the local day ``day`` in ``tz``."""
    return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)


def _b36(number: int) -> str:
    if number < 0:
        raise ValueError("negative numbers are not supported")
    if number == 0:
        return "0"
    out = []
    while number:
        number, rem = divmod(number, 36)
        out.append(_B36[rem])
    return "".join(reversed(out))


def encode_range(first: date, last: date) -> str:
    return f"r{_b36(first.toordinal())}-{_b36(last.toordinal())}"


def parse_range(code: str) -> tuple[date, date]:
    body = code[1:]
    start_s, _, end_s = body.partition("-")
    first = date.fromordinal(int(start_s, 36))
    last = date.fromordinal(int(end_s, 36))
    if last < first:
        first, last = last, first
    return first, last


@dataclass(frozen=True, slots=True)
class Period:
    """A resolved period with an optional UTC ``[start, end)`` range."""

    code: str
    kind: str  # 'd' | '7d' | '30d' | 'all' | 'range'
    label: str
    start: datetime | None
    end: datetime | None

    @property
    def bounded(self) -> bool:
        return self.start is not None and self.end is not None

    @property
    def days(self) -> int:
        """Approximate length in days (used for previous-period trends)."""
        if not self.bounded:
            return 0
        assert self.start is not None and self.end is not None
        return max(1, round((self.end - self.start).total_seconds() / 86400))

    def as_utc(self) -> tuple[datetime, datetime] | None:
        if not self.bounded:
            return None
        assert self.start is not None and self.end is not None
        return self.start, self.end


def resolve(code: str, tz_name: str, now: datetime | None = None) -> Period:
    """Resolve ``code`` into a :class:`Period` relative to ``now`` (UTC)."""
    tz = zone(tz_name)
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    local = moment.astimezone(tz)
    today = local.date()

    if code == ALL:
        return Period(code=ALL, kind=ALL, label=PERIOD_LABELS[ALL], start=None, end=None)

    if code.startswith("r"):
        try:
            first, last = parse_range(code)
        except (ValueError, IndexError):
            return resolve(DEFAULT_PERIOD, tz_name, moment)
        return Period(
            code=code,
            kind="range",
            label=f"{first.isoformat()} – {last.isoformat()}",
            start=local_midnight(first, tz),
            end=local_midnight(last + timedelta(days=1), tz),
        )

    if code == TODAY:
        first, last = today, today
    elif code == WEEK:
        first, last = today - timedelta(days=6), today
    elif code == MONTH:
        first, last = today - timedelta(days=29), today
    else:
        # Unknown code: degrade to the default period rather than failing.
        return resolve(DEFAULT_PERIOD, tz_name, moment)

    return Period(
        code=code,
        kind=code,
        label=PERIOD_LABELS.get(code, code),
        start=local_midnight(first, tz),
        end=local_midnight(last + timedelta(days=1), tz),
    )


def previous(period: Period, tz_name: str, now: datetime | None = None) -> Period | None:
    """The equal-length period immediately before ``period`` (for trends)."""
    if not period.bounded or period.kind in (ALL, "range"):
        return None
    tz = zone(tz_name)
    length = period.days
    assert period.start is not None and period.end is not None
    end_local = period.start.astimezone(tz).date()
    first = end_local - timedelta(days=length)
    last = end_local - timedelta(days=1)
    return Period(
        code=encode_range(first, last),
        kind="range",
        label=f"{first.isoformat()} – {last.isoformat()}",
        start=local_midnight(first, tz),
        end=local_midnight(last + timedelta(days=1), tz),
    )


def period_buttons() -> list[tuple[str, str]]:
    """(code, label) pairs in display order."""
    return [(code, PERIOD_LABELS[code]) for code in PERIOD_ORDER]


def metric_buttons() -> list[tuple[str, str]]:
    return [(code, METRIC_LABELS[code]) for code in METRIC_ORDER]


def is_valid_metric(metric: str) -> bool:
    return metric in METRIC_LABELS
