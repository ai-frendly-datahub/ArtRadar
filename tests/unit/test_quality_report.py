from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from artradar.models import Article, CategoryConfig, Source
from artradar.quality_report import build_quality_report, write_quality_report


def test_build_quality_report_tracks_art_event_statuses() -> None:
    now = datetime(2026, 4, 13, tzinfo=UTC)
    category = CategoryConfig(
        category_name="art",
        display_name="Art Radar",
        sources=[
            Source(
                name="Seoul Auction",
                type="javascript",
                url="https://example.com/auction",
                content_type="auction",
            ),
            Source(
                name="Museum",
                type="javascript",
                url="https://example.com/exhibition",
                content_type="exhibition",
            ),
            Source(
                name="Community",
                type="reddit",
                url="https://example.com/community",
                content_type="community",
                trust_tier="T4_community",
            ),
            Source(
                name="Disabled Auction",
                type="javascript",
                url="https://example.com/disabled-auction",
                content_type="auction",
                enabled=False,
                notes="Disabled after repeated timeout.",
            ),
        ],
        entities=[],
    )
    report = build_quality_report(
        category=category,
        articles=[
            Article(
                title="Auction result for a painter",
                link="https://example.com/auction/1",
                summary="Hammer price and artist context.",
                published=now - timedelta(days=1),
                source="Seoul Auction",
                category="art",
                matched_entities={"Artist": ["artist"], "Market": ["auction"]},
            ),
            Article(
                title="Museum exhibition opens",
                link="https://example.com/exhibition/1",
                summary="Institution exhibition ticket signal.",
                published=now - timedelta(days=2),
                source="Museum",
                category="art",
                matched_entities={"Institution": ["museum"], "Topic": ["exhibition"]},
            ),
            Article(
                title="Disabled auction result",
                link="https://example.com/disabled-auction/1",
                summary="Hammer price and artist context.",
                published=now - timedelta(days=1),
                source="Disabled Auction",
                category="art",
                matched_entities={"Artist": ["artist"], "Market": ["auction"]},
            ),
            Article(
                title="Article from removed source",
                link="https://example.com/unknown/1",
                summary="This source is no longer configured.",
                published=now - timedelta(hours=1),
                source="Removed Source",
                category="art",
            ),
        ],
        quality_config={
            "data_quality": {
                "quality_outputs": {
                    "tracked_event_models": [
                        "auction_result",
                        "art_fair_participant",
                        "exhibition_ticket_signal",
                        "artist_institution_entity",
                    ]
                },
                "freshness_sla": {
                    "auction_result_days": 7,
                    "exhibition_ticket_signal_days": 3,
                },
            }
        },
        generated_at=now,
    )

    summary = report["summary"]
    assert summary["tracked_sources"] == 2
    assert summary["fresh_sources"] == 2
    assert summary["skipped_disabled_sources"] == 1
    assert summary["not_tracked_sources"] == 1
    assert summary["auction_result_events"] == 1
    assert summary["exhibition_ticket_signal_events"] == 1
    assert summary["art_signal_event_count"] == 2
    assert summary["unconfigured_source_count"] == 1
    assert summary["unconfigured_article_count"] == 1
    assert summary["event_required_field_gap_count"] >= 1
    assert summary["daily_review_item_count"] >= 1
    assert report["events"][0]["canonical_key"]
    assert report["unconfigured_sources"][0]["source"] == "Removed Source"
    assert any(item["reason"] == "unconfigured_source" for item in report["daily_review_items"])
    assert "required_field_gaps" in report["events"][0]
    rows = {row["source"]: row for row in report["sources"]}
    assert rows["Disabled Auction"]["tracked"] is False
    assert rows["Disabled Auction"]["status"] == "skipped_disabled"
    assert rows["Disabled Auction"]["skip_reason"] == "Disabled after repeated timeout."


def test_write_quality_report_writes_latest_and_dated_files(tmp_path: Path) -> None:
    report = {
        "category": "art",
        "generated_at": "2026-04-13T00:00:00+00:00",
        "summary": {},
    }

    paths = write_quality_report(report, output_dir=tmp_path, category_name="art")

    assert paths["latest"] == tmp_path / "art_quality.json"
    assert paths["dated"] == tmp_path / "art_20260413_quality.json"
    assert paths["latest"].exists()
    assert paths["dated"].exists()


def test_build_quality_report_skips_source_when_required_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_API_KEY", raising=False)
    category = CategoryConfig(
        category_name="artwork",
        display_name="Artwork",
        sources=[
            Source(
                name="Smithsonian",
                type="smithsonian",
                url="https://example.com",
                content_type="collection",
                config={
                    "event_model": "artist_institution_entity",
                    "required_env": "MISSING_API_KEY",
                },
            )
        ],
        entities=[],
    )

    report = build_quality_report(
        category=category,
        articles=[],
        quality_config={
            "data_quality": {
                "quality_outputs": {
                    "tracked_event_models": ["artist_institution_entity"],
                }
            }
        },
    )

    row = report["sources"][0]
    assert row["enabled"] is False
    assert row["configured_enabled"] is True
    assert row["status"] == "skipped_disabled"
    assert row["skip_reason"] == "missing required env: MISSING_API_KEY"


