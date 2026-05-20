from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from artradar.models import Source


@pytest.mark.unit
def test_browser_collector_passes_source_config_to_core_collector() -> None:
    from artradar.browser_collector import collect_browser_sources

    source = Source(
        name="MonthlyArt",
        type="javascript",
        url="https://monthlyart.com/",
        config={"link_selector": "h3.slide-entry-title a", "detail_limit": 0},
    )
    mock_collect = Mock(return_value=([], []))

    with (
        patch("artradar.browser_collector._BROWSER_COLLECTION_AVAILABLE", True),
        patch("artradar.browser_collector._core_collect", mock_collect),
    ):
        articles, errors = collect_browser_sources([source], "art")

    assert articles == []
    assert errors == []
    core_sources = mock_collect.call_args.kwargs["sources"]
    assert core_sources == [
        {
            "name": "MonthlyArt",
            "type": "javascript",
            "url": "https://monthlyart.com/",
            "config": {"link_selector": "h3.slide-entry-title a", "detail_limit": 0},
        }
    ]


@pytest.mark.unit
def test_browser_collector_adds_body_fallback_for_wait_selector() -> None:
    from artradar.browser_collector import collect_browser_sources

    source = Source(
        name="Museum",
        type="javascript",
        url="https://example.com/museum",
        config={"wait_for": ".cards"},
    )
    mock_collect = Mock(return_value=([], []))

    with (
        patch("artradar.browser_collector._BROWSER_COLLECTION_AVAILABLE", True),
        patch("artradar.browser_collector._core_collect", mock_collect),
    ):
        _, _ = collect_browser_sources([source], "art")

    core_config = mock_collect.call_args.kwargs["sources"][0]["config"]
    assert core_config["wait_for"] == ".cards"
    assert core_config["fallback_wait_for"] == "body"


@pytest.mark.unit
def test_browser_collector_forwards_timeout_to_core_collector() -> None:
    from artradar.browser_collector import collect_browser_sources

    source = Source(
        name="Museum",
        type="javascript",
        url="https://example.com/museum",
    )
    mock_collect = Mock(return_value=([], []))

    with (
        patch("artradar.browser_collector._BROWSER_COLLECTION_AVAILABLE", True),
        patch("artradar.browser_collector._core_collect", mock_collect),
    ):
        _, _ = collect_browser_sources([source], "art", timeout=5_000)

    assert mock_collect.call_args.kwargs["timeout"] == 5_000


@pytest.mark.unit
def test_browser_collector_empty_sources_short_circuits() -> None:
    from artradar.browser_collector import collect_browser_sources

    assert collect_browser_sources([], "art") == ([], [])


@pytest.mark.unit
def test_browser_collector_returns_install_hint_when_unavailable() -> None:
    from artradar.browser_collector import collect_browser_sources

    source = Source(name="Museum", type="javascript", url="https://example.com/museum")

    with (
        patch("artradar.browser_collector._BROWSER_COLLECTION_AVAILABLE", False),
        patch("artradar.browser_collector._core_collect", None),
    ):
        articles, errors = collect_browser_sources([source], "art")

    assert articles == []
    assert errors == [
        "Browser collection unavailable for 1 JS source(s). Install radar-core[browser]."
    ]


@pytest.mark.unit
def test_browser_collector_handles_playwright_import_error() -> None:
    from artradar.browser_collector import collect_browser_sources

    source = Source(name="Museum", type="javascript", url="https://example.com/museum")
    mock_collect = Mock(side_effect=ImportError("missing playwright"))

    with (
        patch("artradar.browser_collector._BROWSER_COLLECTION_AVAILABLE", True),
        patch("artradar.browser_collector._core_collect", mock_collect),
    ):
        articles, errors = collect_browser_sources([source], "art")

    assert articles == []
    assert errors == ["Playwright not installed for 1 JS source(s). Install radar-core[browser]."]


@pytest.mark.unit
def test_browser_collector_handles_core_exception() -> None:
    from artradar.browser_collector import collect_browser_sources

    source = Source(name="Museum", type="javascript", url="https://example.com/museum")
    mock_collect = Mock(side_effect=RuntimeError("boom"))

    with (
        patch("artradar.browser_collector._BROWSER_COLLECTION_AVAILABLE", True),
        patch("artradar.browser_collector._core_collect", mock_collect),
    ):
        articles, errors = collect_browser_sources([source], "art")

    assert articles == []
    assert errors == ["Browser collection failed: boom"]


@pytest.mark.unit
def test_browser_collector_converts_core_articles_to_local_articles() -> None:
    from artradar.browser_collector import collect_browser_sources

    source = Source(name="Museum", type="javascript", url="https://example.com/museum")
    published = datetime(2026, 3, 13, tzinfo=UTC)
    core_article = SimpleNamespace(
        title="Gallery Review",
        link="https://example.com/review",
        summary="Review summary",
        published=published,
        source="Museum",
        category="",
    )
    mock_collect = Mock(return_value=([core_article], ["minor warning"]))

    with (
        patch("artradar.browser_collector._BROWSER_COLLECTION_AVAILABLE", True),
        patch("artradar.browser_collector._core_collect", mock_collect),
    ):
        articles, errors = collect_browser_sources(
            [source],
            "art",
            health_db_path="/tmp/health.duckdb",
        )

    assert errors == ["minor warning"]
    assert len(articles) == 1
    assert articles[0].title == "Gallery Review"
    assert articles[0].category == "art"
    assert mock_collect.call_args.kwargs["health_db_path"] == "/tmp/health.duckdb"


@pytest.mark.unit
def test_browser_collector_import_fallback_when_core_module_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.util

    import artradar.browser_collector as browser_collector

    module_path = Path(browser_collector.__file__)
    module_name = "artradar._browser_collector_import_fallback_test"

    original_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> object:
        if name == "radar_core.browser_collector":
            raise ImportError("missing browser extra")
        return original_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    assert module._BROWSER_COLLECTION_AVAILABLE is False
    assert module._core_collect is None
