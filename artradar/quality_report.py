from __future__ import annotations

import json
import hashlib
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import Article, CategoryConfig, Source


TRACKED_EVENT_MODEL_ORDER = [
    "auction_result",
    "art_fair_participant",
    "exhibition_ticket_signal",
    "artist_institution_entity",
]
TRACKED_EVENT_MODELS = set(TRACKED_EVENT_MODEL_ORDER)


def build_quality_report(
    *,
    category: CategoryConfig,
    articles: Iterable[Article],
    errors: Iterable[str] | None = None,
    quality_config: Mapping[str, object] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = _as_utc(generated_at or datetime.now(UTC))
    articles_list = list(articles)
    errors_list = [str(error) for error in (errors or [])]
    quality = _dict(quality_config or {}, "data_quality")
    freshness_sla = _dict(quality, "freshness_sla")
    event_model_config = _dict(quality, "event_models")
    tracked_event_models = _tracked_event_models(quality)

    events = _build_event_rows(
        articles=articles_list,
        sources=category.sources,
        tracked_event_models=tracked_event_models,
        event_model_config=event_model_config,
    )
    source_rows = [
        _build_source_row(
            source=source,
            articles=articles_list,
            event_rows=events,
            errors=errors_list,
            freshness_sla=freshness_sla,
            tracked_event_models=tracked_event_models,
            generated_at=generated,
        )
        for source in category.sources
    ]

    status_counts = Counter(str(row["status"]) for row in source_rows)
    event_counts = Counter(str(row["event_model"]) for row in events)
    summary = {
        "total_sources": len(source_rows),
        "enabled_sources": sum(1 for row in source_rows if row["enabled"]),
        "tracked_sources": sum(1 for row in source_rows if row["tracked"]),
        "fresh_sources": status_counts.get("fresh", 0),
        "stale_sources": status_counts.get("stale", 0),
        "missing_sources": status_counts.get("missing", 0),
        "missing_event_sources": status_counts.get("missing_event", 0),
        "unknown_event_date_sources": status_counts.get("unknown_event_date", 0),
        "not_tracked_sources": status_counts.get("not_tracked", 0),
        "skipped_disabled_sources": status_counts.get("skipped_disabled", 0),
        "collection_error_count": len(errors_list),
    }
    for event_model in TRACKED_EVENT_MODEL_ORDER:
        summary[f"{event_model}_events"] = event_counts.get(event_model, 0)
    summary.update(
        _event_quality_summary(
            events=events,
            source_rows=source_rows,
            quality_config=quality_config or {},
            tracked_event_models=tracked_event_models,
        )
    )
    daily_review_items = _daily_review_items(
        events=events,
        source_rows=source_rows,
        quality_config=quality_config or {},
        tracked_event_models=tracked_event_models,
    )
    summary["daily_review_item_count"] = len(daily_review_items)

    return {
        "category": category.category_name,
        "generated_at": generated.isoformat(),
        "scope_note": (
            "ArtRadar separates exhibition, auction, art-fair, and artist-institution "
            "signals from broad art news and community feeds. Community feeds are kept "
            "as context until canonical artist, institution, or market fields are present."
        ),
        "summary": summary,
        "sources": source_rows,
        "events": events,
        "daily_review_items": daily_review_items,
        "source_backlog": (quality_config or {}).get("source_backlog", {}),
        "errors": errors_list,
    }


def write_quality_report(
    report: Mapping[str, object],
    *,
    output_dir: Path,
    category_name: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = _parse_datetime(str(report.get("generated_at") or "")) or datetime.now(
        UTC
    )
    date_stamp = _as_utc(generated_at).strftime("%Y%m%d")
    latest_path = output_dir / f"{category_name}_quality.json"
    dated_path = output_dir / f"{category_name}_{date_stamp}_quality.json"
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    latest_path.write_text(encoded + "\n", encoding="utf-8")
    dated_path.write_text(encoded + "\n", encoding="utf-8")
    return {"latest": latest_path, "dated": dated_path}


def _build_event_rows(
    *,
    articles: list[Article],
    sources: list[Source],
    tracked_event_models: set[str],
    event_model_config: Mapping[str, object],
) -> list[dict[str, Any]]:
    source_map = {source.name: source for source in sources}
    rows: list[dict[str, Any]] = []
    for article in articles:
        source = source_map.get(article.source)
        if source is None:
            continue
        if not source.enabled:
            continue
        event_model = _source_event_model(source)
        if event_model not in tracked_event_models:
            continue
        event_at = _event_datetime(article, source)
        row = {
            "source": source.name,
            "source_type": source.type,
            "trust_tier": source.trust_tier,
            "content_type": source.content_type,
            "collection_tier": source.collection_tier,
            "producer_role": source.producer_role,
            "info_purpose": source.info_purpose,
            "event_model": event_model,
            "title": article.title,
            "url": article.link,
            "source_url": article.link or source.url,
            "event_at": event_at.isoformat() if event_at else None,
            "artist": _matches(article, "Artist"),
            "institution": _matches(article, "Institution"),
            "market": _matches(article, "Market"),
            "genre": _matches(article, "Genre"),
            "period": _matches(article, "Period"),
            "topic": _matches(article, "Topic"),
            "art_general": _matches(article, "ArtGeneral"),
            "artwork_title": _artwork_title(article),
            "hammer_price": _hammer_price(article),
            "currency": _currency(article),
            "fair_id": _fair_id(article, source),
            "organization_name": _organization_name(article),
            "role": _role(article),
            "institution_id": _institution_id(article, source),
            "exhibition_id": _exhibition_id(article),
            "ticket_status": _ticket_status(article),
            "relationship_type": _relationship_type(article),
        }
        canonical_key, canonical_key_status = _canonical_key(row)
        row["canonical_key"] = canonical_key
        row["canonical_key_status"] = canonical_key_status
        row["event_key"] = _event_key(row, event_at)
        row["required_field_proxy"] = _required_field_proxy(row, event_model, event_model_config)
        row["required_field_gaps"] = _required_field_gaps(row, event_model, event_model_config)
        rows.append(row)
    return rows


def _build_source_row(
    *,
    source: Source,
    articles: list[Article],
    event_rows: list[dict[str, Any]],
    errors: list[str],
    freshness_sla: Mapping[str, object],
    tracked_event_models: set[str],
    generated_at: datetime,
) -> dict[str, Any]:
    source_articles = [article for article in articles if article.source == source.name]
    source_errors = [error for error in errors if error.startswith(f"{source.name}:")]
    event_model = _source_event_model(source)
    source_event_rows = [
        row
        for row in event_rows
        if row["source"] == source.name and row["event_model"] == event_model
    ]
    latest_event = _latest_event(source_event_rows)
    latest_event_at = (
        _parse_datetime(str(latest_event.get("event_at") or "")) if latest_event else None
    )
    sla_days = _source_sla_days(source, event_model, freshness_sla)
    age_days = _age_days(generated_at, latest_event_at) if latest_event_at else None
    status = _source_status(
        source=source,
        event_model=event_model,
        tracked_event_models=tracked_event_models,
        article_count=len(source_articles),
        event_count=len(source_event_rows),
        latest_event_at=latest_event_at,
        sla_days=sla_days,
        age_days=age_days,
    )

    return {
        "source": source.name,
        "source_type": source.type,
        "enabled": source.enabled,
        "trust_tier": source.trust_tier,
        "content_type": source.content_type,
        "collection_tier": source.collection_tier,
        "producer_role": source.producer_role,
        "info_purpose": source.info_purpose,
        "tracked": source.enabled and event_model in tracked_event_models,
        "event_model": event_model,
        "freshness_sla_days": sla_days,
        "status": status,
        "article_count": len(source_articles),
        "event_count": len(source_event_rows),
        "latest_event_at": latest_event_at.isoformat() if latest_event_at else None,
        "age_days": round(age_days, 2) if age_days is not None else None,
        "latest_title": str(latest_event.get("title", "")) if latest_event else "",
        "latest_url": str(latest_event.get("url", "")) if latest_event else "",
        "latest_artist": latest_event.get("artist", []) if latest_event else [],
        "latest_institution": latest_event.get("institution", []) if latest_event else [],
        "latest_market": latest_event.get("market", []) if latest_event else [],
        "latest_required_field_proxy": (
            latest_event.get("required_field_proxy", {}) if latest_event else {}
        ),
        "errors": source_errors,
    }


def _source_status(
    *,
    source: Source,
    event_model: str,
    tracked_event_models: set[str],
    article_count: int,
    event_count: int,
    latest_event_at: datetime | None,
    sla_days: float | None,
    age_days: float | None,
) -> str:
    if not source.enabled:
        return "skipped_disabled"
    if event_model not in tracked_event_models:
        return "not_tracked"
    if article_count == 0:
        return "missing"
    if event_count == 0:
        return "missing_event"
    if latest_event_at is None or age_days is None:
        return "unknown_event_date"
    if sla_days is not None and age_days > sla_days:
        return "stale"
    return "fresh"


def _tracked_event_models(quality: Mapping[str, object]) -> set[str]:
    outputs = _dict(quality, "quality_outputs")
    raw = outputs.get("tracked_event_models")
    if isinstance(raw, list):
        values = {str(item).strip() for item in raw if str(item).strip()}
        return values & TRACKED_EVENT_MODELS or set(TRACKED_EVENT_MODELS)
    return set(TRACKED_EVENT_MODELS)


def _source_event_model(source: Source) -> str:
    raw = source.config.get("event_model")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()

    content_type = source.content_type.lower()
    trust_tier = source.trust_tier.lower()
    if content_type in {"auction", "auction_result", "market"}:
        return "auction_result"
    if content_type in {"art_fair", "fair", "exhibitor"}:
        return "art_fair_participant"
    if content_type in {"exhibition", "ticket", "calendar"}:
        return "exhibition_ticket_signal"
    if content_type in {"collection", "news", "review", "video"} and not trust_tier.startswith(
        "t4"
    ):
        return "artist_institution_entity"
    return ""


def _source_sla_days(
    source: Source,
    event_model: str,
    freshness_sla: Mapping[str, object],
) -> float | None:
    raw_source_sla = source.config.get("freshness_sla_days")
    parsed_source_sla = _as_float(raw_source_sla)
    if parsed_source_sla is not None:
        return parsed_source_sla

    suffixed_days = _as_float(freshness_sla.get(f"{event_model}_days"))
    if suffixed_days is not None:
        return suffixed_days

    suffixed_hours = _as_float(freshness_sla.get(f"{event_model}_hours"))
    if suffixed_hours is not None:
        return suffixed_hours / 24
    return None


def _latest_event(event_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    dated: list[tuple[datetime, dict[str, Any]]] = []
    undated: list[dict[str, Any]] = []
    for row in event_rows:
        event_at = _parse_datetime(str(row.get("event_at") or ""))
        if event_at is not None:
            dated.append((event_at, row))
        else:
            undated.append(row)
    if dated:
        return max(dated, key=lambda item: item[0])[1]
    return undated[0] if undated else None


def _event_datetime(article: Article, source: Source) -> datetime | None:
    field = str(
        source.config.get("observed_date_field")
        or source.config.get("event_date_field")
        or ""
    )
    if field == "collected_at":
        return _as_utc(article.collected_at) if article.collected_at else None
    article_time = article.published or article.collected_at
    return _as_utc(article_time) if article_time else None


def _event_quality_summary(
    *,
    events: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    quality_config: Mapping[str, object],
    tracked_event_models: set[str],
) -> dict[str, int]:
    event_counts = Counter(str(row.get("event_model") or "") for row in events)
    return {
        "art_signal_event_count": sum(
            event_counts.get(model, 0) for model in tracked_event_models
        ),
        "official_or_operational_event_count": sum(
            1
            for row in events
            if str(row.get("trust_tier") or "").startswith("T1_")
            or str(row.get("source_type") or "").lower() in {"api", "mcp"}
        ),
        "news_proxy_event_count": sum(
            1 for row in events if str(row.get("content_type") or "").lower() == "news"
        ),
        "complete_canonical_key_count": sum(
            1 for row in events if row.get("canonical_key_status") == "complete"
        ),
        "proxy_canonical_key_count": sum(
            1 for row in events if str(row.get("canonical_key_status") or "").endswith("_proxy")
        ),
        "missing_canonical_key_count": sum(1 for row in events if not row.get("canonical_key")),
        "artist_present_count": sum(1 for row in events if row.get("artist")),
        "institution_present_count": sum(1 for row in events if row.get("institution")),
        "market_present_count": sum(1 for row in events if row.get("market")),
        "hammer_price_present_count": sum(
            1 for row in events if row.get("hammer_price") is not None
        ),
        "event_required_field_gap_count": sum(
            len(row.get("required_field_gaps") or []) for row in events
        ),
        "tracked_source_gap_count": sum(
            1
            for row in source_rows
            if row.get("tracked")
            and row.get("status") in {"missing", "missing_event", "unknown_event_date", "stale"}
        ),
        "missing_event_model_count": sum(
            1 for model in tracked_event_models if event_counts.get(model, 0) == 0
        ),
        "source_backlog_candidate_count": len(_source_backlog_items(quality_config)),
    }


def _daily_review_items(
    *,
    events: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    quality_config: Mapping[str, object],
    tracked_event_models: set[str],
) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    for row in events:
        gaps = [str(value) for value in row.get("required_field_gaps") or []]
        if gaps:
            review.append(
                {
                    "reason": "missing_required_fields",
                    "event_model": row.get("event_model"),
                    "source": row.get("source"),
                    "title": row.get("title"),
                    "canonical_key": row.get("canonical_key"),
                    "required_field_gaps": gaps,
                }
            )
        if str(row.get("canonical_key_status") or "").endswith("_proxy"):
            review.append(
                {
                    "reason": "proxy_canonical_key",
                    "event_model": row.get("event_model"),
                    "source": row.get("source"),
                    "title": row.get("title"),
                    "canonical_key_status": row.get("canonical_key_status"),
                }
            )
    for source in source_rows:
        if source.get("tracked") and source.get("status") in {
            "missing",
            "missing_event",
            "unknown_event_date",
            "stale",
        }:
            review.append(
                {
                    "reason": f"source_{source.get('status')}",
                    "source": source.get("source"),
                    "event_model": source.get("event_model"),
                    "age_days": source.get("age_days"),
                }
            )
    event_counts = Counter(str(row.get("event_model") or "") for row in events)
    for event_model in TRACKED_EVENT_MODEL_ORDER:
        if event_model in tracked_event_models and event_counts.get(event_model, 0) == 0:
            review.append({"reason": "missing_event_model", "event_model": event_model})
    for item in _source_backlog_items(quality_config):
        review.append(
            {
                "reason": "source_backlog_pending",
                "source": item.get("name") or item.get("id"),
                "signal_type": item.get("signal_type"),
                "activation_gate": item.get("activation_gate"),
            }
        )
    return review[:50]


def _source_backlog_items(quality_config: Mapping[str, object]) -> list[Mapping[str, object]]:
    backlog = _dict(quality_config, "source_backlog")
    candidates = backlog.get("operational_candidates")
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, Mapping)]


def _required_field_proxy(
    row: Mapping[str, Any],
    event_model: str,
    event_model_config: Mapping[str, object],
) -> dict[str, bool]:
    event_config = _dict(event_model_config, event_model)
    raw_fields = event_config.get("required_fields")
    if not isinstance(raw_fields, list):
        raw_fields = _default_required_fields(event_model)
    return {str(field): _field_present(row, str(field)) for field in raw_fields if str(field).strip()}


def _required_field_gaps(
    row: Mapping[str, Any],
    event_model: str,
    event_model_config: Mapping[str, object],
) -> list[str]:
    return [
        field
        for field, present in _required_field_proxy(row, event_model, event_model_config).items()
        if not present
    ]


def _default_required_fields(event_model: str) -> list[str]:
    if event_model == "auction_result":
        return ["artist_name", "artwork_title", "hammer_price", "currency", "source_url"]
    if event_model == "art_fair_participant":
        return ["fair_id", "organization_name", "role", "source_url"]
    if event_model == "exhibition_ticket_signal":
        return ["institution_id", "exhibition_id", "ticket_status"]
    if event_model == "artist_institution_entity":
        return ["artist_name", "institution_name", "relationship_type"]
    return ["source_url"]


def _field_present(row: Mapping[str, Any], field: str) -> bool:
    aliases = {
        "artist_name": ("artist",),
        "institution_name": ("institution", "organization_name"),
        "source_url": ("source_url", "url"),
    }
    for alias in aliases.get(field.lower(), (field.lower(),)):
        value = row.get(alias)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        return True
    return False


def _canonical_key(row: Mapping[str, Any]) -> tuple[str, str]:
    event_model = str(row.get("event_model") or "")
    artist = _slug(_first(row.get("artist") if isinstance(row.get("artist"), list) else []))
    institution = _slug(_first(row.get("institution") if isinstance(row.get("institution"), list) else []))
    artwork = _slug(row.get("artwork_title") or "")
    fair_id = _slug(row.get("fair_id") or "")
    exhibition_id = _slug(row.get("exhibition_id") or "")
    source = _slug(row.get("source") or "")
    title = _slug(row.get("title") or "")

    if event_model == "auction_result":
        if artist and artwork:
            return f"artwork:{artist}:{artwork}", "complete"
        if artist:
            return f"artist_market:{artist}", "artist_proxy"
    if event_model == "art_fair_participant":
        if fair_id and institution:
            return f"art_fair:{fair_id}:{institution}", "complete"
        if institution:
            return f"art_fair:institution:{institution}", "institution_proxy"
    if event_model == "exhibition_ticket_signal":
        if exhibition_id:
            return f"exhibition:{exhibition_id}", "complete"
        if institution and title:
            return f"exhibition:{institution}:{_digest(title)}", "institution_proxy"
    if event_model == "artist_institution_entity":
        if artist and institution:
            return f"artist_institution:{artist}:{institution}", "complete"
        if artist:
            return f"artist:{artist}", "artist_proxy"
        if institution:
            return f"institution:{institution}", "institution_proxy"
    if source and title:
        return f"art_source:{source}:{_digest(title)}", "source_proxy"
    return "", "missing"


def _event_key(row: Mapping[str, Any], event_at: datetime | None) -> str:
    observed = _as_utc(event_at).strftime("%Y%m%d") if event_at else "undated"
    basis = row.get("canonical_key") or row.get("source_url") or row.get("title") or ""
    return f"{row.get('event_model')}:{_digest(basis)}:{observed}"


def _artwork_title(article: Article) -> str:
    match = re.search(r"artwork\s*[:=]\s*([^.;,]+)", _article_text(article), re.I)
    return match.group(1).strip() if match else ""


def _hammer_price(article: Article) -> float | None:
    match = re.search(r"(?:hammer|price)\s*[:=]?\s*(?:USD|\$|KRW)?\s*(\d[\d,]*(?:\.\d+)?)", _article_text(article), re.I)
    return float(match.group(1).replace(",", "")) if match else None


def _currency(article: Article) -> str:
    text = _article_text(article)
    if "$" in text or "USD" in text.upper():
        return "USD"
    if "KRW" in text.upper():
        return "KRW"
    return ""


def _fair_id(article: Article, source: Source) -> str:
    raw = source.config.get("fair_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return _slug(_first(_matches(article, "Market")))


def _organization_name(article: Article) -> str:
    return _first(_matches(article, "Institution"))


def _role(article: Article) -> str:
    matches = _matches(article, "Topic") or _matches(article, "ArtGeneral")
    return matches[0] if matches else ""


def _institution_id(article: Article, source: Source) -> str:
    raw = source.config.get("institution_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return _slug(_first(_matches(article, "Institution")))


def _exhibition_id(article: Article) -> str:
    match = re.search(r"exhibition\s*[:=]\s*([^.;,]+)", _article_text(article), re.I)
    return _slug(match.group(1)) if match else ""


def _ticket_status(article: Article) -> str:
    text = _article_text(article).lower()
    if "sold out" in text:
        return "sold_out"
    if "ticket" in text:
        return "ticketed"
    return ""


def _relationship_type(article: Article) -> str:
    matches = _matches(article, "Topic") or _matches(article, "ArtGeneral")
    return matches[0] if matches else ""


def _article_text(article: Article) -> str:
    return f"{article.title} {article.summary} {article.link}"


def _matches(article: Article, key: str) -> list[str]:
    values = article.matched_entities.get(key, [])
    if isinstance(values, list):
        return [str(value) for value in values]
    return []


def _first(values: list[str]) -> str:
    return values[0] if values else ""


def _dict(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = mapping.get(key)
    return value if isinstance(value, Mapping) else {}


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _age_days(generated_at: datetime, event_at: datetime) -> float:
    return max(0.0, (_as_utc(generated_at) - _as_utc(event_at)).total_seconds() / 86400)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_datetime(value: str) -> datetime | None:
    if not value or value == "None":
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _slug(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9가-힣]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:120]


def _digest(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
