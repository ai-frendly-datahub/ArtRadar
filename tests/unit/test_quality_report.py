from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

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
    assert summary["event_required_field_gap_count"] >= 1
    assert summary["daily_review_item_count"] >= 1
    assert report["events"][0]["canonical_key"]
    assert "required_field_gaps" in report["events"][0]
    rows = {row["source"]: row for row in report["sources"]}
    assert rows["Disabled Auction"]["tracked"] is False
    assert rows["Disabled Auction"]["status"] == "skipped_disabled"


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
