from __future__ import annotations

import html
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import struct_time
from urllib.parse import urlparse, urlsplit, urlunsplit

import feedparser
import requests
from pybreaker import CircuitBreakerError
from requests.adapters import HTTPAdapter
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from urllib3.util.retry import Retry

from .exceptions import NetworkError, ParseError, SourceError
from .models import Article, Source
from .resilience import get_circuit_breaker_manager

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; ArtRadarBot/1.0; +https://github.com/zzragida/ai-frendly-datahub)",
}


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
) -> requests.Response:
    merged = {**_DEFAULT_HEADERS, **(headers or {})}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        reraise=True,
    )
    def _fetch() -> requests.Response:
        if session is not None:
            response = session.get(url, timeout=timeout, headers=merged, params=params)
        else:
            response = requests.get(url, timeout=timeout, headers=merged, params=params)
        response.raise_for_status()
        return response

    return _fetch()


def collect_sources(
    sources: list[Source],
    *,
    category: str,
    limit_per_source: int = 30,
    timeout: int = 15,
    min_interval_per_host: float = 0.5,
    max_workers: int | None = None,
) -> tuple[list[Article], list[str]]:
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
    session = _create_session()

    def _collect_for_source(source: Source) -> tuple[list[Article], list[str]]:
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
            return result, []
        except CircuitBreakerError:
            return [], [f"{source.name}: Circuit breaker open (source unavailable)"]
        except SourceError as exc:
            return [], [str(exc)]
        except (NetworkError, ParseError) as exc:
            return [], [f"{source.name}: {exc}"]
        except Exception as exc:
            return [], [f"{source.name}: Unexpected error - {type(exc).__name__}: {exc}"]

    try:
        if workers == 1:
            for source in sources:
                source_articles, source_errors = _collect_for_source(source)
                articles.extend(source_articles)
                errors.extend(source_errors)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_map: list[Future[tuple[list[Article], list[str]]]] = [
                    executor.submit(_collect_for_source, source) for source in sources
                ]

                for future in future_map:
                    source_articles, source_errors = future.result()
                    articles.extend(source_articles)
                    errors.extend(source_errors)
    finally:
        session.close()

    return articles, errors


def _collect_single(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    source_type = source.type.lower()
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
        response = _fetch_url_with_retry(source.url, timeout, session=session)
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
            # Data validation: skip entries without title or link
            if not title or title == "(no title)" or not link:
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
    try:
        for object_id in object_ids:
            detail_response = _fetch_url_with_retry(
                f"{source.url.rstrip('/')}/{object_id}", timeout, session=session
            )
            detail = detail_response.json()
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
