"""Tests for circuit breaker resilience module."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

from pybreaker import CircuitBreaker

from artradar.resilience import (
    SourceCircuitBreakerListener,
    SourceCircuitBreakerManager,
    get_circuit_breaker_manager,
)

class TestSourceCircuitBreakerListener:
    """Test SourceCircuitBreakerListener."""

    def test_state_change_logs_transition(self) -> None:
        """Test that state_change logs state transitions."""
        listener = SourceCircuitBreakerListener()
        cb = MagicMock(spec=CircuitBreaker)
        cb.name = "test_source"

        with patch("artradar.resilience.logger") as mock_logger:
            listener.state_change(cb, "closed", "open")
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "circuit_breaker_state_change"
            assert call_args[1]["source"] == "test_source"
            assert call_args[1]["before"] == "closed"
            assert call_args[1]["after"] == "open"

    def test_failure_logs_exception(self) -> None:
        """Test that failure logs exception details."""
        listener = SourceCircuitBreakerListener()
        cb = MagicMock(spec=CircuitBreaker)
        cb.name = "test_source"
        exc = ValueError("Test error")

        with patch("artradar.resilience.logger") as mock_logger:
            listener.failure(cb, exc)
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "circuit_breaker_failure"
            assert call_args[1]["source"] == "test_source"
            assert call_args[1]["exception"] == "ValueError"
            assert call_args[1]["message"] == "Test error"

    def test_success_logs_success(self) -> None:
        """Test that success logs successful call."""
        listener = SourceCircuitBreakerListener()
        cb = MagicMock(spec=CircuitBreaker)
        cb.name = "test_source"

        with patch("artradar.resilience.logger") as mock_logger:
            listener.success(cb)
            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args
            assert call_args[0][0] == "circuit_breaker_success"
            assert call_args[1]["source"] == "test_source"


class TestSourceCircuitBreakerManager:
    """Test SourceCircuitBreakerManager."""

    def test_get_breaker_creates_new_breaker(self) -> None:
        """Test that get_breaker creates a new circuit breaker."""
        manager = SourceCircuitBreakerManager()
        breaker = manager.get_breaker("test_source")

        assert isinstance(breaker, CircuitBreaker)
        assert breaker.name == "test_source"

    def test_get_breaker_returns_same_instance(self) -> None:
        """Test that get_breaker returns same instance for same source."""
        manager = SourceCircuitBreakerManager()
        breaker1 = manager.get_breaker("test_source")
        breaker2 = manager.get_breaker("test_source")

        assert breaker1 is breaker2

    def test_get_breaker_default_settings(self) -> None:
        """Test that circuit breaker has correct default settings."""
        manager = SourceCircuitBreakerManager()
        breaker = manager.get_breaker("test_source")

        assert breaker.fail_max == 5
        assert breaker.reset_timeout == 60
        assert breaker.success_threshold == 2

    def test_get_breaker_excludes_exceptions(self) -> None:
        """Test that circuit breaker excludes certain exceptions."""
        manager = SourceCircuitBreakerManager()
        breaker = manager.get_breaker("test_source")

        assert ValueError in breaker.excluded_exceptions
        assert KeyError in breaker.excluded_exceptions
        assert AttributeError in breaker.excluded_exceptions

    def test_get_breaker_thread_safe(self) -> None:
        """Test that get_breaker is thread-safe."""
        manager = SourceCircuitBreakerManager()
        breakers = []

        def get_breaker() -> None:
            breaker = manager.get_breaker("test_source")
            breakers.append(breaker)

        threads = [threading.Thread(target=get_breaker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All should be the same instance
        assert all(b is breakers[0] for b in breakers)

    def test_reset_breaker_resets_specific_breaker(self) -> None:
        """Test that reset_breaker resets a specific breaker."""
        manager = SourceCircuitBreakerManager()
        breaker = manager.get_breaker("test_source")

        with patch.object(breaker, "close") as mock_close:
            with patch("artradar.resilience.logger") as mock_logger:
                manager.reset_breaker("test_source")
                mock_close.assert_called_once()
                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args
                assert call_args[0][0] == "circuit_breaker_reset"
                assert call_args[1]["source"] == "test_source"

    def test_reset_breaker_nonexistent_source(self) -> None:
        """Test that reset_breaker handles nonexistent source gracefully."""
        manager = SourceCircuitBreakerManager()

        with patch("artradar.resilience.logger") as mock_logger:
            manager.reset_breaker("nonexistent")
            # Should not log anything for nonexistent source
            mock_logger.info.assert_not_called()

    def test_reset_all_resets_all_breakers(self) -> None:
        """Test that reset_all resets all breakers."""
        manager = SourceCircuitBreakerManager()
        breaker1 = manager.get_breaker("source1")
        breaker2 = manager.get_breaker("source2")
        breaker3 = manager.get_breaker("source3")

        with patch.object(breaker1, "close") as mock_close1:
            with patch.object(breaker2, "close") as mock_close2:
                with patch.object(breaker3, "close") as mock_close3:
                    with patch("artradar.resilience.logger") as mock_logger:
                        manager.reset_all()
                        mock_close1.assert_called_once()
                        mock_close2.assert_called_once()
                        mock_close3.assert_called_once()
                        mock_logger.info.assert_called_once()
                        call_args = mock_logger.info.call_args
                        assert call_args[0][0] == "circuit_breaker_reset_all"
                        assert call_args[1]["count"] == 3

    def test_get_status_returns_all_breaker_states(self) -> None:
        """Test that get_status returns status of all breakers."""
        manager = SourceCircuitBreakerManager()
        manager.get_breaker("source1")
        manager.get_breaker("source2")

        status = manager.get_status()

        assert "source1" in status
        assert "source2" in status
        assert status["source1"] is not None
        assert status["source2"] is not None

    def test_get_status_empty_manager(self) -> None:
        """Test that get_status returns empty dict for empty manager."""
        manager = SourceCircuitBreakerManager()
        status = manager.get_status()

        assert status == {}


class TestGlobalCircuitBreakerManager:
    """Test global circuit breaker manager singleton."""

    def test_get_circuit_breaker_manager_returns_singleton(self) -> None:
        """Test that get_circuit_breaker_manager returns singleton."""
        # Reset global state
        import artradar.resilience as resilience_module

        resilience_module._manager = None

        manager1 = get_circuit_breaker_manager()
        manager2 = get_circuit_breaker_manager()

        assert manager1 is manager2

    def test_get_circuit_breaker_manager_thread_safe(self) -> None:
        """Test that get_circuit_breaker_manager is thread-safe."""
        import artradar.resilience as resilience_module

        resilience_module._manager = None

        managers = []

        def get_manager() -> None:
            manager = get_circuit_breaker_manager()
            managers.append(manager)

        threads = [threading.Thread(target=get_manager) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All should be the same instance
        assert all(m is managers[0] for m in managers)
