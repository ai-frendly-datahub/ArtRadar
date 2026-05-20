from __future__ import annotations

import datetime as dt
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from artradar.models import Article, CategoryConfig, Source


def _make_category() -> CategoryConfig:
    return CategoryConfig(
        category_name="art",
        display_name="Art Radar",
        sources=[Source("Artnet News", "rss", "https://news.artnet.com/feed")],
        entities=[],
    )


def _make_article() -> Article:
    return Article(
        title="Test Artwork Report",
        link="https://example.com/artwork",
        summary="A test summary about painting and museum collections.",
        published=dt.datetime.now(dt.UTC),
        source="Artnet News",
        category="art",
        matched_entities={"genre": ["painting"]},
    )


def _make_article_for_date(title: str, published: dt.datetime | None) -> Article:
    return Article(
        title=title,
        link=f"https://example.com/{title.lower().replace(' ', '-')}",
        summary="Date-focused test article.",
        published=published,
        source="Artnet News",
        category="art",
        matched_entities={},
    )


@pytest.mark.unit
def test_generate_report_creates_output_file() -> None:
    from artradar.reporter import generate_report

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        result = generate_report(
            category=_make_category(),
            articles=[_make_article()],
            output_path=output_path,
            stats={"sources": 1, "collected": 1, "matched": 1, "window_days": 7},
            errors=[],
        )

        assert result == output_path
        assert output_path.exists()


@pytest.mark.unit
def test_generate_report_contains_chartjs_443() -> None:
    from artradar.reporter import generate_report

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        _ = generate_report(
            category=_make_category(),
            articles=[_make_article()],
            output_path=output_path,
            stats={"sources": 1, "collected": 1, "matched": 1, "window_days": 7},
            errors=[],
        )

        content = output_path.read_text(encoding="utf-8")
        assert "4.4.3" in content


@pytest.mark.unit
def test_generate_report_contains_standard_charts() -> None:
    from artradar.reporter import generate_report

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        _ = generate_report(
            category=_make_category(),
            articles=[_make_article()],
            output_path=output_path,
            stats={"sources": 1, "collected": 1, "matched": 1, "window_days": 7},
            errors=[],
        )

        content = output_path.read_text(encoding="utf-8")
        for chart_id in (
            "chartEntities",
            "chartTimeline",
            "chartSources",
            "chartFreshness",
            "chartEntityRate",
            "chartSourceHealth",
        ):
            assert chart_id in content


@pytest.mark.unit
def test_generate_report_contains_error_section() -> None:
    from artradar.reporter import generate_report

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        _ = generate_report(
            category=_make_category(),
            articles=[],
            output_path=output_path,
            stats={"sources": 1, "collected": 0, "matched": 0, "window_days": 7},
            errors=["Artnet News: timeout"],
        )

        content = output_path.read_text(encoding="utf-8")
        assert "Errors detected (1)" in content
        assert "Artnet News: timeout" in content


@pytest.mark.unit
def test_generate_report_injects_art_quality_panel() -> None:
    from artradar.reporter import generate_report

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        _ = generate_report(
            category=_make_category(),
            articles=[_make_article()],
            output_path=output_path,
            stats={"sources": 1, "collected": 1, "matched": 1, "window_days": 7},
            errors=[],
            quality_report={
                "summary": {
                    "art_signal_event_count": 1,
                    "auction_result_events": 1,
                    "event_required_field_gap_count": 2,
                },
                "events": [
                    {
                        "event_model": "auction_result",
                        "source": "Auction",
                        "canonical_key": "artwork:artist:work",
                        "canonical_key_status": "complete",
                        "required_field_gaps": [],
                    }
                ],
                "daily_review_items": [],
            },
        )

        content = output_path.read_text(encoding="utf-8")
        assert 'id="art-quality"' in content
        assert "Art Quality" in content
        assert "artwork:artist:work" in content
        summaries = sorted(
            Path(tmpdir).glob("art_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_summary.json")
        )
        assert len(summaries) == 1
        summary = summaries[0].read_text(encoding="utf-8")
        assert '"category": "art"' in summary
        assert '"article_count": 1' in summary


@pytest.mark.unit
def test_generate_report_handles_empty_articles() -> None:
    from artradar.reporter import generate_report

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        _ = generate_report(
            category=_make_category(),
            articles=[],
            output_path=output_path,
            stats={"sources": 0, "collected": 0, "matched": 0, "window_days": 7},
            errors=[],
        )

        content = output_path.read_text(encoding="utf-8")
        assert "No articles were collected for this run." in content


@pytest.mark.unit
def test_generate_index_html_lists_reports() -> None:
    from artradar.reporter import generate_index_html

    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = Path(tmpdir)
        _ = (report_dir / "art_report.html").write_text("<html></html>", encoding="utf-8")
        _ = (report_dir / "market_report.html").write_text("<html></html>", encoding="utf-8")

        index_path = generate_index_html(report_dir)

        content = index_path.read_text(encoding="utf-8")
        assert index_path.exists()
        assert "art_report.html" in content
        assert "market_report.html" in content


