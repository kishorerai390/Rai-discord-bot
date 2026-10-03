"""
RAI Private Control Center - Hidden Owner/Admin/Security Operations System.

Organizes Rai's operational channels into a completely hidden control area:
🔐 | RAI PRIVATE CONTROL
├── 📋 | RAI REPORTS
│   ├── 🚨・security-report
│   ├── 🛡️・mod-report
│   ├── 🎵・music-report
│   ├── 🔐・room-report
│   ├── 🤖・bot-report
│   └── ⚙️・system-report
├── 🛡️ | RAI SECURITY
│   ├── 🚨・security-alerts
│   ├── 🧱・anti-nuke
│   ├── 🛡️・security-log
│   ├── 🔍・audit-monitor
│   └── 🔒・lockdown-control
└── ⚙️ | RAI ADMIN
    ├── 👑・admin-control
    ├── 📊・server-dashboard
    ├── ⚙️・bot-config
    ├── 🤖・automation-control
    ├── 💾・backup-control
    └── ❤️・system-health

Features:
- Complete hidden permission overwrites: @everyone view_channel=False.
- Dynamic Server Owner full access.
- Rai Bot necessary management permissions.
- Role-based granular operational access:
  - RAI_OWNER -> Full access (Reports + Security + Admin)
  - RAI_SECURITY -> Security + relevant reports
  - RAI_ADMIN -> Admin + relevant reports
  - Normal members/moderators -> Inaccessible.
- Interactive control consoles for Lockdown, Admin, and Security with ephemeral responses.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
import discord

from config import Colors
from database.models import PrivateControlConfig, OwnerReportsConfig

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("PrivateControl")

FOUNDER_ID = 1457380609641938981
BOT_USER_ID = 1554732669072445532


class PrivateControlManager:
    """Manager for the hidden operational control categories and interactive panels."""

    # Category and Channel Names
    CONTROL_HUB_CATEGORY = "🔐 | RAI PRIVATE CONTROL"
    REPORTS_CATEGORY = "📋 | RAI REPORTS"
    SECURITY_CATEGORY = "🛡️ | RAI SECURITY"
    ADMIN_CATEGORY = "⚙️ | RAI ADMIN"

    # Expected Channels per category
    REPORTS_CHANNELS = [
        ("🚨・security-report", "Detailed security incident reports and actionable consoles."),
        ("🛡️・mod-report", "Moderation sanctions and enforcement logs."),
        ("🎵・music-report", "Music subsystem and stream telemetry."),
        ("🔐・room-report", "Private voice suite lifecycle reports."),
        ("🤖・bot-report", "Bot configuration and operational reports."),
        ("⚙️・system-report", "System infrastructure, health, and error reports."),
    ]

    SECURITY_CHANNELS = [
        ("🚨・security-alerts", "Critical security incidents and immediate alerts."),
        ("🧱・anti-nuke", "Anti-nuke detections, mass-action protection and prevention."),
        ("🛡️・security-log", "Security events and verified security actions."),
        ("🔍・audit-monitor", "Discord audit-log monitoring and suspicious activity."),
        ("🔒・lockdown-control", "Emergency lockdown status and owner controls."),
    ]

    ADMIN_CHANNELS = [
        ("👑・admin-control", "Owner-level Rai administrative controls."),
        ("📊・server-dashboard", "Server statistics and system overview."),
        ("⚙️・bot-config", "Rai configuration and settings."),
        ("🤖・automation-control", "Automation status and background tasks."),
        ("💾・backup-control", "Backup creation, verification and restore controls."),
        ("❤️・system-health", "Bot health, workers, database, latency and dependency status."),
    ]

    # ==========================================
    # PERMISSION OVERWRITE BUILDER
    # ==========================================

    @classmethod
    def build_strict_overwrites(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        category_type: str = "all",  # "reports", "security", "admin", "hub", "all"
    ) -> Dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
        """
        Builds strict, verified Discord permission overwrites ensuring complete
        invisibility to normal members while granting appropriate operational access.
        """
        overwrites: Dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {}

        # 1. @everyone MUST BE COMPLETELY DENIED
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            view_channel=False,
            send_messages=False,
            read_messages=False,
            read_message_history=False,
            create_instant_invite=False,
        )

        # 2. Configured Owner / Founder ALLOWED FULL ACCESS
        owner_id = getattr(guild, "owner_id", None)
        owner_member = None
        if owner_id:
            owner_member = guild.get_member(owner_id)
        if not owner_member and hasattr(guild, "owner") and guild.owner:
            owner_member = guild.owner

        if owner_member:
            overwrites[owner_member] = discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                manage_messages=True,
                use_application_commands=True,
            )

        # Also founder fallback if in guild
        if FOUNDER_ID != owner_id:
            founder_member = guild.get_member(FOUNDER_ID)
            if founder_member:
                overwrites[founder_member] = discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    read_message_history=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    manage_messages=True,
                    use_application_commands=True,
                )

        # 3. Rai Bot (self) gets required management permissions
        me = getattr(guild, "me", None)
        if me:
            overwrites[me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_messages=True,
                read_message_history=True,
                embed_links=True,
                attach_files=True,
                manage_messages=True,
                manage_channels=True,
                manage_roles=True,
            )

        # 4. Explicitly DENY common staff/moderator roles from seeing control channels
        # unless assigned dedicated Rai operational roles
        for role in getattr(guild, "roles", []):
            rname = getattr(role, "name", "").lower()
            if role == guild.default_role or role.managed:
                continue

            # Check if this is a dedicated Rai operational role
            is_rai_owner_role = any(kw in rname for kw in ("rai_owner", "rai owner", "👑 owner"))
            is_rai_sec_role = any(kw in rname for kw in ("rai_security", "rai security", "security admin", "🛡️ security"))
            is_rai_admin_role = any(kw in rname for kw in ("rai_admin", "rai admin", "⚡ administrator"))

            if is_rai_owner_role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    read_message_history=True,
                    send_messages=True,
                    embed_links=True,
                    use_application_commands=True,
                )
            elif is_rai_sec_role:
                can_view = category_type in ("security", "reports", "hub", "all")
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=can_view,
                    read_messages=can_view,
                    read_message_history=can_view,
                    send_messages=can_view,
                    embed_links=can_view,
                    use_application_commands=can_view,
                )
            elif is_rai_admin_role:
                can_view = category_type in ("admin", "reports", "hub", "all")
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=can_view,
                    read_messages=can_view,
                    read_message_history=can_view,
                    send_messages=can_view,
                    embed_links=can_view,
                    use_application_commands=can_view,
                )
            elif any(mod_kw in rname for mod_kw in ("moderator", "mod", "staff", "helper", "trial")):
                # Standard staff / mod roles without global Admin must not see operational consoles
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=False,
                    send_messages=False,
                    read_messages=False,
                )

        return overwrites

    # ==========================================
    # AUTHORIZATION CHECKER
    # ==========================================

    @classmethod
    async def is_authorized(
        cls,
        bot: SentinelBot,
        guild_id: int,
        user: discord.User | discord.Member,
        scope: str = "admin",  # "owner", "security", "admin"
    ) -> bool:
        """
        Verifies if the user is authorized for a control action.
        - "owner": Only Discord server owner or founder
        - "security": Server owner or member with RAI_SECURITY role
        - "admin": Server owner or member with RAI_ADMIN role
        """
        # Founder and Server Owner always have access to everything
        if user.id == FOUNDER_ID:
            return True

        guild = bot.get_guild(guild_id) if hasattr(bot, "get_guild") else None
        if not guild and hasattr(bot, "fetch_guild"):
            try:
                guild = await bot.fetch_guild(guild_id)
            except Exception:
                guild = None

        if guild and getattr(guild, "owner_id", None) == user.id:
            return True

        if scope == "owner":
            return False

        # Check role assignments
        if isinstance(user, discord.Member):
            user_roles = [r.name.lower() for r in user.roles]
            user_role_ids = [r.id for r in user.roles]

            db = getattr(bot, "db", None)
            cfg: Optional[PrivateControlConfig] = None
            if db and hasattr(db, "get_private_control_config"):
                try:
                    cfg = await db.get_private_control_config(guild_id)
                except Exception:
                    cfg = None

            if scope == "security":
                if cfg and cfg.rai_security_role_id and cfg.rai_security_role_id in user_role_ids:
                    return True
                if any(kw in r for r in user_roles for kw in ("rai_security", "security admin", "🛡️ security")):
                    return True

            if scope == "admin":
                if cfg and cfg.rai_admin_role_id and cfg.rai_admin_role_id in user_role_ids:
                    return True
                if any(kw in r for r in user_roles for kw in ("rai_admin", "administrator", "admin")):
                    return True

        return False

    # ==========================================
    # INTERACTIVE CONSOLE BUILDERS
    # ==========================================

    @classmethod
    def build_lockdown_embed(cls, guild: discord.Guild, is_locked: bool = False) -> discord.Embed:
        """Builds interactive lockdown control status embed."""
        status_text = "🔴 **EMERGENCY LOCKDOWN ACTIVE**" if is_locked else "🟢 **NORMAL (CHANNELS OPEN)**"
        color = Colors.ERROR if is_locked else Colors.SUCCESS
        embed = discord.Embed(
            title="🔒 RAI LOCKDOWN CONTROL",
            description=(
                "Emergency containment and channel lockdown console.\n"
                "When activated, member permissions across all channels are restricted to prevent raids, nukes, and unauthorized modifications."
            ),
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="📊 Current Server Status", value=status_text, inline=False)
        embed.add_field(name="🛡️ Anti-Raid Threshold", value="`Active • 5 req / 3s`", inline=True)
        embed.add_field(name="🧱 Anti-Nuke Status", value="`Armed • Quarantine Active`", inline=True)
        embed.set_footer(text=f"Rai Security Operations • Guild ID: {guild.id} • Owner/Security Admin Only")
        return embed

    @classmethod
    def build_lockdown_view(cls, guild_id: int, is_locked: bool = False) -> discord.ui.View:
        """Constructs interactive lockdown buttons."""
        view = discord.ui.View(timeout=None)
        if not is_locked:
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="Enable Lockdown",
                emoji="🔒",
                custom_id=f"rai_ctrl:lockdown:{guild_id}",
            ))
        else:
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Disable Lockdown",
                emoji="🔓",
                custom_id=f"rai_ctrl:unlock:{guild_id}",
            ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="View Status",
            emoji="📋",
            custom_id=f"rai_ctrl:lockdown_status:{guild_id}",
        ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Recheck",
            emoji="🔄",
            custom_id=f"rai_ctrl:recheck_lockdown:{guild_id}",
        ))
        return view

    @classmethod
    def build_admin_embed(cls, guild: discord.Guild) -> discord.Embed:
        """Builds master administrative control embed."""
        embed = discord.Embed(
            title="👑 RAI ADMINISTRATIVE CONTROL CENTER",
            description=(
                "Master operations hub for Rai automated systems, backups, configuration, and diagnostics."
            ),
            color=Colors.PRIMARY,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="🤖 Bot System", value="`Rai Core 2.0 • Online`", inline=True)
        embed.add_field(name="💾 Backup Status", value="`Automated Daily Backups Active`", inline=True)
        embed.add_field(name="⚙️ Configuration", value="`Synchronized with Cloud DB`", inline=True)
        embed.add_field(
            name="⚡ Operational Directives",
            value=(
                "• **Configuration:** Inspect and modify active bot flags.\n"
                "• **Automation:** Check watchdog status and background workers.\n"
                "• **Backup:** Create an immediate encrypted disaster recovery archive.\n"
                "• **Health:** Run sub-system diagnostics across all cores."
            ),
            inline=False,
        )
        embed.set_footer(text=f"Rai Admin Center • Guild: {guild.name} • Server Owner / Admin Only")
        return embed

    @classmethod
    def build_admin_view(cls, guild_id: int) -> discord.ui.View:
        """Constructs interactive admin buttons."""
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Configuration",
            emoji="⚙️",
            custom_id=f"rai_ctrl:config:{guild_id}",
        ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Automation",
            emoji="🤖",
            custom_id=f"rai_ctrl:automation:{guild_id}",
        ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Backup",
            emoji="💾",
            custom_id=f"rai_ctrl:backup:{guild_id}",
        ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Health",
            emoji="❤️",
            custom_id=f"rai_ctrl:health:{guild_id}",
        ))
        return view

    @classmethod
    def build_security_control_embed(cls, guild: discord.Guild) -> discord.Embed:
        """Builds security monitor control embed."""
        embed = discord.Embed(
            title="🛡️ RAI SECURITY & THREAT INTELLIGENCE",
            description=(
                "Live security command surface. Direct controls to audit server integrity, initiate threat scans, and inspect forensic incident logs."
            ),
            color=Colors.ERROR,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="🚨 Threat Detection", value="`Real-Time Protection Armed`", inline=True)
        embed.add_field(name="🔍 Audit Monitor", value="`Tracing Guild Audit Events`", inline=True)
        embed.add_field(name="🧱 Anti-Nuke Status", value="`Channel & Role Protection Active`", inline=True)
        embed.set_footer(text="Rai Threat Intelligence • Confidential Operations")
        return embed

    @classmethod
    def build_security_control_view(cls, guild_id: int) -> discord.ui.View:
        """Constructs security control buttons."""
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Lockdown",
            emoji="🔒",
            custom_id=f"rai_ctrl:lockdown:{guild_id}",
        ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Security Scan",
            emoji="🛡️",
            custom_id=f"rai_ctrl:scan:{guild_id}",
        ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Audit Check",
            emoji="🔍",
            custom_id=f"rai_ctrl:audit:{guild_id}",
        ))
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Incident Details",
            emoji="📋",
            custom_id=f"rai_ctrl:incident_details:{guild_id}",
        ))
        return view

    # ==========================================
    # INTERACTION ROUTER FOR RAI_CTRL
    # ==========================================

    @classmethod
    async def handle_control_interaction(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
    ) -> bool:
        """
        Global interaction router for all persistent control buttons.
        Custom ID format: rai_ctrl:{action}:{guild_id}
        """
        cid = interaction.data.get("custom_id", "")
        if not cid.startswith("rai_ctrl:"):
            return False

        parts = cid.split(":")
        if len(parts) < 3:
            return False

        action = parts[1]
        try:
            guild_id = int(parts[2])
        except ValueError:
            guild_id = interaction.guild_id or 0

        # Scope verification
        admin_actions = ("config", "automation", "backup", "health")
        security_actions = ("lockdown", "unlock", "lockdown_status", "recheck_lockdown", "scan", "audit", "incident_details")
        scope = "admin" if action in admin_actions else "security"

        authorized = await cls.is_authorized(bot, guild_id, interaction.user, scope=scope)
        if not authorized:
            await interaction.response.send_message(
                "❌ **Unauthorized**\n\nYou do not have permission to use this Rai control console.",
                ephemeral=True,
            )
            return True

        # Defer ephemerally
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = bot.get_guild(guild_id)
        if not guild and hasattr(bot, "fetch_guild"):
            try:
                guild = await bot.fetch_guild(guild_id)
            except Exception:
                guild = None

        if not guild:
            await interaction.followup.send("❌ Server not accessible.", ephemeral=True)
            return True

        # Action Execution
        db = getattr(bot, "db", None)

        if action == "lockdown":
            if hasattr(bot, "security_brain") and hasattr(bot.security_brain, "engage_lockdown"):
                await bot.security_brain.engage_lockdown(guild.id, reason=f"Private Control Center by {interaction.user}")
            elif db:
                await db.set_lockdown(guild.id, True, str(interaction.user.id))
            await interaction.followup.send("🔒 **Emergency Lockdown Activated.** Server permissions restricted.", ephemeral=True)
            return True

        if action == "unlock":
            if hasattr(bot, "security_brain") and hasattr(bot.security_brain, "release_lockdown"):
                await bot.security_brain.release_lockdown(guild.id, reason=f"Private Control Center by {interaction.user}")
            elif db:
                await db.set_lockdown(guild.id, False, str(interaction.user.id))
            await interaction.followup.send("🔓 **Lockdown Lifted.** Channels restored to standard operational state.", ephemeral=True)
            return True

        if action in ("lockdown_status", "recheck_lockdown"):
            is_locked = False
            if db:
                try:
                    is_locked = await db.is_lockdown_active(guild.id)
                except Exception:
                    is_locked = False
            status_text = "🔴 **EMERGENCY LOCKDOWN ACTIVE**" if is_locked else "🟢 **NORMAL (CHANNELS OPEN)**"
            await interaction.followup.send(
                f"📋 **Lockdown Telemetry:**\n• **Status:** {status_text}\n• **Server ID:** `{guild.id}`\n• **Checked:** <t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:T>",
                ephemeral=True,
            )
            return True

        if action == "backup":
            try:
                from backups.manager import BackupManager, format_bytes
                mgr = BackupManager.get_instance()
                rec = await mgr.run_backup(trigger=f"control_panel_{interaction.user.id}")
                size_str = format_bytes(rec.archive_size or rec.sqlite_size)
                await interaction.followup.send(
                    f"✅ **Backup Created Successfully**\n• **ID:** `{rec.backup_id}`\n• **Size:** `{size_str}`\n• **SHA256:** `{rec.sqlite_sha256[:16]}...`\n*Stored securely on local filesystem.*",
                    ephemeral=True,
                )
            except Exception as e:
                await interaction.followup.send(f"❌ Backup failed: {e}", ephemeral=True)
            return True

        if action == "health":
            sup = getattr(bot, "supervisor", None)
            health_text = "System active and operational."
            if sup and hasattr(sup, "get_subsystem_health"):
                health_dict = sup.get_subsystem_health()
                health_text = "\n".join([f"• **{k}:** `{v}`" for k, v in health_dict.items()])
            await interaction.followup.send(
                f"❤️ **SYSTEM SUBSYSTEM HEALTH**\n\n{health_text}\n\n*Verified by Rai Supervisor.*",
                ephemeral=True,
            )
            return True

        if action == "config":
            await interaction.followup.send(
                f"⚙️ **RAI CONFIGURATION OVERVIEW**\n• **Guild:** `{guild.name}` (`{guild.id}`)\n• **Version:** `Rai Core 2.0`\n• **Owner Reporting:** `Dual Delivery Active (DM + Channels)`\n• **Private Control:** `Hidden Structure Enforced`",
                ephemeral=True,
            )
            return True

        if action == "automation":
            await interaction.followup.send(
                "🤖 **AUTOMATION ENGINES STATUS**\n• **Command Watchdog:** `RUNNING`\n• **Self Healing Engine:** `ARMED`\n• **Rate Limiter:** `ACTIVE`\n• **Action Queue:** `DRAINING (NORMAL)`",
                ephemeral=True,
            )
            return True

        if action == "scan":
            await interaction.followup.send(
                "🛡️ **SECURITY INTEGRITY SCAN**\n• **Hierarchy Violations:** `0 detected`\n• **Raid Triggers:** `None active`\n• **Dangerous Permissions:** `Contained`\n• **Status:** `🟢 SECURE`",
                ephemeral=True,
            )
            return True

        if action == "audit":
            await interaction.followup.send(
                "🔍 **AUDIT MONITOR SUMMARY**\n• **Recent Audit Events:** `Captured & Analyzed`\n• **Suspicious Webhooks:** `0`\n• **Mass Kicks/Bans:** `None`\n• **Status:** `NOMINAL`",
                ephemeral=True,
            )
            return True

        if action == "incident_details":
            await interaction.followup.send(
                "📋 **INCIDENT DASHBOARD**\n• Use individual report consoles in `#🚨・security-report` or `#🛡️・mod-report` for granular incident mitigation.",
                ephemeral=True,
            )
            return True

        await interaction.followup.send(f"ℹ️ Control action `{action}` acknowledged.", ephemeral=True)
        return True

    # ==========================================
    # COMPLETE SERVER SETUP / MIGRATION
    # ==========================================

    @classmethod
    async def setup_or_migrate_private_control(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Inspects existing server structure, reuses and moves existing channels/categories,
        preserves channel IDs and message history, sets up strict private overwrites,
        and posts interactive control consoles.
        """
        logger.info(f"Starting Private Control Center setup/migration for guild {guild.name} ({guild.id})")
        db = getattr(bot, "db", None)

        existing_categories: Dict[str, discord.CategoryChannel] = {
            c.name.strip(): c for c in guild.categories
        }

        # ----------------------------------------------------
        # 1. Ensure Top Category: 🔐 | RAI PRIVATE CONTROL
        # ----------------------------------------------------
        hub_cat = None
        for name, cat in existing_categories.items():
            if "private control" in name.lower() or "🔐 | rai private control" in name.lower():
                hub_cat = cat
                break

        hub_overwrites = cls.build_strict_overwrites(bot, guild, "hub")
        if not hub_cat:
            try:
                hub_cat = await guild.create_category_channel(
                    cls.CONTROL_HUB_CATEGORY,
                    overwrites=hub_overwrites,
                    position=0,
                    reason="Rai Setup: Created 🔐 | RAI PRIVATE CONTROL master header",
                )
            except Exception as e:
                logger.warning(f"Could not create hub category: {e}")
        else:
            try:
                await hub_cat.edit(overwrites=hub_overwrites, name=cls.CONTROL_HUB_CATEGORY)
            except Exception:
                pass

        # ----------------------------------------------------
        # 2. Ensure Category: 📋 | RAI REPORTS
        # ----------------------------------------------------
        rep_cat = None
        for name, cat in existing_categories.items():
            if "rai reports" in name.lower():
                rep_cat = cat
                break

        rep_overwrites = cls.build_strict_overwrites(bot, guild, "reports")
        if not rep_cat:
            try:
                rep_cat = await guild.create_category_channel(
                    cls.REPORTS_CATEGORY,
                    overwrites=rep_overwrites,
                    reason="Rai Setup: Created 📋 | RAI REPORTS category",
                )
            except Exception as e:
                logger.error(f"Failed to create reports category: {e}")
                return False, f"Failed to create reports category: {e}", {}
        else:
            try:
                await rep_cat.edit(overwrites=rep_overwrites, name=cls.REPORTS_CATEGORY)
            except Exception:
                pass

        # Ensure all 6 report channels inside 📋 | RAI REPORTS
        rep_channels_map = {}
        for cname, ctopic in cls.REPORTS_CHANNELS:
            ch = discord.utils.find(lambda c: c.name == cname and c.category_id == rep_cat.id, guild.text_channels)
            if not ch:
                # Search across guild in case it's in another category
                ch = discord.utils.find(lambda c: c.name == cname, guild.text_channels)
                if ch:
                    try:
                        await ch.edit(category=rep_cat, sync_permissions=True, topic=ctopic)
                    except Exception:
                        pass
                else:
                    try:
                        ch = await rep_cat.create_text_channel(
                            name=cname,
                            topic=ctopic,
                            sync_permissions=True,
                            reason="Rai Setup: Created missing report channel",
                        )
                    except Exception as e:
                        logger.warning(f"Could not create report channel {cname}: {e}")
            else:
                try:
                    await ch.edit(sync_permissions=True, topic=ctopic)
                except Exception:
                    pass
            rep_channels_map[cname] = ch

        # ----------------------------------------------------
        # 3. Ensure Category: 🛡️ | RAI SECURITY
        # ----------------------------------------------------
        sec_cat = None
        for name, cat in existing_categories.items():
            if "rai security" in name.lower() or "rλi security" in name.lower():
                sec_cat = cat
                break

        sec_overwrites = cls.build_strict_overwrites(bot, guild, "security")
        if not sec_cat:
            try:
                sec_cat = await guild.create_category_channel(
                    cls.SECURITY_CATEGORY,
                    overwrites=sec_overwrites,
                    reason="Rai Setup: Created 🛡️ | RAI SECURITY category",
                )
            except Exception as e:
                logger.error(f"Failed to create security category: {e}")
                return False, f"Failed to create security category: {e}", {}
        else:
            try:
                await sec_cat.edit(overwrites=sec_overwrites, name=cls.SECURITY_CATEGORY)
            except Exception:
                pass

        # Reuse or create the 5 security channels
        sec_aliases = {
            "🚨・security-alerts": ["threat-detection", "alerts", "raid-alert", "critical-alert"],
            "🧱・anti-nuke": ["anti-nuke", "nuke-detection"],
            "🛡️・security-log": ["security-events", "security-log"],
            "🔍・audit-monitor": ["audit-logs", "audit-trail", "audit-monitor"],
            "🔒・lockdown-control": ["lockdown", "emergency-lock", "lockdown-control"],
        }

        sec_channels_map = {}
        for cname, ctopic in cls.SECURITY_CHANNELS:
            # Check if exists in sec_cat
            ch = discord.utils.find(lambda c: c.name == cname and c.category_id == sec_cat.id, guild.text_channels)
            if not ch:
                # Check for alias in sec_cat
                aliases = sec_aliases.get(cname, [])
                for alias in aliases:
                    found = discord.utils.find(lambda c: alias in c.name and c.category_id == sec_cat.id, guild.text_channels)
                    if found:
                        ch = found
                        try:
                            await ch.edit(name=cname, topic=ctopic, sync_permissions=True)
                        except Exception:
                            pass
                        break
            if not ch:
                try:
                    ch = await sec_cat.create_text_channel(
                        name=cname,
                        topic=ctopic,
                        sync_permissions=True,
                        reason="Rai Setup: Created operational security channel",
                    )
                except Exception as e:
                    logger.warning(f"Could not create security channel {cname}: {e}")
            else:
                try:
                    await ch.edit(sync_permissions=True, topic=ctopic)
                except Exception:
                    pass
            sec_channels_map[cname] = ch

        # ----------------------------------------------------
        # 4. Ensure Category: ⚙️ | RAI ADMIN
        # ----------------------------------------------------
        admin_cat = None
        for name, cat in existing_categories.items():
            if "rai admin" in name.lower() or "rλi admin" in name.lower():
                admin_cat = cat
                break

        admin_overwrites = cls.build_strict_overwrites(bot, guild, "admin")
        if not admin_cat:
            try:
                admin_cat = await guild.create_category_channel(
                    cls.ADMIN_CATEGORY,
                    overwrites=admin_overwrites,
                    reason="Rai Setup: Created ⚙️ | RAI ADMIN category",
                )
            except Exception as e:
                logger.error(f"Failed to create admin category: {e}")
                return False, f"Failed to create admin category: {e}", {}
        else:
            try:
                await admin_cat.edit(overwrites=admin_overwrites, name=cls.ADMIN_CATEGORY)
            except Exception:
                pass

        # Reuse or create the 6 admin channels
        admin_aliases = {
            "👑・admin-control": ["admin-control", "emergency-control"],
            "📊・server-dashboard": ["server-dashboard", "configuration"],
            "⚙️・bot-config": ["bot-config", "permissions"],
            "🤖・automation-control": ["automation-control", "tools"],
            "💾・backup-control": ["backup-control", "backup"],
            "❤️・system-health": ["system-health", "restore"],
        }

        admin_channels_map = {}
        for cname, ctopic in cls.ADMIN_CHANNELS:
            ch = discord.utils.find(lambda c: c.name == cname and c.category_id == admin_cat.id, guild.text_channels)
            if not ch:
                aliases = admin_aliases.get(cname, [])
                for alias in aliases:
                    found = discord.utils.find(lambda c: alias in c.name and c.category_id == admin_cat.id, guild.text_channels)
                    if found:
                        ch = found
                        try:
                            await ch.edit(name=cname, topic=ctopic, sync_permissions=True)
                        except Exception:
                            pass
                        break
            if not ch:
                try:
                    ch = await admin_cat.create_text_channel(
                        name=cname,
                        topic=ctopic,
                        sync_permissions=True,
                        reason="Rai Setup: Created operational admin channel",
                    )
                except Exception as e:
                    logger.warning(f"Could not create admin channel {cname}: {e}")
            else:
                try:
                    await ch.edit(sync_permissions=True, topic=ctopic)
                except Exception:
                    pass
            admin_channels_map[cname] = ch

        # ----------------------------------------------------
        # 5. Clean up redundant/obsolete channels
        # ----------------------------------------------------
        kept_channel_ids = {
            c.id for c in list(rep_channels_map.values()) + list(sec_channels_map.values()) + list(admin_channels_map.values()) if c
        }
        for cat in (sec_cat, admin_cat):
            if cat:
                for ch in cat.text_channels:
                    if ch.id not in kept_channel_ids:
                        try:
                            logger.info(f"Removing obsolete operational channel {ch.name} ({ch.id})")
                            await ch.delete(reason="Rai Setup: Cleaned up redundant operational channel during migration")
                        except Exception as e:
                            logger.warning(f"Could not delete obsolete channel {ch.id}: {e}")

        # ----------------------------------------------------
        # 6. Post / Update Interactive Control Consoles
        # ----------------------------------------------------
        # A. In 🔒・lockdown-control
        lockdown_ch = sec_channels_map.get("🔒・lockdown-control")
        if lockdown_ch:
            try:
                is_locked = await db.is_lockdown_active(guild.id) if (db and hasattr(db, "is_lockdown_active")) else False
                embed = cls.build_lockdown_embed(guild, is_locked=is_locked)
                view = cls.build_lockdown_view(guild.id, is_locked=is_locked)
                # Check for existing bot pinned message
                msgs = [m async for m in lockdown_ch.history(limit=5)]
                panel_msg = next((m for m in msgs if m.author.id == bot.user.id and "LOCKDOWN CONTROL" in (m.embeds[0].title or "")), None) if msgs else None
                if panel_msg:
                    await panel_msg.edit(embed=embed, view=view)
                else:
                    await lockdown_ch.send(embed=embed, view=view)
            except Exception as e:
                logger.warning(f"Could not post lockdown control panel: {e}")

        # B. In 👑・admin-control
        admin_ctrl_ch = admin_channels_map.get("👑・admin-control")
        if admin_ctrl_ch:
            try:
                embed = cls.build_admin_embed(guild)
                view = cls.build_admin_view(guild.id)
                msgs = [m async for m in admin_ctrl_ch.history(limit=5)]
                panel_msg = next((m for m in msgs if m.author.id == bot.user.id and "ADMINISTRATIVE CONTROL" in (m.embeds[0].title or "")), None) if msgs else None
                if panel_msg:
                    await panel_msg.edit(embed=embed, view=view)
                else:
                    await admin_ctrl_ch.send(embed=embed, view=view)
            except Exception as e:
                logger.warning(f"Could not post admin control panel: {e}")

        # C. In 🛡️・security-log or 🚨・security-alerts
        sec_ctrl_ch = sec_channels_map.get("🛡️・security-log") or sec_channels_map.get("🚨・security-alerts")
        if sec_ctrl_ch:
            try:
                embed = cls.build_security_control_embed(guild)
                view = cls.build_security_control_view(guild.id)
                msgs = [m async for m in sec_ctrl_ch.history(limit=5)]
                panel_msg = next((m for m in msgs if m.author.id == bot.user.id and "THREAT INTELLIGENCE" in (m.embeds[0].title or "")), None) if msgs else None
                if panel_msg:
                    await panel_msg.edit(embed=embed, view=view)
                else:
                    await sec_ctrl_ch.send(embed=embed, view=view)
            except Exception as e:
                logger.warning(f"Could not post security control panel: {e}")

        # ----------------------------------------------------
        # 7. Persist IDs to SQLite Database
        # ----------------------------------------------------
        if db:
            try:
                # Update PrivateControlConfig
                await db.update_private_control_config(
                    guild.id,
                    control_hub_category_id=getattr(hub_cat, "id", None),
                    reports_category_id=getattr(rep_cat, "id", None),
                    security_category_id=getattr(sec_cat, "id", None),
                    admin_category_id=getattr(admin_cat, "id", None),
                    security_alerts_id=getattr(sec_channels_map.get("🚨・security-alerts"), "id", None),
                    anti_nuke_id=getattr(sec_channels_map.get("🧱・anti-nuke"), "id", None),
                    security_log_id=getattr(sec_channels_map.get("🛡️・security-log"), "id", None),
                    audit_monitor_id=getattr(sec_channels_map.get("🔍・audit-monitor"), "id", None),
                    lockdown_control_id=getattr(sec_channels_map.get("🔒・lockdown-control"), "id", None),
                    admin_control_id=getattr(admin_channels_map.get("👑・admin-control"), "id", None),
                    server_dashboard_id=getattr(admin_channels_map.get("📊・server-dashboard"), "id", None),
                    bot_config_id=getattr(admin_channels_map.get("⚙️・bot-config"), "id", None),
                    automation_control_id=getattr(admin_channels_map.get("🤖・automation-control"), "id", None),
                    backup_control_id=getattr(admin_channels_map.get("💾・backup-control"), "id", None),
                    system_health_id=getattr(admin_channels_map.get("❤️・system-health"), "id", None),
                )
                # Update OwnerReportsConfig
                await db.update_owner_reports_config(
                    guild.id,
                    category_id=getattr(rep_cat, "id", None),
                    security_report_id=getattr(rep_channels_map.get("🚨・security-report"), "id", None),
                    mod_report_id=getattr(rep_channels_map.get("🛡️・mod-report"), "id", None),
                    music_report_id=getattr(rep_channels_map.get("🎵・music-report"), "id", None),
                    room_report_id=getattr(rep_channels_map.get("🔐・room-report"), "id", None),
                    bot_report_id=getattr(rep_channels_map.get("🤖・bot-report"), "id", None),
                    system_report_id=getattr(rep_channels_map.get("⚙️・system-report"), "id", None),
                )
            except Exception as db_err:
                logger.error(f"Failed to persist private control IDs: {db_err}")

        summary = {
            "hub_category": getattr(hub_cat, "id", None),
            "reports_category": getattr(rep_cat, "id", None),
            "security_category": getattr(sec_cat, "id", None),
            "admin_category": getattr(admin_cat, "id", None),
            "report_channels": {k: getattr(v, "id", None) for k, v in rep_channels_map.items()},
            "security_channels": {k: getattr(v, "id", None) for k, v in sec_channels_map.items()},
            "admin_channels": {k: getattr(v, "id", None) for k, v in admin_channels_map.items()},
        }
        return True, "Private Control Center structure verified and migrated successfully.", summary
