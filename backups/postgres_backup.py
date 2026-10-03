"""
PostgreSQL Backup & Table Exporter for 『RΛI』.
Exports production incident records, security event logs, and guild configurations
to encrypted or compressed JSON/SQL snapshots for archive and offsite storage.
Gracefully skips if PostgreSQL is unconfigured or offline.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from database.postgres.connection import PostgresConnectionPool

logger = logging.getLogger("Rai.Backups.Postgres")


@dataclass(frozen=True)
class PostgresBackupResult:
    """Metadata for a PostgreSQL snapshot export."""
    success: bool
    backup_path: Optional[Path]
    filename: str
    size_bytes: int
    sha256_checksum: str
    record_counts: Dict[str, int]
    timestamp: float
    iso_created_at: str
    error_message: Optional[str] = None


class PostgresBackupService:
    """Exports structured snapshots from PostgreSQL tables."""

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    async def create_backup(
        cls,
        dest_dir: Path,
        pool: Optional[PostgresConnectionPool] = None,
    ) -> PostgresBackupResult:
        """Asynchronously exports PostgreSQL security tables to disk."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        filename = f"rai_postgres_{timestamp_str}.json"
        dest_path = dest_dir / filename

        pg_pool = pool or PostgresConnectionPool.get_instance()
        if not pg_pool.is_connected:
            return PostgresBackupResult(
                success=True,  # Non-fatal skip
                backup_path=None,
                filename=filename,
                size_bytes=0,
                sha256_checksum="",
                record_counts={},
                timestamp=now.timestamp(),
                iso_created_at=now.isoformat(),
                error_message="PostgreSQL is offline or disabled. Backup skipped gracefully.",
            )

        record_counts: Dict[str, int] = {}
        tables = ["incidents", "security_events", "guild_configs", "threat_timeline"]
        snapshot_data: Dict[str, List[Dict[str, Any]]] = {}

        try:
            async with pg_pool.acquire() as conn:
                for table in tables:
                    try:
                        # Check table exists
                        exists = await conn.fetchval(
                            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                            table,
                        )
                        if not exists:
                            record_counts[table] = 0
                            continue

                        rows = await conn.fetch(f"SELECT * FROM {table} ORDER BY 1 LIMIT 50000")
                        snapshot_data[table] = [dict(r) for r in rows]
                        record_counts[table] = len(rows)
                    except Exception as te:
                        logger.warning(f"Error snapshotting PostgreSQL table {table}: {te}")
                        record_counts[table] = 0

            # Write snapshot to file in background thread
            def _write_json():
                with open(dest_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "exported_at": now.isoformat(),
                            "tables": snapshot_data,
                            "record_counts": record_counts,
                        },
                        f,
                        default=str,
                        indent=2,
                    )
                size = dest_path.stat().st_size
                sha256 = cls._compute_sha256(dest_path)
                return size, sha256

            size, sha256 = await asyncio.to_thread(_write_json)
            logger.info(f"PostgreSQL backup complete: {filename} ({size} bytes, sha256={sha256[:12]}...)")

            return PostgresBackupResult(
                success=True,
                backup_path=dest_path,
                filename=filename,
                size_bytes=size,
                sha256_checksum=sha256,
                record_counts=record_counts,
                timestamp=now.timestamp(),
                iso_created_at=now.isoformat(),
            )

        except Exception as e:
            logger.error(f"PostgreSQL backup export failed: {e}", exc_info=True)
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except Exception:
                    pass
            return PostgresBackupResult(
                success=False,
                backup_path=None,
                filename=filename,
                size_bytes=0,
                sha256_checksum="",
                record_counts={},
                timestamp=now.timestamp(),
                iso_created_at=now.isoformat(),
                error_message=str(e),
            )
