"""Browser-based article collection for JavaScript-rendered sources.

Uses the 2-pass hybrid collection pattern:
    Pass 1 (collector.py): RSS/API sources -> ThreadPoolExecutor (parallel)
    Pass 2 (this module):  JS/browser sources -> Playwright (sequential)

Playwright is an optional dependency. If ``radar-core[browser]`` is not
installed, this module degrades gracefully -- returning empty results with
a descriptive error string so the caller can log a warning and continue.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

import structlog

from .models import Article

if TYPE_CHECKING:
    from .models import Source

logger = structlog.get_logger()

_BROWSER_COLLECTION_AVAILABLE = False
try:
    _module = importlib.import_module("radar_core.browser_collector")
    _core_collect = _module.collect_browser_sources

    _BROWSER_COLLECTION_AVAILABLE = True
except ImportError:
    _core_collect = None  # type: ignore[assignment]


def collect_browser_sources(
    sources: list[Source],
    category: str,
    *,
    timeout: int = 15_000,
    health_db_path: str | None = None,
) -> tuple[list[Article], list[str]]:
    """Collect articles from JavaScript-rendered sources via Playwright.

    Wraps :func:`radar_core.browser_collector.collect_browser_sources` and
    converts the returned ``radar_core.models.Article`` instances into local
    ``Article`` instances for pipeline compatibility.

    Args:
        sources: Source objects with ``type`` in ``("javascript", "browser")``.
        category: Category name stamped onto every collected article.
        timeout: Default Playwright page-load timeout in milliseconds.
        health_db_path: Optional path to crawl-health DuckDB file.

    Returns:
        ``(articles, errors)`` -- local Article list and human-readable error
        strings.  On failure the articles list is empty and errors explains why.
    """
    if not sources:
        return [], []

    if not _BROWSER_COLLECTION_AVAILABLE or _core_collect is None:
        logger.warning(
            "browser_collection_unavailable",
            reason="radar_core.browser_collector not installed",
            source_count=len(sources),
            hint="pip install 'radar-core[browser]'",
        )
        return [], [
            f"Browser collection unavailable for {len(sources)} JS source(s). "
            "Install radar-core[browser]."
        ]

    try:
        source_dicts: list[dict[str, Any]] = [
            {"name": s.name, "type": s.type, "url": s.url} for s in sources
        ]
        core_articles, errors = _core_collect(
            sources=source_dicts,
            category=category,
            timeout=timeout,
            health_db_path=health_db_path,
        )
    except ImportError:
        logger.warning(
            "playwright_not_installed",
            source_count=len(sources),
            hint="pip install 'radar-core[browser]'",
        )
        return [], [
            f"Playwright not installed for {len(sources)} JS source(s). "
            "Install radar-core[browser]."
        ]
    except Exception as exc:
        logger.error(
            "browser_collection_failed",
            error=str(exc),
            source_count=len(sources),
        )
        return [], [f"Browser collection failed: {exc}"]

    local_articles: list[Article] = []
    for article in core_articles:
        local_articles.append(
            Article(
                title=article.title,
                link=article.link,
                summary=article.summary,
                published=article.published,
                source=article.source,
                category=article.category or category,
            )
        )

    if local_articles:
        logger.info(
            "browser_collection_complete",
            article_count=len(local_articles),
            error_count=len(errors),
        )

    return local_articles, errors
