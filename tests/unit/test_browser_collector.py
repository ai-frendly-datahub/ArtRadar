from __future__ import annotations

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
