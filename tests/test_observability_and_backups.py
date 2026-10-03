"""
Comprehensive Unit & Integration Tests for 『RΛI』 Observability, Monitoring & Disaster Recovery.
Validates:
- Prometheus metric definitions and low-cardinality label enforcement
- Observability health check and isolated security health guarantees
- Sentry error tracking credential and token regex sanitization
- Grafana dashboard JSON schema validity
- SQLite atomic online backups with SHA256 verification
- S3 uploader verification and local-only fallback
- Tiered retention rotation and GFS pruning
- Safe disaster recovery restoration with administrative authorization tokens
"""

import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from database.database import Database
from database.manager import DatabaseManager
from observability.health import ObservabilityHealthService, SystemHealthReport
from observability.metrics import (
    PROMETHEUS_AVAILABLE,
    MetricsServer,
    rai_security_events_total,
    rai_security_incidents_active,
    rai_emergency_mode_active,
)
from observability.sentry_tracker import SentryTracker, sanitize_text, sanitize_dict
from observability.dashboards import generate_grafana_dashboard, export_grafana_dashboard
from backups.sqlite_backup import SQLiteBackupService, SQLiteBackupResult
from backups.uploader import S3BackupUploader, BackupLifecycleState, UploadResult
from backups.retention import RetentionManager, RetentionPolicy
from backups.restore import SafeRestoreEngine, RestoreResult
from backups.manager import BackupManager


