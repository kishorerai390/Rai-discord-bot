"""
Comprehensive Automated Test Suite for Centralized Discord Permission-Failure Handling System in 『RΛI』.

Tests all required test cases:
1. Missing Manage Messages (action: delete_message)
2. Missing Moderate Members (action: timeout_member)
3. Missing Ban Members (action: ban_member)
4. Missing Kick Members (action: kick_member)
5. Missing Manage Channels (action: lock_channel)
6. Missing Manage Roles (action: manage_roles)
7. Missing View Audit Log (action: view_audit_logs)
8. Missing Connect (action: connect_voice)
9. Missing Speak (action: speak_voice)
10. Role hierarchy failure (target role >= bot role, or target is owner)
11. Repeated permission failure & deduplication (prevents alert spam, counts blocked ops)
12. Multi-guild isolation (failures in Guild A do not affect Guild B)
13. Music subsystem isolation (voice permission error isolates to music, security unaffected)
14. Security threat fallback (detection SUCCESS, moderation FAILED, fallback executed, alert dispatched)
15. Database failure resilience (DB error when recording failure does not crash bot)
16. Never claim success on rejection (format_user_message reports failure clearly)
17. Permission audit engine (matrix correctly evaluates AVAILABLE, PARTIAL, UNAVAILABLE)
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from core.permission_safety import (
    PermissionFailureType,
    PermissionResult,
    PermissionFailureTracker,
    permission_safe_execute,
    audit_guild_permissions,
    create_permission_audit_embed,
    check_role_hierarchy,
)


class TestPermissionSafetySystem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Reset tracker singleton for clean test isolation
        self.tracker = PermissionFailureTracker(window_seconds=60.0)
        PermissionFailureTracker._instance = self.tracker

        self.bot = MagicMock()
        self.bot.db = AsyncMock()

        # Guild A
        self.guild_a = MagicMock(spec=discord.Guild)
        self.guild_a.id = 10001
        self.guild_a.name = "Neo-Tokyo Alpha"
        self.guild_a.owner_id = 99999999

        # Bot Member A
        self.bot_member_a = MagicMock(spec=discord.Member)
        self.bot_member_a.id = 55555555
        self.bot_member_a.top_role = MagicMock()
        self.bot_member_a.top_role.name = "RAI Core"
        self.bot_member_a.top_role.position = 50
        self.bot_member_a.guild_permissions = MagicMock()
        # Default all permissions to False for explicit testing
        for perm in [
            "administrator", "manage_messages", "read_message_history",
            "moderate_members", "kick_members", "ban_members",
            "manage_channels", "manage_roles", "view_audit_log",
            "connect", "speak", "move_members"
        ]:
            setattr(self.bot_member_a.guild_permissions, perm, False)

        self.guild_a.me = self.bot_member_a

        # Guild B (for multi-tenant isolation testing)
        self.guild_b = MagicMock(spec=discord.Guild)
        self.guild_b.id = 20002
        self.guild_b.name = "Neo-Tokyo Beta"
        self.guild_b.owner_id = 88888888
        self.bot_member_b = MagicMock(spec=discord.Member)
        self.bot_member_b.id = 55555555
        self.bot_member_b.top_role = MagicMock()
        self.bot_member_b.top_role.position = 100
        self.bot_member_b.guild_permissions = MagicMock()
        # Guild B has all permissions
        for perm in [
            "administrator", "manage_messages", "read_message_history",
            "moderate_members", "kick_members", "ban_members",
            "manage_channels", "manage_roles", "view_audit_log",
            "connect", "speak", "move_members"
        ]:
            setattr(self.bot_member_b.guild_permissions, perm, True)
        self.guild_b.me = self.bot_member_b

    # -------------------------------------------------------------------------
    # Case 1: Missing Manage Messages
    # -------------------------------------------------------------------------
    async def test_01_missing_manage_messages(self):
        """Action delete_message fails pre-flight when bot lacks manage_messages."""
        op = AsyncMock()
        result = await permission_safe_execute(
            action="delete_message",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.MISSING_BOT_PERMISSION)
        self.assertIn("manage_messages", result.missing_permissions)
        self.assertIn("Manage Messages", result.reason)
        op.assert_not_awaited()  # Blocked before calling Discord API

    # -------------------------------------------------------------------------
    # Case 2: Missing Moderate Members
    # -------------------------------------------------------------------------
    async def test_02_missing_moderate_members(self):
        """Action timeout_member fails pre-flight when bot lacks moderate_members."""
        op = AsyncMock()
        result = await permission_safe_execute(
            action="timeout_member",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.MISSING_BOT_PERMISSION)
        self.assertIn("moderate_members", result.missing_permissions)
        op.assert_not_awaited()

    # -------------------------------------------------------------------------
    # Case 3: Missing Ban Members
    # -------------------------------------------------------------------------
    async def test_03_missing_ban_members(self):
        """Action ban_member fails pre-flight when bot lacks ban_members."""
        op = AsyncMock()
        result = await permission_safe_execute(
            action="ban_member",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.MISSING_BOT_PERMISSION)
        self.assertIn("ban_members", result.missing_permissions)
        op.assert_not_awaited()

    # -------------------------------------------------------------------------
    # Case 4: Missing Kick Members
    # -------------------------------------------------------------------------
    async def test_04_missing_kick_members(self):
        """Action kick_member fails pre-flight when bot lacks kick_members."""
        op = AsyncMock()
        result = await permission_safe_execute(
            action="kick_member",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.MISSING_BOT_PERMISSION)
        self.assertIn("kick_members", result.missing_permissions)
        op.assert_not_awaited()

    # -------------------------------------------------------------------------
    # Case 5: Missing Manage Channels
    # -------------------------------------------------------------------------
    async def test_05_missing_manage_channels(self):
        """Action lock_channel fails pre-flight when bot lacks manage_channels."""
        op = AsyncMock()
        result = await permission_safe_execute(
            action="lock_channel",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.MISSING_BOT_PERMISSION)
        self.assertIn("manage_channels", result.missing_permissions)
        op.assert_not_awaited()

    # -------------------------------------------------------------------------
    # Case 6: Missing Manage Roles
    # -------------------------------------------------------------------------
    async def test_06_missing_manage_roles(self):
        """Action manage_roles fails pre-flight when bot lacks manage_roles."""
        op = AsyncMock()
        result = await permission_safe_execute(
            action="manage_roles",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.MISSING_BOT_PERMISSION)
        self.assertIn("manage_roles", result.missing_permissions)
        op.assert_not_awaited()

    # -------------------------------------------------------------------------
    # Case 7: Missing View Audit Log
    # -------------------------------------------------------------------------
    async def test_07_missing_view_audit_log(self):
        """Action view_audit_logs fails pre-flight when bot lacks view_audit_log."""
        op = AsyncMock()
        result = await permission_safe_execute(
            action="view_audit_logs",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.MISSING_BOT_PERMISSION)
        self.assertIn("view_audit_log", result.missing_permissions)
        op.assert_not_awaited()

    # -------------------------------------------------------------------------
    # Case 8: Missing Connect in Voice
    # -------------------------------------------------------------------------
    async def test_08_missing_connect_voice(self):
        """Action connect_voice fails pre-flight when bot lacks connect."""
        op = AsyncMock()
        result = await permission_safe_execute(
            action="connect_voice",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.MISSING_BOT_PERMISSION)
        self.assertIn("connect", result.missing_permissions)
        op.assert_not_awaited()

    # -------------------------------------------------------------------------
    # Case 9: Missing Speak in Voice
    # -------------------------------------------------------------------------
    async def test_09_missing_speak_voice(self):
        """Action speak_voice fails pre-flight when bot lacks speak."""
        op = AsyncMock()
        result = await permission_safe_execute(
            action="speak_voice",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.MISSING_BOT_PERMISSION)
        self.assertIn("speak", result.missing_permissions)
        op.assert_not_awaited()

    # -------------------------------------------------------------------------
    # Case 10: Role Hierarchy Failure
    # -------------------------------------------------------------------------
    async def test_10_role_hierarchy_failure(self):
        """Role hierarchy check rejects action when target role is higher than bot's."""
        self.bot_member_a.guild_permissions.moderate_members = True

        target_member = MagicMock(spec=discord.Member)
        target_member.id = 77777777
        target_member.top_role = MagicMock()
        target_member.top_role.name = "Server Admin"
        target_member.top_role.position = 80  # Bot position is 50

        op = AsyncMock()
        result = await permission_safe_execute(
            action="timeout_member",
            guild=self.guild_a,
            target=target_member,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_type, PermissionFailureType.ROLE_HIERARCHY_VIOLATION)
        self.assertIn("higher than or equal to RAI's highest role", result.reason)
        op.assert_not_awaited()

    # -------------------------------------------------------------------------
    # Case 11: Repeated Permission Failure & Deduplication
    # -------------------------------------------------------------------------
    async def test_11_repeated_permission_failure_deduplication(self):
        """Deduplication tracker suppresses duplicate alert spam and tracks blocked count."""
        op = AsyncMock()

        # 1st attempt: Should trigger alert
        res1 = await permission_safe_execute(
            action="delete_message",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(res1.success)

        # Send 50 repeating attempts in same window
        for _ in range(50):
            await permission_safe_execute(
                action="delete_message",
                guild=self.guild_a,
                operation=op,
                bot=self.bot,
            )

        # Check tracker summary
        summary = self.tracker.get_guild_summary(self.guild_a.id)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["count"], 51)
        self.assertEqual(summary[0]["action"], "delete_message")

    # -------------------------------------------------------------------------
    # Case 12: Multi-Guild Isolation
    # -------------------------------------------------------------------------
    async def test_12_multi_guild_isolation(self):
        """Missing permission in Guild A does not affect or disable Guild B."""
        op_a = AsyncMock()
        op_b = AsyncMock(return_value="executed_in_b")

        # Guild A fails
        res_a = await permission_safe_execute(
            action="delete_message",
            guild=self.guild_a,
            operation=op_a,
            bot=self.bot,
        )
        self.assertFalse(res_a.success)
        op_a.assert_not_awaited()

        # Guild B succeeds independently
        res_b = await permission_safe_execute(
            action="delete_message",
            guild=self.guild_b,
            operation=op_b,
            bot=self.bot,
        )
        self.assertTrue(res_b.success)
        self.assertEqual(res_b.result_data, "executed_in_b")
        op_b.assert_awaited_once()

        # Tracker for Guild B has no failures
        self.assertEqual(len(self.tracker.get_guild_summary(self.guild_b.id)), 0)

    # -------------------------------------------------------------------------
    # Case 13: Music Subsystem Isolation
    # -------------------------------------------------------------------------
    async def test_13_music_permission_failure_isolated(self):
        """Voice permission failure handles gracefully without impacting Security."""
        # Bot lacks speak permission
        self.bot_member_a.guild_permissions.connect = True
        self.bot_member_a.guild_permissions.speak = False

        music_session = MagicMock()
        music_session.is_degraded = False

        async def music_fallback():
            music_session.is_degraded = True
            return "degraded_state"

        op = AsyncMock()
        res = await permission_safe_execute(
            action="speak_voice",
            guild=self.guild_a,
            operation=op,
            subsystem="Music",
            fallback=music_fallback,
            bot=self.bot,
        )

        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.fallback_result, "degraded_state")
        self.assertTrue(music_session.is_degraded)
        self.assertEqual(res.subsystem, "Music")

    # -------------------------------------------------------------------------
    # Case 14: Security Threat Fallback & Alert Dispatch
    # -------------------------------------------------------------------------
    async def test_14_security_threat_fallback_and_alert(self):
        """Security threat detection succeeds, automatic moderation fails safely, fallback triggers."""
        # Bot lacks moderate_members
        notify_ch = MagicMock(spec=discord.TextChannel)
        notify_ch.name = "security-alerts"
        notify_ch.send = AsyncMock()

        fallback_triggered = False

        async def fallback_quarantine():
            nonlocal fallback_triggered
            fallback_triggered = True
            return "quarantine_flagged"

        op = AsyncMock()
        res = await permission_safe_execute(
            action="timeout_member",
            guild=self.guild_a,
            operation=op,
            subsystem="Security",
            fallback=fallback_quarantine,
            notify_channel=notify_ch,
            security_threat_context="Mass user mention raid (45 mentions)",
            bot=self.bot,
        )

        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertTrue(fallback_triggered)

        # Verify staff alert was dispatched reporting Detection: SUCCESS, Moderation: FAILED
        notify_ch.send.assert_awaited_once()
        embed = notify_ch.send.call_args[1]["embed"]
        self.assertIn("SECURITY ALERT", embed.title)
        self.assertIn("Detection:** `SUCCESS`", embed.description)
        self.assertIn("Automatic moderation:** `FAILED`", embed.description)
        self.assertIn("Mass user mention raid", embed.description)

        # Verify no mass mentions allowed
        allowed_mentions = notify_ch.send.call_args[1]["allowed_mentions"]
        self.assertFalse(allowed_mentions.everyone)

    # -------------------------------------------------------------------------
    # Case 15: Database Failure Resilience
    # -------------------------------------------------------------------------
    async def test_15_database_failure_resilience(self):
        """Database exception while logging permission failure does not crash bot."""
        self.bot.db.record_permission_failure.side_effect = RuntimeError("SQLite database is locked")

        op = AsyncMock()
        res = await permission_safe_execute(
            action="delete_message",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        self.assertFalse(res.success)
        # Did not raise uncaught exception

    # -------------------------------------------------------------------------
    # Case 16: Never Claim Success on Rejection
    # -------------------------------------------------------------------------
    async def test_16_never_claim_success(self):
        """format_user_message strictly outputs ❌ when operation fails."""
        op = AsyncMock()
        res = await permission_safe_execute(
            action="ban_member",
            guild=self.guild_a,
            operation=op,
            bot=self.bot,
        )
        msg = res.format_user_message()
        self.assertTrue(msg.startswith("❌"))
        self.assertIn("could not be completed", msg)
        self.assertNotIn("✅", msg)

    # -------------------------------------------------------------------------
    # Case 17: Permission Audit Matrix
    # -------------------------------------------------------------------------
    async def test_17_permission_audit_matrix(self):
        """audit_guild_permissions and create_permission_audit_embed accurately evaluate status."""
        # Guild A has no permissions -> UNAVAILABLE / PARTIAL
        audit_a = audit_guild_permissions(self.guild_a)
        self.assertIn(audit_a["overall_status"], ("PARTIAL", "UNAVAILABLE"))
        self.assertFalse(audit_a["is_administrator"])

        embed_a = create_permission_audit_embed(self.guild_a)
        self.assertIn("PERMISSION AUDIT MATRIX", embed_a.title)

        # Guild B has administrator bypass -> AVAILABLE
        audit_b = audit_guild_permissions(self.guild_b)
        self.assertEqual(audit_b["overall_status"], "AVAILABLE")
        self.assertTrue(audit_b["is_administrator"])


if __name__ == "__main__":
    unittest.main()
