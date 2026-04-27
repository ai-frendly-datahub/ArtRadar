from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest
import yaml

from artradar.models import Article


def _load_main_module() -> ModuleType:
    main_path = Path(__file__).resolve().parents[2] / "main.py"
    spec = spec_from_file_location("artradar_main", main_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FAKE_ARTICLE = Article(
    title="Art market update",
    link="https://example.com/article-1",
    summary="painting demand is rising",
    published=datetime.now(UTC),
    source="Mock RSS",
    category="test_art",
)


@pytest.mark.integration
def test_full_pipeline_creates_all_outputs(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    categories_dir = tmp_path / "categories"
    categories_dir.mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "data" / "art_data.duckdb"
    report_dir = tmp_path / "reports"
    raw_dir = tmp_path / "data" / "raw"
    search_db_path = tmp_path / "data" / "search_index.db"

    _ = config_path.write_text(
        yaml.safe_dump(
            {
                "database_path": str(db_path),
                "report_dir": str(report_dir),
                "raw_data_dir": str(raw_dir),
                "search_db_path": str(search_db_path),
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    category_file = categories_dir / "test_art.yaml"
    _ = category_file.write_text(
        yaml.safe_dump(
            {
                "category_name": "test_art",
                "display_name": "Test Art Category",
                "sources": [
                    {"name": "Mock RSS", "type": "rss", "url": "https://example.com/feed.xml"}
                ],
                "entities": [{"name": "genre", "display_name": "Genre", "keywords": ["painting"]}],
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    main_module = _load_main_module()
    with patch.object(main_module, "collect_sources", return_value=([_FAKE_ARTICLE], [])):
        output_path = main_module.run(
            category="test_art",
            config_path=config_path,
            categories_dir=categories_dir,
            per_source_limit=5,
            recent_days=7,
            timeout=5,
            keep_days=30,
        )

    assert db_path.exists()
    assert raw_dir.exists()
    assert list(raw_dir.rglob("*.jsonl"))
    assert search_db_path.exists()
    assert output_path.exists()
    assert output_path.suffix == ".html"
