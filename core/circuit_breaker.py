"""
Circuit Breaker Pattern for External Dependencies.
Protects Rai from cascading failures when external services (YouTube, Lavalink,
FFmpeg, Webhooks, or REST APIs) experience downtime or rate-limits.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from typing import Any, Callable, Coroutine, Dict, Optional, TypeVar

from core.errors import CircuitBreakerOpenError

logger = logging.getLogger("Rai.CircuitBreaker")

T = TypeVar("T")


class CircuitState(enum.Enum):
    CLOSED = "CLOSED"        # Normal operation: all calls pass through
    OPEN = "OPEN"            # Tripped: requests fail fast without calling external service
    HALF_OPEN = "HALF_OPEN"  # Testing: allows limited probe requests to check if service recovered


class CircuitBreaker:
    """
    State machine that trips open after repeated failures, preventing hung threads
    and resource starvation.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 4,
        recovery_timeout: float = 45.0,
        half_open_max_trials: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_trials = half_open_max_trials

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        self._lock = asyncio.Lock()

    @property
    def is_available(self) -> bool:
        """Returns True if requests can be executed through the circuit."""
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info(f"Circuit Breaker '{self.name}' entering HALF_OPEN probe mode.")
                return True
            return False
        return True

    def get_remaining_open_time(self) -> float:
        """Seconds remaining before circuit transitions from OPEN to HALF_OPEN."""
        if self.state != CircuitState.OPEN:
            return 0.0
        elapsed = time.time() - self.last_failure_time
        return max(0.0, self.recovery_timeout - elapsed)

    async def record_success(self) -> None:
        """Record successful execution."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.half_open_max_trials:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    logger.info(f"Circuit Breaker '{self.name}' fully recovered. State: CLOSED 🟢")
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)

    async def record_failure(self, error: Exception) -> None:
        """Record failed execution and evaluate threshold trip."""
        async with self._lock:
            self.last_failure_time = time.time()
            self.failure_count += 1
            logger.warning(
                f"Circuit Breaker '{self.name}' registered failure ({self.failure_count}/{self.failure_threshold}): {error}"
            )

            if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.error(
                    f"🚨 Circuit Breaker '{self.name}' TRIPPED OPEN 🔴. Rejecting requests for {self.recovery_timeout:.1f}s."
                )

    async def call(self, coroutine_func: Callable[[], Coroutine[Any, Any, T]]) -> T:
        """Executes a coroutine guarded by this circuit breaker."""
        if not self.is_available:
            remaining = self.get_remaining_open_time()
            raise CircuitBreakerOpenError(self.name, reset_after=remaining)

        try:
            result = await coroutine_func()
            await self.record_success()
            return result
        except Exception as exc:
            await self.record_failure(exc)
            raise


class CircuitBreakerRegistry:
    """Singleton registry tracking all circuit breakers across the platform."""

    _breakers: Dict[str, CircuitBreaker] = {}

    @classmethod
    def get(
        cls,
        name: str,
        failure_threshold: int = 4,
        recovery_timeout: float = 45.0,
    ) -> CircuitBreaker:
        if name not in cls._breakers:
            cls._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return cls._breakers[name]

    @classmethod
    def get_all_statuses(cls) -> Dict[str, str]:
        """Exports statuses of all registered circuits."""
        return {name: b.state.value for name, b in cls._breakers.items()}

    @classmethod
    def reset_all(cls) -> None:
        for b in cls._breakers.values():
            b.state = CircuitState.CLOSED
            b.failure_count = 0
