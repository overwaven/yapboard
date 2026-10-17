"""Application configuration loaded from the environment / ``.env``."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    Values are read from environment variables (and an optional ``.env`` file).
    All names are case-insensitive.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = ""

    database_url: str = "postgresql://hubbub:hubbub@db:5432/hubbub"
    db_pool_min: int = 1
    db_pool_max: int = 5

    flush_interval_sec: float = 5.0
    flush_max_keys: int = 500

    page_size: int = 10
    top_cooldown_sec: float = 10.0

    rich_enabled: bool = True
    default_tz: str = "UTC"
    log_level: str = "INFO"

    # Aggregate normalized word frequencies for /words. No message text is
    # stored — only per-user word counts.
    word_stats_enabled: bool = True

    # How long a per-chat board is cached before it is re-queried (seconds).
    board_cache_ttl: float = 10.0
    # Minimum interval between two profile (username/first name) upserts per user.
    profile_refresh_sec: float = 600.0

    migrations_dir: str = ""

    # Optional webhook mode. When ``webhook_url`` is empty long polling is used.
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_path: str = "/webhook"
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    @property
    def use_webhook(self) -> bool:
        return bool(self.webhook_url)

    def require_token(self) -> str:
        if not self.bot_token:
            raise RuntimeError(
                "BOT_TOKEN is not set. Put it in the environment or in a .env file."
            )
        return self.bot_token


@lru_cache
def get_settings() -> Settings:
    return Settings()
