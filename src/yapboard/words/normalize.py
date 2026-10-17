"""Turn message text into aggregated, meaningful word tokens.

The pipeline is intentionally conservative: it keeps content words and removes
the things that otherwise dominate a frequency board — links, mentions,
commands, emoji, numbers, laughter, pronouns, prepositions, particles and
conversational filler.

Tokens are grouped by a language-aware Snowball stem so that inflected forms
(``кот``/``кота``/``коту``, ``study``/``studies``) are counted together.  The
surface form is kept as well, so the board can display a readable word instead
of an ugly stem.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from functools import lru_cache

import snowballstemmer

from .stopwords import STOPWORDS

Token = tuple[str, str]  # (stem, display surface form)
WordCounts = Counter[Token]

# Links, e-mail addresses, mentions and bot commands are removed before
# tokenisation: their parts must not become "words".
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_MENTION_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]+")
_COMMAND_RE = re.compile(r"(?<!\w)/[A-Za-z0-9_]+")
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")

# Latin + Cyrillic words; apostrophes and hyphens are allowed inside a word.
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:['’\-][A-Za-zА-Яа-яЁё]+)*")

# Laughter/interjection patterns that survive stopword lists ("ахаха", "hahaha").
_LAUGH_RE = re.compile(
    r"(?:(?:ха|хе|хи|ах|ох|эх|ух)|(?:ha|he|hi|ah|oh|hm)){2,}",
    re.IGNORECASE,
)
_REPEAT_RE = re.compile(r"(.)\1{2,}")

_CYRILLIC_RE = re.compile(r"[а-я]")
_MIN_LENGTH = 2
_MAX_LENGTH = 40


def is_cyrillic(word: str) -> bool:
    return bool(_CYRILLIC_RE.search(word))


@lru_cache(maxsize=1)
def _stemmers() -> dict[str, object]:
    return {
        "english": snowballstemmer.stemmer("english"),
        "russian": snowballstemmer.stemmer("russian"),
    }


@lru_cache(maxsize=50_000)
def stem_word(word: str) -> str:
    """Stem a lowercase word using the appropriate Snowball algorithm."""
    language = "russian" if is_cyrillic(word) else "english"
    return _stemmers()[language].stemWord(word)  # type: ignore[attr-defined]


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_RE.sub("", text)
    text = _URL_RE.sub(" ", text)
    text = _EMAIL_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    text = _COMMAND_RE.sub(" ", text)
    return text


def _fold(word: str) -> str:
    """Case-fold, merge ``ё`` with ``е`` and drop apostrophes.

    Apostrophes are kept in the displayed surface form, but ignored for
    grouping so contractions (``don't``, ``you're``) match the stopword lists
    and ``rock'n'roll``/``rocknroll`` do not become separate entries.
    """
    return (
        word.casefold()
        .replace("ё", "е")
        .replace("'", "")
        .replace("’", "")
    )


def _is_noise(folded: str) -> bool:
    if len(folded) < _MIN_LENGTH or len(folded) > _MAX_LENGTH:
        return True
    if len(set(folded)) == 1:
        return True
    if _REPEAT_RE.search(folded):
        return True
    return bool(_LAUGH_RE.search(folded))


class WordNormalizer:
    """Extract meaningful words from a message.

    ``stemming=False`` is useful for tests or for a very lightweight mode; the
    normal path groups inflections.
    """

    def __init__(self, *, min_length: int = _MIN_LENGTH, max_length: int = _MAX_LENGTH,
                 stemming: bool = True) -> None:
        self.min_length = min_length
        self.max_length = max_length
        self.stemming = stemming

    def extract(self, text: str) -> WordCounts:
        counts: WordCounts = Counter()
        if not text:
            return counts
        for token in self.tokens(text):
            normalized = self.normalize(token)
            if normalized is not None:
                counts[normalized] += 1
        return counts

    def tokens(self, text: str) -> list[str]:
        return [match.group(0) for match in _TOKEN_RE.finditer(_clean(text))]

    def normalize(self, token: str) -> Token | None:
        folded = _fold(token)
        if len(folded) < self.min_length or len(folded) > self.max_length:
            return None
        if folded in STOPWORDS or _is_noise(folded):
            return None

        stem = stem_word(folded) if self.stemming else folded
        if not stem or stem in STOPWORDS:
            return None

        display = token.strip("-'’")[: self.max_length]
        return stem, display


__all__ = ["WordNormalizer", "WordCounts", "Token", "is_cyrillic", "stem_word"]
