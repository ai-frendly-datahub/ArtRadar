#!/usr/bin/env python3
"""Repair stored article quality issues in the DuckDB article store."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from artradar.analyzer import apply_entity_rules  # noqa: E402
from artradar.common.text_cleaning import clean_text  # noqa: E402
from artradar.common.validators import validate_article  # noqa: E402
from artradar.config_loader import load_category_config, load_settings  # noqa: E402
from artradar.models import Article  # noqa: E402


def _load_articles(con: duckdb.DuckDBPyConnection) -> list[tuple[int, Article, str]]:
    rows = con.execute("""
        SELECT id, category, source, title, link, summary, published, collected_at, entities_json
        FROM articles
        ORDER BY id
        """).fetchall()

    articles: list[tuple[int, Article, str]] = []
    for row in rows:
        row_id, category, source, title, link, summary, published, collected_at, entities_json = row
        article = Article(
            title=str(title),
            link=str(link),
            summary=str(summary or ""),
            published=published if isinstance(published, datetime) else None,
            source=str(source),
            category=str(category),
            collected_at=collected_at if isinstance(collected_at, datetime) else None,
        )
        articles.append((int(row_id), article, str(entities_json or "{}")))
    return articles


def _category_entities(project_root: Path, categories: set[str]) -> dict[str, Any]:
    entities_by_category: dict[str, Any] = {}
    categories_dir = project_root / "config" / "categories"
    for category in categories:
        try:
            entities_by_category[category] = load_category_config(
                category,
                categories_dir=categories_dir,
            ).entities
        except FileNotFoundError:
            entities_by_category[category] = []
    return entities_by_category


def repair_database(
    *,
    project_root: Path = PROJECT_ROOT,
    write: bool = False,
    backup_path: Path | None = None,
    delete_unconfigured_categories: set[str] | None = None,
) -> dict[str, Any]:
    settings = load_settings(project_root / "config" / "config.yaml")
    db_path = settings.database_path
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    if write and backup_path is not None:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, backup_path)

    with duckdb.connect(str(db_path), read_only=not write) as con:
        stored = _load_articles(con)
        entities_by_category = _category_entities(
            project_root,
            {article.category for _, article, _ in stored},
        )
        configured_sources_by_category = _configured_sources(
            project_root,
            set(delete_unconfigured_categories or set()),
        )

        invalid_ids: list[int] = []
        invalid_errors: list[dict[str, object]] = []
        updates: list[tuple[str, str, str, int]] = []

        for row_id, article, previous_entities_json in stored:
            configured_sources = configured_sources_by_category.get(article.category)
            if configured_sources is not None and article.source not in configured_sources:
                invalid_ids.append(row_id)
                invalid_errors.append(
                    {
                        "id": row_id,
                        "category": article.category,
                        "source": article.source,
                        "title": article.title,
                        "link": article.link,
                        "errors": ["source is not configured for category"],
                    }
                )
                continue

            previous_title = article.title
            previous_summary = article.summary
            article.title = clean_text(article.title) or article.title
            article.summary = clean_text(article.summary)
            is_valid, errors = validate_article(article)
            if not is_valid:
                invalid_ids.append(row_id)
                invalid_errors.append(
                    {
                        "id": row_id,
                        "category": article.category,
                        "source": article.source,
                        "title": article.title,
                        "link": article.link,
                        "errors": errors,
                    }
                )
                continue

            entities = entities_by_category.get(article.category, [])
            article = apply_entity_rules([article], entities)[0]
            next_entities_json = json.dumps(article.matched_entities, ensure_ascii=False)
            if (
                article.title != previous_title
                or article.summary != previous_summary
                or next_entities_json != previous_entities_json
            ):
                updates.append((article.title, article.summary, next_entities_json, row_id))

        if write:
            _ = con.begin()
            try:
                if invalid_ids:
                    _ = con.executemany(
                        "DELETE FROM articles WHERE id = ?",
                        [(row_id,) for row_id in invalid_ids],
                    )
                if updates:
                    _ = con.executemany(
                        """
                        UPDATE articles
                        SET title = ?, summary = ?, entities_json = ?
                        WHERE id = ?
                        """,
                        updates,
                    )
                _ = con.commit()
            except Exception:
                _ = con.rollback()
                raise

    return {
        "database_path": str(db_path),
        "backup_path": str(backup_path) if backup_path is not None else None,
        "write": write,
        "delete_unconfigured_categories": sorted(delete_unconfigured_categories or set()),
        "scanned": len(stored),
        "deleted": len(invalid_ids),
        "updated": len(updates),
        "invalid_errors": invalid_errors[:20],
    }


def _configured_sources(project_root: Path, categories: set[str]) -> dict[str, set[str]]:
    categories_dir = project_root / "config" / "categories"
    configured: dict[str, set[str]] = {}
    for category in categories:
        try:
            cfg = load_category_config(category, categories_dir=categories_dir)
        except FileNotFoundError:
            continue
        configured[category] = {source.name for source in cfg.sources}
    return configured


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair stored ArtRadar article quality issues")
    parser.add_argument("--write", action="store_true", help="Apply repairs to DuckDB")
    parser.add_argument(
        "--backup-path",
        type=Path,
        default=None,
        help="Backup path to create before --write. Defaults to /tmp with timestamp.",
    )
    parser.add_argument(
        "--delete-unconfigured",
        action="append",
        default=[],
        metavar="CATEGORY",
        help="Delete articles whose source is not configured for this category. May be repeated.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backup_path = args.backup_path
    if args.write and backup_path is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = Path("/tmp") / f"artradar_art_data_before_quality_repair_{stamp}.duckdb"

    result = repair_database(
        write=bool(args.write),
        backup_path=backup_path,
        delete_unconfigured_categories={str(item) for item in args.delete_unconfigured},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
