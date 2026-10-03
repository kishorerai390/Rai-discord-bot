"""
Centralized Observability Health Check Service for 『RΛI』.
Evaluates Liveness, Readiness, Security Health, Database Health, and Worker Health.
Security Health is strictly isolated and never marked degraded due to cloud dependencies.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from database.enums import DatabaseHealthStatus

logger = logging.getLogger("Rai.Observability.Health")


@dataclass(frozen=True)
class SystemHealthReport:
    """Comprehensive health matrix."""
    liveness: bool
    readiness: bool
    security_health: str       # "HEALTHY", "DEGRADED", "CRITICAL"
    database_health: str       # "HEALTHY", "DEGRADED", "OFFLINE"
    worker_health: str         # "HEALTHY", "DEGRADED"
    overall_status: str        # "HEALTHY", "DEGRADED", "CRITICAL"
    uptime_seconds: float
    details: Dict[str, Any]


class ObservabilityHealthService:
    """
    Evaluates health across all active RAI subsystems.
    Core Guarantee:
    If PostgreSQL, Redis, or Firebase are offline, `security_health` remains HEALTHY
    as long as SQLite and deterministic containment remain active.
    """

    _start_time = time.time()

    @classmethod
    def evaluate_health(cls, bot: Optional[Any] = None) -> SystemHealthReport:
        uptime = round(time.time() - cls._start_time, 1)

        # 1. Evaluate Database Health
        from database.manager import DatabaseManager
        db_mgr = DatabaseManager.get_instance()
        sqlite_ok = db_mgr.sqlite.is_connected
        pg_ok = db_mgr.postgres_conn.is_connected
        redis_ok = db_mgr.redis_conn.is_connected
        fb_ok = db_mgr.firebase_conn.is_connected

        if sqlite_ok and (pg_ok or not db_mgr.postgres_conn.enabled):
            database_health = "HEALTHY"
        elif sqlite_ok:
            database_health = "DEGRADED"
        else:
            database_health = "OFFLINE"

        # 2. Evaluate Security Health (Independent of cloud databases!)
        # Security is HEALTHY if local SQLite is operational and bot has gateway connection
        is_ready = bool(bot and getattr(bot, "is_ready", lambda: True)())
        if sqlite_ok and is_ready:
            security_health = "HEALTHY"
        elif sqlite_ok:
            security_health = "HEALTHY (STANDALONE)"
        else:
            security_health = "DEGRADED"

        # 3. Evaluate Worker Health
        worker_health = "HEALTHY"
        if hasattr(bot, "supervisor") and bot.supervisor:
            supervisor_health = bot.supervisor.get_overall_health()
            if supervisor_health.get("overall_status") != "HEALTHY":
                worker_health = "DEGRADED"

        # 4. Overall Status
        if security_health.startswith("HEALTHY") and database_health == "HEALTHY" and worker_health == "HEALTHY":
            overall_status = "HEALTHY"
        elif security_health.startswith("HEALTHY"):
            overall_status = "DEGRADED"  # Cloud or optional services degraded, but security protected!
        else:
            overall_status = "CRITICAL"

        liveness = True
        readiness = is_ready and sqlite_ok

        details = {
            "sqlite": "ONLINE" if sqlite_ok else "OFFLINE",
            "postgres": db_mgr.postgres_conn.health_status.value,
            "redis": db_mgr.redis_conn.health_status.value,
            "firebase": db_mgr.firebase_conn.health_status.value,
            "redis_fallback_active": db_mgr.redis_conn.is_fallback_active,
            "sync_worker_running": db_mgr.sync_worker._running,
        }

        return SystemHealthReport(
            liveness=liveness,
            readiness=readiness,
            security_health=security_health,
            database_health=database_health,
            worker_health=worker_health,
            overall_status=overall_status,
            uptime_seconds=uptime,
            details=details,
        )
