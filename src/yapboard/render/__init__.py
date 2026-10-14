"""Rendering: neutral views -> rich blocks or HTML fallback."""

from __future__ import annotations

from .bars import bar, clean_name, display_name, human, medal, percent, sparkline
from .fallback import render as render_fallback
from .rich import render as render_rich
from .views import (
    Button,
    Keyboard,
    MeStat,
    Table,
    TopEntry,
    View,
    error_view,
    forget_confirm_view,
    help_view,
    hours_view,
    leaderboard_view,
    me_view,
    settings_view,
    stats_view,
)

__all__ = [
    "Button",
    "Keyboard",
    "MeStat",
    "Table",
    "TopEntry",
    "View",
    "render_rich",
    "render_fallback",
    "leaderboard_view",
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
