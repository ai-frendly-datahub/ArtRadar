from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from artradar.models import Article
from artradar.storage import RadarStorage
from scripts.repair_quality import repair_database


@pytest.mark.unit
def test_repair_database_cleans_html_reanalyzes_entities_and_deletes_error_pages(
    tmp_path: Path,
) -> None:
    (tmp_path / "config" / "categories").mkdir(parents=True)
    db_path = tmp_path / "data" / "art_data.duckdb"
    backup_path = tmp_path / "backup.duckdb"
    (tmp_path / "config" / "config.yaml").write_text(
        (
            f"database_path: {db_path}\n"
            "report_dir: reports\n"
            "raw_data_dir: data/raw\n"
            "search_db_path: data/search_index.db\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "config" / "categories" / "art.yaml").write_text(
        (
            "category_name: art\n"
            "display_name: Art\n"
            "entities:\n"
            "  - name: Topic\n"
            "    display_name: Topic\n"
            "    keywords:\n"
            "      - art\n"
            "      - the\n"
        ),
        encoding="utf-8",
    )

    with RadarStorage(db_path) as storage:
        storage.upsert_articles(
            [
                Article(
                    title="Art market opens",
                    link="https://example.com/article",
                    summary="<p>The <strong>art</strong> market opens.</p>",
                    published=datetime(2026, 5, 20, tzinfo=UTC),
                    source="Example",
                    category="art",
                    matched_entities={"Topic": ["the"]},
                ),
                Article(
                    title="403 Forbidden",
                    link="https://example.com/blocked",
                    summary="403 Forbidden nginx",
                    published=datetime(2026, 5, 20, tzinfo=UTC),
                    source="Example",
                    category="art",
                ),
                Article(
                    title="Legacy artwork source",
                    link="https://legacy.example.com/item",
                    summary="Legacy source should be removed.",
                    published=datetime(2026, 5, 20, tzinfo=UTC),
                    source="Legacy Editorial",
                    category="artwork",
                ),
            ]
        )

    (tmp_path / "config" / "categories" / "artwork.yaml").write_text(
        (
            "category_name: artwork\n"
            "sources:\n"
            "  - name: Metropolitan Museum\n"
            "    type: met_museum\n"
            "    url: https://example.com/met\n"
            "entities: []\n"
        ),
        encoding="utf-8",
    )

    result = repair_database(
        project_root=tmp_path,
        write=True,
        backup_path=backup_path,
        delete_unconfigured_categories={"artwork"},
    )

    assert result["scanned"] == 3
    assert result["deleted"] == 2
    assert result["updated"] == 1
    assert backup_path.exists()

    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            "SELECT title, summary, entities_json FROM articles ORDER BY link"
        ).fetchall()

    assert rows == [
        (
            "Art market opens",
            "The art market opens.",
            '{"Topic": ["art"]}',
        )
    ]
