from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from importlib import import_module
from typing import Protocol, cast

from .models import Article, EntityDefinition


class _KoreanAnalyzerLike(Protocol):
    _kiwi: object | None

    def match_keyword(self, text: str, keyword: str) -> bool: ...


def _load_korean_analyzer_constructor() -> type[_KoreanAnalyzerLike] | None:
    try:
        korean_analyzer_module = import_module("radar_core.common.korean_analyzer")
    except ModuleNotFoundError:
        return None

    korean_analyzer_constructor = getattr(korean_analyzer_module, "KoreanAnalyzer", None)
    if korean_analyzer_constructor is None:
        return None

    return cast(type[_KoreanAnalyzerLike], korean_analyzer_constructor)


_KOREAN_ANALYZER_CONSTRUCTOR = _load_korean_analyzer_constructor()
_korean_analyzer: _KoreanAnalyzerLike | None = None
_korean_analyzer_initialized = False
_LOW_SIGNAL_ASCII_KEYWORDS = {
    "a",
    "after",
    "again",
    "all",
    "also",
    "an",
    "and",
    "any",
    "about",
    "are",
    "around",
    "as",
    "at",
    "away",
    "back",
    "be",
    "been",
    "being",
    "before",
    "but",
    "by",
    "can",
    "come",
    "could",
    "day",
    "did",
    "do",
    "does",
    "down",
    "during",
    "each",
    "even",
    "every",
    "few",
    "find",
    "first",
    "for",
    "from",
    "further",
    "get",
    "goes",
    "good",
    "great",
    "had",
    "hand",
    "has",
    "have",
    "he",
    "her",
    "here",
    "him",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "large",
    "last",
    "latest",
    "less",
    "life",
    "like",
    "little",
    "looking",
    "long",
    "made",
    "make",
    "many",
    "may",
    "me",
    "might",
    "month",
    "more",
    "most",
    "my",
    "new",
    "next",
    "now",
    "of",
    "off",
    "only",
    "on",
    "once",
    "one",
    "or",
    "our",
    "out",
    "over",
    "own",
    "part",
    "place",
    "people",
    "public",
    "recent",
    "recently",
    "really",
    "right",
    "said",
    "say",
    "says",
    "set",
    "she",
    "since",
    "small",
    "so",
    "some",
    "still",
    "that",
    "the",
    "their",
    "there",
    "then",
    "these",
    "than",
    "think",
    "this",
    "those",
    "through",
    "time",
    "today",
    "to",
    "too",
    "took",
    "top",
    "two",
    "until",
    "up",
    "upcoming",
    "use",
    "very",
    "was",
    "way",
    "we",
    "week",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "will",
    "with",
    "work",
    "works",
    "world",
    "would",
    "year",
    "years",
    "you",
    "young",
    "your",
}


def _is_ascii_only(keyword: str) -> bool:
    return all(ord(char) < 128 for char in keyword)


def _is_low_signal_ascii_keyword(keyword: str) -> bool:
    return _is_ascii_only(keyword) and (
        keyword.casefold() in _LOW_SIGNAL_ASCII_KEYWORDS or keyword.isdigit()
    )


@lru_cache(maxsize=2048)
def _compile_ascii_keyword_pattern(keyword: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)


def _get_korean_analyzer() -> _KoreanAnalyzerLike | None:
    global _korean_analyzer
    global _korean_analyzer_initialized

    if _korean_analyzer_initialized:
        return _korean_analyzer

    _korean_analyzer_initialized = True
    if _KOREAN_ANALYZER_CONSTRUCTOR is not None:
        _korean_analyzer = _KOREAN_ANALYZER_CONSTRUCTOR()

    return _korean_analyzer


def _matches_non_ascii_keyword(text: str, text_lower: str, keyword: str) -> bool:
    korean_analyzer = _get_korean_analyzer()
    if korean_analyzer is not None and getattr(korean_analyzer, "_kiwi", None) is not None:
        return korean_analyzer.match_keyword(text, keyword)

    return keyword in text_lower


def apply_entity_rules(
    articles: Iterable[Article], entities: list[EntityDefinition]
) -> list[Article]:
    """Attach matched entity keywords to each article via simple keyword search."""
    analyzed: list[Article] = []
    normalized_entities: list[tuple[EntityDefinition, list[tuple[str, re.Pattern[str] | None]]]] = (
        []
    )
    for entity in entities:
        normalized_keywords: list[tuple[str, re.Pattern[str] | None]] = []
        for keyword in entity.keywords:
            normalized_keyword = keyword.lower()
            if not normalized_keyword:
                continue
            if _is_low_signal_ascii_keyword(normalized_keyword):
                continue

            pattern = (
                _compile_ascii_keyword_pattern(normalized_keyword)
                if _is_ascii_only(normalized_keyword)
                else None
            )
            normalized_keywords.append((normalized_keyword, pattern))

        normalized_entities.append((entity, normalized_keywords))

    for article in articles:
        haystack = "\n".join(
            part for part in (article.title, article.summary, article.source) if part
        )
        haystack_lower = haystack.lower()
        matches: dict[str, list[str]] = {}
        for entity, keywords_with_patterns in normalized_entities:
            hit_keywords = [
                keyword
                for keyword, pattern in keywords_with_patterns
                if (
                    pattern.search(haystack)
                    if pattern is not None
                    else _matches_non_ascii_keyword(haystack, haystack_lower, keyword)
                )
            ]
            if hit_keywords:
                matches[entity.name] = hit_keywords
        article.matched_entities = matches
        analyzed.append(article)

    return analyzed
