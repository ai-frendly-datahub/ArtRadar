from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

import duckdb
import pytest

StorageError = cast(type[Exception], import_module("artradar.exceptions").StorageError)


class _Article(Protocol):
    title: str
    link: str
    summary: str
    published: datetime | None
    source: str
    category: str
    matched_entities: dict[str, list[str]]
    collected_at: datetime | None


class _ArticleCtor(Protocol):
    def __call__(
        self,
        *,
        title: str,
        link: str,
        summary: str,
        published: datetime | None,
        source: str,
        category: str,
        matched_entities: dict[str, list[str]] = ...,
        collected_at: datetime | None = ...,
    ) -> _Article: ...


class _RadarStorage(Protocol):
    def upsert_articles(self, articles: Iterable[_Article]) -> None: ...

    def recent_articles(
        self, category: str, *, days: int = 7, limit: int = 200
    ) -> list[_Article]: ...

    def recent_articles_by_collected_at(
        self, category: str, *, days: int = 7, limit: int = 200
    ) -> list[_Article]: ...

    def delete_older_than(self, days: int) -> int: ...

    def close(self) -> None: ...


class _RadarStorageCtor(Protocol):
    def __call__(self, db_path: Path) -> _RadarStorage: ...


Article = cast(_ArticleCtor, import_module("artradar.models").Article)
RadarStorage = cast(_RadarStorageCtor, import_module("artradar.storage").RadarStorage)
storage_module = import_module("artradar.storage")


def _make_article(
    *,
    title: str,
    link: str,
    summary: str,
    published: datetime | None,
    source: str = "Example RSS",
    category: str = "tech",
    matched_entities: dict[str, list[str]] | None = None,
) -> _Article:
    return Article(
        title=title,
        link=link,
        summary=summary,
        published=published,
        source=source,
        category=category,
        matched_entities=matched_entities or {},
    )


def test_upsert_articles_inserts_new_article(tmp_duckdb: Path, sample_article: object) -> None:
    storage = RadarStorage(tmp_duckdb)
    article = cast(_Article, sample_article)

    try:
        storage.upsert_articles([article])
        results = storage.recent_articles(category="tech", days=30)
    finally:
        storage.close()

    assert len(results) == 1
    assert results[0].link == article.link
    assert results[0].title == article.title
    assert results[0].matched_entities == article.matched_entities


def test_storage_datetime_and_row_helpers_cover_invalid_entities() -> None:
    utc_naive = storage_module._utc_naive
    article_from_row = storage_module._article_from_row
    aware = datetime(2026, 3, 13, 9, 0, tzinfo=UTC)
    naive = aware.replace(tzinfo=None)

    assert utc_naive(None) is None
    assert utc_naive(naive) == naive
    assert utc_naive(aware) == naive

    row = (
        "tech",
        "Source",
        "Title",
        "https://example.com",
        None,
        naive,
        naive,
        '{"Genre": "painting", "Topic": ["review"], "7": ["bad"]}',
    )
    article = article_from_row(row)
    assert article.summary == ""
    assert article.matched_entities == {"Topic": ["review"], "7": ["bad"]}

    bad_json_row = row[:-1] + ("{bad-json",)
    assert article_from_row(bad_json_row).matched_entities == {}


def test_storage_migration_rolls_back_and_reraises_on_failure() -> None:
    class FakeConnection:
        def begin(self) -> None:
            return None

        def execute(self, query: str) -> None:
            return None

        def rollback(self) -> None:
            raise duckdb.Error("rollback failed")

    storage = storage_module.RadarStorage.__new__(storage_module.RadarStorage)
    storage.conn = FakeConnection()
    storage._has_unique_constraint = lambda columns: False
    storage._create_articles_table = lambda table_name: (_ for _ in ()).throw(
        RuntimeError("migration failed")
    )

    with pytest.raises(RuntimeError, match="migration failed"):
        storage_module.RadarStorage._migrate_articles_unique_key_if_needed(storage)


def test_upsert_articles_updates_duplicate_link(tmp_duckdb: Path) -> None:
    storage = RadarStorage(tmp_duckdb)
    link = "https://example.com/dup"
    first = _make_article(
        title="First title",
        link=link,
        summary="first version",
        published=datetime.now(UTC),
    )
    second = _make_article(
        title="Updated title",
        link=link,
        summary="second version",
        published=datetime.now(UTC),
    )

    try:
        storage.upsert_articles([first])
        storage.upsert_articles([second])
        results = storage.recent_articles(category="tech", days=30)
    finally:
        storage.close()

    assert len(results) == 1
    assert results[0].title == "Updated title"
    assert results[0].summary == "second version"


