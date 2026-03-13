"""Tests for artradar.exceptions hierarchy."""

from __future__ import annotations

import pytest

from artradar.exceptions import (
    CollectionError,
    ConfigError,
    NetworkError,
    NotificationError,
    ParseError,
    RadarError,
    ReportError,
    SearchError,
    SourceError,
    StorageError,
)

class TestRadarErrorHierarchy:
    """Test exception hierarchy."""

    def test_radar_error_is_exception(self) -> None:
        """RadarError is an Exception."""
        assert issubclass(RadarError, Exception)

    def test_config_error_is_radar_error(self) -> None:
        """ConfigError inherits from RadarError."""
        assert issubclass(ConfigError, RadarError)

    def test_collection_error_is_radar_error(self) -> None:
        """CollectionError inherits from RadarError."""
        assert issubclass(CollectionError, RadarError)

    def test_source_error_is_collection_error(self) -> None:
        """SourceError inherits from CollectionError."""
        assert issubclass(SourceError, CollectionError)

    def test_network_error_is_collection_error(self) -> None:
        """NetworkError inherits from CollectionError."""
        assert issubclass(NetworkError, CollectionError)

    def test_parse_error_is_collection_error(self) -> None:
        """ParseError inherits from CollectionError."""
        assert issubclass(ParseError, CollectionError)

    def test_storage_error_is_radar_error(self) -> None:
        """StorageError inherits from RadarError."""
        assert issubclass(StorageError, RadarError)

    def test_report_error_is_radar_error(self) -> None:
        """ReportError inherits from RadarError."""
        assert issubclass(ReportError, RadarError)

    def test_search_error_is_radar_error(self) -> None:
        """SearchError inherits from RadarError."""
        assert issubclass(SearchError, RadarError)

    def test_notification_error_is_radar_error(self) -> None:
        """NotificationError inherits from RadarError."""
        assert issubclass(NotificationError, RadarError)


class TestRadarError:
    """Test RadarError exception."""

    def test_radar_error_creation(self) -> None:
        """RadarError can be created with message."""
        error = RadarError("Test error")
        assert str(error) == "Test error"

    def test_radar_error_can_be_raised(self) -> None:
        """RadarError can be raised and caught."""
        with pytest.raises(RadarError):
            raise RadarError("Test error")


class TestConfigError:
    """Test ConfigError exception."""

    def test_config_error_creation(self) -> None:
        """ConfigError can be created with message."""
        error = ConfigError("Invalid config")
        assert str(error) == "Invalid config"

    def test_config_error_can_be_caught_as_radar_error(self) -> None:
        """ConfigError can be caught as RadarError."""
        with pytest.raises(RadarError):
            raise ConfigError("Invalid config")


class TestSourceError:
    """Test SourceError exception."""

    def test_source_error_creation(self) -> None:
        """SourceError can be created with source_name and message."""
        error = SourceError("TestBlog", "Connection failed")
        assert error.source_name == "TestBlog"
        assert "[TestBlog]" in str(error)
        assert "Connection failed" in str(error)

    def test_source_error_with_original_error(self) -> None:
        """SourceError can store original exception."""
        original = ValueError("Invalid URL")
        error = SourceError("TestBlog", "Connection failed", original)
        assert error.original_error == original

    def test_source_error_can_be_caught_as_collection_error(self) -> None:
        """SourceError can be caught as CollectionError."""
        with pytest.raises(CollectionError):
            raise SourceError("TestBlog", "Connection failed")

    def test_source_error_can_be_caught_as_radar_error(self) -> None:
        """SourceError can be caught as RadarError."""
        with pytest.raises(RadarError):
            raise SourceError("TestBlog", "Connection failed")


class TestNetworkError:
    """Test NetworkError exception."""

    def test_network_error_creation(self) -> None:
        """NetworkError can be created with message."""
        error = NetworkError("Timeout")
        assert str(error) == "Timeout"

    def test_network_error_can_be_caught_as_collection_error(self) -> None:
        """NetworkError can be caught as CollectionError."""
        with pytest.raises(CollectionError):
            raise NetworkError("Timeout")

    def test_network_error_can_be_caught_as_radar_error(self) -> None:
        """NetworkError can be caught as RadarError."""
        with pytest.raises(RadarError):
            raise NetworkError("Timeout")


class TestParseError:
    """Test ParseError exception."""

    def test_parse_error_creation(self) -> None:
        """ParseError can be created with message."""
        error = ParseError("Invalid RSS feed")
        assert str(error) == "Invalid RSS feed"

    def test_parse_error_can_be_caught_as_collection_error(self) -> None:
        """ParseError can be caught as CollectionError."""
        with pytest.raises(CollectionError):
            raise ParseError("Invalid RSS feed")

    def test_parse_error_can_be_caught_as_radar_error(self) -> None:
        """ParseError can be caught as RadarError."""
        with pytest.raises(RadarError):
            raise ParseError("Invalid RSS feed")


class TestStorageError:
    """Test StorageError exception."""

    def test_storage_error_creation(self) -> None:
        """StorageError can be created with message."""
        error = StorageError("Database error")
        assert str(error) == "Database error"

    def test_storage_error_can_be_caught_as_radar_error(self) -> None:
        """StorageError can be caught as RadarError."""
        with pytest.raises(RadarError):
            raise StorageError("Database error")


class TestReportError:
    """Test ReportError exception."""

    def test_report_error_creation(self) -> None:
        """ReportError can be created with message."""
        error = ReportError("Template error")
        assert str(error) == "Template error"

    def test_report_error_can_be_caught_as_radar_error(self) -> None:
        """ReportError can be caught as RadarError."""
        with pytest.raises(RadarError):
            raise ReportError("Template error")


class TestSearchError:
    """Test SearchError exception."""

    def test_search_error_creation(self) -> None:
        """SearchError can be created with message."""
        error = SearchError("Index error")
        assert str(error) == "Index error"

    def test_search_error_can_be_caught_as_radar_error(self) -> None:
        """SearchError can be caught as RadarError."""
        with pytest.raises(RadarError):
            raise SearchError("Index error")


class TestNotificationError:
    """Test NotificationError exception."""

    def test_notification_error_creation(self) -> None:
        """NotificationError can be created with message."""
        error = NotificationError("Email send failed")
        assert str(error) == "Email send failed"

    def test_notification_error_can_be_caught_as_radar_error(self) -> None:
        """NotificationError can be caught as RadarError."""
        with pytest.raises(RadarError):
            raise NotificationError("Email send failed")
