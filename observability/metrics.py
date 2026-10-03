"""
Prometheus Observability & Metrics Engine for 『RΛI』.
Tracks security events, database latency, Discord API errors, worker status, and sync queues.

CRITICAL DESIGN RULE:
Never use high-cardinality labels (user_id, message_id, channel_id, incident_id).
All labels are strictly bounded to prevent metric explosion and preserve memory.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger("Rai.Observability.Metrics")

# Safely import prometheus_client with fallback stubbing if disabled
try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server, REGISTRY
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not available. Operating with metrics stubs.")


# ==========================================
# METRICS DEFINITIONS (STRICTLY LOW CARDINALITY)
# ==========================================

if PROMETHEUS_AVAILABLE:
    # 1. Security Metrics
    rai_security_events_total = Counter(
        "rai_security_events_total",
        "Total security events processed by RAI deterministic engine",
        ["event_type", "severity"],
    )
    rai_security_incidents_total = Counter(
        "rai_security_incidents_total",
        "Total unique security incidents recorded",
        ["severity", "status"],
    )
    rai_security_incidents_active = Gauge(
        "rai_security_incidents_active",
        "Number of currently open/mitigating incidents",
    )
    rai_raid_detections_total = Counter(
        "rai_raid_detections_total",
        "Total server raid attacks detected",
        ["classification"],
    )
    rai_antinuke_events_total = Counter(
        "rai_antinuke_events_total",
        "Total anti-nuke unauthorized administrative events detected",
        ["action_type"],
    )
    rai_antispam_events_total = Counter(
        "rai_antispam_events_total",
        "Total content spam events intercepted",
        ["spam_type"],
    )
    rai_mass_mention_events_total = Counter(
        "rai_mass_mention_events_total",
        "Total mass user mention spam attacks contained",
        ["severity"],
    )
    rai_security_actions_total = Counter(
        "rai_security_actions_total",
        "Total mitigation actions executed (timeout, delete, ban, purge)",
        ["action", "status"],
    )
    rai_security_actions_failed_total = Counter(
        "rai_security_actions_failed_total",
        "Total security mitigation actions failed",
        ["action", "reason_code"],
    )
    rai_emergency_mode_active = Gauge(
        "rai_emergency_mode_active",
        "Whether Emergency Protection Mode is currently active in any guild (1=Active, 0=Inactive)",
    )

    # 2. Discord API & Gateway
    rai_discord_events_total = Counter(
        "rai_discord_events_total",
        "Total Discord gateway events processed",
        ["event_name"],
    )
    rai_discord_api_errors_total = Counter(
        "rai_discord_api_errors_total",
        "Total Discord API HTTP errors intercepted",
        ["status_code", "error_code"],
    )
    rai_discord_rate_limits_total = Counter(
        "rai_discord_rate_limits_total",
        "Total Discord HTTP 429 rate limit events hit",
        ["endpoint"],
    )
    rai_discord_command_total = Counter(
        "rai_discord_command_total",
        "Total slash and prefix commands executed",
        ["command_name", "status"],
    )
    rai_discord_event_latency_seconds = Histogram(
        "rai_discord_event_latency_seconds",
        "Duration of Discord event handling",
        ["event_name"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    )

    # 3. Multi-Database Telemetry
    rai_sqlite_operations_total = Counter(
        "rai_sqlite_operations_total",
        "Total SQLite local runtime database operations",
        ["operation", "status"],
    )
    rai_postgres_operations_total = Counter(
        "rai_postgres_operations_total",
        "Total PostgreSQL permanent cloud database operations",
        ["operation", "status"],
    )
    rai_redis_operations_total = Counter(
        "rai_redis_operations_total",
        "Total Redis temporary state operations",
        ["operation", "status"],
    )
    rai_firebase_operations_total = Counter(
        "rai_firebase_operations_total",
        "Total Firebase cloud dashboard operations",
        ["operation", "status"],
    )

    # 4. Synchronization Queue
    rai_sync_queue_size = Gauge(
        "rai_sync_queue_size",
        "Total pending cloud synchronization operations in SQLite queue",
        ["target"],
    )
    rai_sync_operations_total = Counter(
        "rai_sync_operations_total",
        "Total synchronization attempts across cloud targets",
        ["target", "status"],
    )
    rai_sync_dead_letter_total = Counter(
        "rai_sync_dead_letter_total",
        "Total sync operations routed to dead letter queue after max retries",
        ["target"],
    )

    # 5. Workers & Self-Healing
    rai_worker_health = Gauge(
        "rai_worker_health",
        "Health state of internal workers (1=Healthy, 0=Degraded/Offline)",
        ["worker_name"],
    )
    rai_worker_restarts_total = Counter(
        "rai_worker_restarts_total",
        "Total automatic self-healing worker restarts executed by supervisor",
        ["worker_name"],
    )

    # 6. Music & AI
    rai_music_sessions = Gauge(
        "rai_music_sessions",
        "Active guild music player voice sessions",
    )
    rai_ai_requests_total = Counter(
        "rai_ai_requests_total",
        "Total AI inference and threat analysis requests",
        ["provider", "task", "status"],
    )
    rai_ai_latency_seconds = Histogram(
        "rai_ai_latency_seconds",
        "AI response latency in seconds",
        ["provider"],
        buckets=(0.25, 0.5, 1.0, 2.0, 4.0, 8.0),
    )

else:
    # Stubs for environments where prometheus_client is absent
    class _MetricStub:
        def labels(self, *args, **kwargs): return self
        def inc(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass

    rai_security_events_total = _MetricStub()
    rai_security_incidents_total = _MetricStub()
    rai_security_incidents_active = _MetricStub()
    rai_raid_detections_total = _MetricStub()
    rai_antinuke_events_total = _MetricStub()
    rai_antispam_events_total = _MetricStub()
    rai_mass_mention_events_total = _MetricStub()
    rai_security_actions_total = _MetricStub()
    rai_security_actions_failed_total = _MetricStub()
    rai_emergency_mode_active = _MetricStub()
    rai_discord_events_total = _MetricStub()
    rai_discord_api_errors_total = _MetricStub()
    rai_discord_rate_limits_total = _MetricStub()
    rai_discord_command_total = _MetricStub()
    rai_discord_event_latency_seconds = _MetricStub()
    rai_sqlite_operations_total = _MetricStub()
    rai_postgres_operations_total = _MetricStub()
    rai_redis_operations_total = _MetricStub()
    rai_firebase_operations_total = _MetricStub()
    rai_sync_queue_size = _MetricStub()
    rai_sync_operations_total = _MetricStub()
    rai_sync_dead_letter_total = _MetricStub()
    rai_worker_health = _MetricStub()
    rai_worker_restarts_total = _MetricStub()
    rai_music_sessions = _MetricStub()
    rai_ai_requests_total = _MetricStub()
    rai_ai_latency_seconds = _MetricStub()


class MetricsServer:
    """HTTP Exporter for Prometheus scraping (default port 9100)."""

    _server_started = False

    @classmethod
    def start(cls, port: Optional[int] = None) -> bool:
        if cls._server_started or not PROMETHEUS_AVAILABLE:
            return False

        metrics_port = port or int(os.getenv("PROMETHEUS_PORT", "9100"))
        enabled = os.getenv("PROMETHEUS_ENABLED", "true").lower() in ("true", "1", "yes")
        if not enabled:
            logger.info("Prometheus metrics HTTP server disabled via configuration.")
            return False

        try:
            start_http_server(metrics_port)
            cls._server_started = True
            logger.info(f"Prometheus metrics HTTP exporter listening on port {metrics_port}")
            return True
        except Exception as e:
            logger.warning(f"Could not bind Prometheus HTTP server on port {metrics_port}: {e}")
            return False
