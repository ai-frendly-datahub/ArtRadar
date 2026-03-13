from __future__ import annotations

import datetime as dt
import tempfile
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
        assert "Collection errors" in content
        assert "Artnet News: timeout" in content


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
        assert "Date-based review" in content
        assert 'id="dateFilter"' in content


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
        assert "Articles by day" in content
        assert "Undated articles" in content