def test_quality_report_private_helpers_cover_edge_branches() -> None:
    from artradar import quality_report as qr

    now = datetime(2026, 4, 13, tzinfo=UTC)
    article = Article(
        title="Artwork: Blue Vase. exhibition: spring show sold out, tickets",
        link="https://example.com/art?price=KRW",
        summary="Hammer: KRW 1,200. Institution ticket signal.",
        published=now,
        source="Auction",
        category="art",
        matched_entities={
            "Artist": ["Artist Name"],
            "Institution": ["Museum Name"],
            "Market": ["Frieze Seoul"],
            "Topic": ["curated by"],
        },
        collected_at=now,
    )

    assert qr._source_event_model(
        Source("Fair", "rss", "https://example.com", content_type="fair")
    ) == ("art_fair_participant")
    assert (
        qr._source_event_model(
            Source("Collection", "rss", "https://example.com", content_type="collection")
        )
        == "artist_institution_entity"
    )
    assert (
        qr._source_event_model(Source("Video", "rss", "https://example.com", content_type="video"))
        == ""
    )
    assert (
        qr._source_event_model(
            Source(
                "Configured",
                "rss",
                "https://example.com",
                config={"event_model": "custom_model"},
            )
        )
        == "custom_model"
    )
    assert (
        qr._source_event_model(
            Source(
                "Community",
                "rss",
                "https://example.com",
                content_type="community",
                trust_tier="T4_community",
            )
        )
        == ""
    )

    assert (
        qr._source_sla_days(
            Source(
                "Auction",
                "rss",
                "https://example.com",
                config={"freshness_sla_days": "2.5"},
            ),
            "auction_result",
            {},
        )
        == 2.5
    )
    assert (
        qr._source_sla_days(
            Source("Auction", "rss", "https://example.com"),
            "auction_result",
            {"auction_result_hours": "12"},
        )
        == 0.5
    )

    assert (
        qr._source_status(
            source_enabled=False,
            event_model="auction_result",
            tracked_event_models={"auction_result"},
            article_count=0,
            event_count=0,
            latest_event_at=None,
            sla_days=None,
            age_days=None,
        )
        == "skipped_disabled"
    )
    assert (
        qr._source_status(
            source_enabled=True,
            event_model="",
            tracked_event_models={"auction_result"},
            article_count=1,
            event_count=0,
            latest_event_at=None,
            sla_days=None,
            age_days=None,
        )
        == "not_tracked"
    )
    assert (
        qr._source_status(
            source_enabled=True,
            event_model="auction_result",
            tracked_event_models={"auction_result"},
            article_count=0,
            event_count=0,
            latest_event_at=None,
            sla_days=None,
            age_days=None,
        )
        == "missing"
    )
    assert (
        qr._source_status(
            source_enabled=True,
            event_model="auction_result",
            tracked_event_models={"auction_result"},
            article_count=1,
            event_count=0,
            latest_event_at=None,
            sla_days=None,
            age_days=None,
        )
        == "missing_event"
    )
    assert (
        qr._source_status(
            source_enabled=True,
            event_model="auction_result",
            tracked_event_models={"auction_result"},
            article_count=1,
            event_count=1,
            latest_event_at=None,
            sla_days=None,
            age_days=None,
        )
        == "unknown_event_date"
    )
    assert (
        qr._source_status(
            source_enabled=True,
            event_model="auction_result",
            tracked_event_models={"auction_result"},
            article_count=1,
            event_count=1,
            latest_event_at=now,
            sla_days=1.0,
            age_days=2.0,
        )
        == "stale"
    )

    assert qr._latest_event([{"event_at": None, "title": "undated"}]) == {
        "event_at": None,
        "title": "undated",
    }
    assert (
        qr._event_datetime(
            article,
            Source(
                "Auction",
                "rss",
                "https://example.com",
                config={"observed_date_field": "collected_at"},
            ),
        )
        == now
    )
    assert qr._currency(article) == "KRW"
    assert qr._hammer_price(article) == 1200.0
    assert qr._artwork_title(article) == "Blue Vase"
    assert qr._exhibition_id(article) == "spring-show-sold-out"
    assert qr._ticket_status(article) == "sold_out"
    assert qr._role(article) == "curated by"
    assert qr._relationship_type(article) == "curated by"
    assert qr._fair_id(article, Source("Fair", "rss", "https://example.com")) == "frieze-seoul"
    assert (
        qr._institution_id(
            article,
            Source("Museum", "rss", "https://example.com", config={"institution_id": "museum-1"}),
        )
        == "museum-1"
    )
    assert qr._list_field({"artist": "not-list"}, "artist") == []
    assert qr._as_float(True) is None
    assert qr._as_float("bad") is None
    assert qr._parse_datetime("") is None
    assert qr._parse_datetime("None") is None
    assert qr._parse_datetime("bad") is None


