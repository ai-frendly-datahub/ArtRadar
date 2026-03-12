from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

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
        published=datetime.now(UTC),
        source="Artnet News",
        category="art",
        matched_entities={"genre": ["painting"]},
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

        generate_report(
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

        generate_report(
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

        generate_report(
            category=_make_category(),
            articles=[],
            output_path=output_path,
            stats={"sources": 1, "collected": 0, "matched": 0, "window_days": 7},
            errors=["Artnet News: timeout"],
        )

        content = output_path.read_text(encoding="utf-8")
        assert "Collection errors" in content
        assert "Artnet News: timeout" in content


@pytest.mark.unit
def test_generate_report_handles_empty_articles() -> None:
    from artradar.reporter import generate_report

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"

        generate_report(
            category=_make_category(),
            articles=[],
            output_path=output_path,
            stats={"sources": 0, "collected": 0, "matched": 0, "window_days": 7},
            errors=[],
        )

        content = output_path.read_text(encoding="utf-8")
        assert "No articles in the recent window." in content


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
