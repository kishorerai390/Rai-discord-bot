"""
Local SQLite Synchronization Queue Engine for 『RΛI』.
Enforces idempotency, priority ordering, and local persistence before cloud sync.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from database.database import Database
from database.enums import SyncPriority, SyncStatus, SyncTarget
from database.models import PendingSyncOperation

logger = logging.getLogger("Rai.Database.Sync.Queue")


class SyncQueue:
    """
    Manages enqueueing and retrieval of cloud synchronization operations.
    Idempotent: Duplicate submissions with the same idempotency key are safely deduplicated.
    """

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def generate_operation_id(target: str, op_type: str, entity_id: str) -> str:
        """Generates deterministic idempotency key for an operation."""
        raw = f"{target}:{op_type}:{entity_id}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    async def enqueue(
        self,
        target: SyncTarget,
        operation_type: str,
        guild_id: int,
        payload: Dict[str, Any],
        priority: SyncPriority = SyncPriority.SECURITY,
        incident_id: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> bool:
        """
        Enqueues an operation into SQLite pending queue with priority.
        Ensures local persistence before cloud communication.
        """
        key_seed = entity_id or incident_id or f"{guild_id}:{time.time()}"
        op_id = self.generate_operation_id(target.value, operation_type, key_seed)

        return await self.db.queue_sync_operation(
            operation_id=op_id,
            guild_id=guild_id,
            target=target.value,
            operation_type=operation_type,
            payload=payload,
            priority=priority.value,
            incident_id=incident_id,
        )

    async def get_next_batch(self, target: SyncTarget, limit: int = 25) -> List[PendingSyncOperation]:
        """Fetches pending operations sorted by priority."""
        return await self.db.get_pending_sync_operations(target=target.value, limit=limit)

    async def mark_success(self, operation_id: str) -> bool:
        """Marks operation as successfully synchronized (SYNCED)."""
        return await self.db.update_sync_operation_status(
            operation_id=operation_id,
            status=SyncStatus.SYNCED.value,
        )

    async def mark_retry(
        self,
        operation_id: str,
        attempt_count: int,
        error_code: str,
        delay_seconds: float,
    ) -> bool:
        """Calculates backoff with jitter and reschedules operation."""
        next_attempt_ts = time.time() + delay_seconds
        import datetime
        next_iso = datetime.datetime.fromtimestamp(next_attempt_ts, datetime.timezone.utc).isoformat()

        status = SyncStatus.DEAD_LETTER.value if attempt_count >= 5 else SyncStatus.RETRYING.value
        return await self.db.update_sync_operation_status(
            operation_id=operation_id,
            status=status,
            error_code=error_code,
            next_attempt=next_iso,
            attempt_count=attempt_count,
        )
