from __future__ import annotations

import html
import logging
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from time import struct_time
from urllib.parse import urlparse, urlsplit, urlunsplit

import feedparser
import requests
import structlog
from pybreaker import CircuitBreakerError
from requests.adapters import HTTPAdapter
from radar_core import AdaptiveThrottler, CrawlHealthStore
from urllib3.util.retry import Retry

from .exceptions import NetworkError, ParseError, SourceError
from .models import Article, Source
from .resilience import get_circuit_breaker_manager

logger = structlog.get_logger(__name__)
_log = logging.getLogger(__name__)

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; ArtRadarBot/1.0; +https://github.com/zzragida/ai-frendly-datahub)",
}
_DEFAULT_HEALTH_DB_PATH = "data/radar_data.duckdb"
_COLLECTION_CONTROL_LOCK = threading.Lock()
_ACTIVE_THROTTLER: AdaptiveThrottler | None = None
_ACTIVE_HEALTH_STORE: CrawlHealthStore | None = None


def _set_collection_controls(throttler: AdaptiveThrottler, health_store: CrawlHealthStore) -> None:
    global _ACTIVE_THROTTLER, _ACTIVE_HEALTH_STORE
    with _COLLECTION_CONTROL_LOCK:
        _ACTIVE_THROTTLER = throttler
        _ACTIVE_HEALTH_STORE = health_store


def _clear_collection_controls() -> None:
    global _ACTIVE_THROTTLER, _ACTIVE_HEALTH_STORE
    with _COLLECTION_CONTROL_LOCK:
        _ACTIVE_THROTTLER = None
        _ACTIVE_HEALTH_STORE = None


def _get_collection_controls() -> tuple[AdaptiveThrottler | None, CrawlHealthStore | None]:
    with _COLLECTION_CONTROL_LOCK:
        return _ACTIVE_THROTTLER, _ACTIVE_HEALTH_STORE


class RateLimiter:
    def __init__(self, min_interval: float = 0.5):
        self._min_interval: float = min_interval
        self._last_request: float = 0.0
        self._lock: threading.Lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()


def _resolve_max_workers(max_workers: int | None = None) -> int:
    if max_workers is None:
        raw_value = os.environ.get("RADAR_MAX_WORKERS", "5")
        try:
            parsed = int(raw_value)
        except ValueError:
            parsed = 5
    else:
        parsed = max_workers

    return max(1, min(parsed, 10))


def _create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[408, 429, 500, 502, 503, 504, 522, 524],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def _fetch_url_with_retry(
    url: str,
    timeout: int,
    headers: dict[str, str] | None = None,
    params: dict[str, str | int | bool] | None = None,
    session: requests.Session | None = None,
    source_name: str | None = None,
    throttler: AdaptiveThrottler | None = None,
    health_store: CrawlHealthStore | None = None,
    max_attempts: int = 3,
) -> requests.Response:
    """Fetch URL with retry logic on transient errors."""
    merged = {**_DEFAULT_HEADERS, **(headers or {})}
    if throttler is None or health_store is None:
        active_throttler, active_health_store = _get_collection_controls()
        throttler = throttler or active_throttler
        health_store = health_store or active_health_store

    retryable_errors = (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.HTTPError,
    )

    for attempt in range(max_attempts):
        if source_name is not None and throttler is not None:
            throttler.acquire(source_name)

        try:
            if session is not None:
                response = session.get(url, timeout=timeout, headers=merged, params=params)
            else:
                response = requests.get(url, timeout=timeout, headers=merged, params=params)
            response.raise_for_status()

            if source_name is not None and throttler is not None:
                throttler.record_success(source_name)
                if health_store is not None:
                    delay = throttler.get_current_delay(source_name)
                    health_store.record_success(source_name, delay)

            return response
        except retryable_errors as exc:
            if source_name is not None and throttler is not None:
                retry_after: int | str | None = None
                if isinstance(exc, requests.exceptions.HTTPError):
                    response = exc.response
                    if response is not None and response.status_code == 429:
                        retry_after = _parse_retry_after(response.headers.get("Retry-After"))

                throttler.record_failure(source_name, retry_after=retry_after)
                if health_store is not None:
                    delay = throttler.get_current_delay(source_name)
                    health_store.record_failure(source_name, str(exc), delay)

            if attempt == max_attempts - 1:
                raise

    raise RuntimeError("Retry loop exited unexpectedly")


