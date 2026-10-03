"""
Firebase Cloud Firestore Connection Manager for 『RΛI』.
Handles cloud dashboard data synchronization with graceful offline degradation.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from database.enums import DatabaseHealthStatus

logger = logging.getLogger("Rai.Database.Firebase")


class FirebaseConnectionManager:
    """
    Manages Firebase Firestore client lifecycle.
    If Firebase credentials are not provided or connection fails,
    operates safely in DISABLED/OFFLINE mode while synchronization queues accumulate locally in SQLite.
    """

    _instance: Optional[FirebaseConnectionManager] = None

    def __init__(self):
        self.project_id = os.getenv("FIREBASE_PROJECT_ID")
        self.credentials_path = os.getenv("FIREBASE_CREDENTIALS")
        self.enabled = os.getenv("FIREBASE_ENABLED", "true").lower() in ("true", "1", "yes") and bool(
            self.project_id or self.credentials_path
        )
        self._db: Any = None
        self._health_status = DatabaseHealthStatus.STARTING if self.enabled else DatabaseHealthStatus.DISABLED

    @classmethod
    def get_instance(cls) -> FirebaseConnectionManager:
        if cls._instance is None:
            cls._instance = FirebaseConnectionManager()
        return cls._instance

    @property
    def is_connected(self) -> bool:
        return self._db is not None

    @property
    def health_status(self) -> DatabaseHealthStatus:
        if not self.enabled:
            return DatabaseHealthStatus.DISABLED
        if self._db is not None:
            return DatabaseHealthStatus.ONLINE
        return self._health_status

    async def connect(self) -> bool:
        """Initializes Firebase App and Firestore client if configured."""
        if not self.enabled:
            logger.info("Firebase is disabled or credentials not configured. Operating in local-only mode.")
            self._health_status = DatabaseHealthStatus.DISABLED
            return False

        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            if not firebase_admin._apps:
                if self.credentials_path and os.path.exists(self.credentials_path):
                    cred = credentials.Certificate(self.credentials_path)
                    firebase_admin.initialize_app(cred, {"projectId": self.project_id})
                else:
                    firebase_admin.initialize_app(options={"projectId": self.project_id})

            self._db = firestore.client()
            self._health_status = DatabaseHealthStatus.ONLINE
            logger.info("Firebase Firestore client initialized successfully.")
            return True
        except Exception as e:
            self._health_status = DatabaseHealthStatus.OFFLINE
            logger.warning(f"Firebase connection note ({e}). Cloud sync will queue locally in SQLite.")
            return False

    def get_db(self) -> Optional[Any]:
        return self._db if self.is_connected else None
