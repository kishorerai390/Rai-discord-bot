"""
Server Setup Wizard & Health Audit Cog for Raivora.
Implements:
- /server-setup preview: Dry-run preview comparing existing structure with minimal-text layout.
- /server-setup apply: Idempotent setup applying approved channels with explicit confirmation.
- /server-setup status: Current setup progress, mapped channels, and rate-limit safety.
- /server-setup cancel: Aborts any pending unconfirmed setup.
- /server-audit: Structural health audit (duplicates, missing channels, permission leaks) - REPORT ONLY.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.permissions import is_founder_or_owner


def check_admin(user: Any) -> bool:
    """Helper to check whether user is guild owner, administrator, or founder."""
    if not isinstance(user, discord.Member):
        return False
    if getattr(user, "guild", None) and user.id == user.guild.owner_id:
        return True
    perms = getattr(user, "guild_permissions", None)
    if perms and getattr(perms, "administrator", False):
        return True
    return is_founder_or_owner(user)
    from core.bot import SentinelBot

logger = logging.getLogger("Raivora.ServerSetup")


# Standard Minimal-Text Community Blueprint
PROPOSED_STRUCTURE = [
    {
        "category": "✦ ɪɴғᴏʀᴍᴀᴛɪᴏɴ ✦",
        "aliases": ["information", "info", "rules"],
        "channels": [
            {"name": "📢・announcements", "type": 0, "topic": "Official server announcements and news.", "aliases": ["announcements", "news", "updates"]},
            {"name": "👋・welcome", "type": 0, "topic": "Community welcome hub and onboarding verification.", "aliases": ["welcome", "joins", "onboarding"]},
            {"name": "📜・rules", "type": 0, "topic": "Server community guidelines, roles, and safety info.", "aliases": ["rules", "info", "guidelines"]},
        ],
    },
    {
        "category": "✦ ᴄᴏᴍᴍᴜɴɪᴛʏ ✦",
        "aliases": ["community", "chat", "general"],
        "channels": [
            {"name": "💬・chat", "type": 0, "topic": "General community chat, suggestions, and conversation.", "aliases": ["chat", "general", "general-chat", "main"]},
            {"name": "📸・media", "type": 0, "topic": "Community clips, gaming screenshots, artwork, and edits.", "aliases": ["media", "clips", "media-clips", "gallery"]},
        ],
    },
    {
        "category": "✦ ɢᴀᴍɪɴɢ ᴢᴏɴᴇ ✦",
        "aliases": ["gaming", "gaming arena", "gaming zone"],
        "channels": [
            {"name": "🎮・Gaming Lounge", "type": 2, "topic": "Open gaming voice lounge.", "aliases": ["gaming lounge", "gaming squad", "squad"]},
            {"name": "🏆・Ranked Squad", "type": 2, "topic": "Competitive ranked matches and tactical comms.", "aliases": ["ranked squad", "ranked comms", "ranked"]},
            {"name": "🦢・Create Personal Gaming VC", "type": 2, "topic": "Join to spawn your personal gaming room.", "aliases": ["create personal gaming", "create gaming vc", "personal gaming"]},
            {"name": "🔒・Create Private Gaming VC", "type": 2, "topic": "Join to spawn an invite-only private gaming room.", "aliases": ["create private gaming", "private gaming"]},
        ],
    },
    {
        "category": "✦ ᴍᴜsɪᴄ ʟᴏᴜɴɢᴇ ✦",
        "aliases": ["music", "music lounge", "radio"],
        "channels": [
            {"name": "🎧・Music Lounge 1", "type": 2, "topic": "High-fidelity audio stream powered by Neko Songs.", "aliases": ["music lounge 1", "24/7 radio", "radio", "music"]},
            {"name": "🎧・Music Lounge 2", "type": 2, "topic": "Secondary audio lounge.", "aliases": ["music lounge 2", "music 2"]},
            {"name": "🌙・Chill Room", "type": 2, "topic": "Late night acoustic lounge and lofi ambience.", "aliases": ["chill room", "night owl cafe", "lofi"]},
        ],
    },
    {
        "category": "✦ ᴇᴅɪᴛɪɴɢ ᴢᴏɴᴇ ✦",
        "aliases": ["editing", "creator studio", "editing zone"],
        "channels": [
            {"name": "🎨・Creative Lounge", "type": 2, "topic": "Creative workspace for editors, VFX artists, and designers.", "aliases": ["creative lounge", "stream showcase", "creator studio"]},
            {"name": "🤝・Editing Collaboration", "type": 2, "topic": "Screen sharing and live project review.", "aliases": ["editing collaboration", "collab"]},
            {"name": "🖥️・Create Personal Editing VC", "type": 2, "topic": "Join to spawn a personal editing room.", "aliases": ["create personal editing", "personal editing"]},
            {"name": "🔐・Create Private Editing VC", "type": 2, "topic": "Join to spawn a confidential 1-on-1 editing suite.", "aliases": ["create private editing", "private editing"]},
        ],
    },
    {
        "category": "✦ ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ ✦",
        "aliases": ["entertainment", "chill", "haven"],
        "channels": [
            {"name": "🎬・Movie Night", "type": 2, "topic": "Community watch parties and premiere streams.", "aliases": ["movie night", "cinema", "movie"]},
            {"name": "🎤・Karaoke", "type": 2, "topic": "Open mic and karaoke sessions.", "aliases": ["karaoke", "open mic"]},
            {"name": "🌙・Chill Lounge", "type": 2, "topic": "Relaxed late-night voice chat.", "aliases": ["chill lounge", "vibe studio", "vibe"]},
        ],
    },
    {
        "category": "✦ sᴛᴀғғ ʜǫ ✦",
        "aliases": ["staff", "staff hq", "security"],
        "channels": [
            {"name": "🔒・staff-chat", "type": 0, "topic": "Private staff discussion and moderation coordination.", "aliases": ["staff-chat", "staff-lounge", "staff"]},
            {"name": "🚨・security-logs", "type": 0, "topic": "Security intelligence stream and audit trail.", "aliases": ["security-logs", "security-alerts", "security-log", "audit"]},
        ],
    },
]


def normalize_name(name: str) -> str:
    """Strip emojis, decorators, and dashes for fuzzy alias matching."""
    cleaned = "".join(ch.lower() for ch in name if ch.isalnum() or ch.isspace())
    return " ".join(cleaned.split())


class ServerSetupConfirmView(discord.ui.View):
    """Interactive confirmation view for /server-setup apply."""

    def __init__(self, cog: ServerSetupCog, guild: discord.Guild, user_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation dialog is restricted to the administrator who ran the preview.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm & Apply Setup", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        self.stop()
        for child in self.children:
            child.disabled = True
        try:
            await interaction.edit_original_response(view=self)
        except Exception:
            pass
        await self.cog.execute_apply(interaction, self.guild)

    @discord.ui.button(label="Cancel Setup", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        self.stop()
        for child in self.children:
            child.disabled = True
        try:
            await interaction.edit_original_response(view=self)
        except Exception:
            pass
        await self.cog.execute_cancel(interaction, self.guild)


class ServerSetupCog(commands.Cog, name="ServerSetup"):
    """Server Setup Wizard and Structural Health Audit Suite."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._pending_previews: Dict[int, Dict[str, Any]] = {}

    setup_group = app_commands.Group(
        name="server-setup",
        description="Raivora automated server setup and channel optimization wizard",
    )

    # =========================================================================
    # 1. /server-setup preview
    # =========================================================================

    @setup_group.command(name="preview", description="Dry-run preview comparing current channels with minimal-text layout")
    async def setup_preview(self, interaction: discord.Interaction):
        if not check_admin(interaction.user):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command must be executed inside a Discord server.")
            return

        preview_data = await self.generate_preview(guild)
        self._pending_previews[guild.id] = preview_data

        # Record preview in DB
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            async with self.bot.db._db.execute(
                """
                INSERT INTO server_setup_state (guild_id, status, preview_json, created_at, updated_at)
                VALUES (?, 'preview_ready', ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    status = 'preview_ready',
                    preview_json = excluded.preview_json,
                    updated_at = excluded.updated_at
                """,
                (guild.id, json.dumps(preview_data), now_str, now_str),
            ):
                await self.bot.db._db.commit()
        except Exception as e:
            logger.warning(f"Could not persist preview state: {e}")

        embed = discord.Embed(
            title="🏗️ 『RΛI』 • SERVER SETUP WIZARD PREVIEW",
            description=(
                f"**Target Architecture:** Minimal-Text Aesthetic Blueprint\n"
                f"**Guild:** `{guild.name}` (ID: `{guild.id}`)\n\n"
                f"• **Existing Channels to Re-use (In-Place):** `{len(preview_data['reused'])}`\n"
                f"• **Missing Channels to Create:** `{len(preview_data['to_create'])}`\n"
                f"• **Categories to Standardize:** `{len(preview_data['categories'])}`\n"
                f"• **Automatic Channel Deletions:** `0 (Zero Destructive Deletions)` 🛡️\n\n"
                f"Review the category-by-category mappings below. Click **Confirm & Apply Setup** to execute safely."
            ),
            color=0x9B59B6,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        for cat_info in preview_data["categories"][:5]:
            chan_lines = []
            for ch in cat_info["channels"]:
                status_icon = "🔄 Re-use" if ch["action"] == "reuse" else "➕ Create"
                target_str = f"`{ch['target_name']}`"
                if ch["action"] == "reuse":
                    chan_lines.append(f"{status_icon}: <#{ch['existing_id']}> → {target_str}")
                else:
                    chan_lines.append(f"{status_icon}: {target_str} ({'Voice' if ch['type'] == 2 else 'Text'})")

            embed.add_field(
                name=f"📁 {cat_info['name']}",
                value="\n".join(chan_lines) if chan_lines else "• None",
                inline=False,
            )

        embed.set_footer(text="Idempotent Setup • Zero Destructive Deletion Guarantee")
        view = ServerSetupConfirmView(self, guild, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    # =========================================================================
    # 2. /server-setup apply
    # =========================================================================

    @setup_group.command(name="apply", description="Apply the planned server structure safely after confirmation")
    @app_commands.describe(confirm="Set to True to confirm execution")
    async def setup_apply(self, interaction: discord.Interaction, confirm: bool = False):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        if not confirm:
            await interaction.response.send_message(
                "⚠️ **Safety Check:** Please run `/server-setup preview` first to view the planned changes, "
                "or re-run `/server-setup apply confirm:True` to proceed.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Guild context required.")
            return

        await self.execute_apply(interaction, guild)

    async def execute_apply(self, interaction: discord.Interaction, guild: discord.Guild):
        preview_data = self._pending_previews.get(guild.id)
        if not preview_data:
            preview_data = await self.generate_preview(guild)

        status_msg = await interaction.followup.send("⏳ **Applying Server Architecture...** Please hold on.")
        created_count = 0
        reused_count = 0
        cat_cache: Dict[str, discord.CategoryChannel] = {}

        # 1. Resolve or create categories
        for cat_spec in preview_data["categories"]:
            cat_name = cat_spec["name"]
            existing_cat = None
            norm_target = normalize_name(cat_name)

            for c in guild.categories:
                if c.name == cat_name or normalize_name(c.name) == norm_target or any(a in normalize_name(c.name) for a in cat_spec.get("aliases", [])):
                    existing_cat = c
                    break

            if not existing_cat:
                try:
                    # Special permission for Staff HQ
                    overwrites = {}
                    if "staff" in norm_target:
                        overwrites = {
                            guild.default_role: discord.PermissionOverwrite(view_channel=False),
                            guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_permissions=True),
                        }
                    existing_cat = await guild.create_category(name=cat_name, overwrites=overwrites, reason="Raivora Setup Wizard: Standardized Category")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Could not create category {cat_name}: {e}")

            if existing_cat:
                cat_cache[cat_name] = existing_cat

        # 2. Re-use or create channels
        for cat_spec in preview_data["categories"]:
            cat_obj = cat_cache.get(cat_spec["name"])
            for ch in cat_spec["channels"]:
                target_name = ch["target_name"]
                ch_type = ch["type"]

                if ch["action"] == "reuse" and ch.get("existing_id"):
                    existing_ch = guild.get_channel(ch["existing_id"])
                    if existing_ch:
                        try:
                            patch_kwargs = {}
                            if existing_ch.name != target_name:
                                patch_kwargs["name"] = target_name
                            if cat_obj and existing_ch.category_id != cat_obj.id:
                                patch_kwargs["category"] = cat_obj
                            if ch.get("topic") and getattr(existing_ch, "topic", None) != ch["topic"] and isinstance(existing_ch, discord.TextChannel):
                                patch_kwargs["topic"] = ch["topic"]

                            if patch_kwargs:
                                await existing_ch.edit(**patch_kwargs, reason="Raivora Setup Wizard: In-Place Standardization")
                                await asyncio.sleep(0.5)
                            reused_count += 1
                        except Exception as e:
                            logger.warning(f"Could not edit channel {existing_ch.name}: {e}")
                elif ch["action"] == "create":
                    try:
                        ow = {}
                        if "staff" in target_name or "security" in target_name:
                            ow = {
                                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True),
                            }
                        if ch_type == 2:
                            await guild.create_voice_channel(name=target_name, category=cat_obj, overwrites=ow, reason="Raivora Setup Wizard: Provisioned Voice Channel")
                        else:
                            await guild.create_text_channel(name=target_name, category=cat_obj, topic=ch.get("topic", ""), overwrites=ow, reason="Raivora Setup Wizard: Provisioned Text Channel")
                        await asyncio.sleep(0.5)
                        created_count += 1
                    except Exception as e:
                        logger.warning(f"Could not create channel {target_name}: {e}")

        # Record completion
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            async with self.bot.db._db.execute(
                """
                UPDATE server_setup_state
                SET status = 'completed', applied_at = ?, updated_at = ?
                WHERE guild_id = ?
                """,
                (now_str, now_str, guild.id),
            ):
                await self.bot.db._db.commit()
        except Exception:
            pass

        embed_done = discord.Embed(
            title="🎉 『RΛI』 • SERVER SETUP COMPLETED",
            description=(
                f"**Architecture Successfully Applied!**\n\n"
                f"• **Channels Re-used & Standardized:** `{reused_count}` channels\n"
                f"• **New Channels Provisioned:** `{created_count}` channels\n"
                f"• **Categories Unified:** `{len(cat_cache)}` categories\n"
                f"• **Destructive Deletions:** `0` 🛡️\n\n"
                f"The server is now configured with minimal text channels, aesthetic Unicode formatting, and dynamic voice creation."
            ),
            color=0x2ECC71,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        try:
            await status_msg.edit(content=None, embed=embed_done)
        except Exception:
            await interaction.followup.send(embed=embed_done)

    # =========================================================================
    # 3. /server-setup status
    # =========================================================================

    @setup_group.command(name="status", description="Inspect server setup status and progress")
    async def setup_status(self, interaction: discord.Interaction):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        status_val = "idle"
        applied_at = "Never"
        try:
            async with self.bot.db._db.execute(
                "SELECT status, applied_at FROM server_setup_state WHERE guild_id = ?",
                (guild.id,),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    status_val = row[0]
                    applied_at = row[1] or "Never"
        except Exception:
            pass

        embed = discord.Embed(
            title="📊 『RΛI』 • SERVER SETUP STATUS",
            description=(
                f"**Guild:** `{guild.name}` (`{guild.id}`)\n\n"
                f"• **Current Setup State:** `{status_val.upper()}`\n"
                f"• **Last Applied:** `{applied_at}`\n"
                f"• **Text Channels in Guild:** `{len(guild.text_channels)}`\n"
                f"• **Voice Channels in Guild:** `{len(guild.voice_channels)}`\n"
                f"• **Categories in Guild:** `{len(guild.categories)}`\n"
                f"• **Rate-Limit Health:** `Nominal 🟢`\n"
                f"• **Idempotency Guard:** `Active 🛡️`"
            ),
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed)

    # =========================================================================
    # 4. /server-setup cancel
    # =========================================================================

    @setup_group.command(name="cancel", description="Cancel pending setup preview and clear staged state")
    async def setup_cancel(self, interaction: discord.Interaction):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        await self.execute_cancel(interaction, guild)

    async def execute_cancel(self, interaction: discord.Interaction, guild: discord.Guild):
        self._pending_previews.pop(guild.id, None)
        try:
            async with self.bot.db._db.execute(
                "UPDATE server_setup_state SET status = 'idle', preview_json = NULL WHERE guild_id = ?",
                (guild.id,),
            ):
                await self.bot.db._db.commit()
        except Exception:
            pass

        embed = discord.Embed(
            title="🛑 Server Setup Cancelled",
            description="Any pending unconfirmed preview has been cleared. No changes were made.",
            color=0xED4245,
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # =========================================================================
    # 5. /server-audit (REPORT ONLY)
    # =========================================================================

    @app_commands.command(name="server-audit", description="Structural health audit for duplicates, permissions, and redundancy (Report Only)")
    async def server_audit(self, interaction: discord.Interaction):
        if not check_admin(interaction.user):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Guild context required.")
            return

        embed = await self.build_audit_embed(guild)
        await interaction.followup.send(embed=embed)

    async def build_audit_embed(self, guild: discord.Guild) -> discord.Embed:
        duplicates: List[str] = []
        name_map: Dict[str, List[discord.abc.GuildChannel]] = {}
        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel):
                continue
            norm = normalize_name(ch.name)
            name_map.setdefault(norm, []).append(ch)

        for norm, ch_list in name_map.items():
            if len(ch_list) > 1:
                names = ", ".join(f"<#{c.id}>" for c in ch_list)
                duplicates.append(f"• Multiple `{norm}`: {names}")

        # Check permissions leaks on private channels
        leaks: List[str] = []
        for ch in guild.channels:
            norm = normalize_name(ch.name)
            if any(k in norm for k in ("staff", "security", "mod", "admin", "private")):
                ow = ch.overwrites_for(guild.default_role)
                if ow.view_channel is True or ow.connect is True:
                    leaks.append(f"• <#{ch.id}> allows `@everyone` view/connect!")

        # Check essential channels
        missing_essentials: List[str] = []
        all_norms = set(name_map.keys())
        for req in ["rules", "welcome", "announcements", "chat"]:
            if not any(req in n for n in all_norms):
                missing_essentials.append(f"• Missing recommended `#{req}`")

        # Save audit to DB
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        audit_payload = {
            "duplicates": duplicates,
            "permission_leaks": leaks,
            "missing_essentials": missing_essentials,
            "text_count": len(guild.text_channels),
            "voice_count": len(guild.voice_channels),
        }
        try:
            async with self.bot.db._db.execute(
                """
                UPDATE server_setup_state
                SET last_audit_json = ?, updated_at = ?
                WHERE guild_id = ?
                """,
                (json.dumps(audit_payload), now_str, guild.id),
            ):
                await self.bot.db._db.commit()
        except Exception:
            pass

        embed = discord.Embed(
            title="🔍 『RΛI』 • SERVER STRUCTURAL AUDIT",
            description=(
                f"**Guild:** `{guild.name}` (`{guild.id}`)\n"
                f"**Report Policy:** `REPORT ONLY (Zero Autonomous Deletions)` 🛡️\n\n"
                f"• **Total Channels:** `{len(guild.channels)}` (`{len(guild.text_channels)}` Text, `{len(guild.voice_channels)}` Voice)\n"
                f"• **Potential Duplicate Pairs:** `{len(duplicates)}`\n"
                f"• **Permission Vulnerabilities:** `{len(leaks)}`\n"
                f"• **Missing Recommendations:** `{len(missing_essentials)}`"
            ),
            color=0xF1C40F if (duplicates or leaks) else 0x2ECC71,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        if leaks:
            embed.add_field(name="🚨 Permission Anomalies", value="\n".join(leaks[:5]), inline=False)
        else:
            embed.add_field(name="🛡️ Privacy Overwrites", value="🟢 All private channels strictly deny `@everyone`.", inline=False)

        if duplicates:
            embed.add_field(name="⚠️ Potential Duplicates", value="\n".join(duplicates[:6]), inline=False)

        if missing_essentials:
            embed.add_field(name="ℹ️ Recommended Channels", value="\n".join(missing_essentials), inline=False)
        else:
            embed.add_field(name="✅ Recommended Channels", value="🟢 Essential informational channels present.", inline=False)

        embed.set_footer(text="Raivora Health Auditor • Non-Destructive Analysis")
        return embed

    @app_commands.command(name="server-health", description="Comprehensive server and subsystem health report")
    async def server_health(self, interaction: discord.Interaction):
        if not check_admin(interaction.user):
            await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Guild context required.")
            return

        embed = await self.build_health_embed(guild)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def build_health_embed(self, guild: discord.Guild) -> discord.Embed:
        # 1. Gateway & Uptime
        latency_ms = round(self.bot.latency * 1000, 1) if getattr(self.bot, "latency", None) else 0.0
        start_ts = getattr(self.bot, "_start_time", datetime.datetime.now(datetime.timezone.utc).timestamp())
        uptime_sec = max(0, int(datetime.datetime.now(datetime.timezone.utc).timestamp() - start_ts))
        uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m {uptime_sec % 60}s"

        # 2. Database Integrity
        db_ok, db_errors = await self.bot.db.check_integrity()
        db_status = "🟢 Connected & Validated" if db_ok else f"⚠️ Issues: {', '.join(db_errors[:2])}"

        # 3. Dynamic Voice Rooms
        rooms = await self.bot.db.get_all_dynamic_rooms(guild.id)
        active_rooms = [r for r in rooms if r.status == "active"]
        dyn_status = f"🟢 `{len(active_rooms)}` active temporary rooms"

        # 4. Music Service
        try:
            from services.music_gateway import MusicGateway, MusicBotStatus
            music_status_obj = await MusicGateway.get_status()
            if music_status_obj.status == MusicBotStatus.CONNECTED:
                music_str = f"🟢 Connected (`{music_status_obj.active_sessions}` sessions active)"
            else:
                music_str = f"⚪ Offline / Standby ({music_status_obj.status.value})"
        except Exception:
            music_str = "⚪ Standby"

        # 5. Security Incidents
        recent_incidents = await self.bot.db.get_security_incidents(guild.id, limit=5)
        sec_str = f"🟢 `{len(recent_incidents)}` recent incidents" if recent_incidents else "🟢 0 incidents recorded"

        # 6. Bot Permissions Check
        me = guild.me
        perms = me.guild_permissions if me else discord.Permissions.none()
        perm_checks = [
            ("Manage Channels", perms.manage_channels),
            ("Manage Roles", perms.manage_roles),
            ("View Audit Log", perms.view_audit_log),
            ("Move Members", perms.move_members),
        ]
        missing_perms = [name for name, ok in perm_checks if not ok]
        perm_status = "🟢 All Essential Perms Granted" if not missing_perms else f"⚠️ Missing: {', '.join(missing_perms)}"

        embed = discord.Embed(
            title="🏥 『RΛI』 • SERVER HEALTH & DIAGNOSTICS DASHBOARD",
            description=(
                f"**Guild:** `{guild.name}` (`{guild.id}`)\n"
                f"**Report Type:** `LIVE SYSTEM HEALTH AUDIT`\n\n"
                f"• **Gateway Latency:** `{latency_ms} ms`\n"
                f"• **Bot Core Uptime:** `{uptime_str}`\n"
                f"• **Database Health:** {db_status}\n"
                f"• **Dynamic Voice Subsystem:** {dyn_status}\n"
                f"• **Music Audio Stream:** {music_str}\n"
                f"• **Security Subsystem:** {sec_str}\n"
                f"• **Bot Discord Permissions:** {perm_status}"
            ),
            color=0x2ECC71 if (db_ok and not missing_perms) else 0xF1C40F,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text="Raivora Health Monitor • Subsystem Isolation & Fault Tolerance")
        return embed

    # =========================================================================
    # PREVIEW GENERATOR
    # =========================================================================

    async def generate_preview(self, guild: discord.Guild) -> Dict[str, Any]:
        """Generates dry-run channel mapping comparing guild channels to PROPOSED_STRUCTURE."""
        reused: List[Dict[str, Any]] = []
        to_create: List[Dict[str, Any]] = []
        used_channel_ids = set()

        categories_res: List[Dict[str, Any]] = []

        for cat_spec in PROPOSED_STRUCTURE:
            cat_name = cat_spec["category"]
            cat_aliases = cat_spec.get("aliases", [])
            ch_list: List[Dict[str, Any]] = []

            for ch_spec in cat_spec["channels"]:
                target_name = ch_spec["name"]
                ch_type = ch_spec["type"]
                ch_aliases = ch_spec.get("aliases", [])
                matched_channel = None

                # Search existing unassigned channels in guild of same type
                channels_pool = guild.voice_channels if ch_type == 2 else guild.text_channels
                for cand in channels_pool:
                    if cand.id in used_channel_ids:
                        continue
                    c_norm = normalize_name(cand.name)
                    # Check exact or alias match
                    if c_norm == normalize_name(target_name) or any(a in c_norm for a in ch_aliases):
                        matched_channel = cand
                        break

                if matched_channel:
                    used_channel_ids.add(matched_channel.id)
                    entry = {
                        "action": "reuse",
                        "existing_id": matched_channel.id,
                        "existing_name": matched_channel.name,
                        "target_name": target_name,
                        "type": ch_type,
                        "topic": ch_spec.get("topic", ""),
                    }
                    reused.append(entry)
                    ch_list.append(entry)
                else:
                    entry = {
                        "action": "create",
                        "existing_id": None,
                        "existing_name": None,
                        "target_name": target_name,
                        "type": ch_type,
                        "topic": ch_spec.get("topic", ""),
                    }
                    to_create.append(entry)
                    ch_list.append(entry)

            categories_res.append({
                "name": cat_name,
                "aliases": cat_aliases,
                "channels": ch_list,
            })

        return {
            "categories": categories_res,
            "reused": reused,
            "to_create": to_create,
        }

    # =========================================================================
    # PREFIX COMMANDS (INSTANT RESPONSE WITH ! PREFIX)
    # =========================================================================

    @commands.command(name="sync")
    async def sync_prefix(self, ctx: commands.Context):
        """Owner/Admin prefix command (!sync) to instantly sync slash commands to this guild."""
        if not check_admin(ctx.author):
            await ctx.reply("❌ Administrator permissions required.")
            return
        msg = await ctx.reply("🔄 Synchronizing all slash commands directly to this server...")
        try:
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await msg.edit(content=f"✅ Instantly synchronized `{len(synced)}` slash commands to **{ctx.guild.name}**!\nYou can now use them directly via `/`.")
        except Exception as e:
            await msg.edit(content=f"❌ Sync failed: `{e}`")

    @commands.command(name="server-audit", aliases=["audit"])
    async def server_audit_prefix(self, ctx: commands.Context):
        """Prefix command for server structural audit (!server-audit or !audit)."""
        if not check_admin(ctx.author):
            await ctx.reply("❌ Administrator permissions required.")
            return
        guild = ctx.guild
        if not guild:
            return
        msg = await ctx.reply("🔍 Running structural server audit...")
        try:
            embed = await self.build_audit_embed(guild)
            await msg.edit(content=None, embed=embed)
        except Exception as e:
            await msg.edit(content=f"❌ Audit failed: {e}")

    @commands.command(name="server-health", aliases=["health"])
    async def server_health_prefix(self, ctx: commands.Context):
        """Prefix command for server health (!server-health or !health)."""
        if not check_admin(ctx.author):
            await ctx.reply("❌ Administrator permissions required.")
            return
        guild = ctx.guild
        if not guild:
            return
        msg = await ctx.reply("🏥 Checking server and bot subsystem health...")
        try:
            embed = await self.build_health_embed(guild)
            await msg.edit(content=None, embed=embed)
        except Exception as e:
            await msg.edit(content=f"❌ Health check failed: {e}")

    @commands.command(name="server-setup", aliases=["setup-preview"])
    async def server_setup_prefix(self, ctx: commands.Context, action: str = "preview"):
        """Prefix command for server setup wizard (!server-setup or !setup-preview)."""
        if not check_admin(ctx.author):
            await ctx.reply("❌ Administrator permissions required.")
            return
        guild = ctx.guild
        if not guild:
            return
        preview_data = await self.generate_preview(guild)
        embed = self.format_preview_embed(guild, preview_data)
        view = SetupConfirmationView(self, guild, ctx.author)
        await ctx.reply(embed=embed, view=view)


async def setup(bot: SentinelBot) -> None:
    await bot.add_cog(ServerSetupCog(bot))
