"""
Archive Packaging, Verification, and Authenticated Encryption Engine for 『RΛI』.
Handles:
1. Multi-component snapshot archiving (Database, Configuration, Security, Music, Private-Rooms, Metadata)
2. Cryptographic SHA-256 generation and re-verification
3. Optional Authenticated Encryption (Fernet AES-128-CBC + HMAC-SHA256)
4. Truthful encryption state reporting ("NOT CONFIGURED" when no key provided)
5. Zip archive integrity validation and SQLite PRAGMA verification
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import sqlite3
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Rai.Backups.Archive")


def get_fernet_cipher(key_str: str):
    """Initializes or derives a Fernet cipher from key string or passphrase."""
    from cryptography.fernet import Fernet
    try:
        raw_bytes = key_str.strip().encode("utf-8")
        return Fernet(raw_bytes)
    except Exception:
        derived = base64.urlsafe_b64encode(hashlib.sha256(key_str.strip().encode("utf-8")).digest())
        return Fernet(derived)


@dataclass(frozen=True)
class ArchiveResult:
    """Outcome of an archive generation and verification operation."""
    success: bool
    backup_id: str
    archive_path: Optional[Path]
    filename: str
    size_bytes: int
    sha256_checksum: str
    is_encrypted: bool
    encryption_status: str
    verified: bool
    components: Dict[str, bool]
    formatted_created_at: str
    iso_created_at: str
    timestamp: float
    error_message: Optional[str] = None


@dataclass(frozen=True)
class ArchiveVerifyResult:
    """Outcome of an on-demand archive verification."""
    success: bool
    backup_id: str
    archive_path: Path
    size_bytes: int
    sha256_checksum: str
    sha256_matches: bool
    is_encrypted: bool
    encryption_status: str
    archive_integrity_ok: bool
    db_integrity_ok: bool
    components: Dict[str, bool]
    verified: bool = False
    error_message: Optional[str] = None


class BackupArchiveBuilder:
    """Builds, packages, encrypts, and validates disaster recovery archives."""

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        """Calculates cryptographic SHA-256 checksum of target file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def extract_persistent_data(cls, snapshot_db_path: Path) -> Dict[str, Any]:
        """
        Extracts structured configuration, security, music, and private-room
        settings from the verified SQLite snapshot.
        """
        data: Dict[str, Any] = {
            "schema_version": None,
            "configuration": {},
            "security": {},
            "music": {},
            "rooms": {},
            "table_counts": {},
        }

        try:
            conn = sqlite3.connect(f"file:{snapshot_db_path}?mode=ro", uri=True, timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Fetch available table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row["name"] for row in cursor.fetchall()]

            # 2. Table row counts
            for t in tables:
                if t.startswith("sqlite_"):
                    continue
                try:
                    cursor.execute(f"SELECT COUNT(*) as cnt FROM {t}")
                    cnt = cursor.fetchone()["cnt"]
                    data["table_counts"][t] = cnt
                except Exception:
                    data["table_counts"][t] = 0

            # 3. Schema version
            if "schema_version" in tables:
                try:
                    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
                    row = cursor.fetchone()
                    if row:
                        data["schema_version"] = row["version"]
                except Exception:
                    pass

            # 4. General configurations (sanitize secrets)
            config_tables = ["guild_config", "bot_config", "logging_config", "welcome_config", "automod_config"]
            for ct in config_tables:
                if ct in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {ct} LIMIT 500")
                        rows = [dict(r) for r in cursor.fetchall()]
                        # Redact potential secrets
                        for r in rows:
                            for k in list(r.keys()):
                                if any(s in k.lower() for s in ["token", "secret", "password", "api_key"]):
                                    r[k] = "[REDACTED]"
                        data["configuration"][ct] = rows
                    except Exception as e:
                        logger.warning(f"Error extracting config table {ct}: {e}")

            # 5. Security configuration
            sec_tables = [
                "security_config", "security_whitelist", "security_incidents",
                "raid_config", "voiceguard_config", "mention_spam_config"
            ]
            for st in sec_tables:
                if st in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {st} LIMIT 1000")
                        data["security"][st] = [dict(r) for r in cursor.fetchall()]
                    except Exception as e:
                        logger.warning(f"Error extracting security table {st}: {e}")

            # 6. Music & Playlists
            music_tables = ["music_config", "music_playlists"]
            for mt in music_tables:
                if mt in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {mt} LIMIT 1000")
                        data["music"][mt] = [dict(r) for r in cursor.fetchall()]
                    except Exception as e:
                        logger.warning(f"Error extracting music table {mt}: {e}")

            # 7. Private room configurations
            room_tables = ["temp_voice_config", "temp_voice_channels", "hidden_voice_config", "hidden_voice_rooms"]
            for rt in room_tables:
                if rt in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {rt} LIMIT 1000")
                        data["rooms"][rt] = [dict(r) for r in cursor.fetchall()]
                    except Exception as e:
                        logger.warning(f"Error extracting room table {rt}: {e}")

            conn.close()
        except Exception as e:
            logger.error(f"Error extracting persistent data from snapshot: {e}", exc_info=True)

        return data

    @classmethod
    def create_archive(
        cls,
        backup_id: str,
        sqlite_snapshot_path: Path,
        dest_dir: Path,
        encryption_key: Optional[str] = None,
    ) -> ArchiveResult:
        """
        Creates a consistent, verified archive package containing database, configurations,
        security policies, music playlists, and room data.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        iso_created_at = now.isoformat()
        formatted_created = now.strftime("%d %b %Y, %H:%M")

        # Check if encryption key is configured
        raw_key = (encryption_key or os.getenv("BACKUP_ENCRYPTION_KEY", "")).strip()
        is_encrypted = bool(raw_key)
        encryption_status = "🔐 Encrypted (Fernet)" if is_encrypted else "NOT CONFIGURED"

        # Determine output filename
        ext = ".zip.enc" if is_encrypted else ".zip"
        archive_filename = f"{backup_id}{ext}"
        archive_path = dest_dir / archive_filename

        try:
            # 1. Validate SQLite snapshot existence
            if not sqlite_snapshot_path.exists() or sqlite_snapshot_path.stat().st_size == 0:
                return ArchiveResult(
                    success=False,
                    backup_id=backup_id,
                    archive_path=None,
                    filename=archive_filename,
                    size_bytes=0,
                    sha256_checksum="",
                    is_encrypted=is_encrypted,
                    encryption_status=encryption_status,
                    verified=False,
                    components={},
                    formatted_created_at=formatted_created,
                    iso_created_at=iso_created_at,
                    timestamp=now.timestamp(),
                    error_message=f"SQLite snapshot missing or zero bytes: {sqlite_snapshot_path}",
                )

            # 2. Extract persistent data summaries
            extracted = cls.extract_persistent_data(sqlite_snapshot_path)

            components = {
                "database": True,
                "configuration": bool(extracted.get("configuration")),
                "security_configuration": bool(extracted.get("security")),
                "music_playlists": bool(extracted.get("music")),
                "private_room_configuration": bool(extracted.get("rooms")),
            }

            manifest_data = {
                "backup_id": backup_id,
                "version": "1.0",
                "created_at": now.timestamp(),
                "iso_created_at": iso_created_at,
                "formatted_created_at": formatted_created,
                "schema_version": extracted.get("schema_version"),
                "is_encrypted": is_encrypted,
                "encryption_status": encryption_status,
                "storage": "Local Backup",
                "components": components,
                "table_counts": extracted.get("table_counts", {}),
            }

            # 3. Create zip archive in memory / temp buffer
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                # Add database snapshot
                zf.write(sqlite_snapshot_path, arcname="database/bot.db")
                # Add manifest metadata
                zf.writestr("metadata.json", json.dumps(manifest_data, indent=2, default=str))
                # Add configs
                zf.writestr("config/configuration.json", json.dumps(extracted.get("configuration", {}), indent=2, default=str))
                # Add security
                zf.writestr("security/security_config.json", json.dumps(extracted.get("security", {}), indent=2, default=str))
                # Add music
                zf.writestr("music/playlists.json", json.dumps(extracted.get("music", {}), indent=2, default=str))
                # Add rooms
                zf.writestr("rooms/private_rooms.json", json.dumps(extracted.get("rooms", {}), indent=2, default=str))

            zip_bytes = zip_buffer.getvalue()

            # 4. Optional Authenticated Encryption
            final_bytes: bytes
            if is_encrypted:
                cipher = get_fernet_cipher(raw_key)
                final_bytes = cipher.encrypt(zip_bytes)
            else:
                final_bytes = zip_bytes

            # 5. Write to destination file
            with open(archive_path, "wb") as f:
                f.write(final_bytes)

            size_bytes = archive_path.stat().st_size

            # 6. Cryptographic SHA-256 generation
            sha256 = cls.compute_sha256(archive_path)

            # 7. Verification: re-read file from disk and verify SHA-256 + archive integrity
            verify_res = cls.verify_archive(
                archive_path=archive_path,
                expected_sha256=sha256,
                encryption_key=raw_key if is_encrypted else None,
            )

            if not verify_res.verified:
                logger.error(f"Archive {archive_filename} verification failed: {verify_res.error_message}")
                return ArchiveResult(
                    success=False,
                    backup_id=backup_id,
                    archive_path=archive_path,
                    filename=archive_filename,
                    size_bytes=size_bytes,
                    sha256_checksum=sha256,
                    is_encrypted=is_encrypted,
                    encryption_status=encryption_status,
                    verified=False,
                    components=components,
                    formatted_created_at=formatted_created,
                    iso_created_at=iso_created_at,
                    timestamp=now.timestamp(),
                    error_message=f"Archive verification failed: {verify_res.error_message}",
                )

            logger.info(
                f"Disaster Recovery Archive {backup_id} created successfully: "
                f"{archive_filename} ({size_bytes} bytes, sha256={sha256[:12]}..., encrypted={is_encrypted})"
            )

            return ArchiveResult(
                success=True,
                backup_id=backup_id,
                archive_path=archive_path,
                filename=archive_filename,
                size_bytes=size_bytes,
                sha256_checksum=sha256,
                is_encrypted=is_encrypted,
                encryption_status=encryption_status,
                verified=True,
                components=components,
                formatted_created_at=formatted_created,
                iso_created_at=iso_created_at,
                timestamp=now.timestamp(),
            )

        except Exception as e:
            logger.error(f"Failed to create disaster recovery archive: {e}", exc_info=True)
            if archive_path.exists():
                try:
                    archive_path.unlink()
                except Exception:
                    pass
            return ArchiveResult(
                success=False,
                backup_id=backup_id,
                archive_path=None,
                filename=archive_filename,
                size_bytes=0,
                sha256_checksum="",
                is_encrypted=is_encrypted,
                encryption_status=encryption_status,
                verified=False,
                components={},
                formatted_created_at=formatted_created,
                iso_created_at=iso_created_at,
                timestamp=now.timestamp(),
                error_message=str(e),
            )

    @classmethod
    def verify_archive(
        cls,
        archive_path: Path,
        expected_sha256: Optional[str] = None,
        encryption_key: Optional[str] = None,
    ) -> ArchiveVerifyResult:
        """
        Validates archive existence, re-reads file to recompute SHA-256,
        verifies decryption if encrypted, tests zip integrity, and checks internal SQLite database.
        """
        if not archive_path.exists() or archive_path.stat().st_size == 0:
            return ArchiveVerifyResult(
                success=False,
                backup_id=archive_path.stem.replace(".zip", ""),
                archive_path=archive_path,
                size_bytes=0,
                sha256_checksum="",
                sha256_matches=False,
                is_encrypted=False,
                encryption_status="NOT CONFIGURED",
                archive_integrity_ok=False,
                db_integrity_ok=False,
                components={},
                error_message=f"Archive file does not exist or is empty: {archive_path}",
            )

        size_bytes = archive_path.stat().st_size
        actual_sha = cls.compute_sha256(archive_path)

        sha_matches = True
        if expected_sha256:
            sha_matches = actual_sha.lower() == expected_sha256.lower()
            if not sha_matches:
                return ArchiveVerifyResult(
                    success=False,
                    backup_id=archive_path.stem.replace(".zip", ""),
                    archive_path=archive_path,
                    size_bytes=size_bytes,
                    sha256_checksum=actual_sha,
                    sha256_matches=False,
                    is_encrypted=archive_path.name.endswith(".enc"),
                    encryption_status="🔐 Encrypted (Fernet)" if archive_path.name.endswith(".enc") else "NOT CONFIGURED",
                    archive_integrity_ok=False,
                    db_integrity_ok=False,
                    components={},
                    error_message=f"SHA-256 checksum mismatch: expected {expected_sha256}, got {actual_sha}",
                )

        is_encrypted = archive_path.name.endswith(".enc")
        encryption_status = "🔐 Encrypted (Fernet)" if is_encrypted else "NOT CONFIGURED"
        raw_key = (encryption_key or os.getenv("BACKUP_ENCRYPTION_KEY", "")).strip()

        try:
            with open(archive_path, "rb") as f:
                content_bytes = f.read()

            zip_bytes: bytes
            if is_encrypted:
                if not raw_key:
                    return ArchiveVerifyResult(
                        success=False,
                        backup_id=archive_path.stem.replace(".zip", ""),
                        archive_path=archive_path,
                        size_bytes=size_bytes,
                        sha256_checksum=actual_sha,
                        sha256_matches=sha_matches,
                        is_encrypted=True,
                        encryption_status=encryption_status,
                        archive_integrity_ok=False,
                        db_integrity_ok=False,
                        components={},
                        error_message="Archive is encrypted but BACKUP_ENCRYPTION_KEY is not configured.",
                    )
                cipher = get_fernet_cipher(raw_key)
                try:
                    zip_bytes = cipher.decrypt(content_bytes)
                except Exception as de:
                    return ArchiveVerifyResult(
                        success=False,
                        backup_id=archive_path.stem.replace(".zip", ""),
                        archive_path=archive_path,
                        size_bytes=size_bytes,
                        sha256_checksum=actual_sha,
                        sha256_matches=sha_matches,
                        is_encrypted=True,
                        encryption_status=encryption_status,
                        archive_integrity_ok=False,
                        db_integrity_ok=False,
                        components={},
                        error_message=f"Decryption failed: {de}",
                    )
            else:
                zip_bytes = content_bytes

            # Test zip structure
            zip_buffer = io.BytesIO(zip_bytes)
            with zipfile.ZipFile(zip_buffer, "r") as zf:
                bad_file = zf.testzip()
                if bad_file:
                    return ArchiveVerifyResult(
                        success=False,
                        backup_id=archive_path.stem.replace(".zip", ""),
                        archive_path=archive_path,
                        size_bytes=size_bytes,
                        sha256_checksum=actual_sha,
                        sha256_matches=sha_matches,
                        is_encrypted=is_encrypted,
                        encryption_status=encryption_status,
                        archive_integrity_ok=False,
                        db_integrity_ok=False,
                        components={},
                        error_message=f"Corrupted entry in zip: {bad_file}",
                    )

                # Check for metadata.json
                components: Dict[str, bool] = {}
                if "metadata.json" in zf.namelist():
                    meta_raw = zf.read("metadata.json")
                    try:
                        meta = json.loads(meta_raw.decode("utf-8"))
                        components = meta.get("components", {})
                    except Exception:
                        pass

                # Check SQLite database inside
                if "database/bot.db" not in zf.namelist():
                    return ArchiveVerifyResult(
                        success=False,
                        backup_id=archive_path.stem.replace(".zip", ""),
                        archive_path=archive_path,
                        size_bytes=size_bytes,
                        sha256_checksum=actual_sha,
                        sha256_matches=sha_matches,
                        is_encrypted=is_encrypted,
                        encryption_status=encryption_status,
                        archive_integrity_ok=True,
                        db_integrity_ok=False,
                        components=components,
                        error_message="database/bot.db is missing from archive.",
                    )

                # Extract database to temporary file to run quick_check
                db_bytes = zf.read("database/bot.db")
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
                    tmp_db.write(db_bytes)
                    tmp_path = Path(tmp_db.name)

                try:
                    conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA quick_check")
                    row = cursor.fetchone()
                    conn.close()
                    db_ok = bool(row and row[0] == "ok")
                finally:
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass

                if not db_ok:
                    return ArchiveVerifyResult(
                        success=False,
                        backup_id=archive_path.stem.replace(".zip", ""),
                        archive_path=archive_path,
                        size_bytes=size_bytes,
                        sha256_checksum=actual_sha,
                        sha256_matches=sha_matches,
                        is_encrypted=is_encrypted,
                        encryption_status=encryption_status,
                        archive_integrity_ok=True,
                        db_integrity_ok=False,
                        components=components,
                        error_message="Internal SQLite database failed PRAGMA quick_check.",
                    )

            return ArchiveVerifyResult(
                success=True,
                backup_id=archive_path.stem.replace(".zip", ""),
                archive_path=archive_path,
                size_bytes=size_bytes,
                sha256_checksum=actual_sha,
                sha256_matches=sha_matches,
                is_encrypted=is_encrypted,
                encryption_status=encryption_status,
                archive_integrity_ok=True,
                db_integrity_ok=True,
                components=components,
                verified=True,
            )

        except Exception as e:
            return ArchiveVerifyResult(
                success=False,
                backup_id=archive_path.stem.replace(".zip", ""),
                archive_path=archive_path,
                size_bytes=size_bytes,
                sha256_checksum=actual_sha,
                sha256_matches=sha_matches,
                is_encrypted=is_encrypted,
                encryption_status=encryption_status,
                archive_integrity_ok=False,
                db_integrity_ok=False,
                components={},
                error_message=str(e),
            )

    @classmethod
    def extract_database_snapshot(
        cls,
        archive_path: Path,
        target_db_path: Path,
        encryption_key: Optional[str] = None,
    ) -> bool:
        """Extracts the internal SQLite database from the archive package."""
        if not archive_path.exists():
            return False

        raw_key = (encryption_key or os.getenv("BACKUP_ENCRYPTION_KEY", "")).strip()
        is_encrypted = archive_path.name.endswith(".enc")

        with open(archive_path, "rb") as f:
            content = f.read()

        zip_bytes: bytes
        if is_encrypted:
            if not raw_key:
                raise ValueError("Archive is encrypted but BACKUP_ENCRYPTION_KEY is missing.")
            cipher = get_fernet_cipher(raw_key)
            zip_bytes = cipher.decrypt(content)
        else:
            zip_bytes = content

        zip_buffer = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            if "database/bot.db" not in zf.namelist():
                raise FileNotFoundError("Archive does not contain database/bot.db")
            db_bytes = zf.read("database/bot.db")

        target_db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_db_path, "wb") as f:
            f.write(db_bytes)

        return True
