"""Minimal JSON-backed translations.

Only ``en`` ships today; adding ``ru.json`` and selecting it per chat is a
drop-in change (see ``PLAN.md`` §5.1).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_I18N_DIR = Path(__file__).resolve().parent
DEFAULT_LANG = "en"


@lru_cache
def _load(lang: str) -> dict[str, str]:
    path = _I18N_DIR / f"{lang}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def translate(key: str, lang: str = DEFAULT_LANG, /, **kwargs: object) -> str:
    catalogue = _load(lang) or _load(DEFAULT_LANG)
    template = catalogue.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


__all__ = ["translate", "DEFAULT_LANG"]
