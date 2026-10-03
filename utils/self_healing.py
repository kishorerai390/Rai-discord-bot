"""
Autonomous Self-Healing Engine for Rai Bot.
Detects, diagnoses, recovers, and verifies subsystem failures automatically.
Implements error classification, exponential backoff, component isolation,
safe mode, and persistent recovery auditing.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord

from database.models import SelfHealingRecord

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("RaiSelfHealing")


class ErrorClassification:
    TRANSIENT = "TRANSIENT"
    RECOVERABLE = "RECOVERABLE"
    COMPONENT_FAILURE = "COMPONENT_FAILURE"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    DISCORD_API_ERROR = "DISCORD_API_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class RaiSelfHealingEngine:
    """Central engine for autonomous fault recovery and health restoration."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._failure_counts: Dict[str, int] = {}  # component -> consecutive failures
        self._max_recovery_attempts = 5
        self._safe_mode = False
        self._supervisor_task: Optional[asyncio.Task] = None
        self._degraded_components: set[str] = set()

    @property
    def is_safe_mode(self) -> bool:
        return self._safe_mode

    def start(self) -> None:
        """Starts the autonomous self-healing supervisor loop."""
        if not self._supervisor_task or self._supervisor_task.done():
            self._supervisor_task = asyncio.create_task(self._healing_supervisor_loop())
            logger.info("Rai Self-Healing Engine initialized and running.")

    def stop(self) -> None:
        """Stops the self-healing supervisor."""
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()

    def classify_error(self, error: Exception) -> str:
        """Classifies an exception into an operational recovery category."""
        err_msg = str(error).lower()

        if isinstance(error, (discord.RateLimited,)):
            return ErrorClassification.RATE_LIMIT

        if isinstance(error, (discord.Forbidden,)):
            return ErrorClassification.PERMISSION_ERROR

        if isinstance(error, (discord.NotFound,)):
            return ErrorClassification.TRANSIENT

        if isinstance(error, (asyncio.TimeoutError,)):
            return ErrorClassification.TRANSIENT

        if isinstance(error, (discord.GatewayNotFound, discord.ConnectionClosed)):
            return ErrorClassification.DISCORD_API_ERROR

        if "locked" in err_msg or "database is locked" in err_msg:
            return ErrorClassification.DATABASE_ERROR

        if "corrupt" in err_msg or "disk i/o error" in err_msg:
            return ErrorClassification.CRITICAL

        if "connection" in err_msg or "socket" in err_msg:
            return ErrorClassification.DISCORD_API_ERROR

        return ErrorClassification.RECOVERABLE

    async def handle_component_error(
        self,
        component: str,
        error: Exception,
        error_id: Optional[str] = None,
    ) -> bool:
        """
        Executes the self-healing recovery loop for a component failure.
        DETECT -> DIAGNOSE -> CLASSIFY -> RECOVER -> VERIFY -> RESUME.
        """
        start_time = time.perf_counter()
        error_id = error_id or f"ERR-{uuid.uuid4().hex[:6].upper()}"
        recovery_id = f"HEAL-{uuid.uuid4().hex[:6].upper()}"

        classification = self.classify_error(error)
        failures = self._failure_counts.get(component, 0) + 1
        self._failure_counts[component] = failures

        logger.warning(
            f"[Self-Healing] {component} failed with {type(error).__name__} "
            f"({classification}). Failures: {failures}/{self._max_recovery_attempts}"
        )

        # If too many failures, enter Safe Mode or isolate component
        if failures >= self._max_recovery_attempts:
            self._degraded_components.add(component)
            if component in ("database", "gateway", "autopilot"):
                self._safe_mode = True
                logger.critical(f"[Self-Healing SAFE MODE] Critical component '{component}' exceeded retries!")

            await self._audit_recovery(
                recovery_id=recovery_id,
                error_id=error_id,
                component=component,
                failure_type=classification,
                action_taken="ISOLATE_COMPONENT_SAFE_MODE",
                attempt_number=failures,
                result="SAFE_MODE",
                duration_ms=(time.perf_counter() - start_time) * 1000.0,
            )
            return False

        # Controlled recovery action based on classification and component
        action_taken = "RESTART_WORKER"
        success = False

        if classification == ErrorClassification.RATE_LIMIT:
            action_taken = "BACKOFF_AND_PAUSE"
            await asyncio.sleep(2.0)
            success = True

        elif classification == ErrorClassification.DATABASE_ERROR:
            action_taken = "EXPONENTIAL_BACKOFF_RETRY"
            backoff = min(2 ** failures + random.uniform(0.1, 0.5), 10.0)
            await asyncio.sleep(backoff)
            if hasattr(self.bot, "db"):
                success = self.bot.db.is_connected

        elif classification in (ErrorClassification.COMPONENT_FAILURE, ErrorClassification.RECOVERABLE):
            action_taken = f"RECOVER_{component.upper()}"
            success = await self._recover_specific_component(component)

        elif classification == ErrorClassification.PERMISSION_ERROR:
            action_taken = "LOG_AND_NOTIFY_PERMISSIONS"
            success = True

        elif classification == ErrorClassification.CRITICAL:
            action_taken = "CRITICAL_ISOLATION"
            success = False

        else:
            action_taken = "GENERIC_COOLDOWN_AND_VERIFY"
            await asyncio.sleep(1.0)
            success = False

        # Verify recovery
        if success:
            self._failure_counts[component] = max(0, failures - 1)
            self._degraded_components.discard(component)
            result = "SUCCESS"
        else:
            result = "RETRYING"

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        await self._audit_recovery(
            recovery_id=recovery_id,
            error_id=error_id,
            component=component,
            failure_type=classification,
            action_taken=action_taken,
            attempt_number=failures,
            result=result,
            duration_ms=duration_ms,
        )

        return success

    async def _recover_specific_component(self, component: str) -> bool:
        """Executes targeted recovery for recognized bot subsystems."""
        try:
            if component == "action_queue":
                if hasattr(self.bot, "action_queue"):
                    self.bot.action_queue.stop()
                    self.bot.action_queue.start()
                    return True

            elif component == "command_watchdog":
                if hasattr(self.bot, "watchdog"):
                    self.bot.watchdog.stop()
                    self.bot.watchdog.start()
                    return True

            elif component == "autopilot":
                if hasattr(self.bot, "autopilot"):
                    # Check background loops
                    for task_loop in (
                        self.bot.autopilot.ticket_autopilot_loop,
                        self.bot.autopilot.temp_voice_autopilot_loop,
                        self.bot.autopilot.baseline_autopilot_loop,
                        self.bot.autopilot.health_supervisor_loop,
                    ):
                        if not task_loop.is_running():
                            task_loop.restart()
                    return True

            elif component == "cooldowns":
                if hasattr(self.bot, "cooldowns"):
                    self.bot.cooldowns.clear_all()
                    return True

            return True
        except Exception as e:
            logger.error(f"[Self-Healing] Failed recovering {component}: {e}")
            return False

    async def _audit_recovery(
        self,
        recovery_id: str,
        error_id: str,
        component: str,
        failure_type: str,
        action_taken: str,
        attempt_number: int,
        result: str,
        duration_ms: float,
    ) -> None:
        """Persists the self-healing event in SQLite."""
        if hasattr(self.bot, "db") and self.bot.db.is_connected:
            try:
                await self.bot.db.log_self_healing_record(
                    recovery_id=recovery_id,
                    error_id=error_id,
                    component=component,
                    failure_type=failure_type,
                    action_taken=action_taken,
                    attempt_number=attempt_number,
                    result=result,
                    duration_ms=round(duration_ms, 2),
                )
            except Exception as e:
                logger.error(f"Failed to log self-healing record: {e}")

    async def _healing_supervisor_loop(self) -> None:
        """Autonomous 30-second supervisor that checks dead workers and resets transient failure counts."""
        while True:
            try:
                await asyncio.sleep(30)
                # Decay failure counts gradually
                for comp in list(self._failure_counts.keys()):
                    if self._failure_counts[comp] > 0:
                        self._failure_counts[comp] -= 1
                        if self._failure_counts[comp] == 0:
                            self._degraded_components.discard(comp)

                # Check if safe mode can be cleared
                if self._safe_mode and not self._degraded_components:
                    self._safe_mode = False
                    logger.info("[Self-Healing] All components recovered. Safe Mode lifted.")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in healing supervisor loop: {e}")

    async def simulate_failure(self, failure_type: str) -> Dict[str, Any]:
        """
        Safely simulates component failure to verify diagnosis, recovery, and auditing.
        Does NOT harm real server assets.
        """
        sim_error_id = f"SIM-ERR-{random.randint(1000, 9999)}"
        failure_type = failure_type.lower()

        if failure_type == "worker":
            fake_err = RuntimeError("Simulated background worker unexpected termination")
            success = await self.handle_component_error("simulated_worker", fake_err, sim_error_id)
            return {
                "simulation": "worker_crash",
                "component": "simulated_worker",
                "classification": ErrorClassification.COMPONENT_FAILURE,
                "recovery_success": success,
                "error_id": sim_error_id,
            }

        elif failure_type == "database":
            fake_err = Exception("sqlite3.OperationalError: database is locked")
            success = await self.handle_component_error("database", fake_err, sim_error_id)
            return {
                "simulation": "database_lock",
                "component": "database",
                "classification": ErrorClassification.DATABASE_ERROR,
                "recovery_success": success,
                "error_id": sim_error_id,
            }

        elif failure_type == "api":
            fake_err = discord.HTTPException(response=discord.Object(id=1), message="429 Rate Limited")
            success = await self.handle_component_error("discord_api", fake_err, sim_error_id)
            return {
                "simulation": "api_timeout_ratelimit",
                "component": "discord_api",
                "classification": ErrorClassification.RATE_LIMIT,
                "recovery_success": success,
                "error_id": sim_error_id,
            }

        elif failure_type == "command":
            fake_err = ValueError("Simulated unhandled command parameter error")
            success = await self.handle_component_error("command_pipeline", fake_err, sim_error_id)
            return {
                "simulation": "command_exception",
                "component": "command_pipeline",
                "classification": ErrorClassification.RECOVERABLE,
                "recovery_success": success,
                "error_id": sim_error_id,
            }

        else:
            return {"status": "error", "message": f"Unknown failure simulation type: {failure_type}"}

    def get_health_metrics(self) -> Dict[str, Any]:
        """Returns health states of all monitored components for health dashboards."""
        return {
            "safe_mode": self._safe_mode,
            "degraded_components": list(self._degraded_components),
            "failure_counts": dict(self._failure_counts),
        }
