from __future__ import annotations

import html
import os
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import struct_time
from urllib.parse import urlsplit, urlunsplit

import feedparser
import requests
from pybreaker import CircuitBreakerError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .exceptions import NetworkError, ParseError, SourceError
from .models import Article, Source
from .resilience import get_circuit_breaker_manager

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; ArtRadarBot/1.0; +https://github.com/zzragida/ai-frendly-datahub)",
}


def _fetch_url_with_retry(
    url: str,
    timeout: int,
    headers: dict[str, str] | None = None,
    params: dict[str, str | int | bool] | None = None,
) -> requests.Response:
    merged = {**_DEFAULT_HEADERS, **(headers or {})}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        reraise=True,
    )
    def _fetch() -> requests.Response:
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
) -> tuple[list[Article], list[str]]:
    articles: list[Article] = []
    errors: list[str] = []
    manager = get_circuit_breaker_manager()

    for source in sources:
        try:
            breaker = manager.get_breaker(source.name)
            if source.type.lower() == "rss":
                articles.extend(
                    breaker.call(
                        _collect_rss,
                        source,
                        category=category,
                        limit=limit_per_source,
                        timeout=timeout,
                    )
                )
            elif source.type.lower() == "met_museum":
                articles.extend(
                    breaker.call(
                        _collect_met_museum,
                        source,
                        category=category,
                        limit=limit_per_source,
                        timeout=timeout,
                    )
                )
            elif source.type.lower() == "aic":
                articles.extend(
                    breaker.call(
                        _collect_aic,
                        source,
                        category=category,
                        limit=limit_per_source,
                        timeout=timeout,
                    )
                )
            elif source.type.lower() == "smithsonian":
                articles.extend(
                    breaker.call(
                        _collect_smithsonian,
                        source,
                        category=category,
                        limit=limit_per_source,
                        timeout=timeout,
                    )
                )
            else:
                errors.append(f"{source.name}: Unsupported source type '{source.type}'")
        except CircuitBreakerError:
            errors.append(f"{source.name}: Circuit breaker open (source unavailable)")
        except SourceError as exc:
            errors.append(str(exc))
        except (NetworkError, ParseError) as exc:
            errors.append(f"{source.name}: {exc}")
        except Exception as exc:
            errors.append(f"{source.name}: Unexpected error - {type(exc).__name__}: {exc}")

    return articles, errors


def _collect_rss(source: Source, *, category: str, limit: int, timeout: int) -> list[Article]:
    if source.type.lower() != "rss":
        raise SourceError(source.name, f"Unsupported source type '{source.type}'")

    try:
        response = _fetch_url_with_retry(source.url, timeout)
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
            items.append(
                Article(
                    title=html.unescape(_entry_string(entry, "title").strip()) or "(no title)",
                    link=_entry_string(entry, "link").strip(),
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
    source: Source, *, category: str, limit: int, timeout: int
) -> list[Article]:
    search_url = _replace_path(source.url, "/public/collection/v1/search")
    try:
        search_response = _fetch_url_with_retry(
            search_url,
            timeout,
            params={"q": "art", "hasImages": True},
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
                f"{source.url.rstrip('/')}/{object_id}", timeout
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


def _collect_aic(source: Source, *, category: str, limit: int, timeout: int) -> list[Article]:
    try:
        response = _fetch_url_with_retry(
            source.url,
            timeout,
            params={
                "limit": limit,
                "fields": "id,title,artist_display,date_display,medium_display,department_title",
            },
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
    source: Source, *, category: str, limit: int, timeout: int
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
