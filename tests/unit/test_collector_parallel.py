from __future__ import annotations

import os
import threading
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from pybreaker import CircuitBreakerError

from artradar.collector import RateLimiter, collect_sources
from artradar.exceptions import NetworkError, SourceError
from artradar.models import Article, Source


def _build_sources(count: int) -> list[Source]:
    return [
        Source(name=f"source_{idx}", type="rss", url=f"https://example{idx}.com/feed")
        for idx in range(count)
    ]


def _pass_through_manager() -> Mock:
    breaker = Mock()
    breaker.call.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)
    manager = Mock()
    manager.get_breaker.return_value = breaker
    return manager


def test_parallel_collection_reduces_runtime() -> None:
    sources = _build_sources(5)
    manager = _pass_through_manager()

    def delayed_collect(
        source: Source,
        *,
        category: str,
        limit: int,
        timeout: int,
        session: object | None = None,
    ) -> list[Article]:
        time.sleep(0.5)
        return [
            Article(
                title=f"article-{source.name}",
                link=f"https://example.com/{source.name}",
                summary="ok",
                published=None,
                source=source.name,
                category=category,
            )
        ]

    mock_health_store = Mock()
    mock_health_store.is_disabled.return_value = False

    with (
        patch("artradar.collector._collect_single", side_effect=delayed_collect),
        patch("artradar.collector.get_circuit_breaker_manager", return_value=manager),
        patch("artradar.collector.CrawlHealthStore", return_value=mock_health_store),
        patch("artradar.collector._create_session"),
        patch.dict(os.environ, {"RADAR_MAX_WORKERS": "5"}, clear=False),
    ):
        start = time.monotonic()
        articles, errors = collect_sources(sources, category="test", min_interval_per_host=0.0)
        elapsed = time.monotonic() - start

    assert len(articles) == 5
    assert errors == []
    assert elapsed < 1.4


def test_parallel_collection_isolates_source_errors() -> None:
    sources = _build_sources(5)
    manager = _pass_through_manager()

    def selective_collect(
        source: Source,
        *,
        category: str,
        limit: int,
        timeout: int,
        session: object | None = None,
    ) -> list[Article]:
        if source.name == "source_0" or source.name == "source_3":
            return [
                Article(
                    title=f"article-{source.name}",
                    link=f"https://example.com/{source.name}",
                    summary="ok",
                    published=None,
                    source=source.name,
                    category=category,
                )
            ]
        if source.name == "source_1":
            raise SourceError(source.name, "boom")
        if source.name == "source_2":
            raise NetworkError("timeout")
        raise TimeoutError("simulated timeout")

    with (
        patch("artradar.collector._collect_single", side_effect=selective_collect),
        patch("artradar.collector.get_circuit_breaker_manager", return_value=manager),
        patch.dict(os.environ, {"RADAR_MAX_WORKERS": "5"}, clear=False),
    ):
        articles, errors = collect_sources(sources, category="test", min_interval_per_host=0.0)

    assert len(articles) == 2
    assert {item.source for item in articles} == {"source_0", "source_3"}
    assert len(errors) == 3


def test_max_workers_one_preserves_sequential_order() -> None:
    sources = _build_sources(5)
    manager = _pass_through_manager()

    def ordered_collect(
        source: Source,
        *,
        category: str,
        limit: int,
        timeout: int,
        session: object | None = None,
    ) -> list[Article]:
        return [
            Article(
                title=f"article-{source.name}",
                link=f"https://example.com/{source.name}",
                summary="ok",
                published=None,
                source=source.name,
                category=category,
            )
        ]

    with (
        patch("artradar.collector._collect_single", side_effect=ordered_collect),
        patch("artradar.collector.get_circuit_breaker_manager", return_value=manager),
        patch.dict(os.environ, {"RADAR_MAX_WORKERS": "5"}, clear=False),
    ):
        articles, errors = collect_sources(
            sources,
            category="test",
            min_interval_per_host=0.0,
            max_workers=1,
        )

    assert errors == []
    assert [item.source for item in articles] == [source.name for source in sources]


def test_rate_limiter_is_thread_safe() -> None:
    limiter = RateLimiter(min_interval=0.0)
    assert hasattr(limiter, "_lock")

    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(500):
                limiter.acquire()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_env_var_radar_max_workers_is_used() -> None:
    sources = _build_sources(2)
    manager = _pass_through_manager()
    mock_future = Mock()
    mock_future.result.return_value = ([], [])

    with (
        patch("artradar.collector._collect_single", return_value=[]),
        patch("artradar.collector.get_circuit_breaker_manager", return_value=manager),
        patch("artradar.collector.ThreadPoolExecutor") as mock_executor,
        patch.dict(os.environ, {"RADAR_MAX_WORKERS": "7"}, clear=False),
    ):
        executor_instance = mock_executor.return_value.__enter__.return_value
        executor_instance.submit.return_value = mock_future
        collect_sources(sources, category="test", min_interval_per_host=0.0)

    mock_executor.assert_called_once_with(max_workers=7)


@pytest.mark.parametrize("env_value,expected_workers", [("999", 10), ("-3", 1), ("invalid", 5)])
def test_max_workers_is_capped_and_validated(env_value: str, expected_workers: int) -> None:
    sources = _build_sources(2)
    manager = _pass_through_manager()
    mock_future = Mock()
    mock_future.result.return_value = ([], [])

    with (
        patch("artradar.collector._collect_single", return_value=[]),
        patch("artradar.collector.get_circuit_breaker_manager", return_value=manager),
        patch("artradar.collector.ThreadPoolExecutor") as mock_executor,
        patch.dict(os.environ, {"RADAR_MAX_WORKERS": env_value}, clear=False),
    ):
        executor_instance = mock_executor.return_value.__enter__.return_value
        executor_instance.submit.return_value = mock_future
        _, _ = collect_sources(sources, category="test", min_interval_per_host=0.0)

    if expected_workers == 1:
        mock_executor.assert_not_called()
    else:
        mock_executor.assert_called_once_with(max_workers=expected_workers)


