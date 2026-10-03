"""
Join-to-Create Dynamic Voice Room Manager for Rai.
Automatically creates public or private customizable voice channels when users join trigger hubs.
Creates and maintains an associated control panel in 🛠️・ROOM-CONTROL for each active room.
Provides 60-second grace period cleanup, owner protection, and strict channel isolation.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from core.tasks import safe_task_loop
from database.models import DynamicRoom, TempVoiceConfig
from utils.dynamic_vc_control import (
    BUILTIN_TEMPLATES,
    DynamicAdminEmergencyView,
    DynamicVCControlManager,
)
from utils.embeds import (
    create_embed,
    error_embed,
    info_embed,
    success_embed,
    warning_embed,
)
from utils.owner_reporter import OwnerReporter
from utils.permissions import is_admin_or_owner


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class TempVoiceCog(commands.Cog, name="TempVoice"):
    """Autonomous Dynamic Voice Room Manager with central ROOM-CONTROL panel."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._supervisor_task = self._dynamic_vc_supervisor.start()
        self._creation_cooldowns: Dict[int, float] = {}
        self._recent_creations: Dict[int, List[float]] = {}
        self._blocked_users: Dict[int, float] = {}

    def cog_unload(self):
        self._supervisor_task.cancel()

    tempvoice_group = app_commands.Group(
        name="tempvoice",
        description="Dynamic voice room management and central control panel",
    )

    room_group = app_commands.Group(
        name="room",
        description="Dynamic voice room management and privacy controls",
    )
    workspace_group = app_commands.Group(
        name="workspace",
        description="Unified temporary community workspaces",
    )

    # ==========================================
    # STARTUP & RECOVERY
    # ==========================================

    async def cog_load(self) -> None:
        """Run self-healing recovery for active dynamic voice rooms across all guilds."""
        asyncio.create_task(self._run_startup_recovery())

    async def _run_startup_recovery(self) -> None:
        """Re-synchronizes active dynamic voice rooms and cleans up stale records."""
        await self.bot.wait_until_ready()
        logger.info("Running Dynamic Voice Room startup recovery...")
        try:
            rooms = await self.bot.db.get_all_dynamic_rooms()
            for room in rooms:
                guild = self.bot.get_guild(room.guild_id)
                if not guild:
                    continue
                vc = guild.get_channel(room.voice_channel_id)
                if not isinstance(vc, discord.VoiceChannel):
                    logger.info(f"Dynamic room VC {room.voice_channel_id} no longer exists. Cleaning up.")
                    await DynamicVCControlManager.delete_room_panel(self.bot, guild, room.voice_channel_id)
                elif len(vc.members) == 0:
                    # VC exists but empty, enter countdown
                    if room.status != "empty_countdown":
                        await self.bot.db.update_dynamic_room(
                            room.voice_channel_id,
                            status="empty_countdown",
                            last_empty_at=utcnow_iso(),
                        )
                        await DynamicVCControlManager.update_room_panel(self.bot, guild, room.voice_channel_id)
                else:
                    # Active with occupants, ensure panel is fresh
                    if room.status != "active":
                        await self.bot.db.update_dynamic_room(
                            room.voice_channel_id,
                            status="active",
                            last_empty_at=None,
                        )
                    await DynamicVCControlManager.update_room_panel(self.bot, guild, room.voice_channel_id)
        except Exception as e:
            logger.error(f"Error during Dynamic Voice Room startup recovery: {e}", exc_info=True)

    # ==========================================
    # BACKGROUND SUPERVISOR LOOP (CLEANUP & GRACE)
    # ==========================================

    @tasks.loop(seconds=15.0)
    @safe_task_loop(task_name="dynamic_vc_supervisor", timeout_seconds=20.0)
    async def _dynamic_vc_supervisor(self) -> None:
        """Monitors empty dynamic rooms, enforces 60s grace period, and purges stale channels."""
        for guild in self.bot.guilds:
            try:
                rooms = await self.bot.db.get_all_dynamic_rooms(guild.id)
                for room in rooms:
                    vc = guild.get_channel(room.voice_channel_id)

                    # 1. VC completely gone on Discord
                    if not isinstance(vc, discord.VoiceChannel):
                        await DynamicVCControlManager.delete_room_panel(self.bot, guild, room.voice_channel_id)
                        continue

                    # 2. Check occupancy
                    occupant_count = len(vc.members)

                    # If empty
                    if occupant_count == 0:
                        if room.status != "empty_countdown" or not room.last_empty_at:
                            # Start grace countdown
                            now_str = utcnow_iso()
                            await self.bot.db.update_dynamic_room(
                                room.voice_channel_id,
                                status="empty_countdown",
                                last_empty_at=now_str,
                            )
                            await DynamicVCControlManager.update_room_panel(self.bot, guild, room.voice_channel_id)
                        else:
                            # Check if grace period expired (60 seconds)
                            try:
                                empty_dt = datetime.datetime.fromisoformat(room.last_empty_at)
                                elapsed = (utcnow() - empty_dt).total_seconds()
                            except Exception:
                                elapsed = 61.0

                            if elapsed >= 60.0:
                                # Safe delete of empty room
                                try:
                                    await vc.delete(reason="Rai Dynamic VC: 60s empty grace period expired")
                                    logger.info(f"Cleaned up empty dynamic room #{vc.name} ({vc.id}) in {guild.name}")
                                except Exception as e:
                                    logger.warning(f"Could not delete VC {vc.id}: {e}")

                                await DynamicVCControlManager.delete_room_panel(self.bot, guild, room.voice_channel_id)

                                OwnerReporter.send_room_report(
                                    self.bot,
                                    guild.id,
                                    event="Dynamic Voice Room Cleaned Up",
                                    action_taken=f"Automatically deleted empty temporary VC **#{vc.name}** after 60s grace period",
                                    details={"Voice Channel ID": f"`{vc.id}`", "Owner ID": f"`{room.owner_id}`"},
                                )
                    else:
                        # Members currently inside
                        if room.status == "empty_countdown":
                            # Rejoined during grace period! Restore active status.
                            await self.bot.db.update_dynamic_room(
                                room.voice_channel_id,
                                status="active",
                                last_empty_at=None,
                            )
                            await DynamicVCControlManager.update_room_panel(self.bot, guild, room.voice_channel_id)
            except Exception as e:
                logger.error(f"Error in dynamic VC supervisor for {guild.name}: {e}")

    # ==========================================
    # VOICE STATE LISTENER (TRIGGER & OCCUPANCY)
    # ==========================================

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Monitors member voice joins and departures for dynamic channel creation and cleanup."""
        guild = member.guild
        if member.bot:
            return

        cfg = await self.bot.db.get_temp_voice_config(guild.id)

        # -------------------------------------------------------------
        # 1. DETECT JOIN TO TRIGGER CHANNEL (CREATE ROOM)
        # -------------------------------------------------------------
        if after.channel and before.channel != after.channel:
            ch_name = after.channel.name.upper()
            is_public_trigger = (
                (cfg.enabled and cfg.hub_channel_id and after.channel.id == cfg.hub_channel_id)
                or "CREATE YOUR ROOM" in ch_name
            )
            is_private_trigger = "CREATE PRIVATE ROOM" in ch_name

            if is_public_trigger or is_private_trigger:
                await self._handle_trigger_join(
                    member=member,
                    trigger_channel=after.channel,
                    is_private=is_private_trigger,
                    cfg=cfg,
                )
                return

        # -------------------------------------------------------------
        # 2. OCCUPANCY UPDATES ON DYNAMIC ROOMS
        # -------------------------------------------------------------
        # Member departed a channel
        if before.channel and before.channel != after.channel:
            room = await self.bot.db.get_dynamic_room(before.channel.id)
            if room:
                if len(before.channel.members) == 0:
                    # Started empty countdown
                    await self.bot.db.update_dynamic_room(
                        room.voice_channel_id,
                        status="empty_countdown",
                        last_empty_at=utcnow_iso(),
                    )
                await DynamicVCControlManager.update_room_panel(self.bot, guild, room.voice_channel_id)

        # Member entered a channel
        if after.channel and before.channel != after.channel:
            room = await self.bot.db.get_dynamic_room(after.channel.id)
            if room:
                if room.status == "empty_countdown":
                    # Restored to active
                    await self.bot.db.update_dynamic_room(
                        room.voice_channel_id,
                        status="active",
                        last_empty_at=None,
                    )
                await DynamicVCControlManager.update_room_panel(self.bot, guild, room.voice_channel_id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Handles room owner leaving the server: marks owner unavailable and begins cleanup countdown."""
        guild = member.guild
        room = await self.bot.db.get_dynamic_room_by_owner(guild.id, member.id)
        if room and room.status != "deleted":
            vc = guild.get_channel(room.voice_channel_id)
            if isinstance(vc, discord.VoiceChannel):
                await self.bot.db.update_dynamic_room(
                    room.voice_channel_id,
                    status="empty_countdown",
                    last_empty_at=utcnow_iso(),
                )
                await DynamicVCControlManager.update_room_panel(self.bot, guild, room.voice_channel_id)
                OwnerReporter.send_room_report(
                    self.bot,
                    guild.id,
                    event="Room Owner Left Server",
                    user=member,
                    action_taken=f"Marked owner unavailable for #{vc.name}; initiated cleanup grace period",
                    details={"Voice Channel ID": f"`{vc.id}`", "Former Owner ID": f"`{member.id}`"},
                )

    # ==========================================
    # ROOM CREATION LOGIC
    # ==========================================

    async def _handle_trigger_join(
        self,
        member: discord.Member,
        trigger_channel: discord.VoiceChannel,
        is_private: bool,
        cfg: TempVoiceConfig,
    ) -> None:
        """Handles user joining a trigger channel: moves to existing room or provisions new VC & panel."""
        guild = member.guild
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

        # -------------------------------------------------------------
        # ANTI-SPAM & ANTI-RAID PROTECTION (PHASE 14)
        # -------------------------------------------------------------
        # Check 1: User temporarily blocked from rapid spam
        blocked_until = self._blocked_users.get(member.id, 0.0)
        if now_ts < blocked_until:
            rem = int(blocked_until - now_ts)
            try:
                await member.move_to(None, reason="Rai Anti-Spam: Dynamic VC creation blocked")
            except Exception:
                pass
            try:
                await member.send(
                    f"🛡️ **Dynamic Room Anti-Spam Block:** You are temporarily blocked from creating dynamic rooms for another `{rem}s` due to rapid room creation attempts."
                )
            except Exception:
                pass
            return

        # Check 2: Per-user creation cooldown (30 seconds)
        last_created = self._creation_cooldowns.get(member.id, 0.0)
        if now_ts - last_created < 30.0:
            rem = int(30.0 - (now_ts - last_created))
            try:
                await member.move_to(None, reason="Rai Anti-Spam: Dynamic VC cooldown active")
            except Exception:
                pass
            try:
                await member.send(
                    f"⏳ **Creation Cooldown:** Please wait `{rem}s` before creating another dynamic voice room."
                )
            except Exception:
                pass
            return

        # Check 3: Rapid Trigger Joins / Mass Channel Creation Detection
        history = self._recent_creations.setdefault(member.id, [])
        history = [t for t in history if now_ts - t < 60.0]
        history.append(now_ts)
        self._recent_creations[member.id] = history
        if len(history) >= 4:
            self._blocked_users[member.id] = now_ts + 300.0
            try:
                await member.move_to(None, reason="Rai Anti-Spam: Rapid room creation rate-limit triggered")
            except Exception:
                pass
            incident_id = f"RAI-INC-{int(now_ts) % 1000000:06d}"
            try:
                OwnerReporter.send_security_report(
                    self.bot,
                    guild.id,
                    incident_id=incident_id,
                    event="Dynamic Room Mass Creation Abuse",
                    user=member,
                    action_taken="Applied 5-minute temporary room creation block",
                    severity="HIGH",
                    details={
                        "User ID": f"`{member.id}`",
                        "Triggers In 60s": f"`{len(history)}`",
                        "Action": "Temporarily disconnected & blocked room provisioning",
                    },
                )
            except Exception as e:
                logger.error(f"Failed to send security report: {e}")
            try:
                await member.send(
                    "🛡️ **Dynamic Voice Security Alert:** Rapid room creation detected. A 5-minute cooldown has been applied and a security report has been logged."
                )
            except Exception:
                pass
            return

        # 1. Check if user already owns an active room
        existing = await self.bot.db.get_dynamic_room_by_owner(guild.id, member.id)
        if existing and existing.status != "deleted":
            existing_vc = guild.get_channel(existing.voice_channel_id)
            if isinstance(existing_vc, discord.VoiceChannel):
                try:
                    await member.move_to(existing_vc, reason="Rai Dynamic VC: Moved to existing owned room")
                    logger.info(f"Moved {member} to their existing room #{existing_vc.name}")
                    return
                except Exception as e:
                    logger.warning(f"Could not move {member} to existing room: {e}")

        # 2. Determine target category
        category = None
        if cfg.category_id:
            category = guild.get_channel(cfg.category_id)
        elif trigger_channel.category:
            category = trigger_channel.category

        # 3. Configure permissions and initial metadata
        if is_private:
            channel_name = f"🔐・{member.display_name}'s Room"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
                member: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    manage_channels=True,
                    move_members=True,
                    mute_members=True,
                ),
            }
            room_type = "private"
            privacy_mode = "owner_only"
            locked = True
            user_limit = 2
        else:
            channel_name = f"🎙️・{member.display_name}'s Room"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True),
                member: discord.PermissionOverwrite(
                    manage_channels=True,
                    move_members=True,
                    mute_members=True,
                ),
            }
            room_type = "public"
            privacy_mode = "public"
            locked = False
            user_limit = cfg.default_user_limit or 0

        # 4. Create Voice Channel
        try:
            temp_vc = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=user_limit,
                overwrites=overwrites,
                reason=f"Rai Dynamic VC: Provisioned {room_type} room for {member.display_name}",
            )
            # Record creation timestamp for per-user cooldown
            self._creation_cooldowns[member.id] = now_ts
        except Exception as e:
            logger.error(f"Failed to create temporary voice channel on Discord: {e}")
            return

        # 5. Persist to Database
        now_str = utcnow_iso()
        dyn_room = DynamicRoom(
            guild_id=guild.id,
            voice_channel_id=temp_vc.id,
            owner_id=member.id,
            room_type=room_type,
            privacy_mode=privacy_mode,
            user_limit=user_limit,
            locked=locked,
            created_at=now_str,
            status="active",
        )
        await self.bot.db.create_dynamic_room(dyn_room)

        # 6. Move Creator to their new Room
        try:
            await member.move_to(temp_vc, reason="Rai Dynamic VC: Moved owner into created room")
        except Exception as e:
            logger.warning(f"Failed to move {member} to new voice room {temp_vc.id}: {e}")

        # 7. Post Control Panel in 🛠️・ROOM-CONTROL
        msg = await DynamicVCControlManager.create_room_panel(self.bot, guild, dyn_room, temp_vc)
        if msg:
            dyn_room.control_message_id = msg.id
            dyn_room.control_channel_id = msg.channel.id

        # 8. Dual Report Delivery (Owner DM + 🔐・room-report)
        OwnerReporter.send_room_report(
            self.bot,
            guild.id,
            event=f"{room_type.title()} Voice Room Created",
            user=member,
            action_taken=f"Provisioned **#{temp_vc.name}** and posted controls in 🛠️・ROOM-CONTROL",
            details={
                "Room Type": f"`{room_type.upper()}`",
                "Voice Channel ID": f"`{temp_vc.id}`",
                "User Capacity": f"`{user_limit or 'Unlimited'}`",
                "Control Channel": f"<#{dyn_room.control_channel_id}>" if dyn_room.control_channel_id else "ROOM-CONTROL",
            },
        )
        logger.info(f"Successfully provisioned dynamic room #{channel_name} ({temp_vc.id}) for {member}")

        # 9. Send Creator Interactive Setup Panel / Notification
        try:
            welcome_embed = create_embed(
                title="🎙️ ROOM CREATED",
                description=(
                    f"**Your room:** `{temp_vc.name}`\n"
                    f"**Owner:** {member.mention}\n"
                    f"**Members:** `1 / {user_limit or 'Unlimited'}`\n"
                    f"**Privacy:** {privacy_mode.replace('_', ' ').title()}\n\n"
                    f"👉 Use the interactive controls in <#{dyn_room.control_channel_id}> to configure your room."
                ),
                color=Colors.SUCCESS,
            )
            await member.send(embed=welcome_embed)
        except Exception:
            pass

        # 10. Native Voice Channel Text Chat Welcome (Phase 13)
        try:
            vc_chat_welcome = create_embed(
                title=f"🎙️ Welcome to {temp_vc.name}!",
                description=(
                    f"👑 **Owner:** {member.mention}\n"
                    f"👥 **Members:** `1 / {user_limit or 'Unlimited'}`\n"
                    f"🔓 **Visibility:** {privacy_mode.replace('_', ' ').title()}\n\n"
                    f"Central controls available in <#{dyn_room.control_channel_id}>."
                ),
                color=Colors.SUCCESS,
            )
            await temp_vc.send(embed=vc_chat_welcome)
        except Exception:
            pass

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @tempvoice_group.command(name="deploy", description="Deploy central Dynamic Voice Rooms structure and ROOM-CONTROL")
    @is_admin_or_owner()
    async def tempvoice_deploy(self, interaction: discord.Interaction):
        """Provisions or repairs 🔊 | DYNAMIC VOICE ROOMS, trigger hubs, and ROOM-CONTROL."""
        guild = interaction.guild
        cat, pub_hub, priv_hub, ctrl_ch = await DynamicVCControlManager.ensure_dynamic_vc_structure(guild)

        await self.bot.db.update_temp_voice_config(
            guild.id,
            enabled=True,
            hub_channel_id=pub_hub.id,
            category_id=cat.id,
        )

        embed = create_embed(
            title="🔊 Dynamic Voice System Deployed",
            description=(
                f"Successfully provisioned and linked the central dynamic voice infrastructure:\n\n"
                f"• **Category:** {cat.name}\n"
                f"• **Public Hub:** {pub_hub.mention} (`{pub_hub.name}`)\n"
                f"• **Private Hub:** {priv_hub.mention} (`{priv_hub.name}`)\n"
                f"• **Control Channel:** {ctrl_ch.mention} (`{ctrl_ch.name}`)"
            ),
            color=Colors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tempvoice_group.command(name="setup", description="Configure Join-to-Create temporary voice hub")
    @is_admin_or_owner()
    @app_commands.describe(
        hub_channel="The voice channel users click to spawn their room",
        category="Category where new temporary voice channels are created",
        default_user_limit="Default capacity (0 = unlimited)",
    )
    async def tempvoice_setup(
        self,
        interaction: discord.Interaction,
        hub_channel: discord.VoiceChannel,
        category: Optional[discord.CategoryChannel] = None,
        default_user_limit: Optional[int] = 0,
    ):
        await self.bot.db.update_temp_voice_config(
            interaction.guild.id,
            enabled=True,
            hub_channel_id=hub_channel.id,
            category_id=category.id if category else None,
            default_user_limit=max(0, default_user_limit or 0),
        )
        await interaction.response.send_message(
            embed=success_embed(
                "TempVoice Configured",
                f"• **Hub Channel:** {hub_channel.mention}\n"
                f"• **Category:** {category.name if category else 'Same as Hub'}\n"
                f"• **Default Capacity:** `{default_user_limit or 'Unlimited'}`",
            ),
            ephemeral=True,
        )

    @tempvoice_group.command(name="lock", description="Lock your temporary voice channel to prevent new members from joining")
    async def tempvoice_lock(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary voice channel."), ephemeral=True)
            return

        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "You are not the owner of this temporary room."), ephemeral=True)
            return

        await vc.set_permissions(interaction.guild.default_role, connect=False)
        await self.bot.db.update_dynamic_room(vc.id, locked=1, privacy_mode="locked")
        await DynamicVCControlManager.update_room_panel(self.bot, interaction.guild, vc.id)
        await interaction.response.send_message(embed=success_embed("Room Locked", "Your room is now locked. Only existing members can remain."), ephemeral=True)

    @tempvoice_group.command(name="unlock", description="Unlock your temporary voice channel")
    async def tempvoice_unlock(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary voice channel."), ephemeral=True)
            return

        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "You are not the owner of this temporary room."), ephemeral=True)
            return

        await vc.set_permissions(interaction.guild.default_role, connect=True)
        await self.bot.db.update_dynamic_room(vc.id, locked=0, privacy_mode="public")
        await DynamicVCControlManager.update_room_panel(self.bot, interaction.guild, vc.id)
        await interaction.response.send_message(embed=success_embed("Room Unlocked", "Your room is now open for other server members."), ephemeral=True)

    @tempvoice_group.command(name="limit", description="Set a member capacity limit on your room")
    @app_commands.describe(limit="Maximum number of users allowed (0 = unlimited)")
    async def tempvoice_limit(self, interaction: discord.Interaction, limit: int):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary voice channel."), ephemeral=True)
            return

        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "You are not the owner of this temporary room."), ephemeral=True)
            return

        clean_limit = max(0, min(99, limit))
        await vc.edit(user_limit=clean_limit)
        await self.bot.db.update_dynamic_room(vc.id, user_limit=clean_limit)
        await DynamicVCControlManager.update_room_panel(self.bot, interaction.guild, vc.id)
        await interaction.response.send_message(embed=success_embed("Capacity Updated", f"User limit set to `{clean_limit or 'Unlimited'}`."), ephemeral=True)

    @tempvoice_group.command(name="rename", description="Rename your temporary voice channel")
    @app_commands.describe(name="New channel name")
    async def tempvoice_rename(self, interaction: discord.Interaction, name: str):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary voice channel."), ephemeral=True)
            return

        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "You are not the owner of this temporary room."), ephemeral=True)
            return

        clean_name = name[:32]
        await vc.edit(name=clean_name)
        await DynamicVCControlManager.update_room_panel(self.bot, interaction.guild, vc.id)
        await interaction.response.send_message(embed=success_embed("Room Renamed", f"Channel renamed to **{clean_name}**."), ephemeral=True)

    @tempvoice_group.command(name="status", description="Inspect TempVoice hub configuration")
    @is_admin_or_owner()
    async def tempvoice_status(self, interaction: discord.Interaction):
        cfg = await self.bot.db.get_temp_voice_config(interaction.guild.id)
        hub = f"<#{cfg.hub_channel_id}>" if cfg.hub_channel_id else "Not Set"
        cat = f"<#{cfg.category_id}>" if cfg.category_id else "Same as Hub"

        embed = create_embed(
            title=f"🔊 TempVoice Status — {interaction.guild.name}",
            color=Colors.SUCCESS if cfg.enabled else Colors.DEFAULT,
        )
        embed.add_field(name="Engine", value="🟢 Active" if cfg.enabled else "⚪ Disabled", inline=True)
        embed.add_field(name="Hub Channel", value=hub, inline=True)
        embed.add_field(name="Target Category", value=cat, inline=True)
        embed.add_field(name="Default Limit", value=f"`{cfg.default_user_limit or 'Unlimited'}`", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tempvoice_group.command(name="panel", description="Locate or refresh your room's central control panel")
    async def tempvoice_panel(self, interaction: discord.Interaction):
        member = interaction.user
        room = await self.bot.db.get_dynamic_room_by_owner(interaction.guild_id, member.id)
        if not room or room.status == "deleted":
            await interaction.response.send_message(
                embed=error_embed("No Active Room", "You do not currently own an active voice room."),
                ephemeral=True,
            )
            return

        vc = interaction.guild.get_channel(room.voice_channel_id)
        if not isinstance(vc, discord.VoiceChannel):
            await interaction.response.send_message(
                embed=error_embed("Room Not Found", "Your voice room is no longer active."),
                ephemeral=True,
            )
            return

        await DynamicVCControlManager.update_room_panel(self.bot, interaction.guild, vc.id)
        ctrl_ch_id = room.control_channel_id
        await interaction.response.send_message(
            embed=success_embed(
                "Control Panel Ready",
                f"Your room controls are live in <#{ctrl_ch_id}> targeting **#{vc.name}**.",
            ),
            ephemeral=True,
        )

    template_group = app_commands.Group(
        name="template",
        description="Dynamic voice room template presets and configuration",
        parent=tempvoice_group,
    )

    @template_group.command(name="save", description="Save your current room settings as a personal template")
    @app_commands.describe(name="Template preset name")
    async def template_save(self, interaction: discord.Interaction, name: str):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(
                embed=error_embed("Not in Voice", "You must be inside your temporary voice room."),
                ephemeral=True,
            )
            return

        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(
                embed=error_embed("Unauthorized", "You are not the owner of this room."),
                ephemeral=True,
            )
            return

        settings = json.dumps({
            "user_limit": room.user_limit,
            "privacy_mode": room.privacy_mode,
            "prefix": vc.name[:3],
        })
        await self.bot.db.save_room_template(interaction.guild_id, member.id, name[:24], settings)
        await interaction.response.send_message(
            embed=success_embed("Template Saved", f"Saved template **{name[:24]}** for future rooms."),
            ephemeral=True,
        )

    @template_group.command(name="list", description="List built-in and saved custom room templates")
    async def template_list(self, interaction: discord.Interaction):
        builtin_lines = [f"• **{k}**: {v['label']}" for k, v in BUILTIN_TEMPLATES.items()]
        custom_tpls = await self.bot.db.get_room_templates(interaction.guild_id, interaction.user.id)
        custom_lines = [f"• **{t.template_name}**" for t in custom_tpls] or ["*No custom presets saved yet.*"]

        embed = create_embed(
            title="🎨 Dynamic Voice Room Templates",
            description=(
                "**Built-in Presets:**\n" + "\n".join(builtin_lines) +
                "\n\n**Your Custom Presets:**\n" + "\n".join(custom_lines)
            ),
            color=Colors.PRIMARY,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @template_group.command(name="apply", description="Apply a template to your current active room")
    @app_commands.describe(template="Select a template preset")
    @app_commands.choices(template=[
        app_commands.Choice(name=k, value=k) for k in BUILTIN_TEMPLATES
    ])
    async def template_apply(self, interaction: discord.Interaction, template: app_commands.Choice[str]):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(
                embed=error_embed("Not in Voice", "You must be inside your temporary voice room."),
                ephemeral=True,
            )
            return

        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(
                embed=error_embed("Unauthorized", "You are not the owner of this room."),
                ephemeral=True,
            )
            return

        await DynamicVCControlManager._dispatch_template_action(self.bot, interaction, room, vc, template.value)

    @tempvoice_group.command(name="knock", description="Request access to a locked, private, or invite-only room")
    @app_commands.describe(channel="The temporary voice room you want to join")
    async def tempvoice_knock(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Sends an access request to the room owner (Phase 7)."""
        await DynamicVCControlManager._dispatch_knock_action(self.bot, interaction, "request", str(channel.id))

    @tempvoice_group.command(name="admin_panel", description="Deploy emergency master control panel in 👑・admin-control")
    @is_admin_or_owner()
    async def tempvoice_admin_panel(self, interaction: discord.Interaction):
        """Deploys emergency master controls (Phase 32)."""
        guild = interaction.guild
        if not guild:
            return

        admin_channel = None
        for cat in guild.categories:
            if "ADMIN" in cat.name.upper():
                for ch in cat.channels:
                    if "ADMIN-CONTROL" in ch.name.upper() and isinstance(ch, discord.TextChannel):
                        admin_channel = ch
                        break

        target_ch = admin_channel or interaction.channel
        view = DynamicAdminEmergencyView()
        embed = create_embed(
            title="👑 DYNAMIC VOICE ROOMS — EMERGENCY MASTER CONTROLS",
            description=(
                "Administrative emergency overrides and global room management.\n\n"
                "• 🔒 **Lock All Rooms:** Prevent all new joins server-wide\n"
                "• 🛑 **Stop All Music:** Disconnect music bots and clear all queues\n"
                "• 🧹 **Cleanup Empty Rooms:** Instantly purge 0-occupant rooms\n"
                "• 🔄 **Rebuild Permissions:** Reconcile Discord perms against DB state\n"
                "• ❤️ **Health Check:** Live subsystem metrics and worker health\n"
                "• 📋 **System Status:** Active rooms inventory and status"
            ),
            color=Colors.DANGER,
        )
        if isinstance(target_ch, discord.TextChannel):
            await target_ch.send(embed=embed, view=view)
            await interaction.response.send_message(
                embed=success_embed("Admin Panel Posted", f"Master emergency controls posted in {target_ch.mention}."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @tempvoice_group.command(name="reconcile", description="Reconcile database state with Discord channel permissions")
    @is_admin_or_owner()
    async def tempvoice_reconcile(self, interaction: discord.Interaction):
        """Forces immediate reconciliation of Discord permissions against database desired state (Phase 33)."""
        await DynamicVCControlManager._dispatch_admin_emergency_action(self.bot, interaction, "rebuild_perms")

    # ==========================================
    # /room COMMAND SUITE (Native UX)
    # ==========================================

    @room_group.command(name="create", description="Create a temporary dynamic voice room")
    @app_commands.describe(name="Optional custom room name", user_limit="Maximum participants (0 = unlimited)", template="Preset template")
    @app_commands.choices(
        template=[
            app_commands.Choice(name="Gaming (5 Slots)", value="Gaming"),
            app_commands.Choice(name="Chill (Unlimited)", value="Chill"),
            app_commands.Choice(name="Music Lounge", value="Music"),
            app_commands.Choice(name="Creator Studio (10 Slots)", value="Creator"),
            app_commands.Choice(name="Private Sanctum (2 Slots)", value="Private"),
            app_commands.Choice(name="Watch Party (15 Slots)", value="Watch Party"),
        ]
    )
    async def room_create(
        self,
        interaction: discord.Interaction,
        name: Optional[str] = None,
        user_limit: Optional[int] = None,
        template: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            await interaction.followup.send("❌ This command must be used inside a server.", ephemeral=True)
            return

        cfg = await self.bot.db.get_or_create_temp_voice_config(guild.id)
        cat = guild.get_channel(cfg.category_id) if cfg.category_id else None
        if not cat:
            cat = discord.utils.find(lambda c: "DYNAMIC VOICE ROOMS" in c.name.upper(), guild.categories)

        effective_limit = user_limit if user_limit is not None else 0
        pfx = "🎙️・"
        priv_mode = "public"
        locked = False
        if template and template in BUILTIN_TEMPLATES:
            t_data = BUILTIN_TEMPLATES[template]
            pfx = t_data.get("prefix", pfx)
            if user_limit is None:
                effective_limit = t_data.get("user_limit", 0)
            priv_mode = t_data.get("privacy", "public")
            if priv_mode in ("owner_only", "locked"):
                locked = True

        ch_name = f"{pfx}{name.strip()}" if name else f"{pfx}{member.display_name}'s Room"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=not locked, connect=not locked, speak=True),
            member: discord.PermissionOverwrite(manage_channels=True, move_members=True, mute_members=True, connect=True, speak=True),
        }

        try:
            vc = await guild.create_voice_channel(
                name=ch_name[:32],
                category=cat,
                user_limit=effective_limit,
                overwrites=overwrites,
                reason=f"Dynamic Room created via /room create by {member}",
            )
            dyn_room = DynamicRoom(
                guild_id=guild.id,
                voice_channel_id=vc.id,
                owner_id=member.id,
                room_type="public" if not locked else "private",
                privacy_mode=priv_mode,
                user_limit=effective_limit,
                locked=locked,
                created_at=utcnow_iso(),
                status="active",
            )
            await self.bot.db.create_dynamic_room(dyn_room)

            if member.voice and member.voice.channel:
                try:
                    await member.move_to(vc)
                except Exception:
                    pass

            panel_msg = await DynamicVCControlManager.create_room_panel(self.bot, guild, dyn_room, vc)
            await interaction.followup.send(
                embed=success_embed("Room Created", f"🔊 Created your room {vc.mention}! Controls available in <#{cfg.control_channel_id}>."),
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Failed to create room via /room create: {e}")
            await interaction.followup.send(embed=error_embed("Creation Failed", f"Could not create room: {e}"), ephemeral=True)

    @room_group.command(name="create-private", description="Create an invite-only private temporary voice room")
    @app_commands.describe(name="Optional custom room name")
    async def room_create_private(self, interaction: discord.Interaction, name: Optional[str] = None):
        await self.room_create(interaction, name=name, template="Private")

    @room_group.command(name="rename", description="Rename your temporary voice room")
    @app_commands.describe(name="New room name")
    async def room_rename(self, interaction: discord.Interaction, name: str):
        await self.tempvoice_rename(interaction, name)

    @room_group.command(name="privacy", description="Update privacy mode for your room")
    @app_commands.describe(mode="Privacy visibility mode")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Public (Open to server)", value="public"),
            app_commands.Choice(name="Invite Only (Knock to enter)", value="invite_only"),
            app_commands.Choice(name="Owner & Co-Hosts Only", value="owner_only"),
            app_commands.Choice(name="Locked (No new joins)", value="locked"),
        ]
    )
    async def room_privacy(self, interaction: discord.Interaction, mode: str):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary room."), ephemeral=True)
            return
        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "You are not the owner of this room."), ephemeral=True)
            return

        is_locked = mode in ("locked", "owner_only")
        await vc.set_permissions(interaction.guild.default_role, connect=not is_locked, view_channel=mode != "owner_only")
        await self.bot.db.update_dynamic_room(vc.id, privacy_mode=mode, locked=1 if is_locked else 0)
        await DynamicVCControlManager.update_room_panel(self.bot, interaction.guild, vc.id)
        await interaction.response.send_message(embed=success_embed("Privacy Updated", f"Room privacy set to **{mode.replace('_', ' ').title()}**."), ephemeral=True)

    @room_group.command(name="lock", description="Lock your temporary voice room")
    async def room_lock(self, interaction: discord.Interaction):
        await self.tempvoice_lock(interaction)

    @room_group.command(name="unlock", description="Unlock your temporary voice room")
    async def room_unlock(self, interaction: discord.Interaction):
        await self.tempvoice_unlock(interaction)

    @room_group.command(name="invite", description="Invite a user to your temporary voice room")
    @app_commands.describe(user="Member to invite")
    async def room_invite(self, interaction: discord.Interaction, user: discord.Member):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary room."), ephemeral=True)
            return
        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or (room.owner_id != member.id and member.id not in (room.co_host_ids or [])):
            await interaction.response.send_message(embed=error_embed("Unauthorized", "You must be owner or co-host to invite."), ephemeral=True)
            return

        await vc.set_permissions(user, view_channel=True, connect=True, speak=True)
        await self.bot.db.add_room_member(vc.id, user.id, "invited")
        await interaction.response.send_message(embed=success_embed("Member Invited", f"Granted access to {user.mention}."), ephemeral=True)

    @room_group.command(name="remove", description="Remove or kick a user from your temporary room")
    @app_commands.describe(user="Member to remove")
    async def room_remove(self, interaction: discord.Interaction, user: discord.Member):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary room."), ephemeral=True)
            return
        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or (room.owner_id != member.id and member.id not in (room.co_host_ids or [])):
            await interaction.response.send_message(embed=error_embed("Unauthorized", "You must be owner or co-host to remove members."), ephemeral=True)
            return

        await vc.set_permissions(user, connect=False)
        if user.voice and user.voice.channel and user.voice.channel.id == vc.id:
            try:
                await user.move_to(None, reason="Removed by room owner")
            except Exception:
                pass
        await self.bot.db.remove_room_member(vc.id, user.id)
        await interaction.response.send_message(embed=success_embed("Member Removed", f"Removed {user.mention} from your room."), ephemeral=True)

    @room_group.command(name="members", description="List all occupants, co-hosts, and DJ in your room")
    async def room_members(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in a voice room."), ephemeral=True)
            return
        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)

        lines = [f"**Channel:** #{vc.name} (`{vc.id}`)", f"**Occupants ({len(vc.members)}):**"]
        for m in vc.members:
            badges = []
            if room and m.id == room.owner_id:
                badges.append("👑 Owner")
            if room and m.id in (room.co_host_ids or []):
                badges.append("⭐ Co-Host")
            if room and m.id == getattr(room, "dj_user_id", None):
                badges.append("🎧 DJ")
            b_str = f" ({', '.join(badges)})" if badges else ""
            lines.append(f"• {m.mention}{b_str}")

        embed = create_embed(title=f"👥 Room Members — #{vc.name}", description="\n".join(lines), color=Colors.PRIMARY)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @room_group.command(name="limit", description="Set user capacity limit on your room")
    @app_commands.describe(limit="Maximum member capacity (0 = unlimited)")
    async def room_limit(self, interaction: discord.Interaction, limit: int):
        await self.tempvoice_limit(interaction, limit)

    @room_group.command(name="bitrate", description="Adjust voice channel audio bitrate (kbps)")
    @app_commands.describe(kbps="Bitrate in kbps (e.g. 64, 96, 128, 256, 384)")
    async def room_bitrate(self, interaction: discord.Interaction, kbps: int):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary room."), ephemeral=True)
            return
        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "You are not the owner of this room."), ephemeral=True)
            return

        max_bitrate = interaction.guild.bitrate_limit if interaction.guild else 96000
        bps = max(8000, min(max_bitrate, kbps * 1000))
        await vc.edit(bitrate=bps)
        await interaction.response.send_message(embed=success_embed("Bitrate Updated", f"Room audio bitrate set to `{bps // 1000} kbps`."), ephemeral=True)

    @room_group.command(name="cohost", description="Grant or revoke co-host permissions to a member")
    @app_commands.describe(user="Target member to toggle co-host for")
    async def room_cohost(self, interaction: discord.Interaction, user: discord.Member):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary room."), ephemeral=True)
            return
        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "Only the room owner can assign co-hosts."), ephemeral=True)
            return

        cohosts = list(room.co_host_ids or [])
        if user.id in cohosts:
            cohosts.remove(user.id)
            action_str = "Revoked Co-Host from"
        else:
            cohosts.append(user.id)
            action_str = "Granted Co-Host to"

        await self.bot.db.update_dynamic_room(vc.id, co_host_ids=cohosts)
        await DynamicVCControlManager.update_room_panel(self.bot, interaction.guild, vc.id)
        await interaction.response.send_message(embed=success_embed("Co-Host Updated", f"{action_str} {user.mention}."), ephemeral=True)

    @room_group.command(name="dj", description="Designate a member as the room DJ")
    @app_commands.describe(user="Target member")
    async def room_dj(self, interaction: discord.Interaction, user: discord.Member):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary room."), ephemeral=True)
            return
        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "Only the room owner can assign DJ."), ephemeral=True)
            return

        await self.bot.db.update_dynamic_room(vc.id, dj_user_id=user.id)
        await DynamicVCControlManager.update_room_panel(self.bot, interaction.guild, vc.id)
        await interaction.response.send_message(embed=success_embed("DJ Designated", f"Designated {user.mention} as the room DJ."), ephemeral=True)

    @room_group.command(name="transfer", description="Transfer room ownership to another member inside the room")
    @app_commands.describe(user="New owner")
    async def room_transfer(self, interaction: discord.Interaction, user: discord.Member):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary room."), ephemeral=True)
            return
        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "You are not the owner of this room."), ephemeral=True)
            return
        if user.id == member.id:
            await interaction.response.send_message(embed=error_embed("Invalid Target", "You already own this room."), ephemeral=True)
            return

        await self.bot.db.update_dynamic_room(vc.id, owner_id=user.id)
        await vc.set_permissions(user, manage_channels=True, move_members=True, mute_members=True, connect=True, speak=True)
        await DynamicVCControlManager.update_room_panel(self.bot, interaction.guild, vc.id)
        await interaction.response.send_message(embed=success_embed("Ownership Transferred", f"Transferred room ownership to {user.mention}."), ephemeral=True)

    @room_group.command(name="knock", description="Request permission to join a locked or private room")
    @app_commands.describe(channel="Target voice room to knock on")
    async def room_knock(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await self.tempvoice_knock(interaction, channel)

    @room_group.command(name="delete", description="Immediately delete your temporary voice room")
    async def room_delete(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message(embed=error_embed("Not in Voice", "You must be in your temporary room."), ephemeral=True)
            return
        vc = member.voice.channel
        room = await self.bot.db.get_dynamic_room(vc.id)
        if not room or room.owner_id != member.id:
            await interaction.response.send_message(embed=error_embed("Unauthorized", "Only the room owner can delete this room."), ephemeral=True)
            return

        await interaction.response.send_message(embed=info_embed("Deleting Room", "Room is being purged..."), ephemeral=True)
        await DynamicVCCleanupService.execute_room_cleanup(self.bot, vc.id, reason="Owner requested immediate room deletion")

    @room_group.command(name="settings", description="Display room status and control panel")
    async def room_settings(self, interaction: discord.Interaction):
        await self.tempvoice_status(interaction)

    @room_group.command(name="status", description="Display room status and control panel")
    async def room_status(self, interaction: discord.Interaction):
        await self.tempvoice_status(interaction)


async def setup(bot: SentinelBot):
    await bot.add_cog(TempVoiceCog(bot))

