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
            "    language: ko\n"
            "    trust_tier: T1_official\n"
            "    content_type: exhibition\n"
            "    collection_tier: C2_javascript\n"
            "    config:\n"
            "      event_model: exhibition_ticket_signal\n"
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
    assert cfg.sources[0].language == "ko"
    assert cfg.sources[0].trust_tier == "T1_official"
    assert cfg.sources[0].content_type == "exhibition"
    assert cfg.sources[0].collection_tier == "C2_javascript"
    assert cfg.sources[0].config == {"event_model": "exhibition_ticket_signal"}


@pytest.mark.unit
def test_load_category_quality_config_preserves_quality_overlay(tmp_path: Path) -> None:
    from artradar.config_loader import load_category_quality_config

    cat_dir = tmp_path / "categories"
    cat_dir.mkdir()
    _ = (cat_dir / "art.yaml").write_text(
        (
            "category_name: art\n"
            "data_quality:\n"
            "  priority: P2\n"
            "  quality_outputs:\n"
            "    tracked_event_models:\n"
            "      - auction_result\n"
            "source_backlog:\n"
            "  operational_candidates:\n"
            "    - id: auction_results\n"
        ),
        encoding="utf-8",
    )

    quality = load_category_quality_config("art", categories_dir=cat_dir)

    assert quality["data_quality"]["priority"] == "P2"
    assert quality["source_backlog"]["operational_candidates"][0]["id"] == "auction_results"


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
    assert {source.name for source in cfg.sources} == {
        "Metropolitan Museum",
        "Art Institute of Chicago",
        "Smithsonian",
    }
    met_source = next(source for source in cfg.sources if source.name == "Metropolitan Museum")
    assert met_source.url == "https://collectionapi.metmuseum.org/public/collection/v1/objects"
    assert {source.content_type for source in cfg.sources} == {"collection"}


@pytest.mark.unit
def test_load_settings_resolves_absolute_and_default_paths(tmp_path: Path) -> None:
    from artradar.config_loader import load_settings

    absolute_db = tmp_path / "absolute.duckdb"
    config = tmp_path / "config.yaml"
    _ = config.write_text(
        f"database_path: {absolute_db}\n",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.database_path == absolute_db
    assert settings.report_dir.name == "reports"
    assert settings.raw_data_dir.parts[-2:] == ("data", "raw")
    assert settings.search_db_path.parts[-2:] == ("data", "search_index.db")


@pytest.mark.unit
def test_config_loader_private_helpers_cover_scalar_fallbacks(tmp_path: Path) -> None:
    from artradar import config_loader

    non_dict = tmp_path / "non-dict.yaml"
    non_dict.write_text("- item\n", encoding="utf-8")

    assert config_loader._read_yaml_dict(non_dict) == {}
    assert config_loader._bool_value({"enabled": "yes"}, "enabled", False) is True
    assert config_loader._bool_value({"enabled": "0"}, "enabled", True) is False
    assert config_loader._float_value({"weight": 3}, "weight", 1.0) == 3.0
    assert config_loader._string_list_value({"items": ("a", "b")}, "items") == ["a", "b"]
    assert sorted(config_loader._string_list_value({"items": {"b", "a"}}, "items")) == [
        "a",
        "b",
    ]
    assert config_loader._dict_items({"not": "a-list"}) == []
    parsed = config_loader._parse_entity({"name": "Topic", "keywords": ("art", 5, "")})
    assert parsed.keywords == ["art", "5"]
    parsed_empty = config_loader._parse_entity({"name": "Topic", "keywords": "art"})
    assert parsed_empty.keywords == []


@pytest.mark.unit
def test_load_category_quality_config_missing_file_raises(tmp_path: Path) -> None:
    from artradar.config_loader import load_category_quality_config

    categories_dir = tmp_path / "categories"
    categories_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        _ = load_category_quality_config("art", categories_dir=categories_dir)


@pytest.mark.unit
def test_load_category_config_parses_source_defaults_and_scalar_lists(tmp_path: Path) -> None:
    from artradar.config_loader import load_category_config

    cat_dir = tmp_path / "categories"
    cat_dir.mkdir()
    _ = (cat_dir / "art.yaml").write_text(
        (
            "category_name: art\n"
            "sources:\n"
            "  - name: Test\n"
            "    url: https://example.com\n"
            "    enabled: no\n"
            "    weight: invalid\n"
            "    info_purpose: analysis\n"
            "entities:\n"
            "  - name: Topic\n"
            "    keywords:\n"
            "      - art\n"
            "      - 123\n"
            "      - ''\n"
        ),
        encoding="utf-8",
    )

    cfg = load_category_config("art", categories_dir=cat_dir)

    assert cfg.display_name == "art"
    assert cfg.sources[0].type == "rss"
    assert cfg.sources[0].enabled is False
    assert cfg.sources[0].weight == 1.0
    assert cfg.sources[0].info_purpose == ["analysis"]
    assert cfg.entities[0].display_name == "Topic"
    assert cfg.entities[0].keywords == ["art", "123"]


@pytest.mark.unit
def test_load_category_config_rejects_empty_source_and_entity(tmp_path: Path) -> None:
    from artradar.config_loader import load_category_config

    cat_dir = tmp_path / "categories"
    cat_dir.mkdir()
    _ = (cat_dir / "art.yaml").write_text(
        "category_name: art\nsources:\n  - {}\nentities: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_category_config("art", categories_dir=cat_dir)

    _ = (cat_dir / "art.yaml").write_text(
        "category_name: art\nsources: []\nentities:\n  - {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_category_config("art", categories_dir=cat_dir)


@pytest.mark.unit
def test_load_notification_config_resolves_env_refs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from artradar.config_loader import load_notification_config

    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setenv("WEBHOOK_URL", "https://hooks.example.com")
    monkeypatch.setenv("BOT_TOKEN", "bot-token")
    config = tmp_path / "notifications.yaml"
    _ = config.write_text(
        """
notifications:
  enabled: true
  channels: [email, webhook, 123]
  email:
    smtp_host: smtp.example.com
    smtp_port: "2525"
    username: sender
    password: ${SMTP_PASS}
    from_address: from@example.com
    to_addresses:
      - to@example.com
      - 7
  webhook_url: ${WEBHOOK_URL}
  telegram:
    bot_token: ${BOT_TOKEN}
    chat_id: chat-1
  rules:
    min_matches: "3"
""",
        encoding="utf-8",
    )

    parsed = load_notification_config(config)

    assert parsed.enabled is True
    assert parsed.channels == ["email", "webhook"]
    assert parsed.email is not None
    assert parsed.email.smtp_port == 2525
    assert parsed.email.password == "secret"
    assert parsed.email.to_addresses == ["to@example.com"]
    assert parsed.webhook_url == "https://hooks.example.com"
    assert parsed.telegram is not None
    assert parsed.telegram.bot_token == "bot-token"
    assert parsed.rules == {"min_matches": "3"}


@pytest.mark.unit
def test_load_notification_config_handles_invalid_shapes(tmp_path: Path) -> None:
    from artradar.config_loader import load_notification_config

    config = tmp_path / "notifications.yaml"
    _ = config.write_text("notifications: []\n", encoding="utf-8")
    assert load_notification_config(config).enabled is False

    _ = config.write_text(
        """
notifications:
  enabled: true
  channels: email
  email:
    smtp_port: invalid
  telegram: []
  rules: []
""",
        encoding="utf-8",
    )
    parsed = load_notification_config(config)
    assert parsed.enabled is True
    assert parsed.channels == []
    assert parsed.email is None
    assert parsed.telegram is None
    assert parsed.rules == {}
