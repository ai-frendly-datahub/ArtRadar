from __future__ import annotations

import datetime as dt
import shutil
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .models import Article, CategoryConfig

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
    )


def _copy_static_assets(report_dir: Path) -> None:
    src = _TEMPLATE_DIR / "static"
    dst = report_dir / "static"
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        _ = shutil.copytree(str(src), str(dst))


def generate_report(
    *,
    category: CategoryConfig,
    articles: Iterable[Article],
    output_path: Path,
    stats: dict[str, int],
    errors: list[str] | None = None,
) -> Path:
    """Render a simple HTML report for the collected articles."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    articles_list = list(articles)
    entity_counts = _count_entities(articles_list)
    date_counts, undated_count = _count_articles_by_day(articles_list)

    articles_json: list[dict[str, object]] = []
    for article in articles_list:
        article_data: dict[str, object] = {
            "title": article.title,
            "link": article.link,
            "source": article.source,
            "published": article.published.isoformat() if article.published else None,
            "published_at": article.published.isoformat() if article.published else None,
            "summary": article.summary,
            "matched_entities": article.matched_entities or {},
            "collected_at": (
                article.collected_at.isoformat()
                if hasattr(article, "collected_at") and article.collected_at
                else None
            ),
        }
        articles_json.append(article_data)

    template = _get_jinja_env().get_template("report.html")
    rendered = template.render(
        category=category,
        articles=articles_list,
        articles_json=articles_json,
        generated_at=dt.datetime.now(dt.UTC),
        stats=stats,
        entity_counts=entity_counts,
        date_counts=date_counts,
        undated_count=undated_count,
        errors=errors or [],
    )
    _ = output_path.write_text(rendered, encoding="utf-8")

    now_ts = datetime.now(dt.UTC)
    date_stamp = now_ts.strftime("%Y%m%d")
    dated_name = f"{category.category_name}_{date_stamp}.html"
    dated_path = output_path.parent / dated_name
    _ = dated_path.write_text(rendered, encoding="utf-8")

    _copy_static_assets(output_path.parent)

    return output_path


def _count_entities(articles: Iterable[Article]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for article in articles:
        for entity_name, keywords in (article.matched_entities or {}).items():
            counter[entity_name] += len(keywords)
    return counter


def _count_articles_by_day(articles: Iterable[Article]) -> tuple[list[tuple[str, int]], int]:
    dated: Counter[str] = Counter()
    undated = 0
    for article in articles:
        if article.published:
            dated[article.published.date().isoformat()] += 1
        else:
            undated += 1
    return sorted(dated.items(), reverse=True), undated


def generate_index_html(report_dir: Path) -> Path:
    """Generate an index.html that lists all available report files."""
    report_dir.mkdir(parents=True, exist_ok=True)

    html_files = sorted(
        [f for f in report_dir.glob("*.html") if f.name != "index.html"],
        key=lambda p: p.name,
    )

    reports: list[dict[str, str]] = []
    for html_file in html_files:
        name = html_file.stem
        display_name = name.replace("_report", "").replace("_", " ").title()
        reports.append({"filename": html_file.name, "display_name": display_name})

    template = _get_jinja_env().get_template("index.html")
    rendered = template.render(
        reports=reports,
        generated_at=dt.datetime.now(dt.UTC),
    )

    index_path = report_dir / "index.html"
    _ = index_path.write_text(rendered, encoding="utf-8")
    return index_path
