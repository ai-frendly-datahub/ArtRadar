from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.unit
def test_load_settings_defaults(tmp_path: Path) -> None:
    from artradar.config_loader import load_settings

    config = tmp_path / "config.yaml"
    _ = config.write_text(
        "database_path: data/test.duckdb\nreport_dir: reports\nraw_data_dir: data/raw\nsearch_db_path: data/search.db\n",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert "test.duckdb" in str(settings.database_path)


@pytest.mark.unit
def test_load_category_config(tmp_path: Path) -> None:
    from artradar.config_loader import load_category_config

    cat_dir = tmp_path / "categories"
    cat_dir.mkdir()
    _ = (cat_dir / "art.yaml").write_text(
        (
            "category_name: art\n"
            "display_name: Art Radar\n"
            "sources:\n"
            "  - name: TestArt\n"
            "    type: rss\n"
            "    url: https://example.com/feed\n"
            "entities:\n"
            "  - name: genre\n"
            "    display_name: Genre\n"
            "    keywords:\n"
            "      - painting\n"
        ),
        encoding="utf-8",
    )

    cfg = load_category_config("art", categories_dir=cat_dir)

    assert cfg.category_name == "art"
    assert len(cfg.sources) == 1
    assert len(cfg.entities) == 1
    assert cfg.sources[0].url == "https://example.com/feed"


@pytest.mark.unit
def test_load_settings_missing_file_raises(tmp_path: Path) -> None:
    from artradar.config_loader import load_settings

    with pytest.raises(FileNotFoundError):
        _ = load_settings(tmp_path / "missing.yaml")


@pytest.mark.unit
def test_load_category_config_missing_file_raises(tmp_path: Path) -> None:
    from artradar.config_loader import load_category_config

    categories_dir = tmp_path / "categories"
    categories_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        _ = load_category_config("art", categories_dir=categories_dir)


@pytest.mark.unit
def test_load_notification_config_missing_file_returns_disabled(tmp_path: Path) -> None:
    from artradar.config_loader import load_notification_config

    config = load_notification_config(tmp_path / "missing-notifications.yaml")

    assert config.enabled is False
    assert config.channels == []


@pytest.mark.unit
def test_load_project_artwork_category_config() -> None:
    from artradar.config_loader import load_category_config

    cfg = load_category_config("artwork")

    assert cfg.category_name == "artwork"
    assert cfg.display_name == "Artwork Radar"
    assert len(cfg.sources) == 3
    assert {source.type for source in cfg.sources} == {"met_museum", "aic", "smithsonian"}