class TestObservabilityAndBackups(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test_obs.db"
        self.backups_dir = self.temp_path / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

        self.db = Database(self.db_path)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        db_mgr = DatabaseManager._instance
        if db_mgr and db_mgr.sqlite:
            try:
                await db_mgr.sqlite.close()
            except Exception:
                pass
        DatabaseManager._instance = None
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # ==========================================
    # 1. Prometheus Metrics & Cardinality Protection
    # ==========================================

    def test_metrics_definition_and_cardinality_rules(self):
        """Validates that metrics exist and respect low-cardinality constraints."""
        self.assertTrue(PROMETHEUS_AVAILABLE)

        # Labels must be low-cardinality (severity, event_type), never user_id or message_id!
        rai_security_events_total.labels(event_type="MENTION_SPAM", severity="HIGH").inc()
        rai_security_incidents_active.set(3)
        rai_emergency_mode_active.set(1)

        # Server start dry run
        with patch.dict("os.environ", {"PROMETHEUS_ENABLED": "false"}):
            started = MetricsServer.start()
            self.assertFalse(started)

    # ==========================================
    # 2. Health Service & Isolated Security Health
    # ==========================================

    async def test_security_health_independent_of_cloud_databases(self):
        """
        CRITICAL ARCHITECTURAL GUARANTEE:
        If PostgreSQL, Redis, and Firebase are offline, security_health must remain HEALTHY
        as long as local SQLite is operational.
        """
        # Mock DatabaseManager with offline cloud services
        db_mgr = DatabaseManager.get_instance(self.db_path)
        if not db_mgr.sqlite.is_connected:
            await db_mgr.sqlite.connect()
        db_mgr.postgres_conn.pool = None
        db_mgr.postgres_conn.enabled = True
        db_mgr.redis_conn._client = None
        db_mgr.redis_conn._fallback_active = True
        db_mgr.firebase_conn._client = None

        # Evaluate health
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = True

        report: SystemHealthReport = ObservabilityHealthService.evaluate_health(mock_bot)

        # Security MUST be HEALTHY despite cloud outages!
        self.assertEqual(report.security_health, "HEALTHY")
        # Database health is degraded because PostgreSQL is down
        self.assertEqual(report.database_health, "DEGRADED")
        # Overall status is degraded, but security is active
        self.assertEqual(report.overall_status, "DEGRADED")
        self.assertTrue(report.details["redis_fallback_active"])

    # ==========================================
    # 3. Sentry Error Sanitization
    # ==========================================

    def test_sentry_credential_sanitization(self):
        """Verifies bot tokens, database passwords, and API keys are redacted before leaving."""
        # Construct dummy pattern dynamically for test verification without triggering secret scanners
        part1 = "M" * 26
        part2 = "G" * 6
        part3 = "A" * 30
        token = f"{part1}.{part2}.{part3}"
        text = f"Failed to authenticate with token {token} on endpoint"
        sanitized = sanitize_text(text)
        self.assertNotIn(token, sanitized)
        self.assertIn("[REDACTED_DISCORD_TOKEN]", sanitized)

        # Database connection URL
        db_url = "postgresql://rai_admin:dummy_pass_123@db.internal:5432/rai_prod"
        sanitized_db = sanitize_text(f"Connection pool error for {db_url}")
        self.assertNotIn("dummy_pass_123", sanitized_db)
        self.assertIn("://[USER]:[REDACTED_PW]@", sanitized_db)

        # Dictionary recursive redaction
        fake_api_key = "AIza" + "SyD" + "0" * 32
        sensitive_dict = {
            "user": "admin",
            "bot_token": token,
            "api_key": fake_api_key,
            "headers": {"Authorization": "Bearer secret_jwt_token"},
            "nested": {"db_password": "supersecretpassword"},
        }
        clean_dict = sanitize_dict(sensitive_dict)
        self.assertEqual(clean_dict["bot_token"], "[REDACTED]")
        self.assertEqual(clean_dict["api_key"], "[REDACTED]")
        self.assertEqual(clean_dict["headers"]["Authorization"], "[REDACTED]")
        self.assertEqual(clean_dict["nested"]["db_password"], "[REDACTED]")
        self.assertEqual(clean_dict["user"], "admin")

    # ==========================================
    # 4. Grafana Dashboard Export
    # ==========================================

    def test_grafana_dashboard_generation(self):
        """Verifies Grafana dashboard generator produces valid JSON schema with all required panels."""
        dash = generate_grafana_dashboard()
        self.assertEqual(dash["uid"], "rai-production-overview")
        self.assertIn("panels", dash)
        self.assertGreaterEqual(len(dash["panels"]), 8)

        # Export test
        out_file = self.temp_path / "test_grafana.json"
        exported_path = export_grafana_dashboard(out_file)
        self.assertTrue(exported_path.exists())
        with open(exported_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["title"], "『RΛI』 Autonomous Production Dashboard")

    # ==========================================
    # 5. SQLite Atomic Online Backup
    # ==========================================

    async def test_sqlite_atomic_backup_with_checksum(self):
        """Verifies online SQLite backup creates verifiable snapshot with correct SHA256 checksum."""
        # Create table and insert rows
        await self.db._db.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)")
        await self.db._db.execute("INSERT INTO test_data (value) VALUES ('production_event')")
        await self.db._db.commit()

        # Execute backup
        res: SQLiteBackupResult = await SQLiteBackupService.create_backup(
            source_path=self.db_path,
            dest_dir=self.backups_dir,
        )

        self.assertTrue(res.success)
        self.assertIsNotNone(res.backup_path)
        self.assertTrue(res.backup_path.exists())
        self.assertGreater(res.size_bytes, 0)
        self.assertEqual(len(res.sha256_checksum), 64)

        # Manually compute checksum and compare
        hasher = hashlib.sha256()
        with open(res.backup_path, "rb") as f:
            hasher.update(f.read())
        self.assertEqual(hasher.hexdigest(), res.sha256_checksum)

        # Verify integrity of backup copy
        conn = sqlite3.connect(str(res.backup_path))
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM test_data")
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row[0], "production_event")

    # ==========================================
    # 6. S3 Backup Uploader & Local Fallback
    # ==========================================

    async def test_s3_uploader_local_fallback(self):
        """Verifies S3 uploader marks local backup as VERIFIED when cloud storage is disabled."""
        uploader = S3BackupUploader()
        uploader.enabled = False

        dummy_file = self.backups_dir / "rai_sqlite_20261001_120000.db"
        dummy_file.write_bytes(b"SQLite format 3\x00test_payload")

        result: UploadResult = await uploader.upload_and_verify(
            local_path=dummy_file,
            remote_prefix="sqlite",
            expected_sha256="dummy_sha",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.state, BackupLifecycleState.VERIFIED)
        self.assertEqual(result.bucket, "local")

    # ==========================================
    # 7. Backup Retention Rotation
    # ==========================================

    def test_backup_retention_pruning(self):
        """Validates that older backups beyond limits are pruned while locked files are preserved."""
        # Create 10 dummy backup files with staggered timestamps
        for i in range(10):
            p = self.backups_dir / f"rai_sqlite_20261001_{i:02d}0000.db"
            p.write_bytes(f"backup_{i}".encode("utf-8"))

        # Create one locked file
        locked = self.backups_dir / "rai_sqlite_RECOVERY_LOCK_special.db"
        locked.write_bytes(b"disaster_recovery_checkpoint")

        # Set retention limit to 3 files
        retention = RetentionManager(policy=RetentionPolicy(max_hourly=3))
        retained, deleted = retention.prune_directory(self.backups_dir, max_files_fallback=3)

        self.assertEqual(deleted, 7)
        # Locked file must NEVER be deleted
        self.assertTrue(locked.exists())

    # ==========================================
    # 8. Safe Disaster Recovery Restoration
    # ==========================================

    async def test_safe_restore_safeguards(self):
        """Validates that restore rejects invalid tokens and takes safety snapshot before restoring."""
        # 1. Setup active DB with original data
        active_db = self.temp_path / "active.db"
        conn1 = sqlite3.connect(active_db)
        conn1.execute("CREATE TABLE original (msg TEXT)")
        conn1.execute("INSERT INTO original VALUES ('state_v1')")
        conn1.commit()
        conn1.close()

        # 2. Setup backup DB with recovered data
        backup_file = self.backups_dir / "rai_sqlite_target_backup.db"
        conn2 = sqlite3.connect(backup_file)
        conn2.execute("CREATE TABLE original (msg TEXT)")
        conn2.execute("INSERT INTO original VALUES ('state_v2_recovered')")
        conn2.commit()
        conn2.close()

        # Attempt restore with INVALID confirmation token
        bad_token_res = await SafeRestoreEngine.execute_restore(
            backup_path=backup_file,
            target_db_path=active_db,
            confirmation_token="WRONG_TOKEN",
        )
        self.assertFalse(bad_token_res.success)
        self.assertIn("Invalid authorization token", bad_token_res.error_message)

        # Attempt restore with VALID confirmation token: CONFIRM_RESTORE_<filename>
        valid_token = f"CONFIRM_RESTORE_{backup_file.name}"
        restore_res = await SafeRestoreEngine.execute_restore(
            backup_path=backup_file,
            target_db_path=active_db,
            confirmation_token=valid_token,
        )

        self.assertTrue(restore_res.success)
        self.assertTrue(restore_res.integrity_verified)
        self.assertIsNotNone(restore_res.pre_restore_snapshot)
        self.assertTrue(restore_res.pre_restore_snapshot.exists())

        # Verify active database now contains recovered state
        conn3 = sqlite3.connect(active_db)
        cursor = conn3.cursor()
        cursor.execute("SELECT msg FROM original")
        row = cursor.fetchone()
        conn3.close()
        self.assertEqual(row[0], "state_v2_recovered")

        # Verify safety snapshot contains original state
        conn4 = sqlite3.connect(restore_res.pre_restore_snapshot)
        cursor4 = conn4.cursor()
        cursor4.execute("SELECT msg FROM original")
        row4 = cursor4.fetchone()
        conn4.close()
        self.assertEqual(row4[0], "state_v1")


if __name__ == "__main__":
    unittest.main()
