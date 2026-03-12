"""Tests for RadarStorage — DuckDB upsert, query, retention."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from artradar.models import Article
from artradar.storage import RadarStorage


@pytest.fixture
def temp_db() -> Path:
    """Create temporary DuckDB file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.duckdb"


class TestRadarStorageInit:
    """Test RadarStorage initialization."""

    def test_init_creates_db_file(self, temp_db: Path) -> None:
        """RadarStorage.__init__ creates database file."""
        storage = RadarStorage(temp_db)
        assert temp_db.exists()
        storage.close()

    def test_init_creates_articles_table(self, temp_db: Path) -> None:
        """RadarStorage.__init__ creates articles table with correct schema."""
        storage = RadarStorage(temp_db)
        # Verify table exists by querying schema
        result = storage.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"
        ).fetchall()
        assert len(result) > 0
        storage.close()


class TestRadarStorageUpsert:
    """Test RadarStorage.upsert_articles."""

    def test_upsert_single_article(self, temp_db: Path) -> None:
        """upsert_articles inserts single article."""
        storage = RadarStorage(temp_db)
        article = Article(
            title="Test Art",
            link="https://example.com/art1",
            summary="Test summary",
            published=datetime.now(UTC),
            source="test_source",
            category="art",
        )
        storage.upsert_articles([article])

        # Verify article was inserted
        result = storage.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE link = ?",
            ["https://example.com/art1"],
        ).fetchone()
        assert result[0] == 1
        storage.close()

    def test_upsert_duplicate_link_overwrites(self, temp_db: Path) -> None:
        """upsert_articles with duplicate link overwrites previous article."""
        storage = RadarStorage(temp_db)
        article1 = Article(
            title="Original Title",
            link="https://example.com/art1",
            summary="Original summary",
            published=datetime.now(UTC),
            source="test_source",
            category="art",
        )
        article2 = Article(
            title="Updated Title",
            link="https://example.com/art1",
            summary="Updated summary",
            published=datetime.now(UTC),
            source="test_source",
            category="art",
        )

        storage.upsert_articles([article1])
        storage.upsert_articles([article2])

        # Verify only one article exists with updated title
        result = storage.conn.execute(
            "SELECT title FROM articles WHERE link = ?",
            ["https://example.com/art1"],
        ).fetchone()
        assert result[0] == "Updated Title"
        storage.close()

    def test_upsert_multiple_articles(self, temp_db: Path) -> None:
        """upsert_articles inserts multiple articles."""
        storage = RadarStorage(temp_db)
        articles = [
            Article(
                title=f"Art {i}",
                link=f"https://example.com/art{i}",
                summary=f"Summary {i}",
                published=datetime.now(UTC),
                source="test_source",
                category="art",
            )
            for i in range(3)
        ]
        storage.upsert_articles(articles)

        # Verify all articles were inserted
        result = storage.conn.execute("SELECT COUNT(*) FROM articles").fetchone()
        assert result[0] == 3
        storage.close()


class TestRadarStorageQuery:
    """Test RadarStorage.recent_articles."""

    def test_recent_articles_returns_articles(self, temp_db: Path) -> None:
        """recent_articles returns articles from specified category."""
        storage = RadarStorage(temp_db)
        article = Article(
            title="Test Art",
            link="https://example.com/art1",
            summary="Test summary",
            published=datetime.now(UTC),
            source="test_source",
            category="art",
        )
        storage.upsert_articles([article])

        results = storage.recent_articles("art", days=7)
        assert len(results) == 1
        assert results[0].title == "Test Art"
        assert results[0].link == "https://example.com/art1"
        storage.close()

    def test_recent_articles_filters_by_category(self, temp_db: Path) -> None:
        """recent_articles only returns articles from specified category."""
        storage = RadarStorage(temp_db)
        art_article = Article(
            title="Art Article",
            link="https://example.com/art1",
            summary="Art summary",
            published=datetime.now(UTC),
            source="test_source",
            category="art",
        )
        other_article = Article(
            title="Other Article",
            link="https://example.com/other1",
            summary="Other summary",
            published=datetime.now(UTC),
            source="test_source",
            category="other",
        )
        storage.upsert_articles([art_article, other_article])

        results = storage.recent_articles("art", days=7)
        assert len(results) == 1
        assert results[0].category == "art"
        storage.close()

    def test_recent_articles_filters_by_days(self, temp_db: Path) -> None:
        """recent_articles only returns articles within specified days."""
        storage = RadarStorage(temp_db)
        now = datetime.now(UTC)
        recent_article = Article(
            title="Recent",
            link="https://example.com/recent",
            summary="Recent summary",
            published=now,
            source="test_source",
            category="art",
        )
        old_article = Article(
            title="Old",
            link="https://example.com/old",
            summary="Old summary",
            published=now - timedelta(days=10),
            source="test_source",
            category="art",
        )
        storage.upsert_articles([recent_article, old_article])

        results = storage.recent_articles("art", days=7)
        assert len(results) == 1
        assert results[0].title == "Recent"
        storage.close()


class TestRadarStorageRetention:
    """Test RadarStorage.delete_older_than."""

    def test_delete_older_than_removes_old_articles(self, temp_db: Path) -> None:
        """delete_older_than removes articles older than specified days."""
        storage = RadarStorage(temp_db)
        now = datetime.now(UTC)
        recent_article = Article(
            title="Recent",
            link="https://example.com/recent",
            summary="Recent summary",
            published=now,
            source="test_source",
            category="art",
        )
        old_article = Article(
            title="Old",
            link="https://example.com/old",
            summary="Old summary",
            published=now - timedelta(days=100),
            source="test_source",
            category="art",
        )
        storage.upsert_articles([recent_article, old_article])

        deleted_count = storage.delete_older_than(days=90)
        assert deleted_count == 1

        # Verify old article was deleted
        results = storage.recent_articles("art", days=365)
        assert len(results) == 1
        assert results[0].title == "Recent"
        storage.close()

    def test_delete_older_than_returns_count(self, temp_db: Path) -> None:
        """delete_older_than returns count of deleted articles."""
        storage = RadarStorage(temp_db)
        now = datetime.now(UTC)
        articles = [
            Article(
                title=f"Old {i}",
                link=f"https://example.com/old{i}",
                summary=f"Old summary {i}",
                published=now - timedelta(days=100),
                source="test_source",
                category="art",
            )
            for i in range(3)
        ]
        storage.upsert_articles(articles)

        deleted_count = storage.delete_older_than(days=90)
        assert deleted_count == 3
        storage.close()


class TestRadarStorageClose:
    """Test RadarStorage.close."""

    def test_close_closes_connection(self, temp_db: Path) -> None:
        """close() closes database connection."""
        storage = RadarStorage(temp_db)
        storage.close()
        # Verify connection is closed by attempting to use it
        with pytest.raises(duckdb.ConnectionException):
            storage.conn.execute("SELECT 1")
