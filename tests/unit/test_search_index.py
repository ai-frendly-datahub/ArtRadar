"""Tests for SearchIndex — SQLite FTS5 full-text search."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from artradar.search_index import SearchIndex, SearchResult


@pytest.fixture
def temp_search_db() -> Path:
    """Create temporary SQLite search index file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "search.db"


class TestSearchIndexInit:
    """Test SearchIndex initialization."""

    def test_init_creates_db_file(self, temp_search_db: Path) -> None:
        """SearchIndex.__init__ creates database file."""
        index = SearchIndex(temp_search_db)
        assert temp_search_db.exists()
        index.close()

    def test_init_creates_fts_table(self, temp_search_db: Path) -> None:
        """SearchIndex.__init__ creates FTS5 virtual table."""
        index = SearchIndex(temp_search_db)
        # Verify FTS table exists by querying schema
        cursor = index._connection().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='documents_fts'"
        )
        result = cursor.fetchall()
        assert len(result) > 0
        index.close()


class TestSearchIndexUpsert:
    """Test SearchIndex.upsert."""

    def test_upsert_inserts_document(self, temp_search_db: Path) -> None:
        """upsert inserts document into search index."""
        index = SearchIndex(temp_search_db)
        index.upsert(
            link="https://example.com/art1",
            title="Test Art",
            body="This is a test article about art.",
        )

        # Verify document was inserted
        cursor = index._connection().execute(
            "SELECT COUNT(*) FROM documents WHERE link = ?",
            ("https://example.com/art1",),
        )
        result = cursor.fetchone()
        assert result[0] == 1
        index.close()

    def test_upsert_duplicate_link_overwrites(self, temp_search_db: Path) -> None:
        """upsert with duplicate link overwrites previous document."""
        index = SearchIndex(temp_search_db)
        index.upsert(
            link="https://example.com/art1",
            title="Original Title",
            body="Original body text.",
        )
        index.upsert(
            link="https://example.com/art1",
            title="Updated Title",
            body="Updated body text.",
        )

        # Verify only one document exists with updated title
        cursor = index._connection().execute(
            "SELECT title FROM documents WHERE link = ?",
            ("https://example.com/art1",),
        )
        result = cursor.fetchone()
        assert result[0] == "Updated Title"
        index.close()


class TestSearchIndexSearch:
    """Test SearchIndex.search."""

    def test_search_returns_results(self, temp_search_db: Path) -> None:
        """search returns matching documents."""
        index = SearchIndex(temp_search_db)
        index.upsert(
            link="https://example.com/art1",
            title="Modern Art",
            body="This article discusses modern art movements.",
        )

        results = index.search("modern art")
        assert len(results) > 0
        assert isinstance(results[0], SearchResult)
        assert results[0].link == "https://example.com/art1"
        index.close()

    def test_search_returns_empty_for_no_match(self, temp_search_db: Path) -> None:
        """search returns empty list when no documents match."""
        index = SearchIndex(temp_search_db)
        index.upsert(
            link="https://example.com/art1",
            title="Modern Art",
            body="This article discusses modern art movements.",
        )

        results = index.search("nonexistent_query_xyz")
        assert len(results) == 0
        index.close()

    def test_search_respects_limit(self, temp_search_db: Path) -> None:
        """search respects limit parameter."""
        index = SearchIndex(temp_search_db)
        for i in range(5):
            index.upsert(
                link=f"https://example.com/art{i}",
                title=f"Art {i}",
                body="This is an article about art.",
            )

        results = index.search("art", limit=2)
        assert len(results) <= 2
        index.close()

    def test_search_with_zero_limit_returns_empty(self, temp_search_db: Path) -> None:
        """search with limit=0 returns empty list."""
        index = SearchIndex(temp_search_db)
        index.upsert(
            link="https://example.com/art1",
            title="Modern Art",
            body="This article discusses modern art movements.",
        )

        results = index.search("art", limit=0)
        assert len(results) == 0
        index.close()

    def test_search_returns_search_result_objects(self, temp_search_db: Path) -> None:
        """search returns SearchResult objects with correct fields."""
        index = SearchIndex(temp_search_db)
        index.upsert(
            link="https://example.com/art1",
            title="Modern Art",
            body="This article discusses modern art movements and techniques.",
        )

        results = index.search("modern")
        assert len(results) > 0
        result = results[0]
        assert hasattr(result, "link")
        assert hasattr(result, "title")
        assert hasattr(result, "snippet")
        assert hasattr(result, "rank")
        assert result.link == "https://example.com/art1"
        assert result.title == "Modern Art"
        index.close()


class TestSearchIndexContextManager:
    """Test SearchIndex context manager."""

    def test_context_manager_closes_connection(self, temp_search_db: Path) -> None:
        """SearchIndex context manager closes connection on exit."""
        with SearchIndex(temp_search_db) as index:
            index.upsert(
                link="https://example.com/art1",
                title="Test",
                body="Test body",
            )

        # Verify connection is closed by attempting to use it
        with pytest.raises(sqlite3.ProgrammingError):
            index._connection().execute("SELECT 1")
