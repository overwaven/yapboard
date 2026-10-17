from __future__ import annotations

from collections import Counter

from yapboard.words import STOPWORDS, WordNormalizer, stem_word


def tokens(text: str, *, stemming: bool = True) -> list[tuple[str, str]]:
    normalizer = WordNormalizer(stemming=stemming)
    return [token for token, count in normalizer.extract(text).items() for _ in range(count)]


def totals(text: str, *, stemming: bool = True) -> Counter[str]:
    counts: Counter[str] = Counter()
    for stem, _word in tokens(text, stemming=stemming):
        counts[stem] += 1
    return counts


def displays(text: str) -> set[str]:
    return {word.casefold() for _stem, word in tokens(text)}


def test_russian_content_words_survive_stopwords_and_laughter():
    text = "Привет, как дела? Кота видел? Коты и кота тут, ну вот это всё, ахаха!"
    counts = totals(text)
    assert counts["кот"] == 3
    assert counts["видел"] == 1
    assert counts["дел"] == 1
    words = displays(text)
    for stopword in ("привет", "как", "и", "вот", "это", "все", "ахаха", "ну"):
        assert stopword not in words


def test_english_content_words_survive_stopwords_and_stemming():
    text = (
        "The deployment was broken, lol. I really like studies and studying. "
        "Study hard!"
    )
    counts = totals(text)
    assert counts["deploy"] == 1
    assert counts["broken"] == 1
    assert counts["studi"] == 3
    assert counts["hard"] == 1
    words = displays(text)
    for stopword in ("the", "was", "lol", "really", "like", "and"):
        assert stopword not in words


def test_links_mentions_commands_numbers_and_emoji_are_ignored():
    counts = totals("Check https://example.com @alex /top 12345 😂 аааа ммм")
    assert counts == Counter({"check": 1})


def test_apostrophe_contractions_are_stopwords():
    assert totals("don't can't I'm you're thanks please") == Counter()


def test_yo_is_folded_and_laughter_variants_are_dropped():
    counts = totals("Ёж ёжик ежи ежа")
    assert counts["еж"] == 3
    assert counts["ежик"] == 1
    assert totals("хаха ахаха ахах ммм ааа") == Counter()


def test_case_is_folded():
    assert totals("Python python PYTHON") == Counter({"python": 3})


def test_stemming_can_be_disabled():
    counts = totals("кота коту", stemming=False)
    assert counts == Counter({"кота": 1, "коту": 1})


def test_stopword_lists_cover_both_languages():
    assert "the" in STOPWORDS and "и" in STOPWORDS
    assert stem_word("котами") == "кот"
    assert stem_word("studies") == "studi"