def test_browser_collection_receives_cli_timeout_in_milliseconds() -> None:
    source = Source(name="JS Source", type="javascript", url="https://example.com")
    mock_session = Mock()
    mock_health_store = Mock()

    with (
        patch("artradar.collector.CrawlHealthStore", return_value=mock_health_store),
        patch("artradar.collector._create_session", return_value=mock_session),
        patch(
            "artradar.browser_collector.collect_browser_sources",
            return_value=([], []),
        ) as mock_browser_collect,
    ):
        articles, errors = collect_sources(
            [source],
            category="art",
            timeout=5,
            health_db_path=":memory:",
        )

    assert articles == []
    assert errors == []
    assert mock_browser_collect.call_args.kwargs["timeout"] == 5_000
    assert mock_browser_collect.call_args.kwargs["health_db_path"] == ":memory:"
    mock_session.close.assert_called_once()
    mock_health_store.close.assert_called_once()


def test_browser_source_limit_caps_js_sources_for_bounded_smoke() -> None:
    sources = [
        Source(name="JS Source 1", type="javascript", url="https://example.com/1"),
        Source(name="JS Source 2", type="javascript", url="https://example.com/2"),
        Source(name="JS Source 3", type="javascript", url="https://example.com/3"),
    ]
    mock_session = Mock()
    mock_health_store = Mock()

    with (
        patch("artradar.collector.CrawlHealthStore", return_value=mock_health_store),
        patch("artradar.collector._create_session", return_value=mock_session),
        patch(
            "artradar.browser_collector.collect_browser_sources",
            return_value=([], []),
        ) as mock_browser_collect,
    ):
        _, _ = collect_sources(
            sources,
            category="art",
            timeout=5,
            browser_source_limit=2,
            health_db_path=":memory:",
        )

    browser_sources = mock_browser_collect.call_args.args[0]
    assert [source.name for source in browser_sources] == ["JS Source 1", "JS Source 2"]


def test_browser_collection_import_error_is_logged_and_ignored() -> None:
    source = Source(name="JS Source", type="javascript", url="https://example.com")
    mock_session = Mock()
    mock_health_store = Mock()
    original_import = __import__

    def fake_import(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "artradar.browser_collector" or (
            level == 1 and name == "browser_collector" and "collect_browser_sources" in fromlist
        ):
            raise ImportError("missing browser collector")
        return original_import(name, globals, locals, fromlist, level)

    with (
        patch("artradar.collector.CrawlHealthStore", return_value=mock_health_store),
        patch("artradar.collector._create_session", return_value=mock_session),
        patch("builtins.__import__", side_effect=fake_import),
    ):
        articles, errors = collect_sources(
            [source],
            category="art",
            timeout=5,
            health_db_path=":memory:",
        )

    assert articles == []
    assert errors == []


def test_collect_sources_reports_disabled_source_from_health_store() -> None:
    source = Source(name="Disabled Health", type="rss", url="https://example.com/feed")
    mock_session = Mock()
    mock_health_store = Mock()
    mock_health_store.is_disabled.return_value = True

    with (
        patch("artradar.collector.CrawlHealthStore", return_value=mock_health_store),
        patch("artradar.collector._create_session", return_value=mock_session),
    ):
        articles, errors = collect_sources(
            [source],
            category="art",
            max_workers=1,
            health_db_path=":memory:",
        )

    assert articles == []
    assert errors == ["Disabled Health: Source disabled (crawl health threshold reached)"]
    mock_session.close.assert_called_once()
    mock_health_store.close.assert_called_once()


def test_collect_sources_reports_circuit_breaker_open() -> None:
    source = Source(name="Broken", type="rss", url="https://example.com/feed")
    breaker = Mock()
    breaker.call.side_effect = CircuitBreakerError("open")
    manager = Mock()
    manager.get_breaker.return_value = breaker

    with patch("artradar.collector.get_circuit_breaker_manager", return_value=manager):
        articles, errors = collect_sources(
            [source],
            category="art",
            max_workers=1,
            min_interval_per_host=0.0,
        )

    assert articles == []
    assert errors == ["Broken: Circuit breaker open (source unavailable)"]


def test_collect_sources_deduplicates_and_filters_stale_articles() -> None:
    source = Source(name="Feed", type="rss", url="https://example.com/feed")
    fresh = Article(
        title="Fresh",
        link="https://example.com/shared",
        summary="fresh",
        published=datetime.now(UTC),
        source="Feed",
        category="art",
    )
    duplicate = Article(
        title="Duplicate",
        link="https://example.com/shared",
        summary="duplicate",
        published=datetime.now(UTC),
        source="Feed",
        category="art",
    )
    stale = Article(
        title="Stale",
        link="https://example.com/stale",
        summary="stale",
        published=datetime.now(UTC) - timedelta(days=30),
        source="Feed",
        category="art",
    )

    with (
        patch("artradar.collector._collect_single", return_value=[fresh, duplicate, stale]),
        patch(
            "artradar.collector.get_circuit_breaker_manager", return_value=_pass_through_manager()
        ),
    ):
        articles, errors = collect_sources(
            [source],
            category="art",
            max_workers=1,
            min_interval_per_host=0.0,
            max_age_days=7,
        )

    assert errors == []
    assert [article.title for article in articles] == ["Fresh"]
