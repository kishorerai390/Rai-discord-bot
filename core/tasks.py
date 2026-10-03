"""
Core Background Task Manager and Timeout Resilience Engine for 『RΛI』.
Provides:
- Timeout protection wrappers for all @tasks.loop background workers
- Execution telemetry (runs, duration, timeouts, errors, consecutive failures)
- Global BackgroundTaskManager registry for centralized tracking and graceful teardown
- Automatic failure isolation preventing background loop termination
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, TypeVar

from core.errors import generate_error_id

logger = logging.getLogger("Rai.TaskManager")

T = TypeVar("T")


@dataclass
class TaskTelemetry:
    """Runtime execution statistics for a background task or loop."""
    name: str
    timeout_seconds: float
    total_runs: int = 0
    successful_runs: int = 0
    timeouts: int = 0
    unhandled_errors: int = 0
    consecutive_errors: int = 0
    last_run_timestamp: float = 0.0
    last_duration_seconds: float = 0.0
    last_error: Optional[str] = None
    last_error_id: Optional[str] = None
    is_running: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "timeout_seconds": self.timeout_seconds,
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "timeouts": self.timeouts,
            "unhandled_errors": self.unhandled_errors,
            "consecutive_errors": self.consecutive_errors,
            "last_run": self.last_run_timestamp,
            "last_duration_ms": round(self.last_duration_seconds * 1000, 2),
            "last_error": self.last_error,
            "last_error_id": self.last_error_id,
            "status": "HEALTHY" if self.consecutive_errors == 0 else "DEGRADED",
        }


class BackgroundTaskManager:
    """Central registry and watchdog for all background tasks and loops in 『RΛI』."""

    _instance: Optional[BackgroundTaskManager] = None

    def __init__(self):
        self._tasks: Dict[str, TaskTelemetry] = {}
        self._active_asyncio_tasks: Dict[str, asyncio.Task] = {}
        self._active_loops: List[Any] = []

    @classmethod
    def get_instance(cls) -> BackgroundTaskManager:
        if cls._instance is None:
            cls._instance = BackgroundTaskManager()
        return cls._instance

    def register_telemetry(self, name: str, timeout_seconds: float) -> TaskTelemetry:
        if name not in self._tasks:
            self._tasks[name] = TaskTelemetry(name=name, timeout_seconds=timeout_seconds)
        return self._tasks[name]

    def register_loop(self, loop_obj: Any) -> None:
        """Registers a discord.ext.tasks.Loop instance for global shutdown tracking."""
        if loop_obj not in self._active_loops:
            self._active_loops.append(loop_obj)

    def register_asyncio_task(self, name: str, task: asyncio.Task) -> None:
        """Registers a raw asyncio.Task for lifecycle monitoring and graceful shutdown."""
        self._active_asyncio_tasks[name] = task

    def get_telemetry(self, name: str) -> Optional[TaskTelemetry]:
        return self._tasks.get(name)

    def get_all_telemetry(self) -> Dict[str, Dict[str, Any]]:
        return {name: t.to_dict() for name, t in self._tasks.items()}

    async def cancel_all(self, timeout: float = 5.0) -> None:
        """
        Gracefully stops all registered discord tasks.loop workers and cancels asyncio tasks.
        Guarantees that no background workers hang during shutdown.
        """
        logger.info(f"Stopping {len(self._active_loops)} background loops and {len(self._active_asyncio_tasks)} asyncio tasks...")

        # 1. Stop all discord.ext.tasks.Loop instances
        for loop in self._active_loops:
            try:
                if hasattr(loop, "cancel"):
                    loop.cancel()
                elif hasattr(loop, "stop"):
                    loop.stop()
            except Exception as e:
                logger.debug(f"Error stopping loop {loop}: {e}")

        # 2. Cancel and await all tracked asyncio.Tasks
        tasks_to_wait = []
        for name, task in list(self._active_asyncio_tasks.items()):
            if not task.done():
                task.cancel()
                tasks_to_wait.append(task)

        if tasks_to_wait:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_wait, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Some background tasks did not cancel within {timeout}s shutdown timeout.")
            except Exception as e:
                logger.debug(f"Task shutdown note: {e}")

        logger.info("All background tasks safely terminated.")


def safe_task_loop(task_name: str, timeout_seconds: float = 60.0):
    """
    Decorator that protects background tasks with:
    1. Strict execution timeout via asyncio.wait_for
    2. Telemetry tracking (duration, success, failure)
    3. Unhandled error suppression to prevent discord.ext.tasks.Loop from dying silently
    4. Integration with central BackgroundTaskManager and SystemSupervisor
    """
    manager = BackgroundTaskManager.get_instance()
    telemetry = manager.register_telemetry(task_name, timeout_seconds)

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, Optional[T]]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Optional[T]:
            telemetry.total_runs += 1
            telemetry.last_run_timestamp = time.time()
            telemetry.is_running = True
            start_time = time.monotonic()

            try:
                # Wrap the loop body in strict timeout
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
                telemetry.successful_runs += 1
                telemetry.consecutive_errors = 0
                return result

            except asyncio.TimeoutError:
                telemetry.timeouts += 1
                telemetry.consecutive_errors += 1
                err_id = generate_error_id()
                telemetry.last_error = f"Execution timed out after {timeout_seconds}s"
                telemetry.last_error_id = err_id
                logger.warning(
                    f"[{err_id}] [TASK_TIMEOUT] Background task '{task_name}' timed out after {timeout_seconds}s. "
                    "Skipping current iteration to preserve event loop health."
                )
                return None

            except asyncio.CancelledError:
                # Normal cancellation during bot shutdown or loop stop
                raise

            except Exception as e:
                telemetry.unhandled_errors += 1
                telemetry.consecutive_errors += 1
                err_id = getattr(e, "error_id", generate_error_id())
                telemetry.last_error = str(e)
                telemetry.last_error_id = err_id
                logger.error(
                    f"[{err_id}] [TASK_ERROR] Background task '{task_name}' encountered unhandled error: {e}",
                    exc_info=True,
                )
                return None

            finally:
                telemetry.last_duration_seconds = time.monotonic() - start_time
                telemetry.is_running = False

        return wrapper
    return decorator
