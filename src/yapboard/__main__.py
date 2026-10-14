"""Entry point: build the bot and run polling or a webhook."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .collector import Collector
from .config import Settings, get_settings
from .context import AppContext
from .db import Database
from .handlers import build_router
from .messenger import Messenger
from .state import AdminCache, ChatStore, Cooldown, OptoutStore

log = logging.getLogger("yapboard")

ALLOWED_UPDATES = ["message", "callback_query", "my_chat_member"]


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def build_context(settings: Settings, bot: Bot, db: Database) -> AppContext:
    collector = Collector(
        flush_interval=settings.flush_interval_sec,
        max_keys=settings.flush_max_keys,
        profile_refresh_sec=settings.profile_refresh_sec,
    )
    messenger = Messenger(
        bot,
        rich_enabled=settings.rich_enabled,
        cache_ttl=settings.board_cache_ttl,
    )
    return AppContext(
        settings=settings,
        db=db,
        collector=collector,
        messenger=messenger,
        chats=ChatStore(db, default_tz=settings.default_tz),
        optouts=OptoutStore(db),
        cooldown=Cooldown(settings.top_cooldown_sec),
        admins=AdminCache(bot),
    )


async def _health_loop(ctx: AppContext, stop: asyncio.Event, every: float = 30.0) -> None:
    while not stop.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=every)
        collector = ctx.collector
        log.info(
            "health: pending=%d keys, profiles=%d, rows_flushed=%d, flushes=%d, last_flush=%.1fms",
            collector.pending_keys,
            collector.pending_profiles,
            collector.rows_flushed,
            collector.flushes,
            collector.last_flush_ms,
        )


async def run_webhook(ctx: AppContext, bot: Bot, dp: Dispatcher, stop: asyncio.Event) -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler
    from aiohttp import web

    settings = ctx.settings
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret or None,
    ).register(app, path=settings.webhook_path)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)
    await site.start()
    webhook_url = settings.webhook_url.rstrip("/") + settings.webhook_path
    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.webhook_secret or None,
        allowed_updates=ALLOWED_UPDATES,
        drop_pending_updates=False,
    )
    log.info("webhook listening on %s:%s -> %s", settings.webhook_host, settings.webhook_port, webhook_url)
    try:
        await stop.wait()
    finally:
        await bot.delete_webhook()
        await runner.cleanup()


async def run(settings: Settings) -> None:
    configure_logging(settings.log_level)
    token = settings.require_token()

    db = Database(settings.database_url, min_size=settings.db_pool_min, max_size=settings.db_pool_max)
    await db.connect()
    applied = await db.run_migrations(settings.migrations_dir or None)
    if applied:
        log.info("applied %d migration(s): %s", len(applied), ", ".join(applied))

    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    ctx = build_context(settings, bot, db)

    dp = Dispatcher()
    dp.include_router(build_router(ctx))

    me = await bot.get_me()
    log.info("starting as @%s (rich=%s)", me.username, ctx.messenger.rich_available())

    stop = asyncio.Event()
    collector_task = asyncio.create_task(ctx.collector.run(db, stop), name="collector")
    health_task = asyncio.create_task(_health_loop(ctx, stop), name="health")

    try:
        if settings.use_webhook:
            await run_webhook(ctx, bot, dp, stop)
        else:
            await dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES)
    finally:
        stop.set()
        await asyncio.gather(collector_task, health_task, return_exceptions=True)
        await bot.session.close()
        await db.close()
        log.info("shutdown complete")


def main() -> None:
    settings = get_settings()
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        pass
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
