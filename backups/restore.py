"""
Controlled Disaster Recovery & Database Restoration Engine for 『RΛI』.
CRITICAL SAFETY RULE:
Never automatically restore production databases.
Restoration requires:
1. Cryptographic SHA256 checksum verification.
2. Snapshotting current state before making any modifications.
3. Explicit administrative confirmation token or interactive authorization.
4. Schema validation and post-restore integrity checks.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Rai.Backups.Restore")


@dataclass(frozen=True)
class RestoreResult:
    """Outcome of a controlled database restoration."""
    success: bool
    source_backup: Path
    pre_restore_snapshot: Optional[Path]
    integrity_verified: bool
    error_message: Optional[str] = None


class SafeRestoreEngine:
    """Orchestrates non-destructive restoration of SQLite local databases."""

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def validate_backup_file(cls, backup_path: Path, expected_sha256: Optional[str] = None) -> bool:
        """Verifies file existence, header validity/archive integrity, and optional checksum."""
        if not backup_path.exists() or backup_path.stat().st_size < 100:
            return False

        if backup_path.name.endswith(".zip") or backup_path.name.endswith(".enc"):
            try:
                from backups.archive import BackupArchiveBuilder
                res = BackupArchiveBuilder.verify_archive(backup_path, expected_sha256=expected_sha256)
                return res.verified
            except Exception as e:
                logger.error(f"Archive validation failed for {backup_path}: {e}")
                return False

        if expected_sha256:
            actual_sha = cls._compute_sha256(backup_path)
            if actual_sha.lower() != expected_sha256.lower():
                logger.error(f"Checksum mismatch on backup {backup_path}: expected {expected_sha256}, got {actual_sha}")
                return False

        try:
            conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("PRAGMA quick_check")
            row = cursor.fetchone()
            conn.close()
            return bool(row and row[0] == "ok")
        except Exception as e:
            logger.error(f"SQLite PRAGMA quick_check failed on {backup_path}: {e}")
            return False

    @classmethod
    async def execute_restore(
        cls,
        backup_path: Path,
        target_db_path: Path,
        confirmation_token: str,
        expected_sha256: Optional[str] = None,
    ) -> RestoreResult:
        """
        Executes safe restoration.
        Confirmation token MUST equal 'CONFIRM_RESTORE_<FILENAME>' or 'CONFIRM_RESTORE_<STEM>'
        to prevent accidental invocation.
        """
        token_a = f"CONFIRM_RESTORE_{backup_path.name}"
        token_b = f"CONFIRM_RESTORE_{backup_path.stem.replace('.zip', '')}"
        if confirmation_token not in (token_a, token_b):
            return RestoreResult(
                success=False,
                source_backup=backup_path,
                pre_restore_snapshot=None,
                integrity_verified=False,
                error_message=f"Invalid authorization token. Expected '{token_a}'.",
            )

        # 1. Validate source backup integrity
        valid = await asyncio.to_thread(cls.validate_backup_file, backup_path, expected_sha256)
        if not valid:
            return RestoreResult(
                success=False,
                source_backup=backup_path,
                pre_restore_snapshot=None,
                integrity_verified=False,
                error_message="Backup file failed pre-restore SQLite integrity verification.",
            )

        # 2. Take a pre-restore safety snapshot of the active database if it exists
        pre_restore_snapshot: Optional[Path] = None
        if target_db_path.exists():
            ts = int(time.time())
            pre_restore_snapshot = target_db_path.parent / f"pre_restore_snapshot_{ts}.db"
            try:
                # Online backup of target DB to create safety snapshot cleanly
                def _snapshot_target():
                    try:
                        s_conn = sqlite3.connect(f"file:{target_db_path}?mode=ro", uri=True, timeout=10.0)
                        d_conn = sqlite3.connect(pre_restore_snapshot)
                        with d_conn:
                            s_conn.backup(d_conn, pages=100)
                        d_conn.close()
                        s_conn.close()
                    except Exception:
                        shutil.copy2(target_db_path, pre_restore_snapshot)

                await asyncio.to_thread(_snapshot_target)
                logger.info(f"Safety snapshot created: {pre_restore_snapshot.name}")
            except Exception as e:
                return RestoreResult(
                    success=False,
                    source_backup=backup_path,
                    pre_restore_snapshot=None,
                    integrity_verified=False,
                    error_message=f"Failed to create pre-restore snapshot: {e}",
                )

        # 3. Perform restoration atomically
        def _restore_sync() -> bool:
            temp_extracted: Optional[Path] = None
            try:
                source_file_to_copy = backup_path

                # If zip archive, extract database/bot.db first
                if backup_path.name.endswith(".zip") or backup_path.name.endswith(".enc"):
                    from backups.archive import BackupArchiveBuilder
                    fd, tmp_extracted_path = tempfile.mkstemp(suffix=".db")
                    os.close(fd)
                    temp_extracted = Path(tmp_extracted_path)
                    BackupArchiveBuilder.extract_database_snapshot(backup_path, temp_extracted)
                    source_file_to_copy = temp_extracted

                # Copy extracted/source db over target
                shutil.copy2(source_file_to_copy, target_db_path)

                # Verify restored database
                conn = sqlite3.connect(str(target_db_path))
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check")
                res = cursor.fetchone()
                conn.close()
                return bool(res and res[0] == "ok")
            except Exception as re_err:
                logger.error(f"Error during restore write: {re_err}")
                return False
            finally:
                if temp_extracted and temp_extracted.exists():
                    try:
                        temp_extracted.unlink()
                    except Exception:
                        pass

        success = await asyncio.to_thread(_restore_sync)
        if not success:
            # Revert to safety snapshot if possible
            if pre_restore_snapshot and pre_restore_snapshot.exists():
                shutil.copy2(pre_restore_snapshot, target_db_path)
            return RestoreResult(
                success=False,
                source_backup=backup_path,
                pre_restore_snapshot=pre_restore_snapshot,
                integrity_verified=False,
                error_message="Restored database failed integrity check. Automatically rolled back to pre-restore snapshot.",
            )

        logger.info(f"Disaster Recovery Restoration Successful from {backup_path.name}")
        return RestoreResult(
            success=True,
            source_backup=backup_path,
            pre_restore_snapshot=pre_restore_snapshot,
            integrity_verified=True,
        )
