"""Shared pytest fixtures.

Integration tests run against a real PostgreSQL instance. Point
``TEST_DATABASE_URL`` at it (a trust-auth local server is convenient)::

    TEST_DATABASE_URL=postgresql://hubbub@127.0.0.1:55432/hubbub_test

Every test starts from empty tables.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from yapboard.config import Settings
from yapboard.db import Database

DEFAULT_TEST_DSN = "postgresql://hubbub@127.0.0.1:55432/hubbub_test"


def test_dsn() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DSN)


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Database]:
    database = Database(test_dsn(), min_size=1, max_size=4)
    try:
        await database.connect()
        await database.run_migrations()
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not available: {error}")
    await database.execute(
        "TRUNCATE optouts, activity_hourly, users, chats RESTART IDENTITY CASCADE"
    )
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        bot_token="123456:TEST",
        database_url=test_dsn(),
        page_size=10,
    )
