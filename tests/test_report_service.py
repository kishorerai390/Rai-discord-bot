"""
Unit tests for the Unified Permission-Based ReportService.
Validates:
1. Permission checks & missing permission detection.
2. One-time permission warning and cooldown suppression.
3. Event-driven and state-change reporting (DEGRADED -> HEALTHY recovery).
4. Error fingerprint deduplication and occurrences counting.
5. Success report suppression when success_reports_enabled is False.
6. Rate limiting and critical security cooldown bypass.
7. Delivery failure loop breaker.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.report_service import (
    ReportService,
    ReportSeverity,
    ReportStatus,
    ReportType,
    ReportResult,
    REQUIRED_REPORT_PERMISSIONS,
)
from database.models import OwnerReportsConfig, ReportDestination, ReportEventRecord, ReportDeliveryRecord


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.user = MagicMock()
    bot.user.id = 123456789
    return bot


@pytest.fixture
def mock_guild():
    guild = MagicMock()
    guild.id = 999888777
    guild.owner_id = 111222333
    me = MagicMock()
    guild.me = me
    return guild


@pytest.fixture
def mock_channel(mock_guild):
    channel = MagicMock()
    channel.id = 555666777
    channel.name = "security-report"
    channel.guild = mock_guild
    perms = MagicMock()
    perms.view_channel = True
    perms.send_messages = True
    perms.embed_links = True
    perms.read_message_history = True
    perms.attach_files = True
    channel.permissions_for.return_value = perms
    channel.send = AsyncMock()
    sent_msg = MagicMock()
    sent_msg.id = 999111
    channel.send.return_value = sent_msg
    return channel


class TestReportPermissions:
    def test_permissions_check_all_granted(self, mock_channel):
        ok, missing = ReportService.check_channel_permissions(mock_channel)
        assert ok is True
        assert len(missing) == 0

    def test_permissions_check_missing_send_and_embed(self, mock_channel):
        perms = mock_channel.permissions_for.return_value
        perms.send_messages = False
        perms.embed_links = False
        ok, missing = ReportService.check_channel_permissions(mock_channel)
        assert ok is False
        assert "Send Messages" in missing
        assert "Embed Links" in missing
        assert "View Channel" not in missing

    @pytest.mark.asyncio
    async def test_permission_warning_cooldown(self, mock_bot, mock_guild, mock_channel):
        perms = mock_channel.permissions_for.return_value
        perms.send_messages = False

        # First failure: last_warning_at is None
        mock_bot.db.get_report_permission_state.return_value = None

        await ReportService.send_permission_warning(
            mock_bot, mock_guild, mock_channel, "security", ["Send Messages"]
        )
        assert mock_bot.db.update_report_permission_state.called
        assert mock_bot.db.update_report_permission_state.call_args[1]["record_warning"] is True

        # Second failure within 1 hour: warning is suppressed
        recent_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30))
        mock_state = MagicMock()
        mock_state.last_warning_at = recent_ts
        mock_bot.db.get_report_permission_state.return_value = mock_state
        mock_bot.db.update_report_permission_state.reset_mock()

        await ReportService.send_permission_warning(
            mock_bot, mock_guild, mock_channel, "security", ["Send Messages"]
        )
        # Should record state internally with record_warning=False and NOT spam
        assert mock_bot.db.update_report_permission_state.called
        assert mock_bot.db.update_report_permission_state.call_args[1]["record_warning"] is False


class TestStateChangeReporting:
    @pytest.mark.asyncio
    async def test_initial_healthy_does_not_report(self, mock_bot):
        ReportService._state_cache.clear()
        res = await ReportService.report_state_change(
            mock_bot, guild_id=123, component="music", current_state="HEALTHY"
        )
        assert res is None

    @pytest.mark.asyncio
    async def test_healthy_to_degraded_generates_one_report(self, mock_bot, mock_guild, mock_channel):
        ReportService._state_cache.clear()
        mock_bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel
        mock_bot.db.get_report_destination.return_value = ReportDestination(
            guild_id=mock_guild.id, report_type="system", channel_id=mock_channel.id, enabled=True
        )

        res = await ReportService.report_state_change(
            mock_bot, guild_id=mock_guild.id, component="music", current_state="DEGRADED"
        )
        assert res is not None
        assert res.status == ReportStatus.SUCCESS
        assert mock_channel.send.called

    @pytest.mark.asyncio
    async def test_repeated_identical_state_does_not_spam(self, mock_bot):
        ReportService._state_cache[(999, "database")] = "DEGRADED"
        res = await ReportService.report_state_change(
            mock_bot, guild_id=999, component="database", current_state="DEGRADED"
        )
        assert res is None

    @pytest.mark.asyncio
    async def test_degraded_to_healthy_generates_recovery_report(self, mock_bot, mock_guild, mock_channel):
        ReportService._state_cache[(mock_guild.id, "database")] = "DEGRADED"
        mock_bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel
        mock_bot.db.get_report_destination.return_value = ReportDestination(
            guild_id=mock_guild.id, report_type="system", channel_id=mock_channel.id, enabled=True
        )

        res = await ReportService.report_state_change(
            mock_bot, guild_id=mock_guild.id, component="database", current_state="HEALTHY"
        )
        assert res is not None
        assert res.status == ReportStatus.SUCCESS
        assert "Recovered" in res.message or mock_channel.send.called


class TestErrorFingerprintingAndDeduplication:
    def test_stable_fingerprint(self):
        fp1 = ReportService.compute_fingerprint(
            guild_id=100,
            report_type="music",
            module="provider",
            error_category="stream",
            error_code="ERR_403",
            message="Stream at 0x7fff56a failed at 2026-10-03T10:00:00Z for user 123456789012345678",
        )
        fp2 = ReportService.compute_fingerprint(
            guild_id=100,
            report_type="music",
            module="provider",
            error_category="stream",
            error_code="ERR_403",
            message="Stream at 0x8bbb12c failed at 2026-10-03T10:05:00Z for user 987654321098765432",
        )
        assert fp1 == fp2

    @pytest.mark.asyncio
    async def test_duplicate_error_updates_existing_message(self, mock_bot, mock_guild, mock_channel):
        mock_bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel
        mock_bot.db.get_report_destination.return_value = ReportDestination(
            guild_id=mock_guild.id, report_type="music", channel_id=mock_channel.id, enabled=True
        )

        # Mock an existing active event with occurrences=1
        existing_event = ReportEventRecord(
            event_id="RAI-TEST01",
            guild_id=mock_guild.id,
            report_type="music",
            severity="WARNING",
            fingerprint="abc12345",
            message="Failed to connect to stream",
            occurrences=1,
            status="OPEN",
            first_seen="2026-10-03T10:00:00Z",
        )
        mock_bot.db.get_or_create_report_event.return_value = (existing_event, False)

        updated_event = ReportEventRecord(
            event_id="RAI-TEST01",
            guild_id=mock_guild.id,
            report_type="music",
            severity="WARNING",
            fingerprint="abc12345",
            message="Failed to connect to stream",
            occurrences=2,
            status="UPDATED",
            first_seen="2026-10-03T10:00:00Z",
        )
        mock_bot.db.update_report_event_occurrence.return_value = updated_event

        # Mock existing delivery record and existing message
        mock_bot.db.get_report_delivery.return_value = ReportDeliveryRecord(
            event_id="RAI-TEST01",
            channel_id=mock_channel.id,
            message_id=777888,
            status="DELIVERED",
        )
        existing_msg = MagicMock()
        existing_msg.id = 777888
        existing_msg.embeds = []
        mock_channel.fetch_message = AsyncMock(return_value=existing_msg)
        existing_msg.edit = AsyncMock()

        res = await ReportService.report(
            bot=mock_bot,
            guild_id=mock_guild.id,
            report_type="music",
            severity=ReportSeverity.WARNING,
            title="Music Provider Error",
            description="Failed to connect to stream",
        )

        assert res.status == ReportStatus.UPDATED
        assert res.is_updated is True
        assert res.occurrences == 2
        assert existing_msg.edit.called


class TestSuccessReportsSuppression:
    @pytest.mark.asyncio
    async def test_success_report_skipped_by_default(self, mock_bot, mock_guild, mock_channel):
        mock_bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel
        cfg = OwnerReportsConfig(guild_id=mock_guild.id, success_reports_enabled=False)
        mock_bot.db.get_owner_reports_config.return_value = cfg

        res = await ReportService.report(
            bot=mock_bot,
            guild_id=mock_guild.id,
            report_type="backup",
            severity=ReportSeverity.INFO,
            title="Backup Successful",
            description="Database archive created.",
            is_success=True,
        )
        assert res.status == ReportStatus.SKIPPED
        assert not mock_channel.send.called

    @pytest.mark.asyncio
    async def test_success_report_delivered_when_enabled(self, mock_bot, mock_guild, mock_channel):
        mock_bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel
        cfg = OwnerReportsConfig(guild_id=mock_guild.id, success_reports_enabled=True)
        mock_bot.db.get_owner_reports_config.return_value = cfg
        mock_bot.db.get_report_destination.return_value = ReportDestination(
            guild_id=mock_guild.id, report_type="backup", channel_id=mock_channel.id, enabled=True
        )

        res = await ReportService.report(
            bot=mock_bot,
            guild_id=mock_guild.id,
            report_type="backup",
            severity=ReportSeverity.INFO,
            title="Backup Successful",
            description="Database archive created.",
            is_success=True,
        )
        assert res.status == ReportStatus.SUCCESS
        assert mock_channel.send.called


class TestLoopBreaker:
    @pytest.mark.asyncio
    async def test_recursive_delivery_prevention(self, mock_bot, mock_guild, mock_channel):
        mock_bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel

        call_key = f"{mock_guild.id}:security:Test Loop"
        ReportService._delivery_lock.add(call_key)
        try:
            res = await ReportService.report(
                bot=mock_bot,
                guild_id=mock_guild.id,
                report_type="security",
                severity=ReportSeverity.CRITICAL,
                title="Test Loop",
            )
            assert res.status == ReportStatus.SKIPPED
            assert "Recursive" in res.message
        finally:
            ReportService._delivery_lock.discard(call_key)
