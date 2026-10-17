"""Router assembly."""

from __future__ import annotations

from aiogram import Router

from ..context import AppContext


def build_router(ctx: AppContext) -> Router:
    from . import common, hours, leaderboard, me, privacy, settings, stats, tracker, words

    router = Router(name="yapboard")
    # The tracker installs an outer middleware, so registration order does not
    # affect counting. Command routers are added in a natural reading order.
    tracker.setup(router, ctx)
    common.setup(router, ctx)
    leaderboard.setup(router, ctx)
    words.setup(router, ctx)
    me.setup(router, ctx)
    hours.setup(router, ctx)
    stats.setup(router, ctx)
    privacy.setup(router, ctx)
    settings.setup(router, ctx)
    return router


__all__ = ["build_router"]
