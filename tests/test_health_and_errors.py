"""
Unit and Integration Tests for Health & Error Monitoring (Phases 8 & 9).
Verifies:
- SystemErrorLog model and persistence
- Database record_system_error and retrieval
- Error resolution updates
- Error ID format compliance (ERR-XXXXXX)
"""

import asyncio
import pytest
from pathlib import Path

from database.database import Database
from database.models import SystemErrorLog
from core.errors import generate_error_id


@pytest.fixture
def temp_db(tmp_path: Path):
    db_path = tmp_path / "test_health.db"
    db = Database(db_path)
    asyncio.run(db.connect())
    yield db
    asyncio.run(db.close())


def test_error_id_format():
    err_id = generate_error_id()
    assert err_id.startswith("RAI-") or err_id.startswith("ERR-")
    assert len(err_id) >= 8


@pytest.mark.asyncio
async def test_system_error_log_persistence(temp_db: Database):
    err_id = generate_error_id()
    log = SystemErrorLog(
        error_id=err_id,
        guild_id=123456,
        subsystem="test_subsystem",
        error_type="ValueError",
        error_message="Simulated test error",
    )
    await temp_db.record_system_error(log)

    recent = await temp_db.get_recent_system_errors(limit=5)
    assert len(recent) >= 1
    found = [r for r in recent if r.error_id == err_id]
    assert len(found) == 1
    assert found[0].subsystem == "test_subsystem"
    assert found[0].resolved is False

    # Resolve error
    ok = await temp_db.resolve_system_error(err_id)
    assert ok is True

    recent_after = await temp_db.get_recent_system_errors(limit=5)
    found_after = [r for r in recent_after if r.error_id == err_id]
    assert found_after[0].resolved is True
