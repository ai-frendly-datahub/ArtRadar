"""Tests for artradar.models dataclasses."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from artradar.models import (
    Article,
    CategoryConfig,
    EmailSettings,
    EntityDefinition,
    NotificationConfig,
    RadarSettings,
    Source,
    TelegramSettings,
)

class TestSource:
    """Test Source dataclass."""

    def test_source_creation(self) -> None:
        """Source can be created with name, type, url."""
        source = Source(name="TechBlog", type="rss", url="https://example.com/feed")
        assert source.name == "TechBlog"
        assert source.type == "rss"
        assert source.url == "https://example.com/feed"


class TestEntityDefinition:
    """Test EntityDefinition dataclass."""

    def test_entity_definition_creation(self) -> None:
        """EntityDefinition can be created with name, display_name, keywords."""
        entity = EntityDefinition(
            name="python",
            display_name="Python",
            keywords=["python", "py", "cpython"],
        )
        assert entity.name == "python"
        assert entity.display_name == "Python"
        assert entity.keywords == ["python", "py", "cpython"]


class TestArticle:
    """Test Article dataclass."""

    def test_article_creation_minimal(self) -> None:
        """Article can be created with required fields."""
        article = Article(
            title="Test Article",
            link="https://example.com/article",
            summary="A test article",
            published=None,
            source="TestBlog",
            category="tech",
        )
        assert article.title == "Test Article"
        assert article.link == "https://example.com/article"
        assert article.summary == "A test article"
        assert article.published is None
        assert article.source == "TestBlog"
        assert article.category == "tech"
        assert article.matched_entities == {}
        assert article.collected_at is None

    def test_article_creation_with_datetime(self) -> None:
        """Article can be created with published datetime."""
        now = datetime.now(UTC)
        article = Article(
            title="Test Article",
            link="https://example.com/article",
            summary="A test article",
            published=now,
            source="TestBlog",
            category="tech",
            collected_at=now,
        )
        assert article.published == now
        assert article.collected_at == now

    def test_article_with_matched_entities(self) -> None:
        """Article can store matched entities."""
        article = Article(
            title="Test Article",
            link="https://example.com/article",
            summary="A test article",
            published=None,
            source="TestBlog",
            category="tech",
            matched_entities={"language": ["python", "rust"]},
        )
        assert article.matched_entities == {"language": ["python", "rust"]}


class TestCategoryConfig:
    """Test CategoryConfig dataclass."""

    def test_category_config_creation(self) -> None:
        """CategoryConfig can be created with sources and entities."""
        sources = [
            Source(name="Blog1", type="rss", url="https://blog1.com/feed"),
            Source(name="Blog2", type="rss", url="https://blog2.com/feed"),
        ]
        entities = [
            EntityDefinition(name="python", display_name="Python", keywords=["python"]),
            EntityDefinition(name="rust", display_name="Rust", keywords=["rust"]),
        ]
        config = CategoryConfig(
            category_name="techblog",
            display_name="Tech Blog",
            sources=sources,
            entities=entities,
        )
        assert config.category_name == "techblog"
        assert config.display_name == "Tech Blog"
        assert len(config.sources) == 2
        assert len(config.entities) == 2


class TestRadarSettings:
    """Test RadarSettings dataclass."""

    def test_radar_settings_creation(self) -> None:
        """RadarSettings can be created with Path objects."""
        settings = RadarSettings(
            database_path=Path("/data/radar.db"),
            report_dir=Path("/reports"),
            raw_data_dir=Path("/data/raw"),
            search_db_path=Path("/data/search.db"),
        )
        assert settings.database_path == Path("/data/radar.db")
        assert settings.report_dir == Path("/reports")
        assert settings.raw_data_dir == Path("/data/raw")
        assert settings.search_db_path == Path("/data/search.db")


class TestEmailSettings:
    """Test EmailSettings dataclass."""

    def test_email_settings_creation(self) -> None:
        """EmailSettings can be created with SMTP configuration."""
        settings = EmailSettings(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user@example.com",
            password="secret",
            from_address="noreply@example.com",
            to_addresses=["admin@example.com"],
        )
        assert settings.smtp_host == "smtp.example.com"
        assert settings.smtp_port == 587
        assert settings.username == "user@example.com"
        assert settings.password == "secret"
        assert settings.from_address == "noreply@example.com"
        assert settings.to_addresses == ["admin@example.com"]


class TestTelegramSettings:
    """Test TelegramSettings dataclass."""

    def test_telegram_settings_creation(self) -> None:
        """TelegramSettings can be created with bot token and chat ID."""
        settings = TelegramSettings(
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            chat_id="987654321",
        )
        assert settings.bot_token == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        assert settings.chat_id == "987654321"


class TestNotificationConfig:
    """Test NotificationConfig dataclass."""

    def test_notification_config_minimal(self) -> None:
        """NotificationConfig can be created with enabled and channels."""
        config = NotificationConfig(
            enabled=True,
            channels=["email"],
        )
        assert config.enabled is True
        assert config.channels == ["email"]
        assert config.email is None
        assert config.webhook_url is None
        assert config.telegram is None
        assert config.rules == {}

    def test_notification_config_with_email(self) -> None:
        """NotificationConfig can include EmailSettings."""
        email = EmailSettings(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user@example.com",
            password="secret",
            from_address="noreply@example.com",
            to_addresses=["admin@example.com"],
        )
        config = NotificationConfig(
            enabled=True,
            channels=["email"],
            email=email,
        )
        assert config.email == email

    def test_notification_config_with_telegram(self) -> None:
        """NotificationConfig can include TelegramSettings."""
        telegram = TelegramSettings(
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            chat_id="987654321",
        )
        config = NotificationConfig(
            enabled=True,
            channels=["telegram"],
            telegram=telegram,
        )
        assert config.telegram == telegram

    def test_notification_config_with_webhook(self) -> None:
        """NotificationConfig can include webhook URL."""
        config = NotificationConfig(
            enabled=True,
            channels=["webhook"],
            webhook_url="https://example.com/webhook",
        )
        assert config.webhook_url == "https://example.com/webhook"

    def test_notification_config_with_rules(self) -> None:
        """NotificationConfig can include rules."""
        rules = {"min_score": 0.8, "categories": ["tech"]}
        config = NotificationConfig(
            enabled=True,
            channels=["email"],
            rules=rules,
        )
        assert config.rules == rules