@pytest.mark.unit
def test_generate_report_contains_date_filter_controls() -> None:
    from artradar.reporter import generate_report

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        _ = generate_report(
            category=_make_category(),
            articles=[
                _make_article_for_date("Dated One", dt.datetime(2026, 3, 12, 10, 0, tzinfo=dt.UTC)),
                _make_article_for_date("Dated Two", dt.datetime(2026, 3, 11, 10, 0, tzinfo=dt.UTC)),
            ],
            output_path=output_path,
            stats={"sources": 1, "collected": 2, "matched": 0, "window_days": 7},
            errors=[],
        )

        content = output_path.read_text(encoding="utf-8")
        assert 'id="chartTimeline"' in content
        assert "2026-03-12" in content
        assert "2026-03-11" in content


@pytest.mark.unit
def test_generate_report_contains_daily_summary_and_undated_bucket() -> None:
    from artradar.reporter import generate_report

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        _ = generate_report(
            category=_make_category(),
            articles=[
                _make_article_for_date("Dated One", dt.datetime(2026, 3, 12, 10, 0, tzinfo=dt.UTC)),
                _make_article_for_date("Undated", None),
            ],
            output_path=output_path,
            stats={"sources": 1, "collected": 2, "matched": 0, "window_days": 7},
            errors=[],
        )

        content = output_path.read_text(encoding="utf-8")
        assert 'id="chartTimeline"' in content
        assert "Dated One" in content
        assert "Undated" in content


@pytest.mark.unit
def test_generate_report_passes_plugin_charts(monkeypatch: pytest.MonkeyPatch) -> None:
    import artradar.reporter as reporter

    captured: dict[str, object] = {}

    def fake_generate_report(**kwargs: object) -> Path:
        output_path = kwargs["output_path"]
        assert isinstance(output_path, Path)
        captured.update(kwargs)
        output_path.write_text("<html><body>report</body></html>", encoding="utf-8")
        return output_path

    monkeypatch.setitem(
        sys.modules,
        "radar_core.plugins.entity_heatmap",
        SimpleNamespace(get_chart_config=lambda articles: {"id": "heatmap"}),
    )
    monkeypatch.setitem(
        sys.modules,
        "radar_core.plugins.source_reliability",
        SimpleNamespace(get_chart_config=lambda store: {"id": "reliability"}),
    )
    monkeypatch.setattr(reporter, "_core_generate_report", fake_generate_report)
    monkeypatch.setattr(
        reporter,
        "build_summary_ontology_metadata",
        lambda *args, **kwargs: {"radar": "ArtRadar"},
    )

    output_path = Path(tempfile.mkdtemp()) / "report.html"
    result = reporter.generate_report(
        category=_make_category(),
        articles=[_make_article()],
        output_path=output_path,
        stats={"sources": 1},
        store=object(),
    )

    assert result == output_path
    assert captured["plugin_charts"] == [{"id": "heatmap"}, {"id": "reliability"}]


@pytest.mark.unit
def test_generate_report_ignores_plugin_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    import artradar.reporter as reporter

    def raise_plugin_error(**kwargs: object) -> object:
        raise RuntimeError("plugin failed")

    def fake_generate_report(**kwargs: object) -> Path:
        output_path = kwargs["output_path"]
        assert isinstance(output_path, Path)
        assert kwargs["plugin_charts"] is None
        output_path.write_text("<html><body>report</body></html>", encoding="utf-8")
        return output_path

    monkeypatch.setitem(
        sys.modules,
        "radar_core.plugins.entity_heatmap",
        SimpleNamespace(get_chart_config=raise_plugin_error),
    )
    monkeypatch.setitem(
        sys.modules,
        "radar_core.plugins.source_reliability",
        SimpleNamespace(get_chart_config=raise_plugin_error),
    )
    monkeypatch.setattr(reporter, "_core_generate_report", fake_generate_report)
    monkeypatch.setattr(
        reporter,
        "build_summary_ontology_metadata",
        lambda *args, **kwargs: {"radar": "ArtRadar"},
    )

    reporter.generate_report(
        category=_make_category(),
        articles=[],
        output_path=Path(tempfile.mkdtemp()) / "report.html",
        stats={},
    )


@pytest.mark.unit
def test_quality_panel_injection_handles_missing_file_and_missing_body(tmp_path: Path) -> None:
    from artradar.reporter import _inject_art_quality_panel, _render_art_quality_panel

    missing = tmp_path / "missing.html"
    _inject_art_quality_panel(missing, {"summary": {}})
    assert not missing.exists()

    report = tmp_path / "report.html"
    report.write_text("<html>report", encoding="utf-8")
    _inject_art_quality_panel(
        report,
        {
            "summary": {"daily_review_item_count": 1},
            "events": "not-a-list",
            "daily_review_items": [{"reason": "source_missing", "source": "Museum"}],
        },
    )

    content = report.read_text(encoding="utf-8")
    assert "report" in content
    assert "No art quality events were observed" in content
    assert "source_missing: Museum" in content
    assert "No daily review items." in _render_art_quality_panel({"daily_review_items": "bad"})
