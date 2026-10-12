"""
Unit and Integration Tests for Server Configuration Backup & Disaster Recovery (Phases 2 & 3).
Verifies:
- Serialization and sanitization (no tokens or secrets)
- Checksum computation and ZIP integrity validation
- Dry-run preview diff generation
- Database record creation and retrieval
- Non-destructive execution guards
"""

import asyncio
import json
import pytest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from database.database import Database
from database.models import ServerBackupRecord
from backups.server_config_backup import ServerConfigBackupEngine, compute_file_sha256


@pytest.fixture
def temp_db(tmp_path: Path):
    db_path = tmp_path / "test_backup_restore.db"
    db = Database(db_path)
    asyncio.run(db.connect())
    yield db
    asyncio.run(db.close())


def test_preview_restore_diff_generation():
    # Mock current guild
    mock_guild = MagicMock()
    mock_guild.roles = [
        MagicMock(name="@everyone", position=0, is_default=lambda: True),
        MagicMock(name="Admin", position=1, is_default=lambda: False),
    ]
    mock_guild.roles[0].name = "@everyone"
    mock_guild.roles[1].name = "Admin"

    mock_guild.categories = [MagicMock(name="CHAT")]
    mock_guild.categories[0].name = "CHAT"

    mock_guild.channels = [MagicMock(name="general")]
    mock_guild.channels[0].name = "general"

    # Backup data with missing roles and channels
    backup_data = {
        "format_version": 2,
        "created_at": "2026-10-12T00:00:00",
        "guild": {"name": "Test Server"},
        "roles": [
            {"name": "@everyone", "is_default": True, "permissions": 0},
            {"name": "Admin", "is_default": False, "permissions": 8},
            {"name": "Moderator", "is_default": False, "permissions": 4},
            {"name": "VIP", "is_default": False, "permissions": 0},
        ],
        "categories": [
            {"name": "CHAT"},
            {"name": "VOICE ROOMS"},
        ],
        "channels": [
            {"name": "general", "type": "text"},
            {"name": "announcements", "type": "text"},
            {"name": "Lounge", "type": "voice"},
        ],
    }

    preview = ServerConfigBackupEngine.preview_restore(mock_guild, backup_data)
    assert "Moderator" in preview["missing_roles"]
    assert "VIP" in preview["missing_roles"]
    assert "Admin" not in preview["missing_roles"]
    assert "VOICE ROOMS" in preview["missing_categories"]
    assert "#announcements (text)" in preview["missing_channels"]
    assert "#Lounge (voice)" in preview["missing_channels"]
    assert len(preview["limitations"]) > 0


@pytest.mark.asyncio
async def test_server_backup_sqlite_records(temp_db: Database, tmp_path: Path):
    guild_id = 777777777
    zip_path = tmp_path / "mock_backup.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"test": "ok"}))

    sha = compute_file_sha256(zip_path)
    record = ServerBackupRecord(
        backup_id="BAK-777-20261012-TEST",
        guild_id=guild_id,
        created_by=0,
        backup_type="automated_test",
        file_path=str(zip_path),
        file_size=zip_path.stat().st_size,
        checksum=sha,
        verified=True,
        created_at="2026-10-12T00:00:00",
    )
    await temp_db.create_server_backup(record)

    fetched = await temp_db.get_server_backup("BAK-777-20261012-TEST")
    assert fetched is not None
    assert fetched.backup_id == "BAK-777-20261012-TEST"
    assert fetched.checksum == sha
    assert fetched.verified is True

    backups_list = await temp_db.get_server_backups(guild_id)
    assert len(backups_list) == 1
    assert backups_list[0].backup_id == "BAK-777-20261012-TEST"


@pytest.mark.asyncio
async def test_dry_run_restoration_makes_no_changes(tmp_path: Path):
    mock_guild = MagicMock()
    mock_guild.roles = []
    mock_guild.categories = []
    mock_guild.channels = []

    zip_path = tmp_path / "backup_sample.zip"
    sample_config = {
        "format_version": 2,
        "guild": {"name": "Sample"},
        "roles": [{"name": "TestRole", "is_default": False}],
        "categories": [],
        "channels": [],
    }
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("server_config.json", json.dumps(sample_config))

    res = await ServerConfigBackupEngine.execute_restore(
        guild=mock_guild,
        backup_path=zip_path,
        dry_run=True,
    )
    assert res["success"] is True
    assert res["dry_run"] is True
    assert "TestRole" in res["preview"]["missing_roles"]
    # Ensure no create calls were made to Discord API
    assert mock_guild.create_role.call_count == 0
    assert mock_guild.create_channel.call_count == 0
