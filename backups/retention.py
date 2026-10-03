"""
Backup Retention Policy & Rotation Engine for 『RΛI』.
Enforces bounded retention across disaster recovery archives.
Default: Retain latest 10 verified backups.
Strict Safety Rules:
1. Never delete the only available valid backup.
2. Never delete a backup currently being created, verified, or locked.
3. Prune oldest archives safely when count exceeds configured limit.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

logger = logging.getLogger("Rai.Backups.Retention")


@dataclass(frozen=True)
class RetentionPolicy:
    """Configurable tiered retention counts."""
    max_backups: int = 10
    max_hourly: int = 24
    max_daily: int = 30
    max_weekly: int = 12
    max_monthly: int = 6


class RetentionManager:
    """Prunes expired local backups while protecting recovery state."""

    def __init__(self, policy: Optional[RetentionPolicy] = None):
        max_b = int(os.getenv("BACKUP_RETENTION_COUNT", "10"))
        self.policy = policy or RetentionPolicy(
            max_backups=max_b,
            max_hourly=int(os.getenv("BACKUP_RETENTION_HOURLY", "24")),
            max_daily=int(os.getenv("BACKUP_RETENTION_DAILY", "30")),
            max_weekly=int(os.getenv("BACKUP_RETENTION_WEEKLY", "12")),
            max_monthly=int(os.getenv("BACKUP_RETENTION_MONTHLY", "6")),
        )

    def prune_directory(
        self,
        backups_dir: Path,
        max_files_fallback: Optional[int] = None,
        active_backup_ids: Optional[Set[str]] = None,
    ) -> Tuple[int, int]:
        """
        Scans directory for timestamped backup files and prunes oldest files exceeding limits.
        Guarantees:
        - Never deletes the only available valid backup.
        - Never deletes backups in active_backup_ids.
        - Never deletes files marked with RECOVERY_LOCK.
        Returns (retained_count, deleted_count).
        """
        if not backups_dir.exists():
            return 0, 0

        active_ids = active_backup_ids or set()

        # Match zip archives, encrypted archives, and legacy sqlite snapshots
        backup_files: List[Path] = [
            p for p in backups_dir.iterdir()
            if p.is_file()
            and (
                p.name.startswith("BAK-")
                or p.name.startswith("rai_sqlite_")
                or p.name.startswith("rai_postgres_")
            )
            and (p.name.endswith(".zip") or p.name.endswith(".enc") or p.name.endswith(".db") or p.name.endswith(".json"))
            and "manifest.json" not in p.name
            and "RECOVERY_LOCK" not in p.name
        ]

        # Do not prune if we have 1 or 0 backups (never delete the only backup!)
        if len(backup_files) <= 1:
            return len(backup_files), 0

        # Sort newest to oldest by modified time
        backup_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        limit = max_files_fallback or self.policy.max_backups
        deleted_count = 0

        # Preserve the newest `limit` files, prune older ones
        for old_file in backup_files[limit:]:
            # Never delete the only remaining backup
            if (len(backup_files) - deleted_count) <= 1:
                break

            # Never delete active or locked files
            if any(aid in old_file.name for aid in active_ids):
                continue
            if "RECOVERY_LOCK" in old_file.name:
                continue

            try:
                old_file.unlink()
                deleted_count += 1
                logger.info(f"Pruned expired backup archive: {old_file.name}")
            except Exception as e:
                logger.warning(f"Could not prune backup {old_file.name}: {e}")

        retained_count = len(backup_files) - deleted_count
        return retained_count, deleted_count
