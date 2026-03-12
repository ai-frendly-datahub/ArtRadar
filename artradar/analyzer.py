from __future__ import annotations

from collections.abc import Iterable

from .models import Article, EntityDefinition


def apply_entity_rules(
    articles: Iterable[Article], entities: list[EntityDefinition]
) -> list[Article]:
    analyzed: list[Article] = []
    lowered_entities = [
        EntityDefinition(
            name=entity.name,
            display_name=entity.display_name,
            keywords=[keyword.lower() for keyword in entity.keywords],
        )
        for entity in entities
    ]

    for article in articles:
        haystack = f"{article.title}\n{article.summary}".lower()
        matches: dict[str, list[str]] = {}
        for index, entity in enumerate(entities):
            lowered_entity = lowered_entities[index]
            hit_keywords = [
                keyword for keyword in lowered_entity.keywords if keyword and keyword in haystack
            ]
            if hit_keywords:
                matches[entity.name] = hit_keywords
        article.matched_entities = matches
        analyzed.append(article)

    return analyzed
