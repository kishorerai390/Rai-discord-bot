"""
Database and Synchronization Enums for 『RΛI』 Multi-Database Architecture.
Defines health states, synchronization targets, priority levels, and queue states.
"""

from __future__ import annotations

import enum


class DatabaseHealthStatus(str, enum.Enum):
    """Normalized health status for all managed database connections."""
    DISABLED = "DISABLED"
    STARTING = "STARTING"
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"
    RECOVERING = "RECOVERING"


class SyncTarget(str, enum.Enum):
    """Target persistence engines for synchronization."""
    SQLITE = "SQLITE"
    POSTGRESQL = "POSTGRESQL"
    FIREBASE = "FIREBASE"


class SyncPriority(str, enum.Enum):
    """
    Priority ordering for synchronization operations.
    CRITICAL_SECURITY always preempts lower-priority items.
    """
    CRITICAL_SECURITY = "CRITICAL_SECURITY"
    SECURITY = "SECURITY"
    INCIDENT = "INCIDENT"
    MODERATION = "MODERATION"
    SYSTEM = "SYSTEM"
    MUSIC = "MUSIC"
    ANALYTICS = "ANALYTICS"
    NON_CRITICAL = "NON_CRITICAL"

    @property
    def rank(self) -> int:
        """Lower integer value indicates higher priority."""
        ranks = {
            SyncPriority.CRITICAL_SECURITY: 0,
            SyncPriority.SECURITY: 1,
            SyncPriority.INCIDENT: 2,
            SyncPriority.MODERATION: 3,
            SyncPriority.SYSTEM: 4,
            SyncPriority.MUSIC: 5,
            SyncPriority.ANALYTICS: 6,
            SyncPriority.NON_CRITICAL: 7,
        }
        return ranks.get(self, 99)


class SyncStatus(str, enum.Enum):
    """Execution state of a queued synchronization task."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SYNCED = "SYNCED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"
