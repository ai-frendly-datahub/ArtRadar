from __future__ import annotations

from artradar.nl_query import parse_query


def test_parse_query_extracts_korean_days_and_limit() -> None:
    parsed = parse_query("최근 7일 경매 뉴스 5개")

    assert parsed.days == 7
    assert parsed.limit == 5
    assert parsed.search_text == "경매 뉴스"
    assert parsed.category is None


def test_parse_query_extracts_korean_weeks_and_months() -> None:
    assert parse_query("지난 2주 전시").days == 14
    assert parse_query("최근 3개월 컬렉션").days == 90


def test_parse_query_extracts_english_time_and_top_limit() -> None:
    parsed = parse_query("last 2 weeks modern art top 3")

    assert parsed.days == 14
    assert parsed.limit == 3
    assert parsed.search_text == "modern art"


def test_parse_query_handles_singular_english_units() -> None:
    assert parse_query("last 1 day auction").days == 1
    assert parse_query("last 1 month gallery").days == 30


def test_parse_query_without_filters_preserves_cleaned_text() -> None:
    parsed = parse_query("   contemporary    sculpture   ")

    assert parsed.days is None
    assert parsed.limit is None
    assert parsed.search_text == "contemporary sculpture"


def test_parse_query_uses_earliest_time_match() -> None:
    parsed = parse_query("지난 1주 auction last 2 months top 4")

    assert parsed.days == 7
    assert parsed.limit == 4
    assert parsed.search_text == "auction last 2 months"
