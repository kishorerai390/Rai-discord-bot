"""
Unit and Integration Test Suite for 『RΛI』 Centralized Typed Result Architecture
and Mention Spam Explicit Return States.

Verifies:
1. Result invariants (SUCCESS, FAILURE, PARTIAL, and rejection of contradictory states)
2. Machine-readable ErrorCodes consistency
3. Operation data models (DeleteMessageData, ModerationData, PermissionCheckData, OperationSummary)
4. Detection return states: NO_THREAT, SUSPICIOUS, HIGH_RISK, CRITICAL, IGNORED, INVALID, ERROR
5. Moderation return states: SUCCESS, PERMISSION_DENIED, ROLE_HIERARCHY_BLOCKED, NOT_FOUND, RATE_LIMITED
6. Retryable vs non-retryable classification
7. Pipeline partial success handling (PARTIAL)
8. Fail-safe behavior (no crashes on internal error)
9. SQLite database error tolerance (in-memory survival)
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from core.results import (
    Result,
    ResultStatus,
    ResultError,
    ErrorCodes,
    DeleteMessageData,
    ModerationData,
    PermissionCheckData,
    OperationSummary,
    DatabaseResultData,
)
from core.permission_safety import (
    PermissionResult,
    PermissionFailureType,
)
from database.models import MentionSpamConfig
from security.mention_spam import (
    MentionSpamEngine,
    DetectionStatus,
    DetectionResult,
    MentionSpamResult,
)


class TestResultInvariants(unittest.TestCase):
    """Enforces mathematical invariants on the Result[T] container."""

    def test_01_success_invariant(self):
        """SUCCESS must have success=True and error=None."""
        res = Result.ok(data="payload", incident_id="INC-001")
        self.assertEqual(res.status, ResultStatus.SUCCESS)
        self.assertTrue(res.success)
        self.assertIsNone(res.error)
        self.assertEqual(res.data, "payload")
        self.assertEqual(res.incident_id, "INC-001")
        self.assertTrue(bool(res))

    def test_02_failure_invariant(self):
        """Non-success status must have success=False and an error object."""
        res = Result.fail(
            status=ResultStatus.FAILED,
            code=ErrorCodes.INTERNAL_ERROR,
            message="Internal error occurred",
            retryable=False,
        )
        self.assertEqual(res.status, ResultStatus.FAILED)
        self.assertFalse(res.success)
        self.assertIsNotNone(res.error)
        self.assertEqual(res.error.code, ErrorCodes.INTERNAL_ERROR)
        self.assertFalse(res.error.retryable)

    def test_03_partial_invariant(self):
        """PARTIAL must have status=PARTIAL, success=False, error!=None."""
        res = Result.partial(
            code="PARTIAL_ACTION",
            message="Message deleted, but timeout failed",
            data={"deleted": True, "timed_out": False},
        )
        self.assertEqual(res.status, ResultStatus.PARTIAL)
        self.assertFalse(res.success)
        self.assertIsNotNone(res.error)
        self.assertEqual(res.error.code, "PARTIAL_ACTION")

    def test_04_contradictory_success_false_rejected(self):
        """Attempting to construct Result with status=SUCCESS and success=False must raise ValueError."""
        with self.assertRaises(ValueError):
            Result(status=ResultStatus.SUCCESS, success=False, data=None, error=None)

    def test_05_contradictory_success_with_error_rejected(self):
        """Attempting to construct Result with status=SUCCESS and error populated must raise ValueError."""
        err = ResultError(code="ERR", message="Fault")
        with self.assertRaises(ValueError):
            Result(status=ResultStatus.SUCCESS, success=True, data=None, error=err)

    def test_06_contradictory_failure_true_rejected(self):
        """Attempting to construct non-success with success=True must raise ValueError."""
        err = ResultError(code="ERR", message="Fault")
        with self.assertRaises(ValueError):
            Result(status=ResultStatus.FAILED, success=True, data=None, error=err)

    def test_07_non_success_without_error_rejected(self):
        """Attempting to construct non-success with error=None must raise ValueError."""
        with self.assertRaises(ValueError):
            Result(status=ResultStatus.PERMISSION_DENIED, success=False, data=None, error=None)

    def test_08_retryable_classification(self):
        """Permissions and hierarchy must be non-retryable; rate limits must be retryable."""
        perm_res = Result.permission_denied(
            code=ErrorCodes.MISSING_MANAGE_MESSAGES,
            message="Missing Manage Messages",
        )
        self.assertFalse(perm_res.error.retryable)

        hier_res = Result.role_hierarchy_blocked()
        self.assertFalse(hier_res.error.retryable)

        rate_res = Result.rate_limited()
        self.assertTrue(rate_res.error.retryable)

        disc_err = Result.discord_error(message="Network gateway timeout")
        self.assertTrue(disc_err.error.retryable)

    def test_09_operation_summary_aggregations(self):
        """OperationSummary correctly computes all_success, is_partial, and overall_status."""
        # 1. All success
        all_s = OperationSummary(attempted=5, succeeded=5, failed=0)
        self.assertTrue(all_s.is_all_success)
        self.assertFalse(all_s.is_partial)
        self.assertEqual(all_s.overall_status, ResultStatus.SUCCESS)

        # 2. Partial
        part = OperationSummary(attempted=5, succeeded=3, failed=2)
        self.assertFalse(part.is_all_success)
        self.assertTrue(part.is_partial)
        self.assertEqual(part.overall_status, ResultStatus.PARTIAL)

        # 3. All failed due to permissions
        denied = OperationSummary(attempted=3, succeeded=0, failed=3, permission_denied=3)
        self.assertEqual(denied.overall_status, ResultStatus.PERMISSION_DENIED)

    def test_10_permission_result_to_result_adapter(self):
        """PermissionResult seamlessly converts into core Result."""
        p_res = PermissionResult(
            success=False,
            action="delete_message",
            guild_id=123,
            channel_id=456,
            failure_type=PermissionFailureType.ROLE_HIERARCHY_VIOLATION,
            reason="Role hierarchy blocked",
            incident_id="PF-001",
        )
        core_res = p_res.to_result()
        self.assertEqual(core_res.status, ResultStatus.ROLE_HIERARCHY_BLOCKED)
        self.assertFalse(core_res.success)
        self.assertEqual(core_res.error.code, ErrorCodes.ROLE_HIERARCHY_BLOCKED)
        self.assertEqual(core_res.incident_id, "PF-001")


class TestMentionSpamExplicitReturnStates(unittest.IsolatedAsyncioTestCase):
    """Verifies all explicit return states for Mass User Mention Spam Protection."""

    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.db = AsyncMock()
        self.engine = MentionSpamEngine(self.bot)

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 5000000001
        self.guild.name = "Neo Citadel"
        self.guild.owner_id = 999999999

        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = 7000000001
        self.bot_member.top_role = MagicMock()
        self.bot_member.top_role.position = 50
        self.guild.me = self.bot_member

        self.default_cfg = MentionSpamConfig(
            guild_id=self.guild.id,
            enabled=True,
            warning_threshold=5,
            high_threshold=10,
            critical_threshold=20,
            window_seconds=10,
            cross_channel_threshold=3,
            repeat_message_threshold=3,
            action_low="delete",
            action_high="timeout",
            action_critical="timeout_and_purge",
            timeout_duration_high=600,
            timeout_duration_critical=86400,
            purge_window_seconds=60,
            staff_exempt=True,
        )
        self.bot.db.get_or_create_mention_spam_config.return_value = self.default_cfg
        self.bot.db.is_whitelisted.return_value = False
        self.bot.db.get_logging_config.return_value = MagicMock(security_channel_id=None, moderation_channel_id=None)

    def _create_message(
        self,
        author_id: int,
        content: str,
        target_ids: list[int] = None,
        is_bot: bool = False,
        is_staff: bool = False,
        author_role_pos: int = 10,
    ) -> discord.Message:
        msg = MagicMock(spec=discord.Message)
        msg.id = 100000000 + author_id
        msg.guild = self.guild
        msg.content = content

        author = MagicMock(spec=discord.Member)
        author.id = author_id
        author.name = f"User_{author_id}"
        author.display_name = f"User_{author_id}"
        author.discriminator = "0001"
        author.bot = is_bot
        author.guild = self.guild
        author.top_role = MagicMock()
        author.top_role.position = author_role_pos

        author.guild_permissions = MagicMock()
        author.guild_permissions.administrator = is_staff
        author.guild_permissions.manage_guild = is_staff
        author.guild_permissions.moderate_members = is_staff

        author.timeout = AsyncMock()
        msg.author = author

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 201
        channel.name = "general"
        channel.purge = AsyncMock(return_value=[])
        msg.channel = channel
        self.guild.get_channel.return_value = channel

        msg.delete = AsyncMock()

        if target_ids is not None:
            mentions = []
            for tid in target_ids:
                m = MagicMock(spec=discord.User)
                m.id = tid
                mentions.append(m)
            msg.mentions = mentions
        else:
            msg.mentions = []

        return msg

    async def test_11_detection_state_no_threat(self):
        """Normal messages explicitly return NO_THREAT, not False."""
        msg = self._create_message(author_id=101, content="Hello team", target_ids=[])
        res = await self.engine.detect_threat(msg, self.default_cfg)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, DetectionStatus.NO_THREAT)
        self.assertEqual(res.data.mention_count, 0)

        # Full inspect_message returns Result[MentionSpamResult] with detected=False
        inspect_res = await self.engine.inspect_message(msg)
        self.assertTrue(inspect_res.success)
        self.assertFalse(inspect_res.data.detected)
        self.assertEqual(inspect_res.data.severity, "NO_THREAT")
        self.assertEqual(inspect_res.data.detection.status, DetectionStatus.NO_THREAT)

    async def test_12_detection_state_suspicious(self):
        """5 mentions reaches warning threshold, explicitly returning SUSPICIOUS."""
        targets = [200 + i for i in range(5)]
        msg = self._create_message(author_id=102, content="pings", target_ids=targets)
        res = await self.engine.detect_threat(msg, self.default_cfg)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, DetectionStatus.SUSPICIOUS)
        self.assertEqual(res.data.mention_count, 5)

    async def test_13_detection_state_high_risk(self):
        """10 mentions triggers HIGH_RISK detection status."""
        targets = [300 + i for i in range(10)]
        msg = self._create_message(author_id=103, content="pings", target_ids=targets)
        res = await self.engine.detect_threat(msg, self.default_cfg)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, DetectionStatus.HIGH_RISK)
        self.assertEqual(res.data.mention_count, 10)

    async def test_14_detection_state_critical(self):
        """25 mentions triggers CRITICAL detection status."""
        targets = [400 + i for i in range(25)]
        msg = self._create_message(author_id=104, content="pings", target_ids=targets)
        res = await self.engine.detect_threat(msg, self.default_cfg)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, DetectionStatus.CRITICAL)
        self.assertEqual(res.data.mention_count, 25)

    async def test_15_detection_state_ignored_bot(self):
        """Bot messages return SKIPPED with IGNORED detection status."""
        targets = [500 + i for i in range(20)]
        msg = self._create_message(author_id=105, content="bot ping", target_ids=targets, is_bot=True)
        res = await self.engine.detect_threat(msg, self.default_cfg)
        self.assertFalse(res.success)
        self.assertEqual(res.status, ResultStatus.SKIPPED)
        self.assertEqual(res.data.status, DetectionStatus.IGNORED)

    async def test_16_detection_state_ignored_staff(self):
        """Exempt staff member returns SKIPPED with IGNORED status."""
        targets = [600 + i for i in range(20)]
        msg = self._create_message(author_id=106, content="announcement", target_ids=targets, is_staff=True)
        res = await self.engine.detect_threat(msg, self.default_cfg)
        self.assertFalse(res.success)
        self.assertEqual(res.status, ResultStatus.SKIPPED)
        self.assertEqual(res.data.status, DetectionStatus.IGNORED)

    async def test_17_moderation_delete_message_states(self):
        """delete_message_safe returns explicit SUCCESS, PERMISSION_DENIED, NOT_FOUND, RATE_LIMITED."""
        msg = self._create_message(author_id=107, content="spam", target_ids=[1, 2])

        # 1. SUCCESS
        res_ok = await self.engine.delete_message_safe(msg)
        self.assertEqual(res_ok.status, ResultStatus.SUCCESS)
        self.assertTrue(res_ok.success)
        self.assertTrue(res_ok.data.deleted)

        # 2. PERMISSION_DENIED (discord.Forbidden)
        msg.delete.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")
        res_perm = await self.engine.delete_message_safe(msg)
        self.assertEqual(res_perm.status, ResultStatus.PERMISSION_DENIED)
        self.assertFalse(res_perm.success)
        self.assertEqual(res_perm.error.code, ErrorCodes.MISSING_MANAGE_MESSAGES)
        self.assertFalse(res_perm.error.retryable)

        # 3. NOT_FOUND (discord.NotFound)
        msg.delete.side_effect = discord.NotFound(MagicMock(), "Unknown Message")
        res_nf = await self.engine.delete_message_safe(msg)
        self.assertEqual(res_nf.status, ResultStatus.NOT_FOUND)
        self.assertFalse(res_nf.success)
        self.assertEqual(res_nf.error.code, ErrorCodes.MESSAGE_NOT_FOUND)
        self.assertFalse(res_nf.error.retryable)

        # 4. RATE_LIMITED (HTTPException 429)
        mock_http = discord.HTTPException(MagicMock(), "Rate limited")
        mock_http.status = 429
        msg.delete.side_effect = mock_http
        res_rl = await self.engine.delete_message_safe(msg)
        self.assertEqual(res_rl.status, ResultStatus.RATE_LIMITED)
        self.assertTrue(res_rl.error.retryable)

    async def test_18_moderation_apply_restriction_states(self):
        """apply_restriction_safe returns SUCCESS, PERMISSION_DENIED, ROLE_HIERARCHY_BLOCKED, INVALID."""
        # 1. SUCCESS
        msg = self._create_message(author_id=108, content="spam", author_role_pos=10)
        res_ok = await self.engine.apply_restriction_safe(msg.author, 600, "HIGH")
        self.assertEqual(res_ok.status, ResultStatus.SUCCESS)
        self.assertEqual(res_ok.data.duration_seconds, 600)

        # 2. ROLE_HIERARCHY_BLOCKED (author position >= bot position 50)
        msg_high_role = self._create_message(author_id=109, content="spam", author_role_pos=60)
        res_hier = await self.engine.apply_restriction_safe(msg_high_role.author, 600, "HIGH")
        self.assertEqual(res_hier.status, ResultStatus.ROLE_HIERARCHY_BLOCKED)
        self.assertEqual(res_hier.error.code, ErrorCodes.ROLE_HIERARCHY_BLOCKED)
        self.assertFalse(res_hier.error.retryable)

        # 3. PERMISSION_DENIED (discord.Forbidden)
        msg.author.timeout.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")
        res_perm = await self.engine.apply_restriction_safe(msg.author, 600, "HIGH")
        self.assertEqual(res_perm.status, ResultStatus.PERMISSION_DENIED)
        self.assertEqual(res_perm.error.code, ErrorCodes.MISSING_MODERATE_MEMBERS)
        self.assertFalse(res_perm.error.retryable)

        # 4. INVALID (duration <= 0)
        res_inv = await self.engine.apply_restriction_safe(msg.author, -10, "HIGH")
        self.assertEqual(res_inv.status, ResultStatus.INVALID)
        self.assertEqual(res_inv.error.code, ErrorCodes.INVALID_DURATION)

    async def test_19_pipeline_partial_success(self):
        """When message deletion succeeds but timeout fails, pipeline reports PARTIAL."""
        # Target author has higher role (role hierarchy blocked)
        targets = [700 + i for i in range(10)]
        msg = self._create_message(author_id=110, content="spam", target_ids=targets, author_role_pos=60)

        res = await self.engine.inspect_message(msg)
        # Message was deleted
        msg.delete.assert_awaited_once()
        # Overall pipeline outcome is PARTIAL
        self.assertEqual(res.status, ResultStatus.PARTIAL)
        self.assertFalse(res.success)
        self.assertTrue(res.data.detected)
        self.assertEqual(res.data.action_status, ResultStatus.PARTIAL)
        self.assertEqual(res.data.delete_result.status, ResultStatus.SUCCESS)
        self.assertEqual(res.data.restriction_result.status, ResultStatus.ROLE_HIERARCHY_BLOCKED)

    async def test_20_database_error_isolation(self):
        """Database error does not prevent message deletion and is recorded as DATABASE_ERROR."""
        self.bot.db.create_mention_spam_incident.side_effect = RuntimeError("SQLite Disk I/O error")

        targets = [800 + i for i in range(10)]
        msg = self._create_message(author_id=111, content="spam", target_ids=targets, author_role_pos=10)

        res = await self.engine.inspect_message(msg)
        # Security actions still succeeded!
        msg.delete.assert_awaited_once()
        msg.author.timeout.assert_awaited_once()
        # Pipeline action status is SUCCESS
        self.assertEqual(res.data.action_status, ResultStatus.SUCCESS)
        # Database result specifically indicates DATABASE_ERROR
        self.assertEqual(res.data.db_result.status, ResultStatus.DATABASE_ERROR)
        self.assertEqual(res.data.db_result.error.code, ErrorCodes.DATABASE_ERROR)

    async def test_21_fail_safe_internal_error(self):
        """Uncaught exception in extractor or detector returns INTERNAL_ERROR without crashing."""
        msg = self._create_message(author_id=112, content="spam", target_ids=[1])
        # Simulate unexpected internal failure
        with patch.object(self.engine, "detect_threat", side_effect=ValueError("Corrupted memory pointer")):
            res = await self.engine.inspect_message(msg)
            self.assertEqual(res.status, ResultStatus.INTERNAL_ERROR)
            self.assertFalse(res.success)
            self.assertEqual(res.data.detection.status, DetectionStatus.ERROR)
            self.assertEqual(res.error.code, ErrorCodes.INTERNAL_ERROR)


if __name__ == "__main__":
    unittest.main()
