from __future__ import annotations

import threading

import structlog
from pybreaker import CircuitBreaker, CircuitBreakerListener, CircuitBreakerState

logger = structlog.get_logger(__name__)


class SourceCircuitBreakerListener(CircuitBreakerListener):
    def before_call(
        self, cb: CircuitBreaker, func: object, *args: object, **kwargs: object
    ) -> None:
        return None

    def state_change(
        self,
        cb: CircuitBreaker,
        old_state: CircuitBreakerState | None,
        new_state: CircuitBreakerState,
    ) -> None:
        logger.info(
            "circuit_breaker_state_change",
            source=cb.name,
            before=old_state,
            after=new_state,
        )

    def failure(
        self,
        cb: CircuitBreaker,
        exc: BaseException,
    ) -> None:
        logger.warning(
            "circuit_breaker_failure",
            source=cb.name,
            exception=type(exc).__name__,
            message=str(exc),
        )

    def success(self, cb: CircuitBreaker) -> None:
        logger.debug(
            "circuit_breaker_success",
            source=cb.name,
        )


class SourceCircuitBreakerManager:
    def __init__(self) -> None:
        self._instances: dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()
        self._listener = SourceCircuitBreakerListener()

    def get_breaker(self, source_name: str) -> CircuitBreaker:
        if source_name in self._instances:
            return self._instances[source_name]

        with self._lock:
            if source_name in self._instances:
                return self._instances[source_name]

            breaker = CircuitBreaker(
                fail_max=5,
                reset_timeout=60,
                success_threshold=2,
                listeners=[self._listener],
                name=source_name,
                exclude=[ValueError, KeyError, AttributeError],
            )
            self._instances[source_name] = breaker
            return breaker

    def reset_breaker(self, source_name: str) -> None:
        with self._lock:
            if source_name in self._instances:
                self._instances[source_name].close()
                logger.info("circuit_breaker_reset", source=source_name)

    def reset_all(self) -> None:
        with self._lock:
            for breaker in self._instances.values():
                breaker.close()
            logger.info("circuit_breaker_reset_all", count=len(self._instances))

    def get_status(self) -> dict[str, str]:
        with self._lock:
            return {name: str(breaker.state) for name, breaker in self._instances.items()}


_manager: SourceCircuitBreakerManager | None = None
_manager_lock = threading.Lock()


def get_circuit_breaker_manager() -> SourceCircuitBreakerManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = SourceCircuitBreakerManager()
    return _manager
