"""
Atomic SQLite Backup Engine for 『RΛI』.
Utilizes the SQLite Online Backup API (conn.backup) to safely snapshot the database
even under active concurrent WAL-mode writes without corruption or locking failures.
Calculates SHA256 checksum and file metadata for disaster recovery verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Rai.Backups.SQLite")


@dataclass(frozen=True)
class SQLiteBackupResult:
    """Immutable result metadata for a local SQLite snapshot."""
    success: bool
    backup_path: Optional[Path]
    filename: str
    size_bytes: int
    sha256_checksum: str
    timestamp: float
    iso_created_at: str
    error_message: Optional[str] = None


class SQLiteBackupService:
    """Performs atomic SQLite backups to disk with SHA256 verification."""

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """Calculates cryptographic SHA256 checksum of the target file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def _perform_sync_backup(cls, source_path: Path, dest_dir: Path) -> SQLiteBackupResult:
        """Synchronous worker executed in background thread pool."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        filename = f"rai_sqlite_{timestamp_str}.db"
        dest_path = dest_dir / filename

        source_conn = None
        dest_conn = None
        try:
            if not source_path.exists():
                return SQLiteBackupResult(
                    success=False,
                    backup_path=None,
                    filename=filename,
                    size_bytes=0,
                    sha256_checksum="",
                    timestamp=now.timestamp(),
                    iso_created_at=now.isoformat(),
                    error_message=f"Source database file does not exist: {source_path}",
                )

            # Connect with URI or standard path
            source_conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True, timeout=15.0)
            dest_conn = sqlite3.connect(dest_path)

            # Execute online backup
            with dest_conn:
                source_conn.backup(dest_conn, pages=100, sleep=0.01)

            dest_conn.close()
            source_conn.close()

            # Verify integrity & checksum
            if not dest_path.exists() or dest_path.stat().st_size == 0:
                return SQLiteBackupResult(
                    success=False,
                    backup_path=None,
                    filename=filename,
                    size_bytes=0,
                    sha256_checksum="",
                    timestamp=now.timestamp(),
                    iso_created_at=now.isoformat(),
                    error_message="Destination backup file was empty or not created.",
                )

            size = dest_path.stat().st_size
            sha256 = cls._compute_sha256(dest_path)

            logger.info(f"SQLite atomic backup complete: {dest_path.name} ({size} bytes, sha256={sha256[:12]}...)")
            return SQLiteBackupResult(
                success=True,
                backup_path=dest_path,
                filename=filename,
                size_bytes=size,
                sha256_checksum=sha256,
                timestamp=now.timestamp(),
                iso_created_at=now.isoformat(),
            )

        except Exception as e:
            logger.error(f"SQLite backup failed: {e}", exc_info=True)
            if dest_conn:
                try:
                    dest_conn.close()
                except Exception:
                    pass
            if source_conn:
                try:
                    source_conn.close()
                except Exception:
                    pass
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except Exception:
                    pass

            return SQLiteBackupResult(
                success=False,
                backup_path=None,
                filename=filename,
                size_bytes=0,
                sha256_checksum="",
                timestamp=now.timestamp(),
                iso_created_at=now.isoformat(),
                error_message=str(e),
            )

    @classmethod
    async def create_backup(cls, source_path: Path, dest_dir: Path) -> SQLiteBackupResult:
        """Asynchronously dispatches online backup to avoid blocking the event loop."""
        return await asyncio.to_thread(cls._perform_sync_backup, source_path, dest_dir)
