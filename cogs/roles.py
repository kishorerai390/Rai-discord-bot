"""
Rai Automatic Discord Role Management Cog.
Provides staff slash commands (/roles setup, list, status, repair, sync, assign, remove, configure),
real-time event monitoring, timeout synchronization, and booster detection.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, security_embed, success_embed, warning_embed
from utils.interaction_reliability import safe_defer, safe_error_response, safe_response
from utils.permissions import is_admin_or_owner
from utils.role_manager import ROLE_DEFINITIONS

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("RaiRolesCog")


class RoleDashboardSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="System Overview", value="overview", emoji="📊", description="Hierarchy health, permissions & metrics"),
            discord.SelectOption(label="Automatic Setup", value="setup", emoji="⚡", description="Setup configuration & mapped roles"),
            discord.SelectOption(label="Member Roles", value="member_roles", emoji="👤", description="New member, member & verified mappings"),
            discord.SelectOption(label="Verification Roles", value="verification_roles", emoji="🔐", description="Verification required gatekeeper role"),
            discord.SelectOption(label="Security Roles", value="security_roles", emoji="🚨", description="Observation, restriction & threat roles"),
            discord.SelectOption(label="Raid Protection", value="raid_protection", emoji="🛑", description="Temporary anti-raid lockdown roles"),
            discord.SelectOption(label="Booster Role", value="booster_role", emoji="🌟", description="Nitro booster detection and sync"),
            discord.SelectOption(label="Temporary Roles", value="temporary_roles", emoji="⏳", description="Timeout and temporary state representations"),
            discord.SelectOption(label="Synchronization", value="synchronization", emoji="🔄", description="Live state sync with Discord"),
            discord.SelectOption(label="Self-Healing", value="self_healing", emoji="🩺", description="Automatic role restoration & integrity"),
            discord.SelectOption(label="Audit Logging", value="audit_logging", emoji="📜", description="Recent role modifications & events"),
        ]
        super().__init__(placeholder="Select Role Management Category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: RoleDashboardView = self.view  # type: ignore
        await view.handle_selection(interaction, self.values[0])


class RoleDashboardView(discord.ui.View):
    """Interactive visual dashboard for Rai Role Management."""

    def __init__(self, bot: SentinelBot, guild: discord.Guild, author_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.author_id = author_id
        self.current_category = "overview"
        self.add_item(RoleDashboardSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the administrator who opened this dashboard can interact with it.", ephemeral=True
            )
            return False
        return True

    async def handle_selection(self, interaction: discord.Interaction, value: str):
        self.current_category = value
        embed_methods = {
            "overview": self.get_overview_embed,
            "setup": self.get_setup_embed,
            "member_roles": self.get_member_roles_embed,
            "verification_roles": self.get_verification_embed,
            "security_roles": self.get_security_roles_embed,
            "raid_protection": self.get_raid_protection_embed,
            "booster_role": self.get_booster_embed,
            "temporary_roles": self.get_temporary_embed,
            "synchronization": self.get_synchronization_embed,
            "self_healing": self.get_self_healing_embed,
            "audit_logging": self.get_audit_logging_embed,
        }
        method = embed_methods.get(value, self.get_overview_embed)
        embed = await method()
        await interaction.response.edit_message(embed=embed, view=self)

    async def get_overview_embed(self) -> discord.Embed:
        can_manage = self.guild.me.guild_permissions.manage_roles
        top_role = self.guild.me.top_role
        manageable = sum(1 for r in self.guild.roles if r < top_role and not r.managed and not r.is_default())
        db_roles = await self.bot.db.get_all_guild_roles(self.guild.id)
        embed = create_embed(
            title="🛡️ Rai Role Management Dashboard — Overview",
            description=(
                f"**Server:** {self.guild.name} (`{self.guild.id}`)\n"
                f"**Rai's Top Role:** {top_role.mention} (Position: `{top_role.position}`)\n"
                f"**Manage Roles Permission:** {'✅ Active' if can_manage else '❌ Missing'}\n"
                f"**Manageable Hierarchy:** `{manageable}` of `{len(self.guild.roles)}` roles manageable"
            ),
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Configured System Roles", value=f"**{len(db_roles)}** of 23 mapped in database", inline=True)
        embed.add_field(name="Rate-Limit Queue", value="Active (Priority, Dedup & Jitter)", inline=True)
        embed.add_field(name="Self-Healing Engine", value="Online (Automatic Restoration)", inline=True)
        embed.set_footer(text="Use the dropdown menu to inspect categories, or buttons below to take actions.")
        return embed

    async def get_setup_embed(self) -> discord.Embed:
        db_roles = {r.role_key: r for r in await self.bot.db.get_all_guild_roles(self.guild.id)}
        embed = create_embed(
            title="⚡ Automatic Role Setup",
            description="Status of system roles configured during idempotent setup.",
            color=Colors.INFO,
        )
        lines = []
        for k in ["bot", "verified", "member", "new_member", "under_observation", "restricted", "security_threat", "timeout", "raid_protection"]:
            defn = ROLE_DEFINITIONS[k]
            if k in db_roles:
                role = self.guild.get_role(db_roles[k].discord_role_id)
                status = role.mention if role else "⚠️ *Role Missing*"
            else:
                status = "⚪ *Not Configured*"
            lines.append(f"**{defn['name']}**: {status}")
        embed.add_field(name="Core Managed Roles", value="\n".join(lines), inline=False)
        return embed

    async def get_member_roles_embed(self) -> discord.Embed:
        embed = create_embed(
            title="👤 Member & Onboarding Roles",
            description="Lifecycle pipeline for new member arrivals and onboarding.",
            color=Colors.SUCCESS,
        )
        embed.add_field(
            name="1. On Join",
            value="• Assign `🆕 New Member`\n• Assign `🔐 Verification Required` (if verification active)",
            inline=False,
        )
        embed.add_field(
            name="2. After Verification",
            value="• Remove `🆕 New Member` and `🔐 Verification Required`\n• Grant `✅ Verified` and `👤 Member`",
            inline=False,
        )
        return embed

    async def get_verification_embed(self) -> discord.Embed:
        cfg = await self.bot.db.get_verification_config(self.guild.id)
        role = self.guild.get_role(cfg.role_id) if cfg.role_id else None
        embed = create_embed(
            title="🔐 Verification Gatekeeper Roles",
            description="Controls user onboarding gatekeeping and verified member status.",
            color=Colors.WARNING,
        )
        embed.add_field(name="Verification Enabled", value="✅ Yes" if cfg.enabled else "❌ No", inline=True)
        embed.add_field(name="Configured Verified Role", value=role.mention if role else "None", inline=True)
        embed.add_field(name="Min Account Age", value=f"{cfg.min_account_age_hours} hours", inline=True)
        return embed

    async def get_security_roles_embed(self) -> discord.Embed:
        embed = create_embed(
            title="🚨 Security Brain Threat Roles",
            description="Roles automatically assigned during threat escalation.",
            color=Colors.ERROR,
        )
        embed.add_field(
            name="🟡 Under Observation",
            value="Assigned when unconfirmed suspicious behavior is observed (spam, unusual joins).",
            inline=False,
        )
        embed.add_field(
            name="🟠 Restricted",
            value="Assigned during security enforcement: blocks embeds, attachments, and mentions.",
            inline=False,
        )
        embed.add_field(
            name="🔴 Security Threat",
            value="Assigned ONLY when the security engine confirms composite risk thresholds.",
            inline=False,
        )
        return embed

    async def get_raid_protection_embed(self) -> discord.Embed:
        embed = create_embed(
            title="🛑 Anti-Raid Protection",
            description="Temporary quarantine during active elevated server raids.",
            color=Colors.ERROR,
        )
        embed.add_field(
            name="Raid Quarantine Role",
            value="`🛑 Raid Protection`: Applied to recent arrivals when incident enters HIGH or CRITICAL.",
            inline=False,
        )
        embed.add_field(
            name="Auto Restoration",
            value="When raid incident resolves, quarantine roles are automatically removed without mass-bans.",
            inline=False,
        )
        return embed

    async def get_booster_embed(self) -> discord.Embed:
        db_role = await self.bot.db.get_guild_role(self.guild.id, "booster")
        role = self.guild.get_role(db_role.discord_role_id) if db_role else None
        embed = create_embed(
            title="🌟 Server Booster Role",
            description="Auto-detects member Nitro boosts and synchronizes the Booster role.",
            color=0xF47FFF,
        )
        embed.add_field(name="Mapped Role", value=role.mention if role else "Not Configured", inline=True)
        embed.add_field(name="Active Boosters in Guild", value=str(self.guild.premium_subscription_count), inline=True)
        return embed

    async def get_temporary_embed(self) -> discord.Embed:
        embed = create_embed(
            title="⏳ Temporary Roles Management",
            description="Temporary state representations such as Discord Native Timeouts and Quarantines.",
            color=Colors.INFO,
        )
        embed.add_field(
            name="Timeout Role (`⏳ Timeout`)",
            value="Synchronized with Discord native `member.timed_out_until` state automatically.",
            inline=False,
        )
        return embed

    async def get_synchronization_embed(self) -> discord.Embed:
        embed = create_embed(
            title="🔄 Role Synchronization Engine",
            description="Active background checks ensuring Discord state matches configured roles.",
            color=Colors.PRIMARY,
        )
        embed.add_field(
            name="Synchronization Flow",
            value="`CHECK` ➔ `VALIDATE` ➔ `DETECT DIFFERENCES` ➔ `SAFE REPAIR` ➔ `VERIFY` ➔ `LOG`",
            inline=False,
        )
        return embed

    async def get_self_healing_embed(self) -> discord.Embed:
        embed = create_embed(
            title="🩺 Role Self-Healing Engine",
            description="Autonomous restoration of deleted or damaged managed roles.",
            color=Colors.SUCCESS,
        )
        embed.add_field(
            name="Integrity Protection",
            value=(
                "• Detects deleted roles and safely recreates them below Rai's position.\n"
                "• Never recreates dangerous staff roles automatically to prevent privilege escalation.\n"
                "• Invalidates stale caches immediately upon Discord role deletion events."
            ),
            inline=False,
        )
        return embed

    async def get_audit_logging_embed(self) -> discord.Embed:
        audits = await self.bot.db.get_recent_role_audits(self.guild.id, limit=10)
        embed = create_embed(
            title="📜 Role Audit Log History",
            description=f"Showing last {len(audits)} role events in this server.",
            color=Colors.INFO,
        )
        if audits:
            lines = [
                f"`{a.timestamp[11:19]}` **{a.action}** (`{a.role_key}`) -> {'✅' if a.success else '❌'} {a.reason or ''}"
                for a in audits
            ]
            embed.description = "\n".join(lines)
        else:
            embed.description = "No recent role audit events found."
        return embed

    @discord.ui.button(label="Setup Hierarchy", style=discord.ButtonStyle.primary, emoji="⚡", row=1)
    async def btn_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.role_manager.setup_guild_roles(self.guild, executor=interaction.user.display_name)
        embed = await self.get_setup_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Repair Roles", style=discord.ButtonStyle.success, emoji="🩺", row=1)
    async def btn_repair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.role_manager.repair_guild_roles(self.guild)
        embed = await self.get_self_healing_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Sync States", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def btn_sync(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.bot.role_manager.sync_guild_roles(self.guild)
        embed = await self.get_synchronization_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔁", row=1)
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        method_map = {
            "overview": self.get_overview_embed,
            "setup": self.get_setup_embed,
            "member_roles": self.get_member_roles_embed,
            "verification_roles": self.get_verification_embed,
            "security_roles": self.get_security_roles_embed,
            "raid_protection": self.get_raid_protection_embed,
            "booster_role": self.get_booster_embed,
            "temporary_roles": self.get_temporary_embed,
            "synchronization": self.get_synchronization_embed,
            "self_healing": self.get_self_healing_embed,
            "audit_logging": self.get_audit_logging_embed,
        }
        method = method_map.get(self.current_category, self.get_overview_embed)
        embed = await method()
        await interaction.edit_original_response(embed=embed, view=self)


class RolesCog(commands.Cog, name="Roles"):
    """Automatic Role Management, Hierarchy Safety, and Self-Healing."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    roles_group = app_commands.Group(
        name="roles",
        description="Automatic role hierarchy, configuration, and self-healing",
        default_permissions=discord.Permissions(manage_roles=True),
    )

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @roles_group.command(name="setup", description="Inspect, reuse, or safely create server role hierarchy")
    @is_admin_or_owner()
    async def roles_setup(self, interaction: discord.Interaction):
        """Idempotently sets up Rai's role hierarchy."""
        await safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        if not guild:
            await safe_error_response(interaction, "This command can only be used in a server.")
            return

        report = await self.bot.role_manager.setup_guild_roles(
            guild, executor=interaction.user.display_name
        )

        embed = create_embed(
            title="🛡️ Rai Role Hierarchy Setup",
            description=f"Automated role inspection and configuration completed for **{guild.name}**.",
            color=Colors.PRIMARY,
        )

        if report["reused"]:
            embed.add_field(
                name=f"♻️ Reused Existing Roles ({len(report['reused'])})",
                value="\n".join(report["reused"][:15]) or "None",
                inline=False,
            )

        if report["created"]:
            embed.add_field(
                name=f"✨ Created Roles ({len(report['created'])})",
                value="\n".join(report["created"][:15]) or "None",
                inline=False,
            )

        if report["skipped"]:
            embed.add_field(
                name=f"⚠️ Skipped Staff Roles ({len(report['skipped'])})",
                value="\n".join(report["skipped"][:10]) or "None",
                inline=False,
            )

        if report["errors"]:
            embed.add_field(
                name=f"❌ Errors ({len(report['errors'])})",
                value="\n".join(report["errors"][:5]) or "None",
                inline=False,
            )

        embed.set_footer(text="Idempotent: Re-running will never create duplicate roles.")
        await safe_response(interaction, embed=embed)

    @roles_group.command(name="list", description="List all Rai system roles and their mapping status")
    @is_admin_or_owner()
    async def roles_list(self, interaction: discord.Interaction):
        """Displays configured roles grouped by category."""
        await safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        if not guild:
            await safe_error_response(interaction, "This command can only be used in a server.")
            return

        db_roles = {r.role_key: r for r in await self.bot.db.get_all_guild_roles(guild.id)}

        embed = create_embed(
            title=f"📋 Managed Roles — {guild.name}",
            description="Configuration status for all standard role keys in Rai's system.",
            color=Colors.INFO,
        )

        categories = {"STAFF": "👑 Staff Roles", "BOT": "🤖 Bot Roles", "COMMUNITY": "🌟 Community Roles", "SECURITY": "🛡️ Security & Temp Roles"}

        for cat_key, cat_title in categories.items():
            lines: List[str] = []
            for key, defn in ROLE_DEFINITIONS.items():
                if defn["type"] != cat_key:
                    continue

                if key in db_roles:
                    rec = db_roles[key]
                    role = guild.get_role(rec.discord_role_id)
                    if role:
                        lines.append(f"`{key}`: {role.mention} (Pos: {role.position})")
                    else:
                        lines.append(f"`{key}`: ⚠️ **Missing in Guild** (Configured ID: `{rec.discord_role_id}`)")
                else:
                    lines.append(f"`{key}`: ⚪ *Not Configured* ({defn['name']})")

            embed.add_field(name=cat_title, value="\n".join(lines) or "None", inline=False)

        await safe_response(interaction, embed=embed)

    @roles_group.command(name="status", description="Check role manager status and hierarchy health")
    @is_admin_or_owner()
    async def roles_status(self, interaction: discord.Interaction):
        """Displays role manager health and permissions check."""
        await safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        if not guild:
            await safe_error_response(interaction, "This command can only be used in a server.")
            return

        can_manage = guild.me.guild_permissions.manage_roles
        top_role = guild.me.top_role
        manageable_count = sum(1 for r in guild.roles if r < top_role and not r.managed and not r.is_default())
        total_roles = len(guild.roles)
        db_roles = await self.bot.db.get_all_guild_roles(guild.id)
        audits = await self.bot.db.get_recent_role_audits(guild.id, limit=5)

        embed = create_embed(
            title="🩺 Role System Status & Hierarchy Health",
            description=f"Role system status for **{guild.name}**.",
            color=Colors.SUCCESS if can_manage else Colors.ERROR,
        )

        embed.add_field(name="Bot Top Role", value=f"{top_role.mention} (Pos: {top_role.position})", inline=True)
        embed.add_field(name="Manage Roles Perm", value="✅ Granted" if can_manage else "❌ Missing", inline=True)
        embed.add_field(name="Manageable Roles", value=f"{manageable_count} / {total_roles}", inline=True)
        embed.add_field(name="Configured Roles in DB", value=f"{len(db_roles)} mapped", inline=True)

        if audits:
            audit_lines = [
                f"`{a.timestamp[:19]}` **{a.action}** ({a.role_key}) -> {'✅' if a.success else '❌'} {a.reason or ''}"
                for a in audits
            ]
            embed.add_field(name="Recent Role Audit Events", value="\n".join(audit_lines), inline=False)

        await safe_response(interaction, embed=embed)

    @roles_group.command(name="repair", description="Self-healing: detect and restore missing managed roles")
    @is_admin_or_owner()
    async def roles_repair(self, interaction: discord.Interaction):
        """Repairs deleted managed roles safely."""
        await safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        if not guild:
            await safe_error_response(interaction, "This command can only be used in a server.")
            return

        report = await self.bot.role_manager.repair_guild_roles(guild)

        embed = create_embed(
            title="🔄 Role Self-Healing Report",
            description="Inspected all mapped roles against live Discord guild roles.",
            color=Colors.SUCCESS,
        )

        if report["recreated"]:
            embed.add_field(
                name=f"✨ Restored Roles ({len(report['recreated'])})",
                value="\n".join(report["recreated"]),
                inline=False,
            )

        if report["skipped_staff"]:
            embed.add_field(
                name=f"🛡️ Skipped Staff Roles ({len(report['skipped_staff'])})",
                value="\n".join(report["skipped_staff"]),
                inline=False,
            )

        if not report["recreated"] and not report["skipped_staff"] and not report["errors"]:
            embed.description = "✅ All configured roles are healthy and intact. No repair needed."

        if report["errors"]:
            embed.add_field(
                name="❌ Errors",
                value="\n".join(report["errors"]),
                inline=False,
            )

        await safe_response(interaction, embed=embed)

    @roles_group.command(name="sync", description="Synchronize native timeouts and booster status")
    @is_admin_or_owner()
    async def roles_sync(self, interaction: discord.Interaction):
        """Synchronizes temporary roles and member states."""
        await safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        if not guild:
            await safe_error_response(interaction, "This command can only be used in a server.")
            return

        report = await self.bot.role_manager.sync_guild_roles(guild)

        embed = create_embed(
            title="⚡ Role Synchronization Complete",
            description=f"Synchronized temporary states for **{guild.name}**.",
            color=Colors.SUCCESS,
        )
        embed.add_field(name="⏳ Timeouts Synchronized", value=str(report["timeouts_synced"]), inline=True)
        embed.add_field(name="🌟 Boosters Synchronized", value=str(report["boosters_synced"]), inline=True)

        await safe_response(interaction, embed=embed)

    @roles_group.command(name="assign", description="Safely assign a role to a member")
    @app_commands.describe(
        member="Target server member",
        role_key="System role key (e.g. vip, creator, gamer, verified)",
        reason="Reason for role assignment",
    )
    @app_commands.choices(
        role_key=[
            app_commands.Choice(name="💎 VIP", value="vip"),
            app_commands.Choice(name="🎨 Creator", value="creator"),
            app_commands.Choice(name="🎮 Gamer", value="gamer"),
            app_commands.Choice(name="✅ Verified", value="verified"),
            app_commands.Choice(name="👤 Member", value="member"),
            app_commands.Choice(name="🟡 Under Observation", value="under_observation"),
            app_commands.Choice(name="🟠 Restricted", value="restricted"),
            app_commands.Choice(name="🔴 Security Threat", value="security_threat"),
        ]
    )
    async def roles_assign(
        self, interaction: discord.Interaction, member: discord.Member, role_key: str, reason: Optional[str] = "Staff Assignment"
    ):
        """Assigns a role verifying executor permissions and hierarchy."""
        await safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        executor = interaction.user
        if not guild or not isinstance(executor, discord.Member):
            await safe_error_response(interaction, "Command must be used inside a guild.")
            return

        target_role = await self.bot.role_manager.get_role(guild, role_key)
        if not target_role:
            await safe_error_response(interaction, f"Role `{role_key}` is not configured yet. Run `/roles setup` first.")
            return

        can_exec, exec_reason = self.bot.role_manager.validate_executor_permissions(executor, member, target_role)
        if not can_exec:
            await safe_error_response(interaction, f"Permission Denied: {exec_reason}")
            return

        ok, msg = await self.bot.role_manager.assign_role(
            guild, member, role_key, reason=reason or "Staff Assignment", trigger="STAFF", executor=executor.display_name
        )
        if ok:
            await safe_response(
                interaction,
                embed=success_embed("Role Assigned", f"Assigned **{target_role.name}** to {member.mention}.\n{msg}"),
            )
        else:
            await safe_error_response(interaction, f"Failed to assign role: {msg}")

    @roles_group.command(name="remove", description="Safely remove a role from a member")
    @app_commands.describe(
        member="Target server member",
        role_key="System role key (e.g. vip, creator, gamer, under_observation)",
        reason="Reason for role removal",
    )
    @app_commands.choices(
        role_key=[
            app_commands.Choice(name="💎 VIP", value="vip"),
            app_commands.Choice(name="🎨 Creator", value="creator"),
            app_commands.Choice(name="🎮 Gamer", value="gamer"),
            app_commands.Choice(name="✅ Verified", value="verified"),
            app_commands.Choice(name="👤 Member", value="member"),
            app_commands.Choice(name="🟡 Under Observation", value="under_observation"),
            app_commands.Choice(name="🟠 Restricted", value="restricted"),
            app_commands.Choice(name="🔴 Security Threat", value="security_threat"),
            app_commands.Choice(name="🛑 Raid Protection", value="raid_protection"),
        ]
    )
    async def roles_remove(
        self, interaction: discord.Interaction, member: discord.Member, role_key: str, reason: Optional[str] = "Staff Removal"
    ):
        """Removes a role verifying executor permissions and hierarchy."""
        await safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        executor = interaction.user
        if not guild or not isinstance(executor, discord.Member):
            await safe_error_response(interaction, "Command must be used inside a guild.")
            return

        target_role = await self.bot.role_manager.get_role(guild, role_key)
        if not target_role:
            await safe_error_response(interaction, f"Role `{role_key}` is not configured.")
            return

        can_exec, exec_reason = self.bot.role_manager.validate_executor_permissions(executor, member, target_role)
        if not can_exec:
            await safe_error_response(interaction, f"Permission Denied: {exec_reason}")
            return

        ok, msg = await self.bot.role_manager.remove_role(
            guild, member, role_key, reason=reason or "Staff Removal", trigger="STAFF", executor=executor.display_name
        )
        if ok:
            await safe_response(
                interaction,
                embed=success_embed("Role Removed", f"Removed **{target_role.name}** from {member.mention}.\n{msg}"),
            )
        else:
            await safe_error_response(interaction, f"Failed to remove role: {msg}")

    @roles_group.command(name="configure", description="Map a custom server role to a Rai system key")
    @is_admin_or_owner()
    @app_commands.describe(role_key="The system role key to bind", role="The Discord role to map")
    async def roles_configure(self, interaction: discord.Interaction, role_key: str, role: discord.Role):
        """Explicitly binds an existing Discord role to a system key."""
        await safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        if role_key not in ROLE_DEFINITIONS:
            valid_keys = ", ".join(f"`{k}`" for k in ROLE_DEFINITIONS.keys())
            await safe_error_response(interaction, f"Invalid role key. Must be one of:\n{valid_keys}")
            return

        defn = ROLE_DEFINITIONS[role_key]
        await self.bot.db.save_guild_role(
            guild_id=guild.id,
            role_key=role_key,
            discord_role_id=role.id,
            role_name=role.name,
            role_type=defn["type"],
            managed_by_rai=True,
            enabled=True,
            position=role.position,
        )
        self.bot.role_manager.invalidate_guild_cache(guild.id)

        await safe_response(
            interaction,
            embed=success_embed("Role Configured", f"Mapped system key `{role_key}` to {role.mention}."),
        )

    @roles_group.command(name="dashboard", description="Interactive visual Role Management & Configuration Dashboard")
    @is_admin_or_owner()
    async def roles_dashboard(self, interaction: discord.Interaction):
        """Displays interactive dashboard with category select menus and quick actions."""
        await safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        if not guild:
            await safe_error_response(interaction, "Command can only be used in a server.")
            return

        view = RoleDashboardView(self.bot, guild, interaction.user.id)
        embed = await view.get_overview_embed()
        await safe_response(interaction, embed=embed, view=view)

    # ==========================================
    # EVENT LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Auto-assigns new_member and verification_required roles upon member join."""
        if not hasattr(self.bot, "role_manager") or not self.bot.role_manager:
            return
        try:
            await self.bot.role_manager.on_member_join(member)
        except Exception as e:
            logger.error(f"Error in on_member_join role assignment: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Listens for boost status and native timeout changes."""
        if not hasattr(self.bot, "role_manager") or not self.bot.role_manager:
            return

        guild = after.guild

        # 1. Booster detection
        if before.premium_since != after.premium_since:
            if after.premium_since is not None:
                # Started boosting
                await self.bot.role_manager.assign_role(
                    guild, after, "booster", reason="Nitro boost started", trigger="BOOST_DETECTED"
                )
                await self._handle_booster_concierge(after)
            else:
                # Stopped boosting
                await self.bot.role_manager.remove_role(
                    guild, after, "booster", reason="Nitro boost stopped", trigger="BOOST_DETECTED"
                )

    async def _handle_booster_concierge(self, member: discord.Member) -> None:
        """
        VIP Booster Concierge & Autonomous Penthouse Activation:
        1. Celebrates new boost in #🚀・ʙᴏᴏsᴛᴇʀ-ʟᴏᴜɴɢᴇ with rich luxury embed.
        2. Dispatches executive VIP onboarding direct message with perk breakdown.
        3. Grants access to #🚀・ʙᴏᴏsᴛᴇʀ-ʟᴏᴜɴɢᴇ and 👑・VIP Penthouse.
        """
        guild = member.guild
        BOOSTER_LOUNGE_ID = 1557479371001045056   # #🚀・ʙᴏᴏsᴛᴇʀ-ʟᴏᴜɴɢᴇ
        VIP_PENTHOUSE_ID = 1557481242054758482    # 👑・VIP Penthouse

        # 1. Post luxury celebration in Booster Lounge
        lounge_ch = guild.get_channel(BOOSTER_LOUNGE_ID)
        if lounge_ch and isinstance(lounge_ch, discord.TextChannel):
            embed = discord.Embed(
                title="💎 EXCLUSIVE SERVER BOOST ACTIVATED! 💎",
                description=(
                    f"**Welcome to elite status, {member.mention}!**\n\n"
                    f"Thank you for elevating **{guild.name}** with your Nitro boost! "
                    f"Your support powers our high-performance infrastructure.\n\n"
                    f"👑 **Unlocked Booster Privileges:**\n"
                    f"• Access to the private `#🚀・ʙᴏᴏsᴛᴇʀ-ʟᴏᴜɴɢᴇ`\n"
                    f"• High-fidelity 384kbps audio in `👑・VIP Penthouse`\n"
                    f"• Top priority audio request queue on **Neko Songs** 🎵\n"
                    f"• Distinct Booster role badge and elevated member ranking"
                ),
                color=discord.Color.from_rgb(244, 127, 255),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"{guild.name} • VIP Booster Concierge")
            embed.timestamp = discord.utils.utcnow()
            try:
                await lounge_ch.send(content=f"🎉 Welcome {member.mention} to the VIP Club!", embed=embed)
            except Exception as e:
                logger.error(f"Failed to post booster announcement in lounge: {e}")

        # 2. Luxury DM to the booster
        try:
            dm_embed = discord.Embed(
                title=f"👑 VIP Penthouse Access Granted — {guild.name}",
                description=(
                    f"Greetings **{member.display_name}**,\n\n"
                    f"Thank you for boosting **{guild.name}**! Your exclusive VIP privileges are now fully unlocked:\n\n"
                    f"🎧 **1. VIP Penthouse Voice:** Private, high-fidelity studio voice pod (`👑・VIP Penthouse`).\n"
                    f"💬 **2. Booster Lounge:** Secret discussions in `#🚀・ʙᴏᴏsᴛᴇʀ-ʟᴏᴜɴɢᴇ`.\n"
                    f"🎵 **3. Priority Audio:** Fast-tracked songs and priority queue on Neko Songs.\n"
                    f"✨ **4. Prestige Styling:** Exclusive Nitro Booster icon and profile highlight.\n\n"
                    f"Enjoy your luxury experience! Our concierge and staff are always at your service."
                ),
                color=discord.Color.from_rgb(244, 127, 255),
            )
            if guild.icon:
                dm_embed.set_thumbnail(url=guild.icon.url)
            dm_embed.set_footer(text="The Raivora Sanctuary Executive Concierge")
            await member.send(embed=dm_embed)
        except Exception:
            pass  # User DMs closed

        # 2. Native Discord Timeout sync
        if before.timed_out_until != after.timed_out_until:
            now = datetime.datetime.now(datetime.timezone.utc)
            if after.timed_out_until is not None and after.timed_out_until > now:
                await self.bot.role_manager.assign_role(
                    guild, after, "timeout", reason="Discord native timeout active", trigger="TIMEOUT_SYNC"
                )
            else:
                await self.bot.role_manager.remove_role(
                    guild, after, "timeout", reason="Discord native timeout expired or removed", trigger="TIMEOUT_SYNC"
                )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Detects deleted roles and cleans up role cache / triggers healing."""
        if not hasattr(self.bot, "role_manager") or not self.bot.role_manager:
            return

        self.bot.role_manager.invalidate_role_cache(role.guild.id, role.id)
        # Log event in DB
        db_role = await self.bot.db.get_guild_role_by_id(role.guild.id, role.id)
        if db_role:
            await self.bot.db.log_role_audit(
                guild_id=role.guild.id,
                user_id=None,
                role_id=role.id,
                role_key=db_role.role_key,
                action="ROLE_DELETED",
                reason=f"Managed role '{role.name}' was deleted from Discord",
                trigger="ROLE_DELETE_EVENT",
                executor="UNKNOWN",
                success=True,
            )
            logger.warning(
                f"Managed role '{role.name}' ({db_role.role_key}) was deleted in guild {role.guild.name} ({role.guild.id})."
            )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handles interactive component interactions for self-assignable role panels."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if not custom_id.startswith("rai_role_select_"):
            return

        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            return

        # Immediate deferral to satisfy reliability SLA
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        selected_values = interaction.data.get("values", [])

        if custom_id in ("rai_role_select_games", "rai_role_select_notifs"):
            # Multi-select toggle
            added = []
            removed = []
            
            # Find all options present in the select component
            all_component_role_ids = set()
            for opt in interaction.data.get("options", []):
                val = opt.get("value")
                if val and val.isdigit():
                    all_component_role_ids.add(int(val))

            selected_role_ids = {int(v) for v in selected_values if v.isdigit()}
            member_role_ids = {r.id for r in member.roles}

            # Add selected roles that member doesn't have
            for rid in selected_role_ids:
                if rid not in member_role_ids:
                    role = guild.get_role(rid)
                    if role and role < guild.me.top_role:
                        try:
                            await member.add_roles(role, reason="Self-assigned via role panel")
                            added.append(role.name)
                        except Exception as e:
                            logger.debug(f"Failed to add role {role.name}: {e}")

            # Remove unselected roles from the component
            for rid in all_component_role_ids:
                if rid in member_role_ids and rid not in selected_role_ids:
                    role = guild.get_role(rid)
                    if role and role < guild.me.top_role:
                        try:
                            await member.remove_roles(role, reason="Self-removed via role panel")
                            removed.append(role.name)
                        except Exception as e:
                            logger.debug(f"Failed to remove role {role.name}: {e}")

            desc = []
            if added:
                desc.append(f"**Added:** {', '.join(added)}")
            if removed:
                desc.append(f"**Removed:** {', '.join(removed)}")
            if not desc:
                desc.append("No changes were made to your roles.")

            embed = success_embed("Roles Updated", "\n".join(desc))
            await safe_response(interaction, embed=embed, ephemeral=True)

        elif custom_id == "rai_role_select_colors":
            # Single color select: remove other color roles, add new one
            color_role_keywords = ["Sakura Pink", "Neon Purple", "Cyber Cyan", "Royal Gold"]
            color_roles = [r for r in guild.roles if any(k in r.name for k in color_role_keywords)]

            if not selected_values:
                return

            chosen_id = int(selected_values[0]) if selected_values[0].isdigit() else None
            chosen_role = guild.get_role(chosen_id) if chosen_id else None

            # Remove existing color roles
            roles_to_remove = [r for r in color_roles if r in member.roles and r.id != chosen_id and r < guild.me.top_role]
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Color role replacement")
                except Exception:
                    pass

            if chosen_role and chosen_role not in member.roles and chosen_role < guild.me.top_role:
                try:
                    await member.add_roles(chosen_role, reason="Self-assigned chat color")
                    embed = success_embed("Color Updated", f"Your chat color is now set to **{chosen_role.name}**!")
                except Exception as e:
                    embed = error_embed("Color Update Failed", f"Could not assign color role: {e}")
            else:
                embed = info_embed("Color Unchanged", f"You already have the **{chosen_role.name if chosen_role else 'selected'}** color.")

            await safe_response(interaction, embed=embed, ephemeral=True)



async def setup(bot: SentinelBot):
    await bot.add_cog(RolesCog(bot))
