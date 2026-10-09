"""
Rai Autopilot Subsystem & Slash Commands.
Provides autonomous server controls, dry-run toggles, safety rankings,
threat simulations, and real-time audit log inspections.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Literal, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.autopilot import AutopilotEvent
from utils.embeds import create_embed, success_embed, error_embed, alert_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("RaiAutopilotCog")


class AutopilotView(discord.ui.View):
    """Interactive Discord UI View for managing Autopilot configuration."""

    def __init__(self, bot: SentinelBot, guild_id: int):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="Toggle Autopilot", style=discord.ButtonStyle.primary, emoji="🤖", row=0)
    async def toggle_enabled(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await self.bot.db.get_or_create_autopilot_config(self.guild_id)
        new_val = not cfg.enabled
        await self.bot.db.update_autopilot_config(self.guild_id, enabled=new_val)
        status_text = "ENABLED 🟢" if new_val else "DISABLED 🔴"
        await interaction.response.send_message(
            embed=success_embed("Autopilot Updated", f"Master Autopilot is now **{status_text}**."),
            ephemeral=True,
        )

    @discord.ui.button(label="Toggle Dry-Run", style=discord.ButtonStyle.secondary, emoji="🧪", row=0)
    async def toggle_dry_run(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await self.bot.db.get_or_create_autopilot_config(self.guild_id)
        new_val = not cfg.dry_run
        await self.bot.db.update_autopilot_config(self.guild_id, dry_run=new_val)
        status_text = "ACTIVE (Actions simulated only) 🟡" if new_val else "OFF (Live execution) 🟢"
        await interaction.response.send_message(
            embed=success_embed("Dry-Run Mode Updated", f"Dry-Run Mode is now **{status_text}**."),
            ephemeral=True,
        )

    @discord.ui.button(label="Raid Defense", style=discord.ButtonStyle.success, emoji="🚨", row=1)
    async def toggle_raid(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await self.bot.db.get_or_create_autopilot_config(self.guild_id)
        new_val = not cfg.raid_protection
        await self.bot.db.update_autopilot_config(self.guild_id, raid_protection=new_val)
        await interaction.response.send_message(
            embed=success_embed("Raid Autopilot", f"Autonomous Raid Protection: **{'ENABLED' if new_val else 'DISABLED'}**"),
            ephemeral=True,
        )

    @discord.ui.button(label="Anti-Nuke", style=discord.ButtonStyle.success, emoji="💥", row=1)
    async def toggle_nuke(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await self.bot.db.get_or_create_autopilot_config(self.guild_id)
        new_val = not cfg.anti_nuke
        await self.bot.db.update_autopilot_config(self.guild_id, anti_nuke=new_val)
        await interaction.response.send_message(
            embed=success_embed("Anti-Nuke Autopilot", f"Autonomous Anti-Nuke: **{'ENABLED' if new_val else 'DISABLED'}**"),
            ephemeral=True,
        )

    @discord.ui.button(label="Anti-Spam", style=discord.ButtonStyle.success, emoji="🧹", row=1)
    async def toggle_spam(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await self.bot.db.get_or_create_autopilot_config(self.guild_id)
        new_val = not cfg.anti_spam
        await self.bot.db.update_autopilot_config(self.guild_id, anti_spam=new_val)
        await interaction.response.send_message(
            embed=success_embed("Anti-Spam Autopilot", f"Autonomous Anti-Spam: **{'ENABLED' if new_val else 'DISABLED'}**"),
            ephemeral=True,
        )


class AutopilotCog(commands.Cog, name="Autopilot"):
    """Autonomous platform commands, health monitoring, and threat simulations."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    autopilot_group = app_commands.Group(
        name="autopilot",
        description="Rai autonomous defense, dry-run controls, and security simulations",
        default_permissions=discord.Permissions(administrator=True),
    )

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @autopilot_group.command(name="status", description="Display autonomous defense status, workers, and baseline metrics")
    async def status_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command must be run in a server.", ephemeral=True)
            return

        cfg = await self.bot.db.get_or_create_autopilot_config(guild.id)
        baseline = await self.bot.db.get_or_create_security_baseline(guild.id)
        health_list = await self.bot.db.get_all_subsystem_health()

        embed = create_embed(
            title="🤖 Rai Autonomous Autopilot Status",
            description=f"Real-time operational dashboard for **{guild.name}**",
            color=Colors.PRIMARY,
        )

        master_status = "🟢 ACTIVE" if cfg.enabled else "🔴 DISABLED"
        dry_run_status = "🟡 ACTIVE (Simulated Actions)" if cfg.dry_run else "🟢 LIVE (Executing Actions)"
        embed.add_field(name="Autopilot Engine", value=master_status, inline=True)
        embed.add_field(name="Execution Mode", value=dry_run_status, inline=True)
        embed.add_field(name="Max Safety Level", value=f"`{cfg.max_safety_level}`", inline=True)

        modules_text = (
            f"🚨 Anti-Raid: {'🟢' if cfg.raid_protection else '🔴'}\n"
            f"💥 Anti-Nuke: {'🟢' if cfg.anti_nuke else '🔴'}\n"
            f"🧹 Anti-Spam: {'🟢' if cfg.anti_spam else '🔴'}\n"
            f"🔗 Anti-Link: {'🟢' if cfg.anti_link else '🔴'}\n"
            f"📢 Anti-Mention: {'🟢' if cfg.anti_mention else '🔴'}"
        )
        embed.add_field(name="Autonomous Modules", value=modules_text, inline=True)

        automation_text = (
            f"🔊 VoiceGuard: {'🟢' if cfg.voiceguard else '🔴'}\n"
            f"👤 Verification: {'🟢' if cfg.verification else '🔴'}\n"
            f"🎫 Tickets: {'🟢' if cfg.ticket_management else '🔴'}\n"
            f"💾 Backups: {'🟢' if cfg.backups else '🔴'}\n"
            f"🧹 Maintenance: {'🟢' if cfg.maintenance else '🔴'}"
        )
        embed.add_field(name="Management Automation", value=automation_text, inline=True)

        baseline_text = (
            f"• Avg Joins: `{baseline.avg_joins_per_hour:.1f}/hr`\n"
            f"• Avg Messages: `{baseline.avg_messages_per_min:.1f}/min`\n"
            f"• Voice Users: `{baseline.avg_voice_users:.1f}`\n"
            f"• Samples: `{baseline.sample_count}`"
        )
        embed.add_field(name="Server Behavior Baseline", value=baseline_text, inline=False)

        if health_list:
            health_lines = [f"`{h.subsystem}`: {'🟢' if h.status == 'HEALTHY' else ('🟡' if h.status == 'DEGRADED' else '🔴')} {h.status}" for h in health_list[:4]]
            embed.add_field(name="Subsystem Supervisors", value="\n".join(health_lines), inline=False)

        view = AutopilotView(self.bot, guild.id)
        await interaction.followup.send(embed=embed, view=view)

    @autopilot_group.command(name="actions", description="Inspect recent autonomous audit records and actions")
    @app_commands.describe(limit="Number of records to retrieve (default: 10, max: 25)")
    async def actions_cmd(self, interaction: discord.Interaction, limit: Optional[int] = 10):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command must be run in a server.", ephemeral=True)
            return

        limit = max(1, min(limit or 10, 25))
        actions = await self.bot.db.get_recent_autopilot_actions(guild.id, limit=limit)

        if not actions:
            await interaction.followup.send("No autonomous actions recorded yet.", ephemeral=True)
            return

        embed = create_embed(
            title=f"📋 Autopilot Action Audit Log (Last {len(actions)})",
            description=f"Showing the latest autonomous security decisions in **{guild.name}**",
            color=Colors.PRIMARY,
        )

        for act in actions[:8]:
            res_emoji = "✅" if act.result == "SUCCESS" else ("🧪" if act.result == "DRY_RUN" else "⚠️")
            target_str = f"<@{act.target_id}>" if act.target_type == "user" else (f"<#{act.target_id}>" if act.target_type == "channel" else "Server")
            val = (
                f"**Risk**: `{act.risk_level}` | **Action**: `{act.action}`\n"
                f"**Target**: {target_str} | **Result**: {res_emoji} `{act.result}`\n"
                f"**Reason**: {act.reason[:80]}"
            )
            embed.add_field(name=f"Action #{act.action_id[-4:]} ({act.module})", value=val, inline=False)

        await interaction.followup.send(embed=embed)

    @autopilot_group.command(name="dryrun", description="Toggle Dry-Run mode (simulates actions without executing)")
    @app_commands.describe(enabled="Enable or disable Dry-Run mode")
    async def dryrun_cmd(self, interaction: discord.Interaction, enabled: bool):
        guild = interaction.guild
        if not guild:
            return
        await self.bot.db.update_autopilot_config(guild.id, dry_run=enabled)
        mode = "ENABLED 🟡 (No real actions will be taken)" if enabled else "DISABLED 🟢 (Live actions enabled)"
        await interaction.response.send_message(
            embed=success_embed("Dry-Run Mode Updated", f"Autopilot Dry-Run is now **{mode}**."),
            ephemeral=True,
        )

    @autopilot_group.command(name="safety", description="Set maximum allowed autonomous safety action level")
    @app_commands.describe(level="Maximum safety level Rai is authorized to execute autonomously")
    async def safety_cmd(
        self,
        interaction: discord.Interaction,
        level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    ):
        guild = interaction.guild
        if not guild:
            return
        await self.bot.db.update_autopilot_config(guild.id, max_safety_level=level)
        await interaction.response.send_message(
            embed=success_embed("Safety Level Configured", f"Maximum autonomous action level set to: `{level}`"),
            ephemeral=True,
        )

    @autopilot_group.command(name="simulate", description="Run a safe threat simulation through Autopilot & Security Brain")
    @app_commands.describe(threat="Type of threat to simulate")
    async def simulate_cmd(
        self,
        interaction: discord.Interaction,
        threat: Literal["raid", "spam", "nuke", "webhook"],
    ):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            return

        res = await self.bot.autopilot.simulate_threat(guild, threat)

        embed = create_embed(
            title=f"🧪 Autopilot Threat Simulation: {threat.upper()}",
            description="A synthetic threat event was passed through the Autopilot & Security Brain pipeline.\n**No destructive calls were made to live server assets.**",
            color=Colors.WARNING,
        )
        embed.add_field(name="Simulation ID", value=f"`{res.get('simulation_id')}`", inline=True)
        embed.add_field(name="Calculated Risk", value=f"`{res.get('risk_level')}` (Score: `{res.get('risk_score')}`)", inline=True)
        embed.add_field(name="Proposed Action", value=f"`{res.get('proposed_action')}`", inline=True)
        embed.add_field(name="Pipeline Result", value=f"✅ `{res.get('status')}`", inline=False)
        embed.add_field(name="Summary", value=res.get("message", "Success"), inline=False)
        embed.set_footer(text="Rai Simulation Framework • Safe Verification")

        await interaction.followup.send(embed=embed)

    # ==========================================
    # EVENT LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Autopilot analysis for new member accounts."""
        if not member.guild or member.bot:
            return
        cfg = await self.bot.db.get_or_create_autopilot_config(member.guild.id)
        if not cfg.enabled:
            return

        # Check account age (< 24 hours)
        account_age = datetime.datetime.now(datetime.timezone.utc) - member.created_at
        if account_age.total_seconds() < 86400:
            await self.bot.autopilot.dispatch(
                AutopilotEvent(
                    guild_id=member.guild.id,
                    module="ANTI_RAID",
                    event_type="NEW_ACCOUNT_JOIN",
                    reason=f"Account created {int(account_age.total_seconds() // 3600)}h ago (<24h threshold)",
                    risk_level="MEDIUM",
                    target=member,
                    action="LOG",
                )
            )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Autopilot detection for sudden channel deletions."""
        guild = channel.guild
        cfg = await self.bot.db.get_or_create_autopilot_config(guild.id)
        if not cfg.enabled or not getattr(cfg, "anti_nuke", True):
            return

        # 1. Ignore managed temporary / dynamic voice channels
        try:
            if hasattr(self.bot.db, "get_dynamic_room") and await self.bot.db.get_dynamic_room(channel.id):
                return
            if hasattr(self.bot.db, "get_hidden_voice_room") and await self.bot.db.get_hidden_voice_room(channel.id):
                return
        except Exception:
            pass

        # 2. Ignore dynamic voice signatures and hub channels
        ch_name_lower = channel.name.lower()
        if isinstance(channel, discord.VoiceChannel):
            dynamic_signatures = ["'s room", "sanctuary", "lounge", "private", "create your room", "create private room"]
            if any(sig in ch_name_lower for sig in dynamic_signatures):
                return

        # 3. Check audit log: ignore automated bot cleanup or authorized server owners
        from utils.helpers import find_audit_executor
        executor, audit_entry = await find_audit_executor(
            guild, discord.AuditLogAction.channel_delete, target_id=channel.id, max_retries=2, delay_seconds=0.3
        )
        if executor:
            if executor.id == self.bot.user.id or executor.id == guild.owner_id:
                return
            if hasattr(self.bot.db, "is_whitelisted"):
                role_ids = [r.id for r in executor.roles] if isinstance(executor, discord.Member) else []
                if await self.bot.db.is_whitelisted(guild.id, executor.id, role_ids):
                    return

        await self.bot.autopilot.dispatch(
            AutopilotEvent(
                guild_id=guild.id,
                module="ANTI_NUKE",
                event_type="CHANNEL_DELETE",
                reason=f"Channel #{channel.name} deleted" + (f" by {executor.display_name}" if executor else ""),
                risk_level="HIGH",
                target=channel,
                action="LOG",
            )
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Autopilot detection for sudden role deletions."""
        guild = role.guild
        cfg = await self.bot.db.get_or_create_autopilot_config(guild.id)
        if not cfg.enabled or not getattr(cfg, "anti_nuke", True):
            return

        from utils.helpers import find_audit_executor
        executor, audit_entry = await find_audit_executor(
            guild, discord.AuditLogAction.role_delete, target_id=role.id, max_retries=2, delay_seconds=0.3
        )
        if executor:
            if executor.id == self.bot.user.id or executor.id == guild.owner_id:
                return
            if hasattr(self.bot.db, "is_whitelisted"):
                role_ids = [r.id for r in executor.roles] if isinstance(executor, discord.Member) else []
                if await self.bot.db.is_whitelisted(guild.id, executor.id, role_ids):
                    return

        await self.bot.autopilot.dispatch(
            AutopilotEvent(
                guild_id=guild.id,
                module="ANTI_NUKE",
                event_type="ROLE_DELETE",
                reason=f"Role @{role.name} deleted" + (f" by {executor.display_name}" if executor else ""),
                risk_level="HIGH",
                target=role,
                action="LOG",
            )
        )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        """Autopilot detection for webhook modifications."""
        guild = channel.guild
        cfg = await self.bot.db.get_or_create_autopilot_config(guild.id)
        if not cfg.enabled:
            return

        await self.bot.autopilot.dispatch(
            AutopilotEvent(
                guild_id=guild.id,
                module="WEBHOOK_GUARD",
                event_type="WEBHOOK_CHANGE",
                reason=f"Webhook modified in #{channel.name}",
                risk_level="MEDIUM",
                target=channel,
                action="LOG",
            )
        )


async def setup(bot: SentinelBot):
    await bot.add_cog(AutopilotCog(bot))