def _parse_retry_after(value: str | None) -> int | str | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    if stripped.isdigit():
        return int(stripped)

    return stripped


def collect_sources(
    sources: list[Source],
    *,
    category: str,
    limit_per_source: int = 30,
    timeout: int = 15,
    min_interval_per_host: float = 0.5,
    max_workers: int | None = None,
    health_db_path: str | None = None,
    max_age_days: int | None = None,
) -> tuple[list[Article], list[str]]:
    """Fetch items from all configured sources, returning articles and errors."""
    sources = [source for source in sources if source.enabled]
    if not sources:
        return [], []

    articles: list[Article] = []
    errors: list[str] = []
    manager = get_circuit_breaker_manager()
    workers = _resolve_max_workers(max_workers)
    source_hosts: dict[str, str] = {
        source.name: (urlparse(source.url).netloc.lower() or source.name) for source in sources
    }
    rate_limiters: dict[str, RateLimiter] = {
        host: RateLimiter(min_interval=min_interval_per_host) for host in set(source_hosts.values())
    }
    throttler = AdaptiveThrottler(min_delay=max(0.001, min_interval_per_host))
    health_store = CrawlHealthStore(
        health_db_path or os.environ.get("RADAR_CRAWL_HEALTH_DB_PATH", _DEFAULT_HEALTH_DB_PATH)
    )
    _set_collection_controls(throttler, health_store)
    session = _create_session()

    # --- Source splitting: Pass 1 (RSS/API) vs Pass 2 (JS/browser) ---
    _js_types = {"javascript", "browser"}
    rss_sources = [s for s in sources if s.type.lower() not in _js_types]
    js_sources = [s for s in sources if s.type.lower() in _js_types]

    def _collect_for_source(source: Source) -> tuple[list[Article], list[str]]:
        if health_store.is_disabled(source.name):
            logger.warning(
                "source_disabled",
                source=source.name,
                source_type=source.type,
                reason="crawl health threshold reached",
            )
            return [], [f"{source.name}: Source disabled (crawl health threshold reached)"]

        host = source_hosts[source.name]
        rate_limiters[host].acquire()

        try:
            breaker = manager.get_breaker(source.name)
            result = breaker.call(
                _collect_single,
                source,
                category=category,
                limit=limit_per_source,
                timeout=timeout,
                session=session,
            )
            logger.info(
                "source_collection_success",
                source=source.name,
                source_type=source.type,
                article_count=len(result),
            )
            return result, []
        except CircuitBreakerError:
            logger.warning(
                "circuit_breaker_open",
                source=source.name,
                source_type=source.type,
            )
            return [], [f"{source.name}: Circuit breaker open (source unavailable)"]
        except SourceError as exc:
            logger.warning(
                "source_error",
                source=source.name,
                source_type=source.type,
                error=str(exc),
            )
            return [], [str(exc)]
        except (NetworkError, ParseError) as exc:
            logger.warning(
                "collection_error",
                source=source.name,
                source_type=source.type,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return [], [f"{source.name}: {exc}"]
        except Exception as exc:
            logger.error(
                "unexpected_source_error",
                source=source.name,
                source_type=source.type,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return [], [f"{source.name}: Unexpected error - {type(exc).__name__}: {exc}"]

    try:
        # --- Pass 1: RSS/API sources via ThreadPoolExecutor (parallel) ---
        if workers == 1:
            for source in rss_sources:
                source_articles, source_errors = _collect_for_source(source)
                articles.extend(source_articles)
                errors.extend(source_errors)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_map: list[Future[tuple[list[Article], list[str]]]] = [
                    executor.submit(_collect_for_source, source) for source in rss_sources
                ]

                for future in future_map:
                    source_articles, source_errors = future.result()
                    articles.extend(source_articles)
                    errors.extend(source_errors)

        # --- Pass 2: JavaScript/browser sources via Playwright (sequential) ---
        if js_sources:
            try:
                from .browser_collector import collect_browser_sources

                js_articles, js_errors = collect_browser_sources(js_sources, category)
                articles.extend(js_articles)
                errors.extend(js_errors)
            except ImportError:
                logger.warning(
                    "playwright_unavailable",
                    js_source_count=len(js_sources),
                    hint="pip install 'radar-core[browser]'",
                )
    finally:
        session.close()
        health_store.close()
        _clear_collection_controls()

    # --- Deduplicate by link (museum APIs may return overlapping results) ---
    seen_links: set[str] = set()
    unique_articles: list[Article] = []
    for article in articles:
        if article.link not in seen_links:
            seen_links.add(article.link)
            unique_articles.append(article)
    if len(articles) != len(unique_articles):
        logger.info(
            "deduplicated_articles",
            original=len(articles),
            unique=len(unique_articles),
            removed=len(articles) - len(unique_articles),
        )

    # Filter out articles older than max_age_days (freshness gate)
    if max_age_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        before = len(unique_articles)
        unique_articles = [
            a for a in unique_articles if a.published is None or a.published >= cutoff
        ]
        filtered = before - len(unique_articles)
        if filtered > 0:
            logger.info(
                "freshness_filter",
                removed=filtered,
                max_age_days=max_age_days,
                remaining=len(unique_articles),
            )

    return unique_articles, errors


def _collect_single(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    source_type = source.type.lower()

    _source_handlers: dict[str, type | None] = {
        "rss": None,
        "met_museum": None,
        "aic": None,
        "smithsonian": None,
    }

    if source_type not in _source_handlers:
        logger.error(
            "unsupported_source_type",
            source=source.name,
            source_type=source.type,
            supported_types=list(_source_handlers.keys()),
        )
        raise SourceError(source.name, f"Unsupported source type '{source.type}'")

    try:
        if source_type == "rss":
            return _collect_rss(
                source, category=category, limit=limit, timeout=timeout, session=session
            )
        if source_type == "met_museum":
            return _collect_met_museum(
                source,
                category=category,
                limit=limit,
                timeout=timeout,
                session=session,
            )
        if source_type == "aic":
            return _collect_aic(
                source, category=category, limit=limit, timeout=timeout, session=session
            )
        if source_type == "smithsonian":
            return _collect_smithsonian(
                source,
                category=category,
                limit=limit,
                timeout=timeout,
                session=session,
            )
    except (NetworkError, ParseError, SourceError):
        raise
    except Exception as exc:
        logger.error(
            "source_dispatch_error",
            source=source.name,
            source_type=source_type,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise SourceError(
            source.name,
            f"Dispatch error for '{source_type}': {type(exc).__name__}: {exc}",
            exc,
        ) from exc

    # Unreachable but satisfies type checker
    raise SourceError(source.name, f"Unsupported source type '{source.type}'")


def _collect_rss(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    if source.type.lower() != "rss":
        raise SourceError(source.name, f"Unsupported source type '{source.type}'")

    try:
        response = _fetch_url_with_retry(
            source.url,
            timeout,
            session=session,
            source_name=source.name,
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise NetworkError(f"Network error fetching {source.name}: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise SourceError(source.name, f"Request failed: {exc}", exc) from exc

    try:
        feed = feedparser.parse(response.content)
        items: list[Article] = []
        entries = list(getattr(feed, "entries", []))
        for raw_entry in entries[:limit]:
            entry = _entry_dict(raw_entry)
            summary = _entry_string(entry, "summary") or _entry_string(entry, "description")
            if not summary:
                content_items = entry.get("content")
                if isinstance(content_items, list) and content_items:
                    first_item = content_items[0]
                    if isinstance(first_item, dict):
                        summary = str(first_item.get("value") or "")
            title = html.unescape(_entry_string(entry, "title").strip()) or "(no title)"
            link = _entry_string(entry, "link").strip()
            # Keep untitled entries but skip records without a stable link.
            if not link:
                continue
            items.append(
                Article(
                    title=title,
                    link=link,
                    summary=html.unescape(summary.strip()),
                    published=_extract_datetime(entry),
                    source=source.name,
                    category=category,
                )
            )
        return items
    except Exception as exc:
        raise ParseError(f"Failed to parse feed from {source.name}: {exc}") from exc


def _collect_met_museum(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    search_url = _replace_path(source.url, "/public/collection/v1/search")
    try:
        search_response = _fetch_url_with_retry(
            search_url,
            timeout,
            params={"q": "art", "hasImages": True},
            session=session,
            source_name=source.name,
        )
        search_data = search_response.json()
        object_ids = list(search_data.get("objectIDs") or [])[:limit]
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise NetworkError(f"Network error fetching {source.name}: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise SourceError(source.name, f"Request failed: {exc}", exc) from exc
    except Exception as exc:
        raise ParseError(f"Failed to parse API response from {source.name}: {exc}") from exc

    items: list[Article] = []
    skipped = 0
    try:
        for object_id in object_ids:
            try:
                detail_response = _fetch_url_with_retry(
                    f"{source.url.rstrip('/')}/{object_id}",
                    timeout,
                    session=session,
                    source_name=source.name,
                )
                detail = detail_response.json()
                if not isinstance(detail, dict):
                    logger.warning(
                        "invalid_api_response_format",
                        source=source.name,
                        object_id=object_id,
                        response_type=type(detail).__name__,
                    )
                    skipped += 1
                    continue
                title = str(detail.get("title") or "Untitled").strip() or "Untitled"
                artist = str(detail.get("artistDisplayName") or "Unknown artist").strip()
                object_date = str(detail.get("objectDate") or "").strip()
                medium = str(detail.get("medium") or "").strip()
                summary_parts = [part for part in (artist, object_date, medium) if part]
                items.append(
                    Article(
                        title=title,
                        link=str(
                            detail.get("objectURL")
                            or f"https://www.metmuseum.org/art/collection/search/{object_id}"
                        ),
                        summary=". ".join(summary_parts) or "No description available",
                        published=_parse_iso_datetime(detail.get("metadataDate")),
                        source=source.name,
                        category=category,
                    )
                )
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                logger.warning(
                    "met_museum_object_fetch_failed",
                    source=source.name,
                    object_id=object_id,
                    error=str(exc),
                )
                skipped += 1
                continue
            except Exception as exc:
                logger.warning(
                    "met_museum_object_parse_failed",
                    source=source.name,
                    object_id=object_id,
                    error=str(exc),
                )
                skipped += 1
                continue

        if skipped > 0:
            logger.warning(
                "met_museum_objects_skipped",
                source=source.name,
                skipped=skipped,
                total=len(object_ids),
                collected=len(items),
            )
        return items
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise NetworkError(f"Network error fetching {source.name}: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise SourceError(source.name, f"Request failed: {exc}", exc) from exc
    except Exception as exc:
        raise ParseError(f"Failed to parse API response from {source.name}: {exc}") from exc


def _collect_aic(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    try:
        response = _fetch_url_with_retry(
            source.url,
            timeout,
            params={
                "limit": limit,
                "fields": "id,title,artist_display,date_display,medium_display,department_title",
            },
            session=session,
            source_name=source.name,
        )
        data = response.json()
        rows = list(data.get("data") or [])
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise NetworkError(f"Network error fetching {source.name}: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise SourceError(source.name, f"Request failed: {exc}", exc) from exc
    except Exception as exc:
        raise ParseError(f"Failed to parse API response from {source.name}: {exc}") from exc

    items: list[Article] = []
    for row in rows[:limit]:
        title = str(row.get("title") or "Untitled").strip() or "Untitled"
        artist = str(row.get("artist_display") or "Unknown artist").strip()
        object_date = str(row.get("date_display") or "").strip()
        medium = str(row.get("medium_display") or "").strip()
        summary_parts = [part for part in (artist, object_date, medium) if part]
        items.append(
            Article(
                title=title,
                link=f"https://www.artic.edu/artworks/{row.get('id')}",
                summary=". ".join(summary_parts) or "No description available",
                published=None,
                source=source.name,
                category=category,
            )
        )
    return items


def _collect_smithsonian(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    api_key = os.environ.get("SMITHSONIAN_API_KEY", "").strip()
    if not api_key:
        raise SourceError(
            source.name, "SMITHSONIAN_API_KEY is required for Smithsonian Open Access API"
        )

    try:
        response = _fetch_url_with_retry(
            source.url,
            timeout,
            params={
                "q": "art",
                "rows": limit,
                "sort": "newest",
                "type": "edanmdm",
                "row_group": "objects",
                "api_key": api_key,
            },
            session=session,
            source_name=source.name,
        )
        data = response.json()
        rows = list((data.get("response") or {}).get("rows") or [])
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise NetworkError(f"Network error fetching {source.name}: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise SourceError(source.name, f"Request failed: {exc}", exc) from exc
    except Exception as exc:
        raise ParseError(f"Failed to parse API response from {source.name}: {exc}") from exc

    items: list[Article] = []
    for row in rows[:limit]:
        content = row.get("content") or {}
        descriptive = content.get("descriptiveNonRepeating") or {}
        freetext = content.get("freetext") or {}
        notes = freetext.get("notes") or []
        summary = "No description available"
        if isinstance(notes, list):
            for note in notes:
                if isinstance(note, dict) and note.get("label") in {"Summary", "Description"}:
                    summary = str(note.get("content") or summary)
                    break
        title = str(row.get("title") or "Untitled").strip() or "Untitled"
        link = str(
            descriptive.get("record_link")
            or f"https://collections.si.edu/search/{row.get('id', '')}"
        )
        source_name = str(descriptive.get("data_source") or source.name)
        items.append(
            Article(
                title=title,
                link=link,
                summary=summary,
                published=_parse_unix_timestamp(row.get("timestamp")),
                source=source_name,
                category=category,
            )
        )
    return items


def _extract_datetime(entry: dict[str, object]) -> datetime | None:
    published_parsed = entry.get("published_parsed")
    if isinstance(published_parsed, struct_time):
        return datetime.fromtimestamp(time.mktime(published_parsed), tz=UTC)
    updated_parsed = entry.get("updated_parsed")
    if isinstance(updated_parsed, struct_time):
        return datetime.fromtimestamp(time.mktime(updated_parsed), tz=UTC)
    for key in ("published", "updated", "date"):
        raw = entry.get(key)
        if raw:
            try:
                parsed = parsedate_to_datetime(str(raw))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed
            except Exception:
                continue
    return None


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_unix_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(str(value)), tz=UTC)
    except (TypeError, ValueError):
        return None


def _replace_path(url: str, new_path: str) -> str:
    split = urlsplit(url)
    return urlunsplit((split.scheme, split.netloc, new_path, "", ""))


def _entry_dict(entry: object) -> dict[str, object]:
    if isinstance(entry, dict):
        return {str(key): value for key, value in entry.items()}
    return {}


def _entry_string(entry: dict[str, object], key: str) -> str:
    value = entry.get(key)
    return str(value) if isinstance(value, str) else ""
