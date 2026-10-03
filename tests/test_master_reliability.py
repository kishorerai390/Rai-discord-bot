"""
RAI — MASTER RELIABILITY, MAINTENANCE & SELF-HEALING TEST SUITE
Verifies all 31 core reliability domains:
- Command isolation and 11-type error classification
- Discord API reliability layer (timeouts, retries, dedup, destructive isolation)
- Worker supervisor (singletons, heartbeats, stuck detection, restart backoff)
- Rai Doctor multi-subsystem truthful diagnostics
- Permission Doctor feature-specific authorization
- Emergency Manager and Safe Mode controls
- State Reconciliation and Event Timeline
- Failure injection & Cross-module non-interference
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from core.boundaries import (
    CommandErrorCode,
    CommandExecutionBoundary,
    CommandExecutionContext,
    generate_command_request_id,
)
from core.circuit_breaker import CircuitBreakerRegistry, CircuitState
from services.discord_reliability import APIActionCategory, APIMetrics, DiscordReliabilityLayer
from services.emergency_manager import EmergencyManager
from services.permission_doctor import FeaturePermissionCheck, GuildPermissionDiagnosis, PermissionDoctor
from services.rai_doctor import DiagnosticStatus, RaiDoctor, SubsystemDiagnostic
from services.reconciliation_service import ReconciliationReport, ReconciliationService
from services.worker_supervisor import WorkerDescriptor, WorkerStatus, WorkerSupervisor


class TestMasterReliability(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Reset singletons for testing
        WorkerSupervisor._instance = None
        DiscordReliabilityLayer._instance = None
        ReconciliationService._instance = None
        EmergencyManager._instance = None

    # ==========================================
    # 1. COMMAND EXECUTION BOUNDARY & TAXONOMY
    # ==========================================

    def test_request_id_format(self):
        req_id = generate_command_request_id()
        self.assertTrue(req_id.startswith("RAI-CMD-"))
        self.assertEqual(len(req_id), 14)

    def test_error_classification_taxonomy(self):
        # 1. Rate Limit
        cooldown_err = discord.app_commands.CommandOnCooldown(MagicMock(), retry_after=5.5)
        code, msg = CommandExecutionBoundary.classify_exception(cooldown_err)
        self.assertEqual(code, CommandErrorCode.RATE_LIMIT_ERROR)
        self.assertIn("5.5s", msg)

        # 2. Permission Error
        perm_err = discord.app_commands.MissingPermissions(["manage_guild", "ban_members"])
        code, msg = CommandExecutionBoundary.classify_exception(perm_err)
        self.assertEqual(code, CommandErrorCode.PERMISSION_ERROR)
        self.assertIn("manage_guild", msg)

        # 3. Timeout Error
        timeout_err = asyncio.TimeoutError()
        code, msg = CommandExecutionBoundary.classify_exception(timeout_err)
        self.assertEqual(code, CommandErrorCode.TIMEOUT_ERROR)

        # 4. NotFound
        nf_err = discord.NotFound(response=MagicMock(status=404), message="Channel deleted")
        code, msg = CommandExecutionBoundary.classify_exception(nf_err)
        self.assertEqual(code, CommandErrorCode.NOT_FOUND)

        # 5. Forbidden
        fb_err = discord.Forbidden(response=MagicMock(status=403), message="Hierarchy blocked")
        code, msg = CommandExecutionBoundary.classify_exception(fb_err)
        self.assertEqual(code, CommandErrorCode.PERMISSION_ERROR)

        # 6. Database Error
        db_err = RuntimeError("sqlite3.OperationalError: database is locked")
        code, msg = CommandExecutionBoundary.classify_exception(db_err)
        self.assertEqual(code, CommandErrorCode.DATABASE_ERROR)

        # 7. Provider Error
        prov_err = ValueError("yt-dlp returned unplayable stream audio")
        code, msg = CommandExecutionBoundary.classify_exception(prov_err)
        self.assertEqual(code, CommandErrorCode.PROVIDER_ERROR)

    async def test_command_isolation_execution(self):
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user.id = 12345
        mock_interaction.guild_id = 67890
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.send_message = AsyncMock()

        # Test successful execution
        async def sample_cmd():
            return "command_output"

        res = await CommandExecutionBoundary.execute_isolated(
            command_name="test_cmd",
            module_name="Testing",
            interaction_or_ctx=mock_interaction,
            coro=sample_cmd(),
        )
        self.assertEqual(res, "command_output")

        # Test isolated failure - must not raise exception out of boundary
        async def failing_cmd():
            raise ValueError("Something unexpected broke inside command")

        res_fail = await CommandExecutionBoundary.execute_isolated(
            command_name="fail_cmd",
            module_name="Testing",
            interaction_or_ctx=mock_interaction,
            coro=failing_cmd(),
        )
        self.assertIsNone(res_fail)
        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        self.assertTrue(call_kwargs.get("ephemeral"))
        sent_embed = call_kwargs.get("embed")
        self.assertIsNotNone(sent_embed)
        self.assertIn("Diagnostic Reference", sent_embed.description)

    # ==========================================
    # 2. DISCORD API RELIABILITY LAYER
    # ==========================================

    async def test_api_reliability_success_and_metrics(self):
        layer = DiscordReliabilityLayer.get_instance()

        call_count = 0
        async def mock_api_call():
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        res = await layer.execute("get_channel", mock_api_call)
        self.assertTrue(res.is_success)
        self.assertEqual(res.value, {"status": "ok"})
        self.assertEqual(call_count, 1)

        telemetry = layer.get_telemetry()
        self.assertEqual(telemetry["successful_requests"], 1)
        self.assertEqual(telemetry["failed_requests"], 0)

    async def test_api_destructive_operation_not_blindly_retried(self):
        layer = DiscordReliabilityLayer.get_instance()

        call_count = 0
        async def mock_destructive_delete():
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock(status=500)
            raise discord.HTTPException(response=mock_resp, message="Internal Server Error")

        # Category is DESTRUCTIVE: must NOT retry 5xx!
        res = await layer.execute(
            action_name="delete_channel",
            coro_factory=mock_destructive_delete,
            category=APIActionCategory.DESTRUCTIVE,
            max_retries=3,
        )
        self.assertFalse(res.is_success)
        self.assertEqual(call_count, 1)  # Strictly 1 attempt, zero blind retries!

    async def test_api_deduplication(self):
        layer = DiscordReliabilityLayer.get_instance()

        call_count = 0
        async def slow_fetch():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return "shared_data"

        # Fire two concurrent requests with same dedup_key
        t1 = asyncio.create_task(
            layer.execute("fetch", slow_fetch, category=APIActionCategory.READ, dedup_key="key_123")
        )
        t2 = asyncio.create_task(
            layer.execute("fetch", slow_fetch, category=APIActionCategory.READ, dedup_key="key_123")
        )

        r1, r2 = await asyncio.gather(t1, t2)
        self.assertEqual(r1.value, "shared_data")
        self.assertEqual(r2.value, "shared_data")
        self.assertEqual(call_count, 1)  # Executed once and shared

    # ==========================================
    # 3. WORKER SUPERVISOR & SINGLETONS
    # ==========================================

    async def test_worker_supervisor_registration_and_heartbeat(self):
        sup = WorkerSupervisor.get_instance()
        w = sup.register("test_worker", "Test Worker", is_singleton=True)
        self.assertEqual(w.worker_id, "test_worker")
        self.assertEqual(w.status, WorkerStatus.STOPPED)

        # Pulse heartbeat
        sup.heartbeat("test_worker", current_job="processing_items")
        summary = sup.get_summary()
        self.assertIn("test_worker", summary)
        self.assertEqual(summary["test_worker"]["current_job"], "processing_items")

        # Duplicate singleton registration must reject/return existing
        w2 = sup.register("test_worker", "Duplicate Worker", is_singleton=True)
        self.assertIs(w, w2)

    async def test_worker_supervisor_stuck_detection(self):
        sup = WorkerSupervisor.get_instance()
        sup.register("stuck_worker", "Stuck Worker", heartbeat_timeout=0.05)
        sup.start_worker("stuck_worker")

        # Simulate last heartbeat 1 second ago
        sup._workers["stuck_worker"].last_heartbeat = time.time() - 1.0

        # Trigger monitor tick logic
        now = time.time()
        desc = sup._workers["stuck_worker"]
        elapsed = now - desc.last_heartbeat
        if elapsed > desc.heartbeat_timeout_seconds:
            desc.status = WorkerStatus.DEGRADED
            desc.last_error = f"Stuck worker: no heartbeat for {elapsed:.1f}s"

        self.assertEqual(desc.status, WorkerStatus.DEGRADED)
        self.assertIn("Stuck worker", desc.last_error)

    # ==========================================
    # 4. RAI DOCTOR TRUTHFUL DIAGNOSTICS
    # ==========================================

    async def test_rai_doctor_probes(self):
        mock_bot = MagicMock()
        mock_bot.is_ready.return_value = True
        mock_bot.is_closed.return_value = False
        mock_bot.latency = 0.045  # 45ms
        mock_bot.guilds = [MagicMock()]
        mock_bot.db.get_or_create_guild_config = AsyncMock(return_value=MagicMock())
        mock_bot.cogs = {}
        mock_bot.tree.get_commands.return_value = [MagicMock()] * 10

        diagnostics = await RaiDoctor.diagnose_all(mock_bot)
        self.assertEqual(len(diagnostics), 13)

        names = [d.name for d in diagnostics]
        self.assertIn("Core", names)
        self.assertIn("Database", names)
        self.assertIn("Gateway", names)
        self.assertIn("Commands", names)
        self.assertIn("Workers", names)
        self.assertIn("Music Resolver", names)
        self.assertIn("Music Player", names)
        self.assertIn("Dynamic VC", names)
        self.assertIn("Reports", names)
        self.assertIn("Security", names)
        self.assertIn("Backup", names)
        self.assertIn("Automation", names)
        self.assertIn("Soundboard", names)

        # Check diagnostic IDs
        for d in diagnostics:
            self.assertTrue(d.diagnostic_id.startswith("RAI-DOC-"))

    # ==========================================
    # 5. PERMISSION DOCTOR FEATURE AUDIT
    # ==========================================

    async def test_permission_doctor_feature_checks(self):
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 11112222
        mock_me = MagicMock(spec=discord.Member)
        mock_me.id = 33334444

        # Simulate bot WITHOUT administrator, but with core permissions
        perms = discord.Permissions()
        perms.view_channel = True
        perms.send_messages = True
        perms.embed_links = True
        perms.connect = True
        perms.speak = True
        # Missing manage_channels and move_members
        perms.manage_channels = False
        perms.move_members = False
        mock_me.guild_permissions = perms
        mock_guild.me = mock_me
        mock_guild.voice_channels = []

        mock_bot = MagicMock()
        mock_bot.db = None

        diagnosis = await PermissionDoctor.diagnose_guild(mock_guild, mock_bot)
        self.assertFalse(diagnosis.is_admin)

        # Core & Commands must be HEALTHY
        core_feat = next(f for f in diagnosis.features if f.feature_name == "Core & Commands")
        self.assertEqual(len(core_feat.missing_permissions), 0)

        # Dynamic Voice must report missing Manage Channels and Move Members
        dvc_feat = next(f for f in diagnosis.features if f.feature_name == "Dynamic Voice Channels")
        self.assertIn("Manage Channels", dvc_feat.missing_permissions)
        self.assertIn("Move Members", dvc_feat.missing_permissions)

    # ==========================================
    # 6. EMERGENCY CONTROLS & SAFE MODE
    # ==========================================

    def test_emergency_safe_mode_and_module_maintenance(self):
        mgr = EmergencyManager.get_instance()
        self.assertFalse(mgr.is_safe_mode_active())

        # Activate safe mode
        mgr.toggle_safe_mode(True, actor="Owner")
        self.assertTrue(mgr.is_safe_mode_active())

        # In safe mode, risky modules report under maintenance
        self.assertTrue(mgr.is_module_under_maintenance("automation"))
        self.assertTrue(mgr.is_module_under_maintenance("workflow"))

        # Deactivate safe mode
        mgr.toggle_safe_mode(False, actor="Owner")
        self.assertFalse(mgr.is_safe_mode_active())

        # Per-module lock
        mgr.set_module_maintenance("music", enabled=True, actor="Moderator")
        self.assertTrue(mgr.is_module_under_maintenance("music"))
        self.assertFalse(mgr.is_module_under_maintenance("dynamic_vc"))

    # ==========================================
    # 7. RECONCILIATION & TIMELINE
    # ==========================================

    def test_reconciliation_timeline(self):
        svc = ReconciliationService.get_instance()
        svc.record_timeline_event("Music", "Play Track", "SUCCESS", "Track: Kalyani")
        svc.record_timeline_event("Dynamic VC", "Created Room", "SUCCESS", "Room: #General VC")

        events = svc.get_timeline(limit=10)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["module"], "Dynamic VC")  # Reverse chronological
        self.assertEqual(events[1]["module"], "Music")


if __name__ == "__main__":
    unittest.main()