def test_upsert_atomicity_rollback_preserves_data(tmp_duckdb: Path) -> None:
    storage = RadarStorage(tmp_duckdb)
    existing = _make_article(
        title="Existing",
        link="https://example.com/existing",
        summary="stable",
        published=datetime.now(UTC),
    )
    valid = _make_article(
        title="Valid",
        link="https://example.com/valid",
        summary="should rollback",
        published=datetime.now(UTC),
    )
    invalid = _make_article(
        title="Invalid",
        link="https://example.com/invalid",
        summary="should fail",
        published=datetime.now(UTC),
    )
    invalid.link = None

    try:
        storage.upsert_articles([existing])

        with pytest.raises(StorageError):
            storage.upsert_articles([valid, invalid])

        results = storage.recent_articles(category="tech", days=30)
    finally:
        storage.close()

    assert len(results) == 1
    assert results[0].link == existing.link
    assert results[0].title == existing.title


def test_batch_upsert_100_articles(tmp_duckdb: Path) -> None:
    storage = RadarStorage(tmp_duckdb)
    articles = [
        _make_article(
            title=f"Article {idx}",
            link=f"https://example.com/batch-{idx}",
            summary=f"summary {idx}",
            published=datetime.now(UTC),
        )
        for idx in range(100)
    ]

    try:
        storage.upsert_articles(articles)
        results = storage.recent_articles(category="tech", days=30, limit=200)
    finally:
        storage.close()

    assert len(results) == 100
    assert {article.link for article in results} == {article.link for article in articles}


def test_upsert_on_conflict_updates_existing(tmp_duckdb: Path) -> None:
    storage = RadarStorage(tmp_duckdb)
    link = "https://example.com/on-conflict"
    first = _make_article(
        title="Original title",
        link=link,
        summary="original",
        published=datetime.now(UTC),
    )
    updated = _make_article(
        title="Updated by conflict",
        link=link,
        summary="updated",
        published=datetime.now(UTC),
    )

    try:
        storage.upsert_articles([first])
        storage.upsert_articles([updated])
        results = storage.recent_articles(category="tech", days=30)
    finally:
        storage.close()

    assert len(results) == 1
    assert results[0].title == "Updated by conflict"
    assert results[0].summary == "updated"


def test_upsert_allows_same_link_in_different_categories(tmp_duckdb: Path) -> None:
    storage = RadarStorage(tmp_duckdb)
    shared_link = "https://example.com/shared"
    tech_article = _make_article(
        title="Tech copy",
        link=shared_link,
        summary="tech",
        published=datetime.now(UTC),
        category="tech",
    )
    artwork_article = _make_article(
        title="Artwork copy",
        link=shared_link,
        summary="artwork",
        published=datetime.now(UTC),
        category="artwork",
    )

    try:
        storage.upsert_articles([tech_article, artwork_article])
        tech_results = storage.recent_articles(category="tech", days=30)
        artwork_results = storage.recent_articles(category="artwork", days=30)
    finally:
        storage.close()

    assert len(tech_results) == 1
    assert len(artwork_results) == 1
    assert tech_results[0].title == "Tech copy"
    assert artwork_results[0].title == "Artwork copy"


def test_storage_migrates_legacy_global_link_unique_schema(tmp_duckdb: Path) -> None:
    legacy = duckdb.connect(str(tmp_duckdb))
    legacy.execute("CREATE SEQUENCE articles_id_seq START 1")
    legacy.execute("""
        CREATE TABLE articles (
            id BIGINT PRIMARY KEY DEFAULT nextval('articles_id_seq'),
            category TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            link TEXT NOT NULL UNIQUE,
            summary TEXT,
            published TIMESTAMP,
            collected_at TIMESTAMP NOT NULL,
            entities_json TEXT
        )
        """)
    legacy.execute(
        """
        INSERT INTO articles (category, source, title, link, summary, published, collected_at, entities_json)
        VALUES ('tech', 'Legacy', 'Legacy article', 'https://example.com/shared', 'old', ?, ?, '{}')
        """,
        [datetime.now(UTC).replace(tzinfo=None), datetime.now(UTC).replace(tzinfo=None)],
    )
    legacy.close()

    storage = RadarStorage(tmp_duckdb)
    try:
        storage.upsert_articles(
            [
                _make_article(
                    title="Artwork article",
                    link="https://example.com/shared",
                    summary="new category",
                    published=datetime.now(UTC),
                    category="artwork",
                )
            ]
        )
        tech_results = storage.recent_articles(category="tech", days=30)
        artwork_results = storage.recent_articles(category="artwork", days=30)
    finally:
        storage.close()

    assert len(tech_results) == 1
    assert len(artwork_results) == 1


def test_upsert_articles_accepts_empty_iterable(tmp_storage: object) -> None:
    storage = cast(_RadarStorage, tmp_storage)

    storage.upsert_articles([])
    results = storage.recent_articles(category="tech", days=30)

    assert results == []


def test_recent_articles_filters_by_period(tmp_storage: object) -> None:
    storage = cast(_RadarStorage, tmp_storage)
    recent_article = _make_article(
        title="Recent",
        link="https://example.com/recent",
        summary="inside window",
        published=datetime.now(UTC) - timedelta(days=1),
    )
    old_article = _make_article(
        title="Old",
        link="https://example.com/old",
        summary="outside window",
        published=datetime.now(UTC) - timedelta(days=20),
    )

    storage.upsert_articles([recent_article, old_article])
    results = storage.recent_articles(category="tech", days=7)

    assert len(results) == 1
    assert results[0].link == recent_article.link


