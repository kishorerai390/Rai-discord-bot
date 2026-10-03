"""
Core Error Classification and Fault Boundary System for Rai.
Provides structured exceptions, error taxonomy, diagnostic ID generation,
and isolated error boundaries that prevent component failures from propagating.
"""

from __future__ import annotations

import enum
import functools
import logging
import random
import string
import traceback
from typing import Any, Callable, Coroutine, Optional, TypeVar, cast

logger = logging.getLogger("Rai.Errors")

T = TypeVar("T")


def generate_error_id() -> str:
    """Generates a unique diagnostic reference code (e.g. RAI-8F2K9A)."""
    chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"RAI-{chars}"


class ErrorSeverity(enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RaiBaseException(Exception):
    """Base class for all Rai system exceptions."""
    def __init__(self, message: str, error_id: Optional[str] = None, severity: ErrorSeverity = ErrorSeverity.MEDIUM):
        super().__init__(message)
        self.message = message
        self.error_id = error_id or generate_error_id()
        self.severity = severity


class RecoverableError(RaiBaseException):
    """An error from which the subsystem can automatically recover via retry or restart."""
    pass


class CriticalError(RaiBaseException):
    """A severe error requiring admin notification and component safe mode."""
    def __init__(self, message: str, error_id: Optional[str] = None):
        super().__init__(message, error_id, severity=ErrorSeverity.CRITICAL)


class TransientAPIError(RecoverableError):
    """Discord API or external HTTP timeout / rate-limit error."""
    def __init__(self, message: str, retry_after: float = 1.0, error_id: Optional[str] = None):
        super().__init__(message, error_id, severity=ErrorSeverity.LOW)
        self.retry_after = retry_after


class CircuitBreakerOpenError(RecoverableError):
    """Raised when an external service is tripped and temporarily blocked."""
    def __init__(self, service_name: str, reset_after: float, error_id: Optional[str] = None):
        msg = f"Service '{service_name}' is temporarily unavailable (circuit open). Reset in {reset_after:.1f}s."
        super().__init__(msg, error_id, severity=ErrorSeverity.MEDIUM)
        self.service_name = service_name
        self.reset_after = reset_after


class MusicPlaybackError(RecoverableError):
    """Isolated music playback exception. NEVER terminates the security subsystem."""
    def __init__(self, message: str, track_title: Optional[str] = None, error_id: Optional[str] = None):
        super().__init__(message, error_id, severity=ErrorSeverity.LOW)
        self.track_title = track_title or "Unknown Track"


class DatabaseUnavailableError(RecoverableError):
    """Database is temporarily inaccessible; bot operates in safe memory-fallback mode."""
    def __init__(self, message: str, error_id: Optional[str] = None):
        super().__init__(message, error_id, severity=ErrorSeverity.HIGH)


class SecurityPolicyViolation(RaiBaseException):
    """Raised when an unauthorized actor attempts forbidden administrative operations."""
    def __init__(self, message: str, user_id: int, error_id: Optional[str] = None):
        super().__init__(message, error_id, severity=ErrorSeverity.HIGH)
        self.user_id = user_id


def isolated_boundary(subsystem: str, fallback_value: Any = None):
    """
    Decorator that encapsulates execution inside an isolated error boundary.
    If the decorated coroutine raises an exception, it is logged and isolated,
    preventing catastrophic cascade into other subsystems.
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, Optional[T]]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Optional[T]:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                err_id = getattr(exc, "error_id", generate_error_id())
                logger.error(
                    f"[{err_id}] Subsystem '{subsystem}' caught isolated exception in {func.__name__}: {exc}",
                    exc_info=True,
                )
                return fallback_value
        return wrapper
    return decorator
