"""Tests for data validation utilities."""

from __future__ import annotations

from datetime import UTC, datetime

from artradar.common.validators import (
    detect_duplicate_articles,
    is_similar_url,
    normalize_title,
    validate_article,
    validate_url_format,
)
from artradar.models import Article

class TestNormalizeTitle:
    """Test title normalization."""

    def test_normalize_title_removes_extra_whitespace(self) -> None:
        """Test that normalize_title removes extra whitespace."""
        result = normalize_title("  Breaking News  ")
        assert result == "breaking news"

    def test_normalize_title_converts_to_lowercase(self) -> None:
        """Test that normalize_title converts to lowercase."""
        result = normalize_title("BREAKING NEWS")
        assert result == "breaking news"

    def test_normalize_title_removes_special_characters(self) -> None:
        """Test that normalize_title removes special characters."""
        result = normalize_title("Title (Updated)")
        assert result == "title updated"

    def test_normalize_title_handles_empty_string(self) -> None:
        """Test that normalize_title handles empty string."""
        result = normalize_title("")
        assert result == ""

    def test_normalize_title_handles_multiple_spaces(self) -> None:
        """Test that normalize_title collapses multiple spaces."""
        result = normalize_title("Breaking    News")
        assert result == "breaking news"

    def test_normalize_title_preserves_hyphens(self) -> None:
        """Test that normalize_title preserves hyphens."""
        result = normalize_title("Breaking-News")
        assert result == "breaking-news"


class TestValidateUrlFormat:
    """Test URL format validation."""

    def test_validate_url_format_valid_https(self) -> None:
        """Test that valid HTTPS URL passes validation."""
        assert validate_url_format("https://example.com/article") is True

    def test_validate_url_format_valid_http(self) -> None:
        """Test that valid HTTP URL passes validation."""
        assert validate_url_format("http://example.com/article") is True

    def test_validate_url_format_invalid_no_scheme(self) -> None:
        """Test that URL without scheme fails validation."""
        assert validate_url_format("example.com/article") is False

    def test_validate_url_format_invalid_no_domain(self) -> None:
        """Test that URL without domain fails validation."""
        assert validate_url_format("https://") is False

    def test_validate_url_format_empty_string(self) -> None:
        """Test that empty string fails validation."""
        assert validate_url_format("") is False

    def test_validate_url_format_not_a_string(self) -> None:
        """Test that non-string input fails validation."""
        assert validate_url_format(None) is False  # type: ignore

    def test_validate_url_format_invalid_url(self) -> None:
        """Test that invalid URL fails validation."""
        assert validate_url_format("not-a-url") is False


class TestIsSimilarUrl:
    """Test URL similarity detection."""

    def test_is_similar_url_same_url(self) -> None:
        """Test that identical URLs are similar."""
        url = "https://example.com/article/123"
        assert is_similar_url(url, url) is True

    def test_is_similar_url_with_query_params(self) -> None:
        """Test that URLs with different query params are similar."""
        url1 = "https://example.com/article/123"
        url2 = "https://example.com/article/123?ref=abc"
        assert is_similar_url(url1, url2) is True

    def test_is_similar_url_different_domain(self) -> None:
        """Test that URLs with different domains are not similar."""
        url1 = "https://example.com/article/123"
        url2 = "https://other.com/article/123"
        assert is_similar_url(url1, url2) is False

    def test_is_similar_url_different_path(self) -> None:
        """Test that URLs with different paths may not be similar."""
        url1 = "https://example.com/article/123"
        url2 = "https://example.com/article/456"
        assert is_similar_url(url1, url2) is False

    def test_is_similar_url_custom_threshold(self) -> None:
        """Test that custom threshold affects similarity."""
        url1 = "https://example.com/article/123"
        url2 = "https://example.com/article/124"
        assert is_similar_url(url1, url2, threshold=0.9) is True

    def test_is_similar_url_invalid_urls(self) -> None:
        """Test that invalid URLs return False."""
        assert is_similar_url("not-a-url", "also-not-a-url") is False