def test_recent_articles_by_collected_at_includes_old_published_article(
    tmp_storage: object,
) -> None:
    storage = cast(_RadarStorage, tmp_storage)
    old_article = _make_article(
        title="Collected now but published long ago",
        link="https://example.com/old-published-recollected",
        summary="inside collected_at window",
        published=datetime.now(UTC) - timedelta(days=40),
    )

    storage.upsert_articles([old_article])

    assert storage.recent_articles(category="tech", days=7) == []
    collected_results = storage.recent_articles_by_collected_at(category="tech", days=7)
    assert len(collected_results) == 1
    assert collected_results[0].link == old_article.link


def test_recent_articles_filters_by_category(tmp_storage: object) -> None:
    storage = cast(_RadarStorage, tmp_storage)
    tech_article = _make_article(
        title="Tech",
        link="https://example.com/tech",
        summary="tech",
        published=datetime.now(UTC),
        category="tech",
    )
    policy_article = _make_article(
        title="Policy",
        link="https://example.com/policy",
        summary="policy",
        published=datetime.now(UTC),
        category="policy",
    )

    storage.upsert_articles([tech_article, policy_article])
    tech_results = storage.recent_articles(category="tech", days=30)
    policy_results = storage.recent_articles(category="policy", days=30)

    assert len(tech_results) == 1
    assert len(policy_results) == 1
    assert tech_results[0].category == "tech"
    assert policy_results[0].category == "policy"


def test_recent_articles_ignores_malformed_entities(tmp_duckdb: Path) -> None:
    storage = RadarStorage(tmp_duckdb)
    article = _make_article(
        title="Bad entities",
        link="https://example.com/bad-entities",
        summary="bad json",
        published=datetime.now(UTC),
    )
    try:
        storage.upsert_articles([article])
        storage.conn.execute(
            "UPDATE articles SET entities_json = ? WHERE link = ?",
            ['{"Genre": "painting", "Topic": ["review"], "7": ["bad"]}', article.link],
        )
        results = storage.recent_articles(category="tech", days=30)
        storage.conn.execute(
            "UPDATE articles SET entities_json = ? WHERE link = ?",
            ["{bad-json", article.link],
        )
        bad_results = storage.recent_articles(category="tech", days=30)
    finally:
        storage.close()

    assert results[0].matched_entities == {"Topic": ["review"], "7": ["bad"]}
    assert bad_results[0].matched_entities == {}


def test_delete_older_than_preserves_recent_articles(tmp_storage: object) -> None:
    storage = cast(_RadarStorage, tmp_storage)
    recent_article = _make_article(
        title="Recent",
        link="https://example.com/recent-keep",
        summary="should remain",
        published=datetime.now(UTC) - timedelta(days=2),
    )

    storage.upsert_articles([recent_article])
    deleted = storage.delete_older_than(days=7)
    results = storage.recent_articles(category="tech", days=30)

    assert deleted == 0
    assert len(results) == 1
    assert results[0].link == recent_article.link


def test_delete_older_than_preserves_recently_collected_old_published_article(
    tmp_storage: object,
) -> None:
    storage = cast(_RadarStorage, tmp_storage)
    old_article = _make_article(
        title="Old but recollected",
        link="https://example.com/old-published-keep",
        summary="published long ago but collected in this run",
        published=datetime.now(UTC) - timedelta(days=40),
    )

    storage.upsert_articles([old_article])
    deleted = storage.delete_older_than(days=7)
    collected_results = storage.recent_articles_by_collected_at(category="tech", days=7)

    assert deleted == 0
    assert len(collected_results) == 1
    assert collected_results[0].link == old_article.link


def test_delete_older_than_removes_old_collected_articles(
    tmp_duckdb: Path,
) -> None:
    storage = RadarStorage(tmp_duckdb)
    old_article = _make_article(
        title="Old",
        link="https://example.com/old-delete",
        summary="should be deleted",
        published=datetime.now(UTC) - timedelta(days=40),
    )

    storage.upsert_articles([old_article])
    old_collected_at = datetime.now(UTC) - timedelta(days=40)
    storage.conn.execute(
        "UPDATE articles SET collected_at = ? WHERE link = ?",
        [old_collected_at.replace(tzinfo=None), old_article.link],
    )
    deleted = storage.delete_older_than(days=7)
    results = storage.recent_articles(category="tech", days=365)
    storage.close()

    assert deleted == 1
    assert results == []


def test_storage_close_then_reuse_raises_error(tmp_duckdb: Path) -> None:
    storage = RadarStorage(tmp_duckdb)
    storage.close()

    with pytest.raises(StorageError):
        storage.upsert_articles(
            [
                _make_article(
                    title="After close",
                    link="https://example.com/closed",
                    summary="cannot write",
                    published=datetime.now(UTC),
                )
            ]
        )
