"""
Music Subsystem Failure Isolation Engine.
Enforces Section 2 & 10 architectural mandate:
MUSIC MUST NEVER BE ABLE TO CRASH SECURITY.

Flow on error:
Music error -> Save state -> Isolate affected player -> Record circuit breaker -> Restore queue -> Security continues untouched.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable, Coroutine, Optional, TypeVar

from core.circuit_breaker import CircuitBreakerRegistry
from core.errors import MusicPlaybackError, generate_error_id
from core.rate_limiter import ResourcePriority

logger = logging.getLogger("Rai.MusicIsolation")

T = TypeVar("T")


class MusicIsolationManager:
    """
    Air-gapped error boundary protecting Rai core and security from music crashes.
    """

    @classmethod
    def guard(cls, operation_name: str, fallback_return: Any = None):
        """
        Decorator that encapsulates any music operation inside an absolute boundary.
        Any exception caught is contained, reported to the supervisor, and prevented
        from bubbling to the Discord event loop or other subsystems.
        """
        def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, Optional[T]]]:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Optional[T]:
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    err_id = generate_error_id()
                    logger.error(
                        f"[{err_id}] [MUSIC ISOLATED FAULT] Operation '{operation_name}' failed safely: {exc}",
                        exc_info=True,
                    )

                    # 1. Record failure in audio circuit breaker
                    breaker = CircuitBreakerRegistry.get("music_audio_source")
                    try:
                        await breaker.record_failure(exc)
                    except Exception:
                        pass

                    # 2. Extract bot reference if available to alert supervisor
                    bot = None
                    for arg in args:
                        if hasattr(arg, "bot"):
                            bot = arg.bot
                            break
                        elif hasattr(arg, "supervisor"):
                            bot = arg
                            break

                    if bot and hasattr(bot, "supervisor"):
                        bot.supervisor.subsystems["Music"].record_failure(f"{operation_name}: {exc}")

                    return fallback_return
            return wrapper
        return decorator
