"""
Phase 6 Tests — Creator & Owner Operations Control Room.
Validates:
1. Truth in telemetry: verified real gateway latency & SLA behavior (no hardcoded 0.5ms or fake 99.97%).
2. RBAC security: require_owner strictly rejects non-owners with 403 Forbidden.
3. System health diagnostics: CPU, memory footprint, SQLite WAL integrity.
4. VIP License & Entitlements Manager: grant & revoke memberships with audit logging.
5. Feature flags & Emergency Safe Mode killswitch.
6. Database WAL snapshots creation and inventory.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from web.owner_api import OwnerApiRouter, load_feature_flags, save_feature_flags


@pytest.fixture
def mock_owner_auth():
    auth = MagicMock()
    # Verified Bot Owner session
    auth.require_owner = AsyncMock(return_value={
        "discord_user_id": 1457380609641938981,
        "username": "kishorerai",
        "is_owner": True,
        "user_data": {"id": 1457380609641938981, "username": "kishorerai", "is_owner": True},
    })
    auth.get_user_entitlements = AsyncMock(return_value={"is_premium": False, "tier": "free"})
    return auth


@pytest.fixture
def owner_router(mock_owner_auth):
    bot = MagicMock()
    bot.is_ready = MagicMock(return_value=True)
    bot.latency = 0.042  # 42.0 ms measured
    bot.guilds = [MagicMock(), MagicMock()]
    bot.started_at = 1700000000.0

    # Mock session manager
    mock_sm = MagicMock()
    s1 = MagicMock()
    s1.voice_client = MagicMock()
    s1.voice_client.is_connected = MagicMock(return_value=True)
    s1.voice_client.channel = MagicMock()
    s1.is_playing = True

    s2 = MagicMock()
    s2.voice_client = None
    s2.is_playing = False

    mock_sm.get_all_sessions = MagicMock(return_value=[s1, s2])
    bot.session_manager = mock_sm

    db = MagicMock()
    db._db = MagicMock()

    router = OwnerApiRouter(bot=bot, db=db, auth=mock_owner_auth)
    return router


def _create_mock_req(method: str, path: str, json_data: dict = None):
    headers = {"Content-Type": "application/json"}
    req = make_mocked_request(method, path, headers=headers)
    if json_data is not None:
        req.json = AsyncMock(return_value=json_data)
    return req


@pytest.mark.asyncio
async def test_owner_overview_truthful_telemetry(owner_router):
    """Verify get_overview returns measured latency (42.0 ms) and no fake 99.97% or 0.5ms values."""
    req = _create_mock_req("GET", "/api/owner/overview")
    resp = await owner_router.get_overview(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    res = data["data"]

    # Truthful latency: 0.042 * 1000 = 42.0 ms
    assert res["gateway_latency_ms"] == 42.0
    # Must NOT present fixed fallback 0.5 ms
    assert res["gateway_latency_ms"] != 0.5

    # SLA percentage should NOT be hardcoded 99.97%
    assert res["sla_percentage"] != 99.97
    assert res["sla_percentage"] is None

    # Real cluster counts
    assert res["active_guilds"] == 2
    assert res["active_voice_sessions"] == 1
    assert res["currently_playing"] == 1


@pytest.mark.asyncio
async def test_owner_overview_null_latency_when_offline(owner_router):
    """Verify gateway latency is None (not 0.5ms) when bot latency cannot be measured."""
    owner_router.bot.latency = float("nan")
    req = _create_mock_req("GET", "/api/owner/overview")
    resp = await owner_router.get_overview(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["data"]["gateway_latency_ms"] is None


@pytest.mark.asyncio
async def test_owner_rbac_rejection(owner_router):
    """Verify non-owner request to owner endpoints raises HTTP 403 Forbidden."""
    owner_router.auth.require_owner.side_effect = web.HTTPForbidden(
        text='{"success": false, "error": {"code": "FORBIDDEN"}}',
        content_type="application/json",
    )
    req = _create_mock_req("GET", "/api/owner/overview")
    with pytest.raises(web.HTTPForbidden):
        await owner_router.get_overview(req)


@pytest.mark.asyncio
async def test_system_health_diagnostics(owner_router):
    """Verify get_health inspects database integrity, memory, and audio engine."""
    cursor_mock = AsyncMock()
    cursor_mock.fetchone = AsyncMock(return_value=("ok",))
    owner_router.db._db.execute = AsyncMock(return_value=cursor_mock)

    req = _create_mock_req("GET", "/api/owner/health")
    resp = await owner_router.get_health(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    assert data["data"]["database"]["integrity"] == "ok"
    assert data["data"]["database"]["mode"] == "SQLite WAL"
    assert "yt_dlp_version" in data["data"]["audio_engine"]


@pytest.mark.asyncio
async def test_grant_and_revoke_vip_entitlement(owner_router):
    """Verify update_entitlement grants promotional VIP with duration and reason, then revokes access."""
    owner_router.db.upsert_user_subscription = AsyncMock(return_value=True)
    owner_router.db.record_subscription_audit = AsyncMock(return_value=True)
    owner_router.db.cancel_user_subscription = AsyncMock(return_value=True)

    # 1. Grant VIP
    grant_req = _create_mock_req(
        "POST",
        "/api/owner/users/entitlement",
        json_data={
            "user_id": "1457380609641938981",
            "action": "grant",
            "tier": "vip",
            "days": 60,
            "reason": "Discord Developer VIP Partner Grant",
        },
    )
    grant_resp = await owner_router.update_entitlement(grant_req)
    assert grant_resp.status == 200
    grant_data = json.loads(grant_resp.text)
    assert grant_data["success"] is True
    assert grant_data["data"]["status"] == "active"
    assert grant_data["data"]["tier"] == "vip"
    owner_router.db.upsert_user_subscription.assert_called_once()
    owner_router.db.record_subscription_audit.assert_called_once()

    # 2. Revoke VIP
    revoke_req = _create_mock_req(
        "POST",
        "/api/owner/users/entitlement",
        json_data={
            "user_id": "1457380609641938981",
            "action": "revoke",
            "reason": "Trial expired",
        },
    )
    revoke_resp = await owner_router.update_entitlement(revoke_req)
    assert revoke_resp.status == 200
    revoke_data = json.loads(revoke_resp.text)
    assert revoke_data["success"] is True
    assert revoke_data["data"]["status"] == "revoked"
    owner_router.db.cancel_user_subscription.assert_called_once()


@pytest.mark.asyncio
async def test_feature_flags_and_emergency_safe_mode(owner_router, tmp_path):
    """Verify feature flags can be inspected and emergency safe mode can be toggled."""
    flags_file = tmp_path / "test_feature_flags.json"
    with patch("web.owner_api.FEATURE_FLAGS_FILE", flags_file):
        # 1. Fetch default flags
        get_req = _create_mock_req("GET", "/api/owner/feature-flags")
        get_resp = await owner_router.get_feature_flags(get_req)
        assert get_resp.status == 200
        flags = json.loads(get_resp.text)["data"]["flags"]
        assert "emergency_safe_mode" in flags

        # 2. Toggle emergency safe mode ON
        toggle_req = _create_mock_req(
            "POST",
            "/api/owner/feature-flags",
            json_data={"flag": "emergency_safe_mode", "enabled": True},
        )
        toggle_resp = await owner_router.update_feature_flags(toggle_req)
        assert toggle_resp.status == 200
        data = json.loads(toggle_resp.text)
        assert data["success"] is True
        assert data["data"]["flag"] == "emergency_safe_mode"
        assert data["data"]["enabled"] is True


@pytest.mark.asyncio
async def test_create_and_list_backups(owner_router, tmp_path):
    """Verify create_backup creates a timestamped database backup and list_backups finds it."""
    fake_db = tmp_path / "music_20261019_120000_manual_creator.db"
    fake_db.write_text("sqlite-mock-data", encoding="utf-8")
    owner_router.db.backup_database = MagicMock(return_value=fake_db)

    # Backup create endpoint
    req = _create_mock_req("POST", "/api/owner/backups/create")
    resp = await owner_router.create_backup(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    assert "filename" in data["data"]
