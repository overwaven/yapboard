"""Shared application state passed to every handler."""

from __future__ import annotations

from dataclasses import dataclass

from .collector import Collector
from .config import Settings
from .db import Database
from .messenger import Messenger
from .state import AdminCache, ChatStore, Cooldown, OptoutStore


@dataclass(slots=True)
class AppContext:
    settings: Settings
    db: Database
    collector: Collector
    messenger: Messenger
    chats: ChatStore
    optouts: OptoutStore
    cooldown: Cooldown
    admins: AdminCache

    @property
    def page_size(self) -> int:
        return self.settings.page_size
