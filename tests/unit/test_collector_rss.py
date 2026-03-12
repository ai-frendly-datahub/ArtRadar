from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from artradar.models import Source


def _feed_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "title": "Painting fair opens",
        "link": "https://example.com/post-1",
        "summary": "A contemporary painting fair.",
        "published": "Tue, 12 Mar 2024 10:00:00 GMT",
    }
    entry.update(overrides)
    return entry


@pytest.mark.unit
def test_collect_sources_empty() -> None:
    from artradar.collector import collect_sources

    articles, errors = collect_sources([], category="art")

    assert articles == []
    assert errors == []


@pytest.mark.unit
def test_collect_sources_unsupported_type() -> None:
    from artradar.collector import collect_sources

    source = Source(name="unknown", type="html", url="https://example.com")

    articles, errors = collect_sources([source], category="art")

    assert articles == []
    assert len(errors) == 1
    assert "Unsupported source type" in errors[0]


@pytest.mark.unit
def test_collect_rss_parses_article() -> None:
    from artradar.collector import _collect_rss

    source = Source(name="Artforum", type="rss", url="https://www.artforum.com/feed/")
    response = SimpleNamespace(content=b"<rss />")
    parsed = SimpleNamespace(entries=[_feed_entry()])

    with (
        patch("artradar.collector._fetch_url_with_retry", return_value=response),
        patch("artradar.collector.feedparser.parse", return_value=parsed),
    ):
        articles = _collect_rss(source, category="art", limit=10, timeout=15)

    assert len(articles) == 1
    assert articles[0].title == "Painting fair opens"
    assert articles[0].source == "Artforum"


@pytest.mark.unit
def test_collect_rss_missing_title_uses_default() -> None:
    from artradar.collector import _collect_rss

    source = Source(name="Artnet", type="rss", url="https://news.artnet.com/feed")
    response = SimpleNamespace(content=b"<rss />")
    parsed = SimpleNamespace(entries=[_feed_entry(title="")])

    with (
        patch("artradar.collector._fetch_url_with_retry", return_value=response),
        patch("artradar.collector.feedparser.parse", return_value=parsed),
    ):
        articles = _collect_rss(source, category="art", limit=10, timeout=15)

    assert articles[0].title == "(no title)"


@pytest.mark.unit
def test_collect_rss_network_error_raises_custom_error() -> None:
    from artradar.collector import _collect_rss
    from artradar.exceptions import NetworkError

    source = Source(name="ARTnews", type="rss", url="https://www.artnews.com/feed/")

    with patch(
        "artradar.collector._fetch_url_with_retry",
        side_effect=requests.exceptions.Timeout("timeout"),
    ):
        with pytest.raises(NetworkError):
            _ = _collect_rss(source, category="art", limit=10, timeout=15)


@pytest.mark.unit
def test_collect_rss_parse_error_raises_custom_error() -> None:
    from artradar.collector import _collect_rss
    from artradar.exceptions import ParseError

    source = Source(name="Artforum", type="rss", url="https://www.artforum.com/feed/")
    response = SimpleNamespace(content=b"<rss />")

    with (
        patch("artradar.collector._fetch_url_with_retry", return_value=response),
        patch("artradar.collector.feedparser.parse", side_effect=ValueError("bad xml")),
    ):
        with pytest.raises(ParseError):
            _ = _collect_rss(source, category="art", limit=10, timeout=15)


@pytest.mark.unit
def test_collect_sources_dispatches_rss() -> None:
    from artradar.collector import collect_sources

    source = Source(name="월간미술", type="rss", url="https://monthlyart.com/feed/")
    fake_article = SimpleNamespace(
        title="Art review",
        link="https://example.com/review",
        summary="Summary",
        published=datetime.now(UTC),
        source="월간미술",
        category="art",
        matched_entities={},
        collected_at=None,
    )

    with patch("artradar.collector._collect_rss", return_value=[fake_article]):
        articles, errors = collect_sources([source], category="art")

    assert len(articles) == 1
    assert errors == []