def test_quality_report_canonical_key_branches() -> None:
    from artradar import quality_report as qr

    assert qr._canonical_key(
        {
            "event_model": "auction_result",
            "artist": ["Artist Name"],
            "artwork_title": "Blue Vase",
        }
    ) == ("artwork:artist-name:blue-vase", "complete")
    assert qr._canonical_key({"event_model": "auction_result", "artist": ["Artist Name"]}) == (
        "artist_market:artist-name",
        "artist_proxy",
    )
    assert qr._canonical_key(
        {
            "event_model": "art_fair_participant",
            "fair_id": "frieze-seoul",
            "institution": ["Gallery A"],
        }
    ) == ("art_fair:frieze-seoul:gallery-a", "complete")
    assert qr._canonical_key(
        {"event_model": "art_fair_participant", "institution": ["Gallery A"]}
    ) == ("art_fair:institution:gallery-a", "institution_proxy")
    assert qr._canonical_key(
        {"event_model": "exhibition_ticket_signal", "exhibition_id": "show-1"}
    ) == ("exhibition:show-1", "complete")
    assert (
        qr._canonical_key(
            {
                "event_model": "exhibition_ticket_signal",
                "institution": ["Museum"],
                "title": "Summer Show",
            }
        )[1]
        == "institution_proxy"
    )
    assert qr._canonical_key(
        {
            "event_model": "artist_institution_entity",
            "artist": ["Artist Name"],
            "institution": ["Museum"],
        }
    ) == ("artist_institution:artist-name:museum", "complete")
    assert qr._canonical_key(
        {"event_model": "artist_institution_entity", "artist": ["Artist Name"]}
    ) == ("artist:artist-name", "artist_proxy")
    assert qr._canonical_key(
        {"event_model": "artist_institution_entity", "institution": ["Museum"]}
    ) == ("institution:museum", "institution_proxy")
    assert qr._canonical_key({"event_model": "other", "source": "Feed", "title": "Title"})[1] == (
        "source_proxy"
    )
    assert qr._canonical_key({"event_model": "other"}) == ("", "missing")


def test_quality_report_build_event_rows_skips_unknown_disabled_and_untracked_sources() -> None:
    from artradar import quality_report as qr

    now = datetime(2026, 4, 13, tzinfo=UTC)
    sources = [
        Source("Disabled", "rss", "https://example.com/disabled", enabled=False),
        Source("Community", "rss", "https://example.com/community", content_type="community"),
        Source("Auction", "rss", "https://example.com/auction", content_type="auction"),
    ]
    rows = qr._build_event_rows(
        articles=[
            Article(
                title="Unknown source",
                link="https://example.com/unknown",
                summary="ignored",
                published=now,
                source="Unknown",
                category="art",
            ),
            Article(
                title="Disabled source",
                link="https://example.com/disabled",
                summary="ignored",
                published=now,
                source="Disabled",
                category="art",
            ),
            Article(
                title="Community source",
                link="https://example.com/community",
                summary="ignored",
                published=now,
                source="Community",
                category="art",
            ),
            Article(
                title="Auction result",
                link="https://example.com/auction",
                summary="Artwork: Vase. Hammer: $500.",
                published=now,
                source="Auction",
                category="art",
                matched_entities={"Artist": ["Artist"]},
            ),
        ],
        sources=sources,
        tracked_event_models={"auction_result"},
        event_model_config={},
    )

    assert len(rows) == 1
    assert rows[0]["source"] == "Auction"
    assert rows[0]["currency"] == "USD"


def test_quality_report_review_backlog_and_default_required_field_helpers() -> None:
    from artradar import quality_report as qr

    review = qr._daily_review_items(
        events=[],
        source_rows=[
            {
                "tracked": True,
                "status": "missing",
                "source": "Museum",
                "event_model": "exhibition_ticket_signal",
                "age_days": None,
            }
        ],
        quality_config={
            "source_backlog": {
                "operational_candidates": [
                    {
                        "name": "Auction API",
                        "signal_type": "auction_result",
                        "activation_gate": "api_key",
                    },
                    "ignored",
                ]
            }
        },
        tracked_event_models={"auction_result"},
    )

    assert review[0]["reason"] == "source_missing"
    assert review[0]["source"] == "Museum"
    assert review[-1]["reason"] == "source_backlog_pending"
    assert review[-1]["source"] == "Auction API"
    assert qr._source_backlog_items({"source_backlog": {"operational_candidates": "bad"}}) == []
    assert qr._default_required_fields("art_fair_participant") == [
        "fair_id",
        "organization_name",
        "role",
        "source_url",
    ]
    assert qr._default_required_fields("unknown") == ["source_url"]
    assert (
        qr._fair_id(
            Article(
                title="Fair",
                link="https://example.com/fair",
                summary="summary",
                published=None,
                source="Fair",
                category="art",
            ),
            Source("Fair", "rss", "https://example.com", config={"fair_id": "fair-1"}),
        )
        == "fair-1"
    )
    weird_article = Article(
        title="Weird",
        link="https://example.com/weird",
        summary="summary",
        published=None,
        source="Feed",
        category="art",
        matched_entities={"Artist": "not-a-list"},
    )
    assert qr._matches(weird_article, "Artist") == []
