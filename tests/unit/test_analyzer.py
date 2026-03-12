from __future__ import annotations

from datetime import UTC, datetime

import pytest

from artradar.models import Article, EntityDefinition


def _make_article(title: str = "", summary: str = "") -> Article:
    return Article(
        title=title,
        link="https://example.com/art-post",
        summary=summary,
        published=datetime.now(UTC),
        source="test",
        category="art",
    )


@pytest.mark.unit
def test_entity_match_in_title() -> None:
    from artradar.analyzer import apply_entity_rules

    articles = [_make_article(title="Painting retrospective opens at MoMA")]
    entities = [EntityDefinition(name="genre", display_name="Genre", keywords=["painting"])]

    result = apply_entity_rules(articles, entities)

    assert "genre" in result[0].matched_entities
    assert "painting" in result[0].matched_entities["genre"]


@pytest.mark.unit
def test_entity_match_case_insensitive() -> None:
    from artradar.analyzer import apply_entity_rules

    articles = [_make_article(summary="The MUSEUM hosts a major biennale this year")]
    entities = [
        EntityDefinition(name="institution", display_name="Institution", keywords=["museum"])
    ]

    result = apply_entity_rules(articles, entities)

    assert "institution" in result[0].matched_entities


@pytest.mark.unit
def test_no_match_returns_empty() -> None:
    from artradar.analyzer import apply_entity_rules

    articles = [_make_article(title="A quiet studio visit")]
    entities = [
        EntityDefinition(name="period", display_name="Period", keywords=["baroque", "renaissance"])
    ]

    result = apply_entity_rules(articles, entities)

    assert result[0].matched_entities == {}


@pytest.mark.unit
def test_empty_articles() -> None:
    from artradar.analyzer import apply_entity_rules

    result = apply_entity_rules([], [])

    assert result == []


@pytest.mark.unit
def test_multiple_entity_categories_match_same_article() -> None:
    from artradar.analyzer import apply_entity_rules

    articles = [
        _make_article(title="Contemporary painting exhibition", summary="Major museum event")
    ]
    entities = [
        EntityDefinition(name="period", display_name="Period", keywords=["contemporary"]),
        EntityDefinition(name="genre", display_name="Genre", keywords=["painting"]),
        EntityDefinition(name="institution", display_name="Institution", keywords=["museum"]),
    ]

    result = apply_entity_rules(articles, entities)

    assert set(result[0].matched_entities) == {"period", "genre", "institution"}
