"""Compact, testable ``callback_data`` encoding/decoding.

Telegram limits ``callback_data`` to 64 bytes, so the format is intentionally
terse. Every board carries the requesting user id so the "only requester may
press" setting can be enforced (or ignored) without extra round-trips::

    top:    t:<uid>:<period>:<metric>:<page>
    setting:s:<uid>:<field>:<value>
    forget: f:<uid>:<yes|no>
    noop:   n
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_CALLBACK_BYTES = 64

# Callback kinds
TOP = "top"
SETTING = "setting"
FORGET = "forget"
NOOP = "noop"

# Settings fields
FIELD_COLLECTING = "collecting"
FIELD_ONLY_REQUESTER = "only_requester"
FIELDS = (FIELD_COLLECTING, FIELD_ONLY_REQUESTER)


@dataclass(frozen=True, slots=True)
class Callback:
    kind: str
    user_id: int | None = None
    period: str | None = None
    metric: str | None = None
    page: int = 0
    field: str | None = None
    value: str | None = None

    @property
    def truthy_value(self) -> bool:
        return self.value in ("1", "true", "yes")


def encode_top(user_id: int, period: str, metric: str, page: int) -> str:
    return f"t:{user_id}:{period}:{metric}:{page}"


def encode_setting(user_id: int, field: str, value: str) -> str:
    return f"s:{user_id}:{field}:{value}"


def encode_forget(user_id: int, confirm: bool) -> str:
    return f"f:{user_id}:{'yes' if confirm else 'no'}"


NOOP_DATA = "n"


def encode_noop() -> str:
    return NOOP_DATA


def _to_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def decode(data: str | None) -> Callback | None:
    """Parse callback data. Returns ``None`` for anything unrecognised."""
    if not data or len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        return None

    if data == NOOP_DATA:
        return Callback(kind=NOOP)

    parts = data.split(":")
    head = parts[0]

    if head == "t" and len(parts) == 5:
        uid = _to_int(parts[1])
        period, metric, page = parts[2], parts[3], _to_int(parts[4])
        if uid is None or page is None or not period or not metric or page < 0:
            return None
        return Callback(kind=TOP, user_id=uid, period=period, metric=metric, page=page)

    if head == "s" and len(parts) == 4:
        uid = _to_int(parts[1])
        field, value = parts[2], parts[3]
        if uid is None or not field or not value:
            return None
        return Callback(kind=SETTING, user_id=uid, field=field, value=value)

    if head == "f" and len(parts) == 3:
        uid = _to_int(parts[1])
        if uid is None or parts[2] not in ("yes", "no"):
            return None
        return Callback(kind=FORGET, user_id=uid, value=parts[2])

    return None
