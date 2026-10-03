"""
Firebase Firestore Cloud Synchronization Repository for 『RΛI』.
Provides real-time cloud dashboard data synchronization.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from database.firebase.connection import FirebaseConnectionManager
from core.results import Result, ResultStatus, ErrorCodes, DatabaseResultData

logger = logging.getLogger("Rai.Database.Firebase.Repo")


class FirebaseRepository:
    """
    Manages non-critical cloud dashboard synchronization in Firestore.
    Never blocks security execution.
    """

    def __init__(self, conn_manager: Optional[FirebaseConnectionManager] = None):
        self.conn = conn_manager or FirebaseConnectionManager.get_instance()

    async def sync_incident(self, incident_data: Dict[str, Any]) -> Result[DatabaseResultData]:
        """Synchronizes incident record to Firestore collection 'incidents'."""
        db = self.conn.get_db()
        if db is None:
            return Result.database_error(
                message="Firebase offline or unconfigured. Queued in local SQLite.",
                code=ErrorCodes.DATABASE_ERROR,
                retryable=True,
            )

        inc_id = str(incident_data.get("incident_id"))
        try:
            doc_ref = db.collection("incidents").document(inc_id)
            doc_ref.set(incident_data, merge=True)
            return Result.ok(
                data=DatabaseResultData(
                    operation="firebase_sync_incident",
                    incident_id=inc_id,
                    affected_rows=1,
                    table="firestore:incidents",
                ),
                incident_id=inc_id,
            )
        except Exception as e:
            logger.debug(f"Firestore sync error for incident '{inc_id}': {e}")
            return Result.database_error(
                message=f"Firestore sync error: {e}",
                code=ErrorCodes.DATABASE_ERROR,
                retryable=True,
                incident_id=inc_id,
            )

    async def sync_dashboard_summary(self, guild_id: int, summary: Dict[str, Any]) -> Result[DatabaseResultData]:
        """Synchronizes guild dashboard telemetry to Firestore."""
        db = self.conn.get_db()
        if db is None:
            return Result.database_error(
                message="Firebase offline. Queued in SQLite.",
                code=ErrorCodes.DATABASE_ERROR,
                retryable=True,
            )

        try:
            doc_ref = db.collection("guild_dashboards").document(str(guild_id))
            doc_ref.set(summary, merge=True)
            return Result.ok(
                data=DatabaseResultData(
                    operation="firebase_sync_dashboard",
                    affected_rows=1,
                    table="firestore:guild_dashboards",
                )
            )
        except Exception as e:
            return Result.database_error(
                message=f"Firestore dashboard sync error: {e}",
                code=ErrorCodes.DATABASE_ERROR,
                retryable=True,
            )
