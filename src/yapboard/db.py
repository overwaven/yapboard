"""asyncpg connection pool and a tiny forward-only migration runner."""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

log = logging.getLogger(__name__)

_SCHEMA_MIGRATIONS = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def default_migrations_dir() -> Path:
    """Locate the ``migrations`` directory both in the repo and in a wheel."""
    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / "migrations",
        here.parents[2] / "migrations",  # <repo>/src/yapboard/db.py -> <repo>
        here.parents[1] / "migrations",
        Path("/app/migrations"),
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


class Database:
    """Thin wrapper around an :class:`asyncpg.Pool`."""

    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 5) -> None:
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._pool

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=self.min_size,
                max_size=self.max_size,
                command_timeout=30,
            )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    # -- convenience helpers -------------------------------------------------
    async def fetch(self, query: str, *args: object) -> list[asyncpg.Record]:
        return await self.pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: object) -> asyncpg.Record | None:
        return await self.pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: object) -> object:
        return await self.pool.fetchval(query, *args)

    async def execute(self, query: str, *args: object) -> str:
        return await self.pool.execute(query, *args)

    # -- migrations ----------------------------------------------------------
    async def run_migrations(self, migrations_dir: str | Path | None = None) -> list[str]:
        """Apply every ``*.sql`` file that has not been applied yet.

        Returns the list of newly applied versions.
        """
        directory = Path(migrations_dir) if migrations_dir else default_migrations_dir()
        if not directory.is_dir():
            raise FileNotFoundError(f"migrations directory not found: {directory}")

        applied: list[str] = []
        async with self.pool.acquire() as conn:
            await conn.execute(_SCHEMA_MIGRATIONS)
            done = {
                row["version"]
                for row in await conn.fetch("SELECT version FROM schema_migrations")
            }
            for path in sorted(directory.glob("*.sql")):
                version = path.stem
                if version in done:
                    continue
                sql = path.read_text(encoding="utf-8")
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)", version
                    )
                applied.append(version)
                log.info("applied migration %s", version)
        return applied
