"""Rendering: neutral views -> rich blocks or HTML fallback."""

from __future__ import annotations

from .bars import bar, clean_name, display_name, human, medal, percent, sparkline
from .fallback import render as render_fallback
from .rich import render as render_rich
from .views import (
    Button,
    Keyboard,
    MemberWord,
    MemberWords,
    MeStat,
    Table,
    TopEntry,
    View,
    WordEntry,
    error_view,
    forget_confirm_view,
    help_view,
    hours_view,
    leaderboard_view,
    me_view,
    settings_view,
    stats_view,
    words_by_member_view,
    words_total_view,
)

__all__ = [
    "Button",
    "Keyboard",
    "MeStat",
    "Table",
    "TopEntry",
    "View",
    "WordEntry",
    "MemberWord",
    "MemberWords",
    "render_rich",
    "render_fallback",
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
    "bar",
    "clean_name",
    "display_name",
    "human",
    "medal",
    "percent",
    "sparkline",
]
