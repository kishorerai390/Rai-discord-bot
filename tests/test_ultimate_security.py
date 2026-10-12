"""
Comprehensive Test Suite for Raivora — Ultimate Auto Security Upgrade.
Tests all requirements across Phases 2 through 7:
- Owner-only @everyone and @here graduated punishment
- Anti-nuke sliding window, event correlation, and severity scoring
- Anti-raid join burst detection, account age quarantine, and auto-recovery
- Permission & role security monitoring and reversion
- Trusted user allowlist management
- Bot hierarchy safeguards and non-destructive diagnostics
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from config import Colors
from cogs.security import SecurityCog
from database.models import (
    MentionProtectionConfig,
    MentionViolation,
    TrustedSecurityUser,
    AntiNukeConfig,
    AntiRaidConfig,
    SecurityIncident,
)
from security.antinuke import AntiNukeEngine, ACTION_SEVERITY_WEIGHTS
from utils.permissions import check_bot_hierarchy, is_verified_owner_or_trusted


class MockRole:
    def __init__(self, name: str, position: int, permissions: discord.Permissions = None, is_default: bool = False):
        self.name = name
        self.position = position
        self.permissions = permissions or discord.Permissions.none()
        self._is_default = is_default

    def is_default(self) -> bool:
        return self._is_default

    def __ge__(self, other):
        if not isinstance(other, MockRole):
            return NotImplemented
        return self.position >= other.position

    def __gt__(self, other):
        if not isinstance(other, MockRole):
            return NotImplemented
        return self.position > other.position

    def __lt__(self, other):
        if not isinstance(other, MockRole):
            return NotImplemented
        return self.position < other.position

    def __le__(self, other):
        if not isinstance(other, MockRole):
            return NotImplemented
        return self.position <= other.position


class TestUltimateSecurity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.user.id = 1554732669072445532
        self.bot.db = MagicMock()

        # Database mocks
        self.bot.db.get_logging_config = AsyncMock(return_value=MagicMock(
            security_channel_id=1546593526073135107,
            moderation_channel_id=None,
            general_channel_id=None,
        ))
        self.bot.db.get_security_state = AsyncMock(return_value=MagicMock(emergency_stop=False, lockdown_enabled=False))
        self.bot.db.get_security_config = AsyncMock(return_value=MagicMock(
            channel_delete_limit=3,
            channel_delete_window=15,
            role_delete_limit=3,
            role_delete_window=15,
            ban_limit=3,
            ban_window=15,
            punishment="timeout",
        ))
        self.bot.db.record_security_incident = AsyncMock()
        self.bot.db.record_violation = AsyncMock()
        self.bot.db.record_mention_violation = AsyncMock()
        self.bot.db.count_recent_mention_violations = AsyncMock(return_value=0)
        self.bot.db.is_user_trusted = AsyncMock(return_value=False)
        self.bot.db.is_whitelisted = AsyncMock(return_value=False)
        self.bot.db.record_permission_audit = AsyncMock()
        self.bot.db.set_lockdown = AsyncMock()
        self.bot.db.get_anti_nuke_config = AsyncMock(return_value=AntiNukeConfig(guild_id=1457382179981099090))
        self.bot.db.get_anti_raid_config = AsyncMock(return_value=AntiRaidConfig(guild_id=1457382179981099090))
        self.bot.db.get_mention_protection_config = AsyncMock(return_value=MentionProtectionConfig(guild_id=1457382179981099090))

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "Ultimate Security Test Guild"
        self.guild.owner_id = 999111222  # Verified Server Owner ID

        # Bot member
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = self.bot.user.id
        self.bot_member.top_role = MockRole("Raivora Sentinel", 50)
        self.guild.me = self.bot_member

        self.cog = SecurityCog(self.bot)
        self.antinuke = AntiNukeEngine(self.bot)

    # =========================================================================
    # SECTION 2: OWNER-ONLY @EVERYONE AND @HERE PROTECTION
    # =========================================================================

    async def test_owner_mention_is_permitted(self):
        """Verified server owner ID is always permitted to ping @everyone."""
        owner = MagicMock(spec=discord.Member)
        owner.id = self.guild.owner_id
        owner.guild = self.guild
        owner.bot = False
        owner.name = "VerifiedOwner"
        owner.roles = []

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.author = owner
        message.webhook_id = None
        message.mention_everyone = True
        message.content = "@everyone Server announcement"
        message.delete = AsyncMock()

        await self.cog._handle_everyone_mention(message)

        # Message must not be deleted, owner must not be kicked or timed out
        message.delete.assert_not_called()
        owner.kick.assert_not_called()
        owner.timeout.assert_not_called()

    async def test_trusted_allowlist_user_is_permitted(self):
        """User on trusted_security_users allowlist is permitted to ping @everyone."""
        trusted_user = MagicMock(spec=discord.Member)
        trusted_user.id = 777888999
        trusted_user.guild = self.guild
        trusted_user.bot = False
        trusted_user.name = "TrustedOfficer"
        trusted_user.roles = []

        self.bot.db.is_user_trusted = AsyncMock(return_value=True)

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.author = trusted_user
        message.webhook_id = None
        message.mention_everyone = True
        message.content = "Authorized ping @everyone"
        message.delete = AsyncMock()

        await self.cog._handle_everyone_mention(message)

        message.delete.assert_not_called()
        trusted_user.kick.assert_not_called()

    async def test_graduated_punishment_level_1_warns_and_deletes(self):
        """Level 1 punishment deletes message and warns user, no kick or timeout."""
        member = MagicMock(spec=discord.Member)
        member.id = 444555666
        member.guild = self.guild
        member.bot = False
        member.name = "FirstTimeViolator"
        member.roles = []
        member.top_role = MockRole("Member", 5)
        member.send = AsyncMock()
        member.timeout = AsyncMock()
        member.kick = AsyncMock()

        self.bot.db.get_mention_protection_config = AsyncMock(return_value=MentionProtectionConfig(
            guild_id=self.guild.id,
            enabled=True,
            punishment_level=1,
            delete_message=True,
        ))
        self.bot.db.count_recent_mention_violations = AsyncMock(return_value=0)

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = MagicMock(name="chat")
        message.channel.id = 11111
        message.channel.name = "general"
        message.author = member
        message.webhook_id = None
        message.mention_everyone = True
        message.content = "@everyone check this out"
        message.delete = AsyncMock()

        await self.cog._handle_everyone_mention(message)

        # Message deleted
        message.delete.assert_awaited_once()
        # Warned via DM
        member.send.assert_awaited_once()
        # NOT timed out or kicked
        member.timeout.assert_not_called()
        member.kick.assert_not_called()
        # Violation recorded
        self.bot.db.record_mention_violation.assert_awaited_once()

    async def test_graduated_punishment_level_2_timeouts(self):
        """Level 2 punishment applies timeout for configured duration."""
        member = MagicMock(spec=discord.Member)
        member.id = 444555666
        member.guild = self.guild
        member.bot = False
        member.name = "RepeatViolator"
        member.roles = []
        member.top_role = MockRole("Member", 5)
        member.timeout = AsyncMock()
        member.kick = AsyncMock()

        self.bot.db.get_mention_protection_config = AsyncMock(return_value=MentionProtectionConfig(
            guild_id=self.guild.id,
            enabled=True,
            punishment_level=2,
            timeout_duration_seconds=600,
        ))

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = MagicMock()
        message.channel.id = 11111
        message.channel.name = "general"
        message.author = member
        message.webhook_id = None
        message.mention_everyone = True
        message.content = "Hey @here look"
        message.delete = AsyncMock()

        await self.cog._handle_everyone_mention(message)

        message.delete.assert_awaited_once()
        member.timeout.assert_awaited_once()
        member.kick.assert_not_called()

    async def test_graduated_punishment_level_3_kicks(self):
        """Level 3 punishment kicks member from server."""
        member = MagicMock(spec=discord.Member)
        member.id = 444555666
        member.guild = self.guild
        member.bot = False
        member.name = "SevereAbuser"
        member.roles = []
        member.top_role = MockRole("Member", 5)
        member.kick = AsyncMock()
        member.send = AsyncMock()

        self.bot.db.get_mention_protection_config = AsyncMock(return_value=MentionProtectionConfig(
            guild_id=self.guild.id,
            enabled=True,
            punishment_level=3,
        ))

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = MagicMock()
        message.channel.id = 11111
        message.channel.name = "general"
        message.author = member
        message.webhook_id = None
        message.mention_everyone = True
        message.content = "@everyone attack"
        message.delete = AsyncMock()

        await self.cog._handle_everyone_mention(message)

        message.delete.assert_awaited_once()
        member.kick.assert_awaited_once()

    async def test_hierarchy_safeguard_prevents_kick_of_higher_role(self):
        """Bot never fails or illegally attempts to moderate users above it in role hierarchy."""
        senior_admin = MagicMock(spec=discord.Member)
        senior_admin.id = 888999111
        senior_admin.guild = self.guild
        senior_admin.bot = False
        senior_admin.name = "CoOwnerRole"
        senior_admin.roles = []
        # Role higher than bot top role (60 > 50)
        senior_admin.top_role = MockRole("Server VIP / Higher Admin", 60)
        senior_admin.kick = AsyncMock()
        senior_admin.timeout = AsyncMock()

        self.bot.db.get_mention_protection_config = AsyncMock(return_value=MentionProtectionConfig(
            guild_id=self.guild.id,
            punishment_level=3,
        ))

        can_mod, reason = check_bot_hierarchy(senior_admin, self.bot_member)
        self.assertFalse(can_mod)
        self.assertIn("equal or higher", reason)

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = MagicMock()
        message.channel.id = 11111
        message.channel.name = "general"
        message.author = senior_admin
        message.webhook_id = None
        message.mention_everyone = True
        message.content = "@everyone hello"
        message.delete = AsyncMock()

        await self.cog._handle_everyone_mention(message)

        # Hierarchy protected: kick was safely aborted
        senior_admin.kick.assert_not_called()

    # =========================================================================
    # SECTION 3 & 6: ANTI-NUKE & FAST RESPONSE ENGINE
    # =========================================================================

    async def test_antinuke_sliding_window_threshold(self):
        """Single action exceeding threshold triggers containment."""
        actor = MagicMock(spec=discord.Member)
        actor.id = 555666777
        actor.name = "RogueAdmin"
        actor.roles = []
        actor.top_role = MockRole("Admin", 20)
        actor.timeout = AsyncMock()
        actor.edit = AsyncMock()

        self.guild.get_role = MagicMock(return_value=None)
        self.bot.db.get_anti_nuke_config = AsyncMock(return_value=AntiNukeConfig(
            guild_id=self.guild.id,
            max_channel_deletions=3,
            sliding_window_seconds=15,
        ))

        # 1st and 2nd deletions within threshold
        r1 = await self.antinuke.record_and_evaluate(self.guild, actor, "channel_delete", threshold=3)
        self.assertFalse(r1)
        r2 = await self.antinuke.record_and_evaluate(self.guild, actor, "channel_delete", threshold=3)
        self.assertFalse(r2)

        # 3rd deletion breaches threshold
        r3 = await self.antinuke.record_and_evaluate(self.guild, actor, "channel_delete", threshold=3)
        self.assertTrue(r3)
        actor.timeout.assert_awaited_once()

    async def test_antinuke_multi_action_event_correlation(self):
        """Correlating multiple distinct actions (severity score >= 50) triggers containment."""
        actor = MagicMock(spec=discord.Member)
        actor.id = 123987456
        actor.name = "MultiVectorAttacker"
        actor.roles = []
        actor.top_role = MockRole("Admin", 20)
        actor.timeout = AsyncMock()
        actor.edit = AsyncMock()

        # Action 1: Channel Delete (Weight 25) - threshold is 5 so single check doesn't trigger
        r1 = await self.antinuke.record_and_evaluate(self.guild, actor, "channel_delete", threshold=5)
        self.assertFalse(r1)

        # Action 2: Role Delete (Weight 25) - combined severity = 50!
        r2 = await self.antinuke.record_and_evaluate(self.guild, actor, "role_delete", threshold=5)
        self.assertTrue(r2)
        actor.timeout.assert_awaited_once()

    async def test_antinuke_exempts_verified_owner_and_trusted(self):
        """Verified owner and trusted users are never contained by anti-nuke."""
        owner = MagicMock(spec=discord.Member)
        owner.id = self.guild.owner_id
        owner.roles = []

        is_t = await self.antinuke.is_trusted(self.guild, owner)
        self.assertTrue(is_t)

        r = await self.antinuke.record_and_evaluate(self.guild, owner, "channel_delete", threshold=1)
        self.assertFalse(r)

    # =========================================================================
    # SECTION 4: AUTOMATIC ANTI-RAID MODE
    # =========================================================================

    async def test_anti_raid_burst_join_triggers_lockdown(self):
        """A burst of joins exceeding threshold activates auto-lockdown."""
        self.bot.db.get_anti_raid_config = AsyncMock(return_value=AntiRaidConfig(
            guild_id=self.guild.id,
            enabled=True,
            join_threshold=3,
            join_window_seconds=10,
            auto_lockdown=True,
            lockdown_duration_seconds=300,
        ))

        # Mock channels for lockdown
        ch = MagicMock(spec=discord.TextChannel)
        ch.id = 1234
        ch.permissions_for.return_value = MagicMock(manage_channels=True)
        ch.overwrites_for.return_value = discord.PermissionOverwrite(send_messages=True)
        ch.set_permissions = AsyncMock()
        self.guild.text_channels = [ch]

        # Simulate 3 rapid joins
        for i in range(3):
            member = MagicMock(spec=discord.Member)
            member.id = 1000 + i
            member.guild = self.guild
            member.bot = False
            member.created_at = discord.utils.utcnow() - datetime.timedelta(days=1)  # Young account
            await self.cog.on_member_join(member)

        # Lockdown executed: send_messages denied
        ch.set_permissions.assert_awaited()
        # Incident recorded
        self.bot.db.record_security_incident.assert_awaited()

    # =========================================================================
    # SECTION 5: PERMISSION & ROLE SECURITY
    # =========================================================================

    async def test_unauthorized_role_permission_grant_is_reverted(self):
        """Granting administrator to a role by non-trusted actor is detected and reverted."""
        role_before = MagicMock(spec=discord.Role)
        role_before.id = 8888
        role_before.name = "Moderator"
        role_before.permissions = discord.Permissions(send_messages=True)

        role_after = MagicMock(spec=discord.Role)
        role_after.id = 8888
        role_after.guild = self.guild
        role_after.name = "Moderator"
        role_after.permissions = discord.Permissions(send_messages=True, administrator=True)
        role_after.edit = AsyncMock()

        # Executor who made the change in audit log
        executor = MagicMock(spec=discord.Member)
        executor.id = 333444555  # Untrusted user
        executor.name = "CompromisedAdmin"
        executor.roles = []

        audit_entry = MagicMock()
        audit_entry.id = 99999

        with patch("cogs.security.find_audit_executor", AsyncMock(return_value=(executor, audit_entry))):
            await self.cog.on_guild_role_update(role_before, role_after)

        # Role permissions reverted to before state
        role_after.edit.assert_awaited_once_with(
            permissions=role_before.permissions,
            reason="Security: Unauthorized grant of administrator"
        )
        # Audit history logged
        self.bot.db.record_permission_audit.assert_awaited_once()

    # =========================================================================
    # SECTION 6 & 8: DIAGNOSTICS AND SELF-RECOVERY
    # =========================================================================

    async def test_security_diagnostic_checks(self):
        """Diagnostic check validates permissions, hierarchy, and audit logs non-destructively."""
        # Bot member permissions
        self.bot_member.guild_permissions = discord.Permissions.all()
        # Audit log mock
        async def mock_audit_logs(limit=1):
            yield MagicMock()
        self.guild.audit_logs = mock_audit_logs

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        await self.cog.security_test.callback(self.cog, interaction)

        interaction.followup.send.assert_awaited_once()
        embed = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("Diagnostic Report", embed.title)
        self.assertEqual(embed.color.value, Colors.SUCCESS)


if __name__ == "__main__":
    unittest.main()
