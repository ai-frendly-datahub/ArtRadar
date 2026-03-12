from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from artradar.models import Article, CategoryConfig, EntityDefinition, Source


@pytest.fixture
def tmp_duckdb() -> Path:
    """Temporary DuckDB database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_art_data.duckdb"
        yield db_path


@pytest.fixture
def tmp_search_db() -> Path:
    """Temporary SQLite FTS5 search database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_search_index.db"
        yield db_path


@pytest.fixture
def sample_sources() -> list[Source]:
    """Sample art-domain sources (1 RSS + 1 API)."""
    from artradar.models import Source

    return [
        Source(
            name="월간미술",
            type="rss",
            url="https://monthlyart.com/feed/",
        ),
        Source(
            name="Metropolitan Museum",
            type="met_museum",
            url="https://collectionapi.metmuseum.org/public/collection/v1/objects",
        ),
    ]


@pytest.fixture
def sample_articles() -> list[Article]:
    """Sample art-domain articles for testing."""
    from artradar.models import Article

    return [
        Article(
            title="Contemporary Art Market Trends 2024",
            link="https://monthlyart.com/article/contemporary-trends",
            summary="Analysis of emerging trends in contemporary art market with focus on digital art and NFT integration.",
            published=datetime(2024, 3, 10, 12, 0, 0, tzinfo=UTC),
            source="월간미술",
            category="art",
            matched_entities={
                "genre": ["digital art", "contemporary"],
                "market": ["market trend", "investment"],
            },
            collected_at=datetime(2024, 3, 12, 10, 0, 0, tzinfo=UTC),
        ),
        Article(
            title="Renaissance Masterpieces Exhibition Opens",
            link="https://news.artnet.com/exhibition-renaissance",
            summary="Major museum exhibition showcasing Renaissance paintings and sculptures from private collections.",
            published=datetime(2024, 3, 9, 14, 30, 0, tzinfo=UTC),
            source="Artnet News",
            category="art",
            matched_entities={
                "period": ["renaissance"],
                "institution": ["museum", "exhibition"],
                "genre": ["painting", "sculpture"],
            },
            collected_at=datetime(2024, 3, 12, 10, 0, 0, tzinfo=UTC),
        ),
        Article(
            title="Art Conservation Techniques in Modern Museums",
            link="https://www.artnews.com/conservation-techniques",
            summary="Exploring cutting-edge conservation and restoration methods used by leading museums worldwide.",
            published=datetime(2024, 3, 8, 9, 15, 0, tzinfo=UTC),
            source="ARTnews",
            category="art",
            matched_entities={
                "institution": ["museum", "conservator", "restoration"],
                "topic": ["technique", "preservation"],
            },
            collected_at=datetime(2024, 3, 12, 10, 0, 0, tzinfo=UTC),
        ),
    ]


@pytest.fixture
def sample_entities() -> list[EntityDefinition]:
    """Sample art-domain entity definitions."""
    from artradar.models import EntityDefinition

    return [
        EntityDefinition(
            name="genre",
            display_name="Art Genre",
            keywords=[
                "painting",
                "sculpture",
                "drawing",
                "printmaking",
                "photography",
                "installation",
                "video art",
                "digital art",
                "performance art",
                "conceptual art",
            ],
        ),
        EntityDefinition(
            name="period",
            display_name="Art Period",
            keywords=[
                "renaissance",
                "baroque",
                "rococo",
                "neoclassical",
                "romantic",
                "impressionism",
                "post-impressionism",
                "modernism",
                "contemporary",
                "ancient",
            ],
        ),
        EntityDefinition(
            name="market",
            display_name="Art Market",
            keywords=[
                "auction",
                "gallery",
                "collector",
                "investment",
                "valuation",
                "provenance",
                "appraisal",
                "sale",
                "acquisition",
                "market trend",
            ],
        ),
        EntityDefinition(
            name="institution",
            display_name="Art Institution",
            keywords=[
                "museum",
                "gallery",
                "foundation",
                "institute",
                "academy",
                "biennale",
                "exhibition",
                "collection",
                "curator",
                "conservator",
            ],
        ),
        EntityDefinition(
            name="topic",
            display_name="Art Topic",
            keywords=[
                "technique",
                "composition",
                "color theory",
                "perspective",
                "symbolism",
                "iconography",
                "cultural heritage",
                "art history",
                "artist biography",
                "exhibition review",
            ],
        ),
    ]


@pytest.fixture
def sample_category_config(
    sample_sources: list[Source],
    sample_entities: list[EntityDefinition],
) -> CategoryConfig:
    """Sample art category configuration."""
    from artradar.models import CategoryConfig

    return CategoryConfig(
        category_name="art",
        display_name="Art Radar",
        sources=sample_sources,
        entities=sample_entities,
    )
