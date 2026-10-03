"""
RAI — WORKER SUPERVISOR & SINGLETON LIFECYCLE CONTROLLER
Provides unified orchestration, heartbeat monitoring, stuck-worker detection,
duplicate suppression, and isolated auto-healing for all background workers.

Guarantees:
1. Strict Singleton Enforcement: No two workers with the same singleton ID can run concurrently.
2. Heartbeat tracking: Flags STUCK or DEAD workers exceeding heartbeat thresholds.
3. Bounded auto-restart with exponential backoff.
4. Comprehensive status telemetry for diagnostics and `/rai doctor`.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger("Rai.WorkerSupervisor")


class WorkerStatus(str, enum.Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass
class WorkerDescriptor:
    worker_id: str
    worker_name: str
    coro_factory: Optional[Callable[[], Coroutine[Any, Any, None]]] = None
    is_singleton: bool = True
    max_restarts: int = 5
    heartbeat_timeout_seconds: float = 120.0
    status: WorkerStatus = WorkerStatus.STOPPED
    started_at: float = 0.0
    last_heartbeat: float = 0.0
    last_success: Optional[float] = None
    last_error: Optional[str] = None
    restart_count: int = 0
    current_job: Optional[str] = None
    task: Optional[asyncio.Task] = None


class WorkerSupervisor:
    """
    Central background worker supervisor for RAI.
    Monitors all background processes, schedulers, and queue consumers.
    """

    _instance: Optional[WorkerSupervisor] = None

    def __init__(self) -> None:
        self._workers: Dict[str, WorkerDescriptor] = {}
        self._supervision_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> WorkerSupervisor:
        if cls._instance is None:
            cls._instance = WorkerSupervisor()
        return cls._instance

    def register(
        self,
        worker_id: str,
        worker_name: str,
        coro_factory: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
        is_singleton: bool = True,
        max_restarts: int = 5,
        heartbeat_timeout: float = 120.0,
    ) -> WorkerDescriptor:
        """Register a worker with the supervisor. Rejects duplicate registrations for running singletons."""
        if worker_id in self._workers:
            existing = self._workers[worker_id]
            if existing.status in (WorkerStatus.RUNNING, WorkerStatus.STARTING) and existing.is_singleton:
                logger.debug(
                    f"[WORKER_SUPERVISOR] Duplicate registration ignored for active singleton '{worker_id}'."
                )
                return existing
            # Update factory if re-registering
            existing.coro_factory = coro_factory or existing.coro_factory
            return existing

        desc = WorkerDescriptor(
            worker_id=worker_id,
            worker_name=worker_name,
            coro_factory=coro_factory,
            is_singleton=is_singleton,
            max_restarts=max_restarts,
            heartbeat_timeout_seconds=heartbeat_timeout,
        )
        self._workers[worker_id] = desc
        logger.info(f"[WORKER_SUPERVISOR] Registered worker '{worker_id}' ({worker_name})")
        return desc

    def heartbeat(self, worker_id: str, current_job: Optional[str] = None) -> None:
        """Worker periodically calls this to prove liveness."""
        if worker_id in self._workers:
            w = self._workers[worker_id]
            w.last_heartbeat = time.time()
            if current_job is not None:
                w.current_job = current_job
            if w.status in (WorkerStatus.STARTING, WorkerStatus.DEGRADED):
                w.status = WorkerStatus.RUNNING

    def record_success(self, worker_id: str, job_name: Optional[str] = None) -> None:
        """Worker records successful execution of a job cycle."""
        if worker_id in self._workers:
            w = self._workers[worker_id]
            w.last_success = time.time()
            w.last_heartbeat = time.time()
            w.status = WorkerStatus.RUNNING
            if job_name:
                w.current_job = f"completed:{job_name}"

    def record_error(self, worker_id: str, error: Exception | str) -> None:
        """Worker records non-fatal failure."""
        if worker_id in self._workers:
            w = self._workers[worker_id]
            w.last_error = str(error)
            w.status = WorkerStatus.DEGRADED
            logger.warning(f"[WORKER_SUPERVISOR] Worker '{worker_id}' degraded: {error}")

    def start_worker(self, worker_id: str) -> bool:
        """Starts a registered worker if not already active."""
        if worker_id not in self._workers:
            logger.error(f"[WORKER_SUPERVISOR] Cannot start unregistered worker '{worker_id}'")
            return False

        desc = self._workers[worker_id]
        if desc.status in (WorkerStatus.RUNNING, WorkerStatus.STARTING) and desc.task and not desc.task.done():
            logger.debug(f"[WORKER_SUPERVISOR] Worker '{worker_id}' already running.")
            return True

        if not desc.coro_factory:
            desc.status = WorkerStatus.RUNNING
            desc.started_at = time.time()
            desc.last_heartbeat = time.time()
            return True

        desc.status = WorkerStatus.STARTING
        desc.started_at = time.time()
        desc.last_heartbeat = time.time()

        async def _runner():
            try:
                desc.status = WorkerStatus.RUNNING
                await desc.coro_factory()
            except asyncio.CancelledError:
                desc.status = WorkerStatus.STOPPED
                logger.info(f"[WORKER_SUPERVISOR] Worker '{worker_id}' stopped gracefully.")
            except Exception as e:
                desc.status = WorkerStatus.FAILED
                desc.last_error = str(e)
                logger.error(f"[WORKER_SUPERVISOR] Worker '{worker_id}' crashed: {e}", exc_info=True)
                # Auto-recovery if permitted
                if desc.restart_count < desc.max_restarts:
                    desc.restart_count += 1
                    backoff = min(60.0, (2 ** desc.restart_count) * 2.0)
                    logger.info(f"[WORKER_SUPERVISOR] Auto-restarting '{worker_id}' in {backoff:.1f}s (attempt {desc.restart_count}/{desc.max_restarts})")
                    await asyncio.sleep(backoff)
                    self.start_worker(worker_id)

        desc.task = asyncio.create_task(_runner(), name=f"rai_worker_{worker_id}")
        return True

    def stop_worker(self, worker_id: str) -> bool:
        """Stops a running worker gracefully."""
        if worker_id not in self._workers:
            return False
        desc = self._workers[worker_id]
        desc.status = WorkerStatus.STOPPING
        if desc.task and not desc.task.done():
            desc.task.cancel()
        desc.status = WorkerStatus.STOPPED
        return True

    async def start_supervision(self) -> None:
        """Starts the supervisor self-monitoring loop."""
        if self._running:
            return
        self._running = True
        self._supervision_task = asyncio.create_task(self._monitor_loop(), name="worker_supervisor_loop")
        logger.info("[WORKER_SUPERVISOR] Self-healing supervision loop started.")

    def stop_supervision(self) -> None:
        self._running = False
        if self._supervision_task:
            self._supervision_task.cancel()

    async def _monitor_loop(self) -> None:
        """Checks for dead or stuck workers every 15 seconds."""
        while self._running:
            try:
                await asyncio.sleep(15.0)
                now = time.time()
                for wid, desc in list(self._workers.items()):
                    if desc.status == WorkerStatus.RUNNING:
                        # Check heartbeat timeout
                        elapsed = now - desc.last_heartbeat
                        if desc.last_heartbeat > 0 and elapsed > desc.heartbeat_timeout_seconds:
                            desc.status = WorkerStatus.DEGRADED
                            desc.last_error = f"Stuck worker: no heartbeat for {elapsed:.1f}s (threshold {desc.heartbeat_timeout_seconds}s)"
                            logger.warning(f"[WORKER_SUPERVISOR] {desc.last_error} on '{wid}'")

                        # Check if task died silently
                        if desc.task and desc.task.done() and not desc.task.cancelled():
                            exc = desc.task.exception()
                            desc.status = WorkerStatus.FAILED
                            desc.last_error = f"Task died silently: {exc}"
                            if desc.restart_count < desc.max_restarts:
                                desc.restart_count += 1
                                logger.info(f"[WORKER_SUPERVISOR] Restarting silently dead task '{wid}'")
                                self.start_worker(wid)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WORKER_SUPERVISOR] Exception in supervision loop: {e}", exc_info=True)

    def get_summary(self) -> Dict[str, Any]:
        """Provides status summary for Rai Doctor and health checks."""
        summary = {}
        for wid, w in self._workers.items():
            summary[wid] = {
                "name": w.worker_name,
                "status": w.status.value,
                "started_at": w.started_at,
                "last_heartbeat_ago": round(time.time() - w.last_heartbeat, 1) if w.last_heartbeat else None,
                "last_success_ago": round(time.time() - w.last_success, 1) if w.last_success else None,
                "last_error": w.last_error,
                "restart_count": w.restart_count,
                "current_job": w.current_job,
            }
        return summary
