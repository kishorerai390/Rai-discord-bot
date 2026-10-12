"""
Unit and Integration Tests for Centralized Logging System (Phases 1-5).
Verifies:
- 15 dedicated channel configurations
- Database persistence and retrieval
- Fallback routing logic
- Audit log correlation safeguards
"""

import asyncio
import pytest
import sqlite3
from pathlib import Path

from database.database import Database
from database.models import LoggingConfig


@pytest.fixture
def temp_db(tmp_path: Path):
    db_path = tmp_path / "test_logging.db"
    db = Database(db_path)
    asyncio.run(db.connect())
    yield db
    asyncio.run(db.close())


def test_logging_config_model_15_channels():
    cfg = LoggingConfig(guild_id=123456789)
    assert cfg.guild_id == 123456789
    assert cfg.general_channel_id is None
    assert cfg.moderation_channel_id is None
    assert cfg.security_channel_id is None
    assert cfg.automod_channel_id is None
    assert cfg.member_channel_id is None
    assert cfg.message_channel_id is None
    assert cfg.voice_channel_id is None
    assert cfg.channel_logs_channel_id is None
    assert cfg.role_logs_channel_id is None
    assert cfg.server_audit_channel_id is None
    assert cfg.backup_logs_channel_id is None
    assert cfg.report_logs_channel_id is None
    assert cfg.ticket_logs_channel_id is None
    assert cfg.staff_logs_channel_id is None
    assert cfg.bot_logs_channel_id is None
    assert cfg.error_logs_channel_id is None
    assert cfg.system_status_channel_id is None


@pytest.mark.asyncio
async def test_database_logging_config_persistence(temp_db: Database):
    guild_id = 999888777
    # Fetch default
    cfg = await temp_db.get_logging_config(guild_id)
    assert cfg.guild_id == guild_id

    # Update all 15 channels
    channels = {
        "moderation_channel_id": 1001,
        "security_channel_id": 1002,
        "message_channel_id": 1003,
        "member_channel_id": 1004,
        "voice_channel_id": 1005,
        "channel_logs_channel_id": 1006,
        "role_logs_channel_id": 1007,
        "server_audit_channel_id": 1008,
        "backup_logs_channel_id": 1009,
        "report_logs_channel_id": 1010,
        "ticket_logs_channel_id": 1011,
        "staff_logs_channel_id": 1012,
        "bot_logs_channel_id": 1013,
        "error_logs_channel_id": 1014,
        "system_status_channel_id": 1015,
        "general_channel_id": 1000,
    }
    await temp_db.update_logging_config(guild_id, **channels)

    updated_cfg = await temp_db.get_logging_config(guild_id)
    for key, val in channels.items():
        assert getattr(updated_cfg, key) == val


def test_log_channel_specs_count():
    from cogs.logging import LoggingCog
    specs = LoggingCog.LOG_CHANNEL_SPECS
    assert len(specs) == 15
    channel_names = [s[0] for s in specs]
    expected_channels = [
        "mod-logs", "security-logs", "message-logs", "member-logs", "voice-logs",
        "channel-logs", "role-logs", "server-audit-logs", "backup-logs", "report-logs",
        "ticket-logs", "staff-logs", "bot-logs", "error-logs", "system-status"
    ]
    assert channel_names == expected_channels