class TestDetectDuplicateArticles:
    """Test duplicate article detection."""

    def test_detect_duplicate_articles_identical(self) -> None:
        """Test that identical articles are detected as duplicates."""
        assert (
            detect_duplicate_articles(
                "Breaking News",
                "https://example.com/article/123",
                "Breaking News",
                "https://example.com/article/123",
            )
            is True
        )

    def test_detect_duplicate_articles_with_query_params(self) -> None:
        """Test that articles with query param differences are duplicates."""
        assert (
            detect_duplicate_articles(
                "Breaking News",
                "https://example.com/article/123",
                "Breaking News",
                "https://example.com/article/123?ref=abc",
            )
            is True
        )

    def test_detect_duplicate_articles_different_title(self) -> None:
        """Test that articles with different titles are not duplicates."""
        assert (
            detect_duplicate_articles(
                "Breaking News",
                "https://example.com/article/123",
                "Different Title",
                "https://example.com/article/123",
            )
            is False
        )

    def test_detect_duplicate_articles_different_domain(self) -> None:
        """Test that articles from different domains are not duplicates."""
        assert (
            detect_duplicate_articles(
                "Breaking News",
                "https://example.com/article/123",
                "Breaking News",
                "https://other.com/article/123",
            )
            is False
        )

    def test_detect_duplicate_articles_normalized_title(self) -> None:
        """Test that title normalization is applied."""
        assert (
            detect_duplicate_articles(
                "  Breaking News  ",
                "https://example.com/article/123",
                "BREAKING NEWS",
                "https://example.com/article/123",
            )
            is True
        )


class TestValidateArticle:
    """Test article validation."""

    def test_validate_article_valid(self) -> None:
        """Test that valid article passes validation."""
        article = Article(
            title="Valid Article",
            link="https://example.com/article",
            summary="Summary",
            published=datetime.now(UTC),
            source="Example",
            category="news",
        )
        is_valid, errors = validate_article(article)
        assert is_valid is True
        assert errors == []

    def test_validate_article_missing_title(self) -> None:
        """Test that article without title fails validation."""
        article = Article(
            title="",
            link="https://example.com/article",
            summary="Summary",
            published=datetime.now(UTC),
            source="Example",
            category="news",
        )
        is_valid, errors = validate_article(article)
        assert is_valid is False
        assert any("title" in error for error in errors)

    def test_validate_article_missing_link(self) -> None:
        """Test that article without link fails validation."""
        article = Article(
            title="Valid Article",
            link="",
            summary="Summary",
            published=datetime.now(UTC),
            source="Example",
            category="news",
        )
        is_valid, errors = validate_article(article)
        assert is_valid is False
        assert any("link" in error for error in errors)

    def test_validate_article_invalid_url(self) -> None:
        """Test that article with invalid URL fails validation."""
        article = Article(
            title="Valid Article",
            link="not-a-url",
            summary="Summary",
            published=datetime.now(UTC),
            source="Example",
            category="news",
        )
        is_valid, errors = validate_article(article)
        assert is_valid is False
        assert any("link" in error for error in errors)

    def test_validate_article_missing_summary(self) -> None:
        """Test that article without summary fails validation."""
        article = Article(
            title="Valid Article",
            link="https://example.com/article",
            summary="",
            published=datetime.now(UTC),
            source="Example",
            category="news",
        )
        is_valid, errors = validate_article(article)
        assert is_valid is False
        assert any("summary" in error for error in errors)

    def test_validate_article_missing_source(self) -> None:
        """Test that article without source fails validation."""
        article = Article(
            title="Valid Article",
            link="https://example.com/article",
            summary="Summary",
            published=datetime.now(UTC),
            source="",
            category="news",
        )
        is_valid, errors = validate_article(article)
        assert is_valid is False
        assert any("source" in error for error in errors)

    def test_validate_article_missing_category(self) -> None:
        """Test that article without category fails validation."""
        article = Article(
            title="Valid Article",
            link="https://example.com/article",
            summary="Summary",
            published=datetime.now(UTC),
            source="Example",
            category="",
        )
        is_valid, errors = validate_article(article)
        assert is_valid is False
        assert any("category" in error for error in errors)

    def test_validate_article_multiple_errors(self) -> None:
        """Test that multiple validation errors are reported."""
        article = Article(
            title="",
            link="",
            summary="",
            published=datetime.now(UTC),
            source="",
            category="",
        )
        is_valid, errors = validate_article(article)
        assert is_valid is False
        assert len(errors) >= 5
