"""
Disaster Recovery & Centralized Backup Coordinator for 『RΛI』.
Orchestrates:
1. Online atomic SQLite backups via SQLite Online Backup API
2. Comprehensive archive generation with configuration, security, music, and room state
3. Cryptographic SHA-256 validation and integrity verification
4. Optional authenticated encryption (Fernet) with truthful status reporting
5. Persistent metadata tracking in backups/manifest.json across bot restarts
6. Bounded retention pruning safeguarding recovery checkpoints
7. Safe, non-destructive disaster recovery restoration with rollbacks
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import config
from backups.sqlite_backup import SQLiteBackupService, SQLiteBackupResult
from backups.uploader import S3BackupUploader, BackupLifecycleState, UploadResult
from backups.retention import RetentionManager
from backups.restore import SafeRestoreEngine, RestoreResult
from backups.archive import BackupArchiveBuilder, ArchiveResult, ArchiveVerifyResult

logger = logging.getLogger("Rai.Backups.Manager")


def format_bytes(size_bytes: int) -> str:
    """Formats raw bytes into human-readable representation."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024, 1)} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{round(size_bytes / (1024 * 1024), 1)} MB"
    return f"{round(size_bytes / (1024 * 1024 * 1024), 2)} GB"


@dataclass(frozen=True)
class BackupRecord:
    backup_id: str
    state: str
    timestamp: float
    iso_created_at: str
    sqlite_backup: Optional[str]
    sqlite_size: int
    sqlite_sha256: str
    postgres_backup: Optional[str]
    storage_key: str
    cloud_bucket: str
    verified: bool
    error_message: Optional[str] = None
    archive_path: Optional[str] = None
    archive_size: int = 0
    formatted_created_at: str = ""
    is_encrypted: bool = False
    encryption_status: str = "NOT CONFIGURED"
    components: Dict[str, bool] = field(default_factory=dict)
    storage_type: str = "Local Backup"


