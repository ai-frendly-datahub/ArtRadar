from __future__ import annotations

import os
import time as time_module
from datetime import UTC, datetime
from time import struct_time
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
def test_collect_sources_skips_disabled_sources() -> None:
    from artradar.collector import collect_sources

    source = Source(
        name="Disabled Feed",
        type="rss",
        url="https://example.com/feed",
        enabled=False,
    )

    with patch("artradar.collector._collect_single") as mock_collect:
        articles, errors = collect_sources([source], category="art")

    assert articles == []
    assert errors == []
    mock_collect.assert_not_called()


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
def test_collect_rss_uses_content_fallback_and_skips_missing_links() -> None:
    from artradar.collector import _collect_rss

    source = Source(name="Artforum", type="rss", url="https://www.artforum.com/feed/")
    response = SimpleNamespace(content=b"<rss />")
    parsed = SimpleNamespace(
        entries=[
            {
                "title": "Content fallback",
                "link": "https://example.com/content",
                "content": [{"value": "Fallback body"}],
            },
            {
                "title": "No link",
                "summary": "Skipped because there is no stable URL",
            },
        ]
    )

    with (
        patch("artradar.collector._fetch_url_with_retry", return_value=response),
        patch("artradar.collector.feedparser.parse", return_value=parsed),
    ):
        articles = _collect_rss(source, category="art", limit=10, timeout=15)

    assert len(articles) == 1
    assert articles[0].summary == "Fallback body"


@pytest.mark.unit
def test_collect_rss_rejects_non_rss_source_type() -> None:
    from artradar.collector import _collect_rss
    from artradar.exceptions import SourceError

    source = Source(name="HTML", type="html", url="https://example.com")

    with pytest.raises(SourceError):
        _collect_rss(source, category="art", limit=10, timeout=15)


@pytest.mark.unit
def test_extract_datetime_treats_feedparser_struct_time_as_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artradar.collector import _extract_datetime

    original_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Asia/Seoul")
    if hasattr(time_module, "tzset"):
        time_module.tzset()

    try:
        parsed = time_module.strptime("2024-03-12 10:00:00", "%Y-%m-%d %H:%M:%S")
        result = _extract_datetime({"published_parsed": parsed})
    finally:
        if original_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", original_tz)
        if hasattr(time_module, "tzset"):
            time_module.tzset()

    assert result == datetime(2024, 3, 12, 10, 0, tzinfo=UTC)


@pytest.mark.unit
def test_collector_datetime_and_entry_helpers_cover_fallbacks() -> None:
    from artradar.collector import (
        _entry_dict,
        _extract_datetime,
        _parse_iso_datetime,
        _parse_retry_after,
        _parse_unix_timestamp,
    )

    parsed = struct_time((2026, 3, 13, 9, 0, 0, 4, 72, 0))

    assert _extract_datetime({"updated_parsed": parsed}) == datetime(2026, 3, 13, 9, 0, tzinfo=UTC)
    assert _extract_datetime({"published": "Fri, 13 Mar 2026 09:00:00"}) == datetime(
        2026, 3, 13, 9, 0, tzinfo=UTC
    )
    assert _extract_datetime({"published": "not a date", "updated": "also bad"}) is None
    assert _parse_iso_datetime(None) is None
    assert _parse_iso_datetime("") is None
    assert _parse_iso_datetime("bad") is None
    assert _parse_unix_timestamp(None) is None
    assert _parse_unix_timestamp("bad") is None
    assert _entry_dict(object()) == {}
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("   ") is None
    assert _parse_retry_after("120") == 120
    assert _parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == ("Wed, 21 Oct 2015 07:28:00 GMT")


@pytest.mark.unit
def test_fetch_url_with_retry_records_throttled_failure() -> None:
    from artradar.collector import _fetch_url_with_retry

    response = Mock()
    response.status_code = 429
    response.headers = {"Retry-After": "5"}
    error = requests.exceptions.HTTPError("rate limited", response=response)
    response.raise_for_status.side_effect = error
    session = Mock()
    session.get.return_value = response
    throttler = Mock()
    throttler.get_current_delay.return_value = 5.0
    health_store = Mock()

    with pytest.raises(requests.exceptions.HTTPError):
        _fetch_url_with_retry(
            "https://example.com/feed",
            15,
            session=session,
            source_name="Artforum",
            throttler=throttler,
            health_store=health_store,
            max_attempts=1,
        )

    throttler.record_failure.assert_called_once_with("Artforum", retry_after=5)
    health_store.record_failure.assert_called_once_with("Artforum", "rate limited", 5.0)


@pytest.mark.unit
def test_fetch_url_with_retry_zero_attempts_raises_runtime_error() -> None:
    from artradar.collector import _fetch_url_with_retry

    with pytest.raises(RuntimeError):
        _fetch_url_with_retry("https://example.com/feed", 15, max_attempts=0)


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
