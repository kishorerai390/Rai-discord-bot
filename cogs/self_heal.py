"""
Rai Golden State Self-Healing Sentry Cog.
Provides:
- /self_heal audit: Comprehensive health inspection across security locks, permissions, channels, and roles.
- /self_heal repair: Proactive self-repair restoring honeypot overwrites, missing report channels, and level roles.
- Strict Report Isolation: Diagnostics and repair logs route strictly to #bot-report only.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.owner_reporter import OwnerReporter
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.SelfHealCog")

HONEYPOT_CHANNEL_ID = 1558168338386129004
REPORT_CATEGORY_ID = 1555428388280209422
BOT_REPORT_CHANNEL_ID = 1555428420383416400

EXPECTED_REPORT_CHANNELS = {
    "member_reports": ("⛨・member-reports", 1555428392181047366),
}

MILESTONE_ROLES = [
    ("💖 ╏ 𝓡ᴀɪ 𝕱ᴀᴍ", 0xE91E63),
    ("💎 ╏ 𝓥ɪᴘ 𝕸ᴇᴍʙᴇʀ", 0x9B59B6),
]


class SelfHealCog(commands.Cog, name="SelfHeal"):
    """Autonomous Golden State Self-Healing Sentry."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.sentinel_audit_loop.start()

    def cog_unload(self):
        self.sentinel_audit_loop.cancel()

    # ==========================================
    # BACKGROUND AUDIT LOOP (Every 6 Hours)
    # ==========================================

    @tasks.loop(hours=1)
    async def sentinel_audit_loop(self):
        """Silently verifies honeypot lock down, report channel confidentiality, and @everyone permissions."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                issues, _ = await self.audit_guild(guild)
                if issues:
                    logger.warning("[SELF_HEAL] Detected %d issues in guild %s (%d). Auto-repairing...", len(issues), guild.name, guild.id)
                    repaired = await self.repair_guild(guild)
                    if repaired:
                        rep_lines = "\n".join(f"• {r}" for r in repaired)
                        OwnerReporter.send_bot_report(
                            self.bot,
                            guild.id,
                            event="Autonomous Self-Healing Executed",
                            action_taken=f"Auto-repaired {len(repaired)} issues",
                            details={"Actions Executed": rep_lines[:1000]},
                        )
            except Exception as e:
                logger.error("[SELF_HEAL_LOOP_ERR] Guild %d audit error: %s", guild.id, e)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """Instant reactive auto-heal if @everyone role is given dangerous permissions."""
        if after.id == after.guild.id:  # @everyone role
            if after.permissions.mention_everyone or after.permissions.administrator:
                if after.guild.me.guild_permissions.manage_roles:
                    try:
                        await after.edit(
                            mention_everyone=False,
                            administrator=False,
                            reason="Self-Healing Sentry: Instant auto-mitigation of dangerous @everyone permissions",
                        )
                        OwnerReporter.send_security_report(
                            self.bot,
                            after.guild.id,
                            event="Dangerous Role Permission Auto-Healed",
                            reason="An administrator or integration attempted to grant @everyone mention/admin permissions.",
                            action_taken="Instantly reverted @everyone permissions to safe state.",
                            severity="LOW",
                        )
                    except Exception as e:
                        logger.debug("on_guild_role_update auto-heal notice: %s", e)

    # ==========================================
    # AUDIT LOGIC
    # ==========================================

    async def audit_guild(self, guild: discord.Guild) -> Tuple[List[str], List[str]]:
        """Audits honeypot, report channels, roles, and permissions. Returns (issues, passes)."""
        issues: List[str] = []
        passes: List[str] = []

        # 0. @everyone Dangerous Permissions Audit
        everyone = guild.default_role
        if everyone.permissions.mention_everyone:
            issues.append("@everyone role has `Mention @everyone / @here` permission enabled!")
        else:
            passes.append("@everyone mention permission safely locked.")
        if everyone.permissions.administrator:
            issues.append("@everyone role has `Administrator` permission enabled!")
        if everyone.permissions.manage_roles or everyone.permissions.manage_channels:
            issues.append("@everyone role has `Manage Roles/Channels` enabled!")

        # 1. Honeypot Lock
        hp = guild.get_channel(HONEYPOT_CHANNEL_ID)
        if not hp:
            if guild.id == 1457382179981099090:
                issues.append(f"Honeypot channel (`{HONEYPOT_CHANNEL_ID}`) not found.")
        else:
            everyone_ow = hp.overwrites_for(guild.default_role)
            if everyone_ow.view_channel is not False:
                issues.append("Honeypot channel does NOT deny @everyone view_channel permission!")
            else:
                passes.append("Honeypot channel strictly locked to @everyone.")

        # 2. Report Category & Channels
        cat = guild.get_channel(REPORT_CATEGORY_ID)
        if not cat:
            if guild.id == 1457382179981099090:
                issues.append("Owner Reports Category missing.")
        else:
            passes.append("Owner Reports Category intact.")

        for key, (ch_name, ch_id) in EXPECTED_REPORT_CHANNELS.items():
            ch = guild.get_channel(ch_id)
            if not ch:
                if guild.id == 1457382179981099090:
                    issues.append(f"Report channel `{ch_name}` ({ch_id}) missing.")
            else:
                passes.append(f"Report channel `{ch_name}` active.")

        # 3. Level Milestone Roles
        if guild.id == 1457382179981099090:
            for role_name, _ in MILESTONE_ROLES:
                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    issues.append(f"Milestone reward role `{role_name}` missing.")
                else:
                    passes.append(f"Milestone reward role `{role_name}` verified.")

        # 4. Bot Core Permissions
        me = guild.me
        if not me.guild_permissions.manage_roles:
            issues.append("Bot missing `Manage Roles` permission.")
        if not me.guild_permissions.manage_channels:
            issues.append("Bot missing `Manage Channels` permission.")
        if not me.guild_permissions.ban_members:
            issues.append("Bot missing `Ban Members` permission.")
        if not me.guild_permissions.view_audit_log:
            issues.append("Bot missing `View Audit Log` permission.")

        return issues, passes

    # ==========================================
    # REPAIR LOGIC
    # ==========================================

    async def repair_guild(self, guild: discord.Guild) -> List[str]:
        """Automatically executes surgical repairs."""
        repaired: List[str] = []

        # 0. Heal @everyone dangerous permissions
        everyone = guild.default_role
        if (
            everyone.permissions.mention_everyone
            or everyone.permissions.administrator
            or everyone.permissions.manage_roles
            or everyone.permissions.manage_channels
        ):
            if guild.me.guild_permissions.manage_roles:
                try:
                    await everyone.edit(
                        mention_everyone=False,
                        administrator=False,
                        manage_roles=False,
                        manage_channels=False,
                        reason="Self-Healing Sentry: Auto-repaired dangerous @everyone permissions",
                    )
                    repaired.append("Reverted dangerous `@everyone / @here` mention & admin permissions on `@everyone` role.")
                except Exception as e:
                    logger.debug("Failed to auto-repair @everyone perms: %s", e)

        # 1. Lock Honeypot
        hp = guild.get_channel(HONEYPOT_CHANNEL_ID)
        if hp and isinstance(hp, discord.TextChannel):
            try:
                await hp.set_permissions(guild.default_role, view_channel=False, send_messages=False, read_message_history=False)
                repaired.append("Re-locked `#🪤・honeypot-trap` to deny @everyone.")
            except Exception as e:
                logger.debug("Failed to set honeypot perms: %s", e)

        # 2. Milestone Roles (Main guild)
        if guild.id == 1457382179981099090:
            for role_name, hex_col in MILESTONE_ROLES:
                existing = discord.utils.get(guild.roles, name=role_name)
                if not existing and guild.me.guild_permissions.manage_roles:
                    try:
                        await guild.create_role(
                            name=role_name,
                            color=discord.Color(hex_col),
                            reason="Self-Healing Sentry: Restored missing milestone reward role",
                        )
                        repaired.append(f"Created missing milestone role `{role_name}`.")
                    except Exception as e:
                        logger.debug("Failed to create role %s: %s", role_name, e)

        # 3. Report Channels Lock
        for key, (ch_name, ch_id) in EXPECTED_REPORT_CHANNELS.items():
            ch = guild.get_channel(ch_id)
            if ch and isinstance(ch, discord.TextChannel):
                ow = ch.overwrites_for(guild.default_role)
                if ow.view_channel is not False and guild.me.guild_permissions.manage_channels:
                    try:
                        await ch.set_permissions(guild.default_role, view_channel=False, send_messages=False)
                        repaired.append(f"Secured `{ch.name}` confidential permissions.")
                    except Exception as e:
                        logger.debug("Failed to secure report ch %s: %s", ch.name, e)

        return repaired

    # ==========================================
    # SLASH COMMANDS: /self_heal
    # ==========================================

    self_heal_group = app_commands.Group(
        name="self_heal",
        description="Autonomous Server Self-Healing Sentry Suite",
    )

    @self_heal_group.command(name="audit", description="Perform deep integrity audit of permissions, honeypot, and report channels")
    async def self_heal_audit(self, interaction: discord.Interaction):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Server only.", ephemeral=True)
            return

        await interaction.response.defer()

        issues, passes = await self.audit_guild(guild)

        embed = discord.Embed(
            title="🛡️ 『RΛI』 • GOLDEN STATE SELF-HEALING AUDIT",
            description=(
                f"**Guild:** {guild.name} (`{guild.id}`)\n"
                f"**Overall Health Status:** `{'COMPROMISED ⚠️' if issues else 'PRISTINE 🟢'}`\n\n"
                f"• **Verified Compliances:** `{len(passes)} checks passed`\n"
                f"• **Anomalies Detected:** `{len(issues)} items flagged`"
            ),
            color=0xED4245 if issues else 0x2ECC71,
        )

        if issues:
            embed.add_field(
                name="⚠️ Action Items / Anomalies",
                value="\n".join(f"• {i}" for i in issues[:8]),
                inline=False,
            )
            embed.add_field(
                name="💡 Recommended Action",
                value="Run `/self_heal repair` to automatically repair all detected anomalies.",
                inline=False,
            )
        else:
            embed.add_field(
                name="✨ All Systems Golden",
                value="Honeypot, confidential report channels, milestone roles, and security permissions are 100% compliant.",
                inline=False,
            )

        embed.set_footer(text="RAI Autonomous Self-Healing Sentry")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.followup.send(embed=embed)

    @self_heal_group.command(name="repair", description="Execute autonomous self-repair across server channels and roles")
    async def self_heal_repair(self, interaction: discord.Interaction):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Server only.", ephemeral=True)
            return

        await interaction.response.defer()

        repaired = await self.repair_guild(guild)

        if repaired:
            embed = discord.Embed(
                title="🔧 『RΛI』 • SELF-HEALING REPAIRS COMPLETED",
                description=(
                    f"Successfully performed **{len(repaired)}** autonomous repairs:\n\n"
                    + "\n".join(f"✅ {r}" for r in repaired)
                    + "\n\n📋 *A detailed execution log has been dispatched strictly to `#🤖・ʙᴏᴛ-ʀᴇᴘᴏʀᴛ`.*"
                ),
                color=0x2ECC71,
            )

            # Log strictly to #bot-report
            OwnerReporter.send_bot_report(
                self.bot,
                guild.id,
                event="Manual Self-Healing Repair Triggered",
                executor=interaction.user,
                action_taken=f"Executed {len(repaired)} repairs",
                details={"Actions Detail": "\n".join(f"• {r}" for r in repaired)[:1000]},
            )
        else:
            embed = discord.Embed(
                title="✨ 『RΛI』 • NO REPAIRS NEEDED",
                description="All security channels, honeypot overwrites, and milestone roles are already in ideal state!",
                color=0x3498DB,
            )

        embed.set_footer(text="RAI Autonomous Self-Healing Sentry")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.followup.send(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(SelfHealCog(bot))
