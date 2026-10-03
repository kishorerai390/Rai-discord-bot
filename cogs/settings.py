"""
Central Automation Settings & Autonomous Task Supervisor Cog for Rai.
Provides /settings automation dashboard, /settings raid configuration,
scheduled SQLite database backups to data/backups/, background cooldown & maintenance cleanup,
and autonomous health monitoring.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from database.models import AutomationConfig, RaidConfig
from utils.embeds import (
    create_embed,
    error_embed,
    info_embed,
    security_embed,
    success_embed,
    warning_embed,
)
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

BACKUPS_DIR = Path("data/backups")
DB_PATH = Path("data/bot.db")
MAX_BACKUPS_RETAINED = 10


class AutomationDashboardView(discord.ui.View):
    """Interactive Discord UI View to inspect and toggle autonomous subsystems."""

    def __init__(self, bot: SentinelBot, guild_id: int, config: AutomationConfig, user_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id
        self.config = config
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                embed=error_embed("Unauthorized", "Only the administrator who opened this dashboard can interact with it."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Toggle Raid Monitor", style=discord.ButtonStyle.primary, emoji="🛡️", row=0)
    async def toggle_raid(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_val = not self.config.raid_detection
        await self.bot.db.update_automation_config(self.guild_id, raid_detection=new_val)
        self.config.raid_detection = new_val
        await self._refresh(interaction)

    @discord.ui.button(label="Toggle AutoMod", style=discord.ButtonStyle.primary, emoji="🤖", row=0)
    async def toggle_automod(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_val = not self.config.automod
        await self.bot.db.update_automation_config(self.guild_id, automod=new_val)
        self.config.automod = new_val
        await self._refresh(interaction)

    @discord.ui.button(label="Toggle VoiceGuard", style=discord.ButtonStyle.primary, emoji="🔊", row=0)
    async def toggle_vg(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_val = not self.config.voiceguard
        await self.bot.db.update_automation_config(self.guild_id, voiceguard=new_val)
        self.config.voiceguard = new_val
        await self._refresh(interaction)

    @discord.ui.button(label="Toggle Ticket Inactivity", style=discord.ButtonStyle.secondary, emoji="🎫", row=1)
    async def toggle_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_val = not self.config.ticket_automation
        await self.bot.db.update_automation_config(self.guild_id, ticket_automation=new_val)
        self.config.ticket_automation = new_val
        await self._refresh(interaction)

    @discord.ui.button(label="Toggle Suggestions", style=discord.ButtonStyle.secondary, emoji="💡", row=1)
    async def toggle_suggestions(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_val = not self.config.suggestion_automation
        await self.bot.db.update_automation_config(self.guild_id, suggestion_automation=new_val)
        self.config.suggestion_automation = new_val
        await self._refresh(interaction)

    @discord.ui.button(label="Run DB Maintenance", style=discord.ButtonStyle.success, emoji="🧹", row=2)
    async def run_maintenance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        counts = await self.bot.cooldowns.cleanup_expired()
        await interaction.followup.send(
            embed=success_embed(
                "Maintenance Completed",
                f"• Cleaned Runtime Cooldowns: `{counts['runtime_cooldowns']}`\n"
                f"• Cleaned Persistent Cooldowns: `{counts['db_cooldowns']}`\n"
                f"• Cleaned Stale Violations: `{counts['db_violations']}`",
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Create DB Backup", style=discord.ButtonStyle.success, emoji="💾", row=2)
    async def backup_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        cog: Optional[SettingsCog] = self.bot.get_cog("Settings")
        if cog:
            backup_file = await cog.execute_backup()
            if backup_file:
                await interaction.followup.send(
                    embed=success_embed("Database Backup Successful", f"Created safe backup: `{backup_file.name}`"),
                    ephemeral=True,
                )
                return
        await interaction.followup.send(
            embed=error_embed("Backup Failed", "Could not complete safe SQLite database backup."),
            ephemeral=True,
        )

    async def _refresh(self, interaction: discord.Interaction):
        embed = SettingsCog.build_automation_embed(interaction.guild, self.config)
        await interaction.response.edit_message(embed=embed, view=self)


class SettingsCog(commands.Cog, name="Settings"):
    """Autonomous Subsystems Configuration and Supervisor."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.supervisor_task.start()
        self.backup_task.start()

    def cog_unload(self):
        self.supervisor_task.cancel()
        self.backup_task.cancel()

    settings_group = app_commands.Group(
        name="settings",
        description="Central bot configuration and autonomous systems control",
        default_permissions=discord.Permissions(administrator=True),
    )

    @staticmethod
    def build_automation_embed(guild: discord.Guild, cfg: AutomationConfig) -> discord.Embed:
        embed = create_embed(
            title=f"⚙️ Rai Autonomous Systems — {guild.name}",
            description="Manage background tasks, automated monitors, and self-healing systems.",
            color=Colors.PRIMARY,
        )

        def badge(val: bool) -> str:
            return "🟢 Active" if val else "⚪ Disabled"

        embed.add_field(
            name="Security & Defenses",
            value=(
                f"• **Anti-Nuke Monitor:** {badge(cfg.security_monitor)}\n"
                f"• **Raid Detection:** {badge(cfg.raid_detection)}\n"
                f"• **AutoMod Engine:** {badge(cfg.automod)}\n"
                f"• **VoiceGuard:** {badge(cfg.voiceguard)}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Server Management",
            value=(
                f"• **Welcome & Departure:** {badge(cfg.welcome)}\n"
                f"• **Auto Roles:** {badge(cfg.autorole)}\n"
                f"• **Automatic Logging:** {badge(cfg.logging)}\n"
                f"• **Ticket Lifecycle:** {badge(cfg.ticket_automation)}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Autonomous Reliability",
            value=(
                f"• **Suggestion Automation:** {badge(cfg.suggestion_automation)}\n"
                f"• **Database Maintenance:** {badge(cfg.database_maintenance)}\n"
                f"• **Health Supervisor:** {badge(cfg.health_monitor)}\n"
                f"• **Scheduled Backups:** 🟢 Active (`data/backups/`)"
            ),
            inline=False,
        )
        embed.set_footer(text="Use the interactive buttons below to toggle systems or run on-demand maintenance.")
        return embed

    # ==========================================
    # COMMANDS
    # ==========================================

    @settings_group.command(name="automation", description="Open the central autonomous systems dashboard")
    @is_admin_or_owner()
    async def settings_automation(self, interaction: discord.Interaction):
        cfg = await self.bot.db.get_automation_config(interaction.guild.id)
        embed = self.build_automation_embed(interaction.guild, cfg)
        view = AutomationDashboardView(self.bot, interaction.guild.id, cfg, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @settings_group.command(name="raid", description="Configure Automatic Raid Detection thresholds and parameters")
    @is_admin_or_owner()
    @app_commands.describe(
        enabled="Enable or disable automatic raid detection",
        join_threshold="Number of joins per minute to flag as elevated (default 10)",
        join_multiplier="Multiplier over server baseline join rate (default 3.0)",
        observation_window="Sliding window in seconds to analyze join spikes (default 60)",
        alert_cooldown="Seconds between repeat raid alert notifications (default 120)",
        auto_containment="Automatically engage verification containment upon critical raids",
    )
    async def settings_raid(
        self,
        interaction: discord.Interaction,
        enabled: Optional[bool] = None,
        join_threshold: Optional[int] = None,
        join_multiplier: Optional[float] = None,
        observation_window: Optional[int] = None,
        alert_cooldown: Optional[int] = None,
        auto_containment: Optional[bool] = None,
    ):
        updates = {}
        if enabled is not None:
            updates["enabled"] = enabled
        if join_threshold is not None:
            if not (2 <= join_threshold <= 100):
                await interaction.response.send_message(embed=error_embed("Join threshold must be between 2 and 100."), ephemeral=True)
                return
            updates["join_threshold"] = join_threshold
        if join_multiplier is not None:
            if not (1.5 <= join_multiplier <= 10.0):
                await interaction.response.send_message(embed=error_embed("Join multiplier must be between 1.5 and 10.0."), ephemeral=True)
                return
            updates["join_multiplier"] = join_multiplier
        if observation_window is not None:
            if not (15 <= observation_window <= 300):
                await interaction.response.send_message(embed=error_embed("Observation window must be between 15 and 300 seconds."), ephemeral=True)
                return
            updates["observation_window_seconds"] = observation_window
        if alert_cooldown is not None:
            if not (30 <= alert_cooldown <= 600):
                await interaction.response.send_message(embed=error_embed("Alert cooldown must be between 30 and 600 seconds."), ephemeral=True)
                return
            updates["alert_cooldown_seconds"] = alert_cooldown
        if auto_containment is not None:
            updates["auto_containment"] = auto_containment

        if not updates:
            cfg = await self.bot.db.get_raid_config(interaction.guild.id)
            embed = info_embed(
                "Raid Detection Configuration",
                f"• **Status:** {'🟢 Enabled' if cfg.enabled else '⚪ Disabled'}\n"
                f"• **Join Threshold:** `{cfg.join_threshold}` joins / {cfg.observation_window_seconds}s\n"
                f"• **Join Multiplier:** `{cfg.join_multiplier}×` baseline\n"
                f"• **Alert Cooldown:** `{cfg.alert_cooldown_seconds}s`\n"
                f"• **Auto Containment:** {'🟢 Yes' if cfg.auto_containment else '⚪ No'}",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await self.bot.db.update_raid_config(interaction.guild.id, **updates)
        desc = "\n".join(f"• **{k}:** `{v}`" for k, v in updates.items())
        await interaction.response.send_message(
            embed=success_embed("Raid Parameters Updated", f"Saved configuration changes:\n{desc}"),
            ephemeral=True,
        )

    @settings_group.command(name="security", description="Inspect and manage server security configuration")
    @is_admin_or_owner()
    async def settings_security_cmd(self, interaction: discord.Interaction):
        guild = interaction.guild
        g_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        s_cfg = await self.bot.db.get_security_config(guild.id)
        embed = create_embed(
            title=f"🛡️ Security Settings — {guild.name}",
            color=Colors.SECURITY,
        )
        embed.add_field(name="Anti-Nuke Defense", value="🟢 Enabled" if g_cfg.security_enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Punishment Policy", value=f"`{s_cfg.punishment}`", inline=True)
        embed.add_field(
            name="Threshold Limits",
            value=(
                f"• Channel Deletions: `{s_cfg.channel_delete_limit}` / `{s_cfg.channel_delete_window}s`\n"
                f"• Role Deletions: `{s_cfg.role_delete_limit}` / `{s_cfg.role_delete_window}s`\n"
                f"• Bans Limit: `{s_cfg.ban_limit}` / `{s_cfg.ban_window}s`"
            ),
            inline=False,
        )
        embed.set_footer(text="Use /security setup to update thresholds or /security lockdown for emergency.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="moderation", description="Inspect moderation filters and timeout thresholds")
    @is_admin_or_owner()
    async def settings_moderation_cmd(self, interaction: discord.Interaction):
        am_cfg = await self.bot.db.get_automod_config(interaction.guild.id)
        embed = create_embed(
            title=f"🔨 Moderation & AutoMod Settings — {interaction.guild.name}",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Spam Filter", value="🟢 Enabled" if am_cfg.anti_spam_enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Invite Blocker", value="🟢 Enabled" if am_cfg.anti_invites_enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Link Filter", value="🟢 Enabled" if am_cfg.anti_links_enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Mention Limit", value=f"`{am_cfg.max_mentions}` mentions", inline=True)
        embed.set_footer(text="Use /automod setup to adjust filtering parameters.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="welcome", description="Inspect welcome message and departure announcement settings")
    @is_admin_or_owner()
    async def settings_welcome_cmd(self, interaction: discord.Interaction):
        w_cfg = await self.bot.db.get_welcome_config(interaction.guild.id)
        embed = create_embed(
            title=f"👋 Welcome Settings — {interaction.guild.name}",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Welcome System", value="🟢 Enabled" if w_cfg.enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Channel", value=f"<#{w_cfg.channel_id}>" if w_cfg.channel_id else "Not Set", inline=True)
        embed.add_field(name="DM On Join", value="🟢 Yes" if w_cfg.dm_enabled else "⚪ No", inline=True)
        embed.set_footer(text="Use /welcome setup to modify channels or embed cards.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="tickets", description="Inspect support ticket system configuration")
    @is_admin_or_owner()
    async def settings_tickets_cmd(self, interaction: discord.Interaction):
        t_cfg = await self.bot.db.get_ticket_config(interaction.guild.id)
        embed = create_embed(
            title=f"🎫 Ticket System Settings — {interaction.guild.name}",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Support System", value="🟢 Enabled" if t_cfg.enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Category", value=f"<#{t_cfg.category_id}>" if t_cfg.category_id else "Default", inline=True)
        embed.add_field(name="Transcripts", value="🟢 SQLite Saved" if t_cfg.save_transcripts else "⚪ Off", inline=True)
        embed.set_footer(text="Use /ticket setup to post interactive support panel.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="suggestions", description="Inspect community suggestions and voting configuration")
    @is_admin_or_owner()
    async def settings_suggestions_cmd(self, interaction: discord.Interaction):
        s_cfg = await self.bot.db.get_suggestion_config(interaction.guild.id)
        embed = create_embed(
            title=f"💡 Suggestion Settings — {interaction.guild.name}",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Suggestions Channel", value=f"<#{s_cfg.suggestion_channel_id}>" if s_cfg.suggestion_channel_id else "Not Set", inline=True)
        embed.add_field(name="Voting Enabled", value="🟢 Yes" if s_cfg.voting_enabled else "⚪ No", inline=True)
        embed.add_field(name="Discussion Threads", value="🟢 Yes" if s_cfg.discussion_enabled else "⚪ No", inline=True)
        embed.add_field(name="Cooldown", value=f"`{s_cfg.cooldown_seconds}s`", inline=True)
        embed.set_footer(text="Use /suggestion setup to configure channel and staff roles.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="verification", description="Inspect smart verification and account-age requirements")
    @is_admin_or_owner()
    async def settings_verification_cmd(self, interaction: discord.Interaction):
        v_cfg = await self.bot.db.get_verification_config(interaction.guild.id)
        embed = create_embed(
            title=f"✅ Verification Settings — {interaction.guild.name}",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Verification Gate", value="🟢 Enabled" if v_cfg.enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Role Granted", value=f"<@&{v_cfg.role_id}>" if v_cfg.role_id else "Not Set", inline=True)
        embed.add_field(name="Min Account Age", value=f"`{v_cfg.min_account_age_hours}h`", inline=True)
        embed.set_footer(text="Use /verification setup to post the interactive verification panel.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="voiceguard", description="Inspect VoiceGuard acoustic monitoring settings")
    @is_admin_or_owner()
    async def settings_voiceguard_cmd(self, interaction: discord.Interaction):
        vg_cfg = await self.bot.db.get_voiceguard_config(interaction.guild.id)
        embed = create_embed(
            title=f"🔊 VoiceGuard Settings — {interaction.guild.name}",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Audio Monitor", value="🟢 Enabled" if vg_cfg.enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="RMS Threshold", value=f"`{vg_cfg.default_threshold:.2f}`", inline=True)
        embed.add_field(name="Extreme Threshold", value=f"`{vg_cfg.extreme_threshold:.2f}`", inline=True)
        embed.add_field(name="Automated Action", value=f"`{vg_cfg.automatic_action}`", inline=True)
        embed.set_footer(text="Use /voiceguard configure or /voiceguard threshold to modify settings.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_group.command(name="roles", description="Inspect autorole and role synchronization settings")
    @is_admin_or_owner()
    async def settings_roles_cmd(self, interaction: discord.Interaction):
        ar_cfg = await self.bot.db.get_autorole_config(interaction.guild.id)
        embed = create_embed(
            title=f"🎭 Role Settings — {interaction.guild.name}",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Autorole System", value="🟢 Enabled" if ar_cfg.enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Join Role", value=f"<@&{ar_cfg.role_id}>" if ar_cfg.role_id else "Not Set", inline=True)
        embed.set_footer(text="Use /autorole set to configure new member join roles.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # BACKGROUND TASKS
    # ==========================================

    @tasks.loop(minutes=10)
    async def supervisor_task(self):
        """Background maintenance: cleans expired runtime/db cooldowns and checks health."""
        try:
            counts = await self.bot.cooldowns.cleanup_expired()
            if any(counts.values()):
                logger.info(f"Autonomous Maintenance: Cleaned expired records -> {counts}")
        except Exception as e:
            logger.error(f"Error during supervisor maintenance loop: {e}")

    @tasks.loop(hours=6)
    async def backup_task(self):
        """Autonomous backup worker: safely snapshots SQLite database to data/backups/."""
        await self.execute_backup()

    @supervisor_task.before_loop
    @backup_task.before_loop
    async def before_tasks(self):
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass

    async def execute_backup(self) -> Optional[Path]:
        """Performs non-blocking safe SQLite database copy with timestamping and retention pruning."""
        if not DB_PATH.exists():
            return None

        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_file = BACKUPS_DIR / f"bot-{timestamp}.db"

        try:
            # Non-blocking file copy in thread pool
            await asyncio.to_thread(shutil.copy2, DB_PATH, backup_file)
            logger.info(f"Autonomous Backup: Successfully created {backup_file}")

            # Retention prune: Keep newest MAX_BACKUPS_RETAINED files
            backups = sorted(BACKUPS_DIR.glob("bot-*.db"), key=os.path.getmtime, reverse=True)
            if len(backups) > MAX_BACKUPS_RETAINED:
                for stale in backups[MAX_BACKUPS_RETAINED:]:
                    try:
                        stale.unlink()
                        logger.info(f"Autonomous Backup Prune: Removed stale backup {stale.name}")
                    except Exception:
                        pass

            return backup_file
        except Exception as e:
            logger.error(f"Autonomous Backup Failed: {e}")
            return None


async def setup(bot: SentinelBot):
    await bot.add_cog(SettingsCog(bot))