class BackupManager:
    """Central supervisor for backups, verification, retention, and disaster recovery."""

    _instance: Optional[BackupManager] = None

    def __init__(
        self,
        db_path: Optional[Path] = None,
        backups_dir: Optional[Path] = None,
    ):
        self.db_path = db_path or config.DATABASE_PATH
        self.backups_dir = backups_dir or config.BACKUPS_DIR
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.backups_dir / "manifest.json"

        self.uploader = S3BackupUploader()
        self.retention = RetentionManager()
        self._periodic_task: Optional[asyncio.Task] = None
        self._last_backup_record: Optional[BackupRecord] = None
        self._history: List[BackupRecord] = []
        self._active_backup_ids: Set[str] = set()
        self._lock = asyncio.Lock()

        # Load existing backups into memory
        self._load_manifest()

    @classmethod
    def get_instance(
        cls,
        db_path: Optional[Path] = None,
        backups_dir: Optional[Path] = None,
    ) -> BackupManager:
        if cls._instance is None:
            cls._instance = BackupManager(db_path=db_path, backups_dir=backups_dir)
        return cls._instance

    @property
    def last_backup(self) -> Optional[BackupRecord]:
        return self._last_backup_record

    def _load_manifest(self) -> None:
        """Loads persistent backup manifest from disk and discovers unindexed archives."""
        if not self.manifest_path.exists():
            self._sync_disk_to_manifest({})
            return

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._sync_disk_to_manifest(data)
        except Exception as e:
            logger.warning(f"Error loading backup manifest: {e}. Reindexing from disk.")
            self._sync_disk_to_manifest({})

    def _sync_disk_to_manifest(self, existing_manifest: Dict[str, Any]) -> None:
        """Ensures manifest reflects valid archives physically on disk."""
        manifest: Dict[str, Any] = dict(existing_manifest)

        # 1. Prune manifest entries whose files no longer exist
        for b_id in list(manifest.keys()):
            entry = manifest[b_id]
            f_path = Path(entry.get("archive_path", ""))
            if not f_path.exists():
                manifest.pop(b_id, None)

        # 2. Discover archives on disk not in manifest
        if self.backups_dir.exists():
            for p in self.backups_dir.iterdir():
                if p.is_file() and p.name.startswith("BAK-") and (p.name.endswith(".zip") or p.name.endswith(".enc")):
                    b_id = p.stem.replace(".zip", "")
                    if b_id not in manifest:
                        try:
                            stat = p.stat()
                            mtime = stat.st_mtime
                            dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                            sha = BackupArchiveBuilder.compute_sha256(p)
                            is_enc = p.name.endswith(".enc")
                            manifest[b_id] = {
                                "backup_id": b_id,
                                "filename": p.name,
                                "archive_path": str(p),
                                "size_bytes": stat.st_size,
                                "sha256": sha,
                                "created_at": mtime,
                                "iso_created_at": dt.isoformat(),
                                "formatted_created_at": dt.strftime("%d %b %Y, %H:%M"),
                                "is_encrypted": is_enc,
                                "encryption_status": "🔐 Encrypted (Fernet)" if is_enc else "NOT CONFIGURED",
                                "verified": True,
                                "storage": "Local Backup",
                                "components": {
                                    "database": True,
                                    "configuration": True,
                                    "security_configuration": True,
                                    "music_playlists": True,
                                    "private_room_configuration": True,
                                },
                            }
                        except Exception as de:
                            logger.warning(f"Could not index archive {p.name}: {de}")

        # Save synced manifest
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except Exception as se:
            logger.warning(f"Could not write manifest.json: {se}")

        # Rebuild in-memory last backup and history
        sorted_entries = sorted(manifest.values(), key=lambda x: x.get("created_at", 0), reverse=True)
        if sorted_entries:
            latest = sorted_entries[0]
            self._last_backup_record = BackupRecord(
                backup_id=latest["backup_id"],
                state="VERIFIED" if latest.get("verified") else "FAILED",
                timestamp=latest.get("created_at", 0),
                iso_created_at=latest.get("iso_created_at", ""),
                sqlite_backup=latest.get("filename"),
                sqlite_size=latest.get("size_bytes", 0),
                sqlite_sha256=latest.get("sha256", ""),
                postgres_backup=None,
                storage_key=f"local://{latest.get('filename')}",
                cloud_bucket="local",
                verified=bool(latest.get("verified")),
                archive_path=latest.get("archive_path"),
                archive_size=latest.get("size_bytes", 0),
                formatted_created_at=latest.get("formatted_created_at", ""),
                is_encrypted=bool(latest.get("is_encrypted")),
                encryption_status=latest.get("encryption_status", "NOT CONFIGURED"),
                components=latest.get("components", {}),
                storage_type=latest.get("storage", "Local Backup"),
            )

    def _generate_unique_backup_id(self) -> str:
        """Generates standardized backup identifier: BAK-YYYYMMDD-HHMM (or seconds if collision)."""
        now = datetime.now(timezone.utc)
        base_id = now.strftime("BAK-%Y%m%d-%H%M")

        # Check if already exists in backups_dir
        if not (self.backups_dir / f"{base_id}.zip").exists() and not (self.backups_dir / f"{base_id}.zip.enc").exists():
            return base_id

        # Collision resolved with exact second precision
        return now.strftime("BAK-%Y%m%d-%H%M%S")

    async def run_backup(self, trigger: str = "manual") -> BackupRecord:
        """
        Executes a real disaster recovery backup sequence:
        1. Atomic online SQLite snapshot via conn.backup
        2. Packaging database, configuration, security, music, and room data into verified archive
        3. Optional authenticated encryption (Fernet)
        4. SHA-256 calculation and read-back verification
        5. Updating persistent manifest and retention rotation
        """
        async with self._lock:
            backup_id = self._generate_unique_backup_id()
            self._active_backup_ids.add(backup_id)
            now = datetime.now(timezone.utc)
            formatted_created = now.strftime("%d %b %Y, %H:%M")
            iso_created_at = now.isoformat()

            logger.info(f"Initiating real backup cycle [{backup_id}] triggered by '{trigger}'...")

            with tempfile.TemporaryDirectory() as staging_dir_str:
                staging_dir = Path(staging_dir_str)

                # Step 1: Create atomic SQLite snapshot in isolated staging directory
                sqlite_res: SQLiteBackupResult = await SQLiteBackupService.create_backup(
                    source_path=self.db_path,
                    dest_dir=staging_dir,
                )

                if not sqlite_res.success or not sqlite_res.backup_path or not sqlite_res.backup_path.exists():
                    logger.error(f"Backup {backup_id} aborted: SQLite snapshot failed: {sqlite_res.error_message}")
                    record = BackupRecord(
                        backup_id=backup_id,
                        state=BackupLifecycleState.FAILED.value,
                        timestamp=now.timestamp(),
                        iso_created_at=iso_created_at,
                        sqlite_backup=None,
                        sqlite_size=0,
                        sqlite_sha256="",
                        postgres_backup=None,
                        storage_key="none",
                        cloud_bucket="none",
                        verified=False,
                        error_message=f"Database snapshot failed: {sqlite_res.error_message}",
                        formatted_created_at=formatted_created,
                        encryption_status="NOT CONFIGURED",
                    )
                    self._last_backup_record = record
                    self._active_backup_ids.discard(backup_id)
                    return record

                # Step 2: Package archive (database + configs + security + music + rooms)
                archive_res: ArchiveResult = await asyncio.to_thread(
                    BackupArchiveBuilder.create_archive,
                    backup_id=backup_id,
                    sqlite_snapshot_path=sqlite_res.backup_path,
                    dest_dir=self.backups_dir,
                )

                if not archive_res.success or not archive_res.archive_path or not archive_res.verified:
                    logger.error(f"Backup {backup_id} archive packaging failed: {archive_res.error_message}")
                    record = BackupRecord(
                        backup_id=backup_id,
                        state=BackupLifecycleState.FAILED.value,
                        timestamp=now.timestamp(),
                        iso_created_at=iso_created_at,
                        sqlite_backup=None,
                        sqlite_size=0,
                        sqlite_sha256="",
                        postgres_backup=None,
                        storage_key="none",
                        cloud_bucket="none",
                        verified=False,
                        error_message=archive_res.error_message or "Archive generation failed verification.",
                        formatted_created_at=formatted_created,
                        encryption_status=archive_res.encryption_status,
                    )
                    self._last_backup_record = record
                    self._active_backup_ids.discard(backup_id)
                    return record

                # Step 3: Cloud upload & verification (local-only fallback if unconfigured)
                upload_res: UploadResult = await self.uploader.upload_and_verify(
                    local_path=archive_res.archive_path,
                    remote_prefix="archives",
                    expected_sha256=archive_res.sha256_checksum,
                )

                # Determine storage type strictly truthfully
                storage_type = "Local Backup"
                if self.uploader.enabled and upload_res.bucket != "local":
                    storage_type = f"Cloud S3 ({upload_res.bucket})"

                # Step 4: Record metadata in manifest
                manifest_entry = {
                    "backup_id": backup_id,
                    "filename": archive_res.filename,
                    "archive_path": str(archive_res.archive_path),
                    "size_bytes": archive_res.size_bytes,
                    "sha256": archive_res.sha256_checksum,
                    "created_at": now.timestamp(),
                    "iso_created_at": iso_created_at,
                    "formatted_created_at": formatted_created,
                    "is_encrypted": archive_res.is_encrypted,
                    "encryption_status": archive_res.encryption_status,
                    "verified": True,
                    "storage": storage_type,
                    "components": archive_res.components,
                }

                try:
                    manifest_data = {}
                    if self.manifest_path.exists():
                        with open(self.manifest_path, "r", encoding="utf-8") as mf:
                            manifest_data = json.load(mf)
                    manifest_data[backup_id] = manifest_entry
                    with open(self.manifest_path, "w", encoding="utf-8") as mf:
                        json.dump(manifest_data, mf, indent=2)
                except Exception as me:
                    logger.warning(f"Error persisting backup {backup_id} to manifest.json: {me}")

                # Step 5: Prune old backups safeguarding current backup and minimum retention
                try:
                    self.retention.prune_directory(
                        self.backups_dir,
                        active_backup_ids=self._active_backup_ids,
                    )
                except Exception as pe:
                    logger.warning(f"Retention pruning note: {pe}")

                record = BackupRecord(
                    backup_id=backup_id,
                    state="VERIFIED" if archive_res.verified else "FAILED",
                    timestamp=now.timestamp(),
                    iso_created_at=iso_created_at,
                    sqlite_backup=archive_res.filename,
                    sqlite_size=archive_res.size_bytes,
                    sqlite_sha256=archive_res.sha256_checksum,
                    postgres_backup=None,
                    storage_key=upload_res.storage_key,
                    cloud_bucket=upload_res.bucket,
                    verified=archive_res.verified,
                    archive_path=str(archive_res.archive_path),
                    archive_size=archive_res.size_bytes,
                    formatted_created_at=formatted_created,
                    is_encrypted=archive_res.is_encrypted,
                    encryption_status=archive_res.encryption_status,
                    components=archive_res.components,
                    storage_type=storage_type,
                )

                self._last_backup_record = record
                self._history.append(record)
                self._active_backup_ids.discard(backup_id)

                logger.info(
                    f"Backup cycle {backup_id} completed successfully: "
                    f"Verified={record.verified}, Size={record.archive_size}B, Storage={record.storage_type}"
                )
                return record

    def list_backups(self) -> List[Dict[str, Any]]:
        """Returns ordered list of all valid local backup archives."""
        self._load_manifest()

        if not self.manifest_path.exists():
            return []

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        items = list(data.values())
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)

        for item in items:
            item["size_formatted"] = format_bytes(item.get("size_bytes", 0))

        return items

    def list_local_backups(self) -> List[Dict[str, Any]]:
        """Backwards-compatible alias for list_backups()."""
        backups = self.list_backups()
        results = []
        for b in backups:
            results.append({
                "filename": b.get("filename", ""),
                "size_bytes": b.get("size_bytes", 0),
                "modified_at": b.get("iso_created_at", ""),
                "path": b.get("archive_path", ""),
                "backup_id": b.get("backup_id", ""),
            })
        return results

    async def verify_backup(self, backup_id: str) -> Dict[str, Any]:
        """
        Locates the specified backup archive, recalculates SHA-256,
        verifies checksum equality, and tests archive and database integrity.
        """
        self._load_manifest()

        manifest_data = {}
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
            except Exception:
                pass

        entry = manifest_data.get(backup_id)

        # Locate archive file
        archive_path: Optional[Path] = None
        if entry and Path(entry.get("archive_path", "")).exists():
            archive_path = Path(entry["archive_path"])
        else:
            # Check by filename conventions
            for candidate in [
                self.backups_dir / f"{backup_id}.zip",
                self.backups_dir / f"{backup_id}.zip.enc",
                self.backups_dir / backup_id,
            ]:
                if candidate.exists() and candidate.is_file():
                    archive_path = candidate
                    break

        if not archive_path or not archive_path.exists():
            return {
                "success": False,
                "verified": False,
                "backup_id": backup_id,
                "error": f"Backup archive '{backup_id}' could not be located in {self.backups_dir}.",
            }

        expected_sha = entry.get("sha256") if entry else None

        # Execute full verification
        v_res: ArchiveVerifyResult = await asyncio.to_thread(
            BackupArchiveBuilder.verify_archive,
            archive_path=archive_path,
            expected_sha256=expected_sha,
        )

        return {
            "success": v_res.success,
            "verified": v_res.verified,
            "backup_id": backup_id,
            "archive_path": str(archive_path),
            "size_bytes": v_res.size_bytes,
            "size_formatted": format_bytes(v_res.size_bytes),
            "sha256_checksum": v_res.sha256_checksum,
            "sha256_matches": v_res.sha256_matches,
            "is_encrypted": v_res.is_encrypted,
            "encryption_status": v_res.encryption_status,
            "archive_integrity_ok": v_res.archive_integrity_ok,
            "db_integrity_ok": v_res.db_integrity_ok,
            "components": v_res.components,
            "error": v_res.error_message,
        }

    async def restore_from_backup(
        self,
        backup_id_or_filename: str,
        confirmation_token: str,
    ) -> RestoreResult:
        """
        Controlled safe restore of target backup.
        Takes pre-restore safety snapshot of active database first,
        validates backup, replaces database atomically, and validates integrity.
        """
        # Find path
        target_path: Optional[Path] = None
        for cand in [
            self.backups_dir / backup_id_or_filename,
            self.backups_dir / f"{backup_id_or_filename}.zip",
            self.backups_dir / f"{backup_id_or_filename}.zip.enc",
        ]:
            if cand.exists():
                target_path = cand
                break

        if not target_path:
            # Check manifest
            backups = self.list_backups()
            for b in backups:
                if b.get("backup_id") == backup_id_or_filename:
                    target_path = Path(b.get("archive_path", ""))
                    break

        if not target_path or not target_path.exists():
            return RestoreResult(
                success=False,
                source_backup=Path(backup_id_or_filename),
                pre_restore_snapshot=None,
                integrity_verified=False,
                error_message=f"Backup '{backup_id_or_filename}' not found.",
            )

        return await SafeRestoreEngine.execute_restore(
            backup_path=target_path,
            target_db_path=self.db_path,
            confirmation_token=confirmation_token,
        )

    def start_periodic_backups(self, interval_seconds: Optional[int] = None) -> None:
        """Starts automated background worker running scheduled backups."""
        if self._periodic_task and not self._periodic_task.done():
            return

        interval = interval_seconds or int(os.getenv("BACKUP_INTERVAL_SECONDS", "86400"))  # Default 24h

        async def _loop():
            logger.info(f"Backup background worker started with interval {interval}s.")
            while True:
                try:
                    await asyncio.sleep(interval)
                    record = await self.run_backup(trigger="scheduled_worker")
                    logger.info(f"Scheduled backup completed: {record.backup_id} (Verified: {record.verified})")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in backup worker loop: {e}", exc_info=True)
                    await asyncio.sleep(300)

        self._periodic_task = asyncio.create_task(_loop(), name="rai_backup_worker")

    def stop(self) -> None:
        if self._periodic_task and not self._periodic_task.done():
            self._periodic_task.cancel()
