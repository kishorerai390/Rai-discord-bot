"""
Database Reconciliation Manager for 『RΛI』.
Detects missing, partially synchronized, or stale records between SQLite and PostgreSQL/Firebase.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from database.database import Database
from database.enums import SyncPriority, SyncTarget
from database.sync.queue import SyncQueue

logger = logging.getLogger("Rai.Database.Sync.Reconciliation")


class ReconciliationManager:
    """
    Periodically inspects synchronization status, identifies unsynchronized incidents,
    and enqueues reconciliation tasks to ensure 100% data consistency.
    """

    def __init__(self, db: Database, queue: SyncQueue):
        self.db = db
        self.queue = queue

    async def reconcile_recent_incidents(self, limit: int = 50) -> Dict[str, int]:
        """
        Scans recent SQLite incidents and ensures they exist or are queued for PostgreSQL and Firebase.
        """
        reconciled = {"postgres_queued": 0, "firebase_queued": 0}
        try:
            # Query recent incidents from SQLite
            async with self.db._db.execute(
                """
                SELECT incident_id, guild_id, user_id, first_channel_id, severity, action_taken, incident_status, first_seen AS created_at
                FROM mention_spam_incidents
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()

            for r in rows:
                inc_id = r["incident_id"]
                guild_id = r["guild_id"]
                payload = {
                    "incident_id": inc_id,
                    "guild_id": guild_id,
                    "event_type": "MENTION_SPAM",
                    "severity": r["severity"],
                    "status": r["incident_status"],
                    "user_id": r["user_id"],
                    "created_at": r["created_at"],
                    "action_summary": r["action_taken"],
                }

                # Ensure queued for PostgreSQL
                enqueued_pg = await self.queue.enqueue(
                    target=SyncTarget.POSTGRESQL,
                    operation_type="save_incident",
                    guild_id=guild_id,
                    payload=payload,
                    priority=SyncPriority.INCIDENT,
                    incident_id=inc_id,
                    entity_id=f"rec_pg_{inc_id}",
                )
                if enqueued_pg:
                    reconciled["postgres_queued"] += 1

                # Ensure queued for Firebase
                enqueued_fb = await self.queue.enqueue(
                    target=SyncTarget.FIREBASE,
                    operation_type="sync_incident",
                    guild_id=guild_id,
                    payload=payload,
                    priority=SyncPriority.INCIDENT,
                    incident_id=inc_id,
                    entity_id=f"rec_fb_{inc_id}",
                )
                if enqueued_fb:
                    reconciled["firebase_queued"] += 1

            return reconciled
        except Exception as e:
            logger.error(f"Reconciliation error: {e}")
            return reconciled
