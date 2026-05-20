from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from artradar.models import Article
from artradar.raw_logger import RawLogger


def _article(link: str, *, ontology: dict[str, object] | None = None) -> Article:
    article = Article(
        title="Artwork update",
        link=link,
        summary="Oil on canvas",
        published=datetime(2026, 5, 21, 1, 0, tzinfo=UTC),
        source="Source/Name",
        category="artwork",
        matched_entities={"Medium": ["oil on canvas"]},
    )
    if ontology is not None:
        article.ontology = ontology
    return article


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_raw_logger_sanitizes_source_name_and_writes_ontology(tmp_path: Path) -> None:
    path = RawLogger(tmp_path).log(
        [_article("https://example.com/a", ontology={"event_model": "collection"})],
        source_name="Source/Name",
        run_id="run-1",
    )

    assert path.name == "Source_Name_run-1.jsonl"
    rows = _read_jsonl(path)
    assert len(rows) == 1
    assert rows[0]["ontology"] == {"event_model": "collection"}
    assert rows[0]["matched_entities"] == {"Medium": ["oil on canvas"]}


def test_raw_logger_deduplicates_links_with_run_id(tmp_path: Path) -> None:
    logger = RawLogger(tmp_path)

    first_path = logger.log([_article("https://example.com/a")], source_name="Source", run_id="run")
    second_path = logger.log(
        [_article("https://example.com/a"), _article("https://example.com/b")],
        source_name="Source",
        run_id="run",
    )

    assert first_path == second_path
    rows = _read_jsonl(second_path)
    assert [row["link"] for row in rows] == ["https://example.com/a", "https://example.com/b"]


def test_raw_logger_ignores_malformed_existing_jsonl(tmp_path: Path) -> None:
    logger = RawLogger(tmp_path)
    path = logger.log([_article("https://example.com/a")], source_name="Source", run_id="run")
    path.write_text("{not-json\n", encoding="utf-8")

    logger.log([_article("https://example.com/a")], source_name="Source", run_id="run")

    content = path.read_text(encoding="utf-8")
    assert "{not-json" in content
    assert "https://example.com/a" in content
