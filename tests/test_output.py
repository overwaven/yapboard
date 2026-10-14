from __future__ import annotations

from datetime import UTC, datetime

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage

from yapboard.messenger import EDIT_EDITED, EDIT_UNCHANGED, Messenger
from yapboard.render import (
    MeStat,
    TopEntry,
    hours_view,
    leaderboard_view,
    me_view,
    render_fallback,
    render_rich,
    stats_view,
)

NOW = datetime(2026, 1, 10, 21, 4, tzinfo=UTC)
METHOD = SendMessage(chat_id=1, text="x")


def sample_entries(count: int = 3) -> list[TopEntry]:
    return [
        TopEntry(user_id=i + 1, username=f"user{i + 1}", first_name=None, value=100 - i * 10)
        for i in range(count)
    ]


def lb_view(count: int = 3, *, page: int = 0, pages: int = 1):
    entries = sample_entries(count)
    return leaderboard_view(
        entries=entries,
        total_activity=sum(e.value for e in entries) or 1,
        active_users=count,
        period_code="7d",
        period_label="Last 7 days",
        metric="m",
        page=page,
        pages=pages,
        requester_id=42,
        updated_at=NOW,
    )


def test_leaderboard_rich_blocks_and_buttons():
    message = render_rich(lb_view())
    assert [b.type.value for b in message.blocks] == ["heading", "table", "footer", "buttons", "buttons"]
    heading, table = message.blocks[0], message.blocks[1]
    assert "Last 7 days" in heading.text and "Messages" in heading.text
    assert table.is_striped and table.is_compact
    assert [c.text for c in table.cells[0]] == ["#", "Member", "Messages", "Share"]
    assert table.cells[0][0].is_header and table.cells[1][0].text == "🥇"
    assert table.cells[1][2].text == "100"

    styles = {b.text: b.style for b in message.blocks[3].buttons}
    assert styles["Last 7 days"] == "primary" and styles["Today"] is None

    # Pager shows up only for multi-page boards; previewing page 2 of 3.
    pager = render_rich(lb_view(page=1, pages=3)).blocks[-1]
    assert len(pager.buttons) == 3 and "2 / 3" in pager.buttons[1].text
    assert pager.buttons[0].disabled is None
    assert render_rich(lb_view(page=0, pages=3)).blocks[-1].buttons[0].disabled is not None


def test_leaderboard_empty_and_weird_names():
    empty = leaderboard_view(
        entries=[],
        total_activity=0,
        active_users=0,
        period_code="d",
        period_label="Today",
        metric="m",
        page=0,
        pages=1,
        requester_id=1,
    )
    assert any(b.type.value == "paragraph" and "No activity" in b.text for b in render_rich(empty).blocks)

    entries = [
        TopEntry(user_id=1, username=None, first_name="a" * 60, value=10),
        TopEntry(user_id=2, username="normal", first_name=None, value=5),
        TopEntry(user_id=3, username=None, first_name="\u202eRTL", value=1),
    ]
    view = leaderboard_view(
        entries=entries,
        total_activity=16,
        active_users=3,
        period_code="7d",
        period_label="Last 7 days",
        metric="m",
        page=0,
        pages=1,
        requester_id=1,
    )
    names = [render_rich(view).blocks[1].cells[i][1].text for i in (1, 2, 3)]
    assert all(len(name) <= 19 for name in names) and names[2] == "RTL"


def test_fallback_html_is_escaped():
    view = leaderboard_view(
        entries=[TopEntry(user_id=1, username="a<b>", first_name=None, value=5)],
        total_activity=5,
        active_users=1,
        period_code="7d",
        period_label="Last 7 days",
        metric="m",
        page=0,
        pages=1,
        requester_id=1,
        updated_at=NOW,
    )
    text, markup = render_fallback(view)
    assert "&lt;b&gt;" in text and "Leaderboard" in text
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]
    assert "t:1:7d:m:0" in callbacks


def test_me_hours_and_stats_views():
    me = render_rich(
        me_view(
            user_id=7,
            username="alex",
            first_name="Alex",
            stats=[MeStat("Today", 10, 2, 5), MeStat("Last 7 days", 100, 1, 5)],
            favourite_hour=21,
            spark_values=[0, 1, 2, 3],
            requester_id=7,
        )
    )
    assert me.blocks[0].text == "👤 @alex"
    assert next(b for b in me.blocks if b.type.value == "table").cells[1][2].text == "#2 / 5"
    assert any("21:00" in b.text for b in me.blocks if b.type.value == "paragraph")

    histogram = [0] * 24
    histogram[9] = 5
    histogram[21] = 10
    hours = render_rich(hours_view(histogram=histogram, period_label="Last 7 days", peak_hour=21))
    values = {row[0].text: row[1].text for row in next(b for b in hours.blocks if b.type.value == "table").cells[1:]}
    assert values["☀️ Morning 06–11"] == "5" and values["🌆 Evening 18–23"] == "10"
    assert any("21:00" in b.text for b in hours.blocks if b.type.value == "footer")

    summary = render_rich(
        stats_view(
            total_messages=10,
            active_users=2,
            busiest_day=datetime(2026, 1, 6, tzinfo=UTC).date(),
            busiest_hour=21,
            histogram=histogram,
            period_label="Last 7 days",
        )
    )
    top_row = next(b for b in summary.blocks if b.type.value == "table").cells[1]
    assert top_row[0].text == "21:00" and top_row[1].text == "10"


class FakeBot:
    def __init__(self, *, rich_error=None, edit_error=None):
        self.calls: list[tuple[str, dict]] = []
        self.rich_error = rich_error
        self.edit_error = edit_error

    async def send_rich_message(self, **kwargs):
        self.calls.append(("send_rich", kwargs))
        if self.rich_error:
            raise self.rich_error
        return "sent"

    async def send_message(self, **kwargs):
        self.calls.append(("send", kwargs))
        return "sent"

    async def edit_message_text(self, **kwargs):
        self.calls.append(("edit", kwargs))
        if self.edit_error:
            raise self.edit_error
        return True


def bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=METHOD, message=message)


async def test_messenger_fallback_remembering_and_cache():
    bot = FakeBot()
    messenger = Messenger(bot, rich_enabled=False)
    await messenger.send(-100, lb_view())
    assert bot.calls[0][0] == "send" and bot.calls[0][1]["parse_mode"] == "HTML"

    failing = FakeBot(rich_error=bad_request("Bad Request: method not found"))
    messenger = Messenger(failing, rich_enabled=True)
    await messenger.send(-100, lb_view())
    await messenger.send(-100, lb_view())
    assert [name for name, _ in failing.calls] == ["send_rich", "send", "send"]
    assert messenger.use_rich(-100) is False

    not_modified = FakeBot(edit_error=bad_request("Bad Request: message is not modified"))
    messenger = Messenger(not_modified, rich_enabled=True)
    assert await messenger.edit(-100, 5, lb_view()) == EDIT_UNCHANGED
    assert len(not_modified.calls) == 1

    cached = FakeBot()
    messenger = Messenger(cached, rich_enabled=True, cache_max=2)
    assert await messenger.edit(-100, 5, lb_view(), cache_key="7d:m:0") == EDIT_EDITED
    assert await messenger.edit(-100, 5, lb_view(), cache_key="7d:m:0") == EDIT_UNCHANGED
    assert len(cached.calls) == 1
    for message_id in range(5):
        await messenger.edit(-100, message_id, lb_view(), cache_key=f"k{message_id}", force=True)
    assert len(messenger._cache) <= 2
