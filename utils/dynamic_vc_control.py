"""
Dynamic Voice Channel Control Panel and Room Manager for Rai.
Provides central control panel in 🛠️・ROOM-CONTROL for all temporary voice rooms.
Strictly maps each control panel to its specific voice channel with zero cross-room leakage.
All user-facing button responses and confirmations are EPHEMERAL ("Only you can see this").
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import unicodedata
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import discord
from discord import ui

from config import Colors
from database.models import DynamicRoom, RoomMember
from utils.embeds import create_embed, error_embed, success_embed, warning_embed
from utils.owner_reporter import OwnerReporter

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

# Small caps translation map for styled Discord channel/category names
_SMALL_CAPS_MAP = str.maketrans("ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ", "abcdefghijklmnopqrstuvwxyz")


def normalize_channel_name(text: str) -> str:
    """Normalizes Unicode mathematical, styled, and small caps fonts into plain lowercase ASCII."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.translate(_SMALL_CAPS_MAP).lower()

# Built-in room templates
BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "Gaming": {"prefix": "🎮・", "user_limit": 5, "privacy": "public", "label": "Gaming (5 Slots)"},
    "Chill": {"prefix": "🌙・", "user_limit": 0, "privacy": "public", "label": "Chill (Unlimited)"},
    "Music": {"prefix": "🎵・", "user_limit": 0, "privacy": "public", "label": "Music Lounge"},
    "Creator": {"prefix": "🎨・", "user_limit": 10, "privacy": "invite_only", "label": "Creator Studio (10 Slots)"},
    "Private": {"prefix": "🔐・", "user_limit": 2, "privacy": "owner_only", "label": "Private Sanctum (2 Slots)"},
    "Watch Party": {"prefix": "🎬・", "user_limit": 15, "privacy": "public", "label": "Watch Party (15 Slots)"},
}


class DynamicVCControlManager:
    """Central manager for Dynamic Voice Rooms, lifecycle, and control panel interaction."""

    CATEGORY_NAME = "🔊 | DYNAMIC VOICE ROOMS"
    PUBLIC_HUB_NAME = "🔊・CREATE YOUR ROOM"
    PRIVATE_HUB_NAME = "🔐・CREATE PRIVATE ROOM"
    CONTROL_CHANNEL_NAME = "🛠️・ROOM-CONTROL"

    # =========================================================================
    # CHANNEL INFRASTRUCTURE
    # =========================================================================

    @classmethod
    async def ensure_dynamic_vc_structure(
        cls, guild: discord.Guild
    ) -> Tuple[discord.CategoryChannel, discord.VoiceChannel, discord.VoiceChannel, discord.TextChannel]:
        """Ensures the central category, trigger voice hubs, and room-control text channel exist."""
        # 1. Locate category
        category = None
        for cat in guild.categories:
            norm_cat = normalize_channel_name(cat.name)
            if "dynamic voice" in norm_cat or "private voice" in norm_cat or "voice room" in norm_cat:
                category = cat
                break

        if not category:
            for cat in guild.categories:
                for ch in cat.channels:
                    n = normalize_channel_name(ch.name)
                    if ("create" in n and "room" in n) or ("room" in n and "control" in n):
                        category = cat
                        break
                if category:
                    break

        if not category:
            category = await guild.create_category(
                name=cls.CATEGORY_NAME,
                reason="Rai Dynamic VC: Provisioned dynamic rooms category",
            )
            logger.info(f"Created category '{cls.CATEGORY_NAME}' in {guild.name}")

        # 2. Locate or create trigger voice hubs
        public_hub = None
        private_hub = None
        control_channel = None

        search_channels = category.channels if category else guild.channels
        for ch in search_channels:
            norm_name = normalize_channel_name(ch.name)
            if isinstance(ch, discord.VoiceChannel):
                if "create" in norm_name and "room" in norm_name and "private" not in norm_name:
                    public_hub = ch
                elif "private" in norm_name and "room" in norm_name:
                    private_hub = ch
            elif isinstance(ch, discord.TextChannel):
                if "room-control" in norm_name or ("room" in norm_name and "control" in norm_name):
                    control_channel = ch

        if not public_hub:
            public_hub = await guild.create_voice_channel(
                name=cls.PUBLIC_HUB_NAME,
                category=category,
                user_limit=1,
                reason="Rai Dynamic VC: Provisioned public room trigger hub",
            )

        if not private_hub:
            private_hub = await guild.create_voice_channel(
                name=cls.PRIVATE_HUB_NAME,
                category=category,
                user_limit=1,
                reason="Rai Dynamic VC: Provisioned private room trigger hub",
            )

        # 3. Locate or create central control text channel
        if not control_channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True,
                    read_message_history=True,
                    send_messages=False,
                    add_reactions=False,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    read_message_history=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    manage_messages=True,
                ),
            }
            control_channel = await guild.create_text_channel(
                name=cls.CONTROL_CHANNEL_NAME,
                category=category,
                overwrites=overwrites,
                topic="🛠️ Central Interactive Control Center for Temporary Dynamic Voice Rooms",
                reason="Rai Dynamic VC: Provisioned central room-control channel",
            )
            logger.info(f"Created central control channel '{cls.CONTROL_CHANNEL_NAME}' in {guild.name}")

        return category, public_hub, private_hub, control_channel

    # =========================================================================
    # EMBED & VIEW BUILDERS
    # =========================================================================

    @classmethod
    def build_panel_embed(
        cls,
        room: DynamicRoom,
        vc: Optional[discord.VoiceChannel] = None,
        bot: Optional[SentinelBot] = None,
    ) -> discord.Embed:
        """Constructs the high-fidelity room control embed."""
        vc_name = vc.name if vc else f"Room #{room.voice_channel_id}"
        member_count = len(vc.members) if vc else 0
        limit_str = str(room.user_limit) if room.user_limit > 0 else "Unlimited"

        privacy_labels = {
            "public": "🌐 Public",
            "locked": "🔒 Locked",
            "invite_only": "👥 Invite Only",
            "owner_only": "👑 Owner Only",
        }
        privacy_display = privacy_labels.get(room.privacy_mode, "🌐 Public")
        if room.locked and room.privacy_mode != "locked":
            privacy_display = f"🔒 Locked ({privacy_display})"

        status_display = "🟢 Active"
        if room.status == "empty_countdown":
            status_display = "⏳ Empty (Cleanup Pending)"
        elif room.status == "deleted":
            status_display = "🔴 Closed"

        # Timestamp conversion
        try:
            created_dt = datetime.datetime.fromisoformat(room.created_at)
            ts_str = f"<t:{int(created_dt.timestamp())}:t> (<t:{int(created_dt.timestamp())}:R>)"
        except Exception:
            ts_str = "Just now"

        owner_display = f"<@{room.owner_id}>"
        if vc and vc.guild:
            owner_member = vc.guild.get_member(room.owner_id)
            if owner_member:
                owner_display = f"{owner_member.display_name} (<@{room.owner_id}>)"

        embed = create_embed(
            title=f"🎙️ YOUR ROOM • {vc_name.upper()}",
            description=(
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"**{vc_name}**\n\n"
                f"👥 **Members:** `{member_count} / {limit_str}`\n"
                f"{privacy_display}\n"
                f"👑 **Owner:** {owner_display}\n"
                f"⚡ **Status:** {status_display}\n"
                f"⏱️ **Created:** {ts_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=Colors.PRIMARY if room.room_type == "public" else 0x9B59B6,
        )

        # Check for active music session in this specific VC
        if bot and hasattr(bot, "cogs"):
            music_cog = bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players") and vc:
                player = music_cog.players.get(vc.guild.id)
                if player and player.voice_client and player.voice_client.channel and player.voice_client.channel.id == vc.id:
                    track_info = "Streaming Audio"
                    if hasattr(player, "current") and player.current:
                        title = getattr(player.current, "title", "Audio Track")
                        track_info = f"**{title}**"
                    music_status = "⏸️ Paused" if getattr(player, "is_paused", False) else "▶️ Playing"
                    embed.add_field(
                        name="🎵 Active Music Stream",
                        value=f"{music_status} • {track_info}",
                        inline=False,
                    )

        embed.set_footer(text=f"Rai Dynamic Voice Sentinel • Target VC ID: {room.voice_channel_id}")
        return embed

    @classmethod
    def build_hub_embed(cls) -> discord.Embed:
        """Constructs the permanent Master Hub embed for ROOM-CONTROL."""
        embed = create_embed(
            title="🔧・ROOM-CONTROL",
            description=(
                "**➕ CREATE ROOM**\n"
                "Create your own temporary voice room.\n\n"
                "**🔒 PRIVATE ROOM**\n"
                "Create a hidden private room.\n\n"
                "────────────────────\n"
                "Click a button below or join a trigger voice channel to spawn your room!"
            ),
            color=Colors.PRIMARY,
        )
        return embed

    @classmethod
    def build_hub_view(cls) -> ui.View:
        """Constructs buttons for the permanent Master Hub in ROOM-CONTROL."""
        view = ui.View(timeout=None)
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.primary,
                label="CREATE ROOM",
                emoji="➕",
                custom_id="rai_vc_hub:create_public",
                row=0,
            )
        )
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="PRIVATE ROOM",
                emoji="🔒",
                custom_id="rai_vc_hub:create_private",
                row=0,
            )
        )
        return view

    @classmethod
    def build_panel_view(
        cls,
        voice_channel_id: int,
        has_music: bool = False,
        locked: bool = False,
    ) -> ui.View:
        """Builds interactive UI buttons strictly keyed to the target voice_channel_id."""
        view = ui.View(timeout=None)

        # Row 0: Primary Management, Lock/Unlock, Invite, Rename
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Manage Room",
                emoji="⚙️",
                custom_id=f"rai_vc:manage:{voice_channel_id}",
                row=0,
            )
        )
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.primary if locked else discord.ButtonStyle.secondary,
                label="Unlock" if locked else "Lock",
                emoji="🔓" if locked else "🔒",
                custom_id=f"rai_vc:lock_toggle:{voice_channel_id}",
                row=0,
            )
        )
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Invite",
                emoji="👥",
                custom_id=f"rai_vc:invite:{voice_channel_id}",
                row=0,
            )
        )
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Rename",
                emoji="✏️",
                custom_id=f"rai_vc:rename:{voice_channel_id}",
                row=0,
            )
        )

        # Row 1: User Limit, DJ, Co-Host, Delete Room
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="User Limit",
                emoji="👤",
                custom_id=f"rai_vc:limit:{voice_channel_id}",
                row=1,
            )
        )
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="DJ",
                emoji="🎵",
                custom_id=f"rai_vc:dj:{voice_channel_id}",
                row=1,
            )
        )
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Co-Host",
                emoji="🤝",
                custom_id=f"rai_vc:cohost:{voice_channel_id}",
                row=1,
            )
        )
        view.add_item(
            ui.Button(
                style=discord.ButtonStyle.danger,
                label="Delete Room",
                emoji="🗑️",
                custom_id=f"rai_vc:delete:{voice_channel_id}",
                row=1,
            )
        )

        # Row 2: Optional Music Controls if active or requested
        if has_music:
            view.add_item(
                ui.Button(
                    style=discord.ButtonStyle.primary,
                    label="Play",
                    emoji="▶️",
                    custom_id=f"rai_vc:music_play:{voice_channel_id}",
                    row=2,
                )
            )
            view.add_item(
                ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Pause",
                    emoji="⏸️",
                    custom_id=f"rai_vc:music_pause:{voice_channel_id}",
                    row=2,
                )
            )
            view.add_item(
                ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Skip",
                    emoji="⏭️",
                    custom_id=f"rai_vc:music_skip:{voice_channel_id}",
                    row=2,
                )
            )
            view.add_item(
                ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Queue",
                    emoji="📋",
                    custom_id=f"rai_vc:music_queue:{voice_channel_id}",
                    row=2,
                )
            )

        return view

    # =========================================================================
    # PANEL LIFECYCLE
    # =========================================================================

    @classmethod
    async def create_room_panel(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        room: DynamicRoom,
        vc: discord.VoiceChannel,
    ) -> Optional[discord.Message]:
        """Creates and posts the room control panel message into ROOM-CONTROL."""
        try:
            _, _, _, control_channel = await cls.ensure_dynamic_vc_structure(guild)
            embed = cls.build_panel_embed(room, vc, bot)
            view = cls.build_panel_view(room.voice_channel_id, has_music=False, locked=room.locked)

            msg = await control_channel.send(embed=embed, view=view)
            await bot.db.update_dynamic_room(
                room.voice_channel_id,
                control_channel_id=control_channel.id,
                control_message_id=msg.id,
            )
            return msg
        except Exception as e:
            logger.error(f"Failed to post dynamic room control panel for VC {room.voice_channel_id}: {e}")
            return None

    @classmethod
    async def update_room_panel(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        voice_channel_id: int,
    ) -> None:
        """Refreshes the room control panel message in ROOM-CONTROL with current room state."""
        try:
            room = await bot.db.get_dynamic_room(voice_channel_id)
            if not room or not room.control_message_id or not room.control_channel_id:
                return

            channel = guild.get_channel(room.control_channel_id)
            if not isinstance(channel, discord.TextChannel):
                return

            try:
                msg = await channel.fetch_message(room.control_message_id)
            except discord.NotFound:
                return

            vc = guild.get_channel(voice_channel_id)
            vc_obj = vc if isinstance(vc, discord.VoiceChannel) else None

            # Detect music presence in this VC
            has_music = False
            music_cog = bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players") and vc_obj:
                player = music_cog.players.get(guild.id)
                if player and player.voice_client and player.voice_client.channel and player.voice_client.channel.id == vc_obj.id:
                    has_music = True

            embed = cls.build_panel_embed(room, vc_obj, bot)
            view = cls.build_panel_view(room.voice_channel_id, has_music=has_music, locked=room.locked)

            await msg.edit(embed=embed, view=view)
        except Exception as e:
            logger.debug(f"Failed to update room panel {voice_channel_id}: {e}")

    @classmethod
    async def delete_room_panel(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        voice_channel_id: int,
    ) -> None:
        """Deletes the control panel message and cleans up database record."""
        try:
            room = await bot.db.get_dynamic_room(voice_channel_id)
            if room and room.control_channel_id and room.control_message_id:
                channel = guild.get_channel(room.control_channel_id)
                if isinstance(channel, discord.TextChannel):
                    try:
                        msg = await channel.fetch_message(room.control_message_id)
                        await msg.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass

            await bot.db.delete_dynamic_room(voice_channel_id)
        except Exception as e:
            logger.warning(f"Error deleting room panel for VC {voice_channel_id}: {e}")

    # =========================================================================
    # INTERACTION ROUTING & AUTHORIZATION
    # =========================================================================

    @classmethod
    async def _dispatch_hub_action(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
        action: str,
    ) -> bool:
        """Handles button clicks on the permanent Master Hub in ROOM-CONTROL."""
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True, thinking=True)
            except Exception:
                pass

        guild = interaction.guild
        if not guild:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ This button must be used in a server.", ephemeral=True)
            else:
                await interaction.followup.send("❌ This button must be used in a server.", ephemeral=True)
            return True

        member = guild.get_member(interaction.user.id)
        if not member:
            try:
                member = await guild.fetch_member(interaction.user.id)
            except Exception:
                member = interaction.user

        cog = bot.cogs.get("TempVoice")
        if not cog:
            msg = "❌ Dynamic voice system is currently initializing. Please try again in a moment."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return True

        is_private = (action == "create_private")
        try:
            vc = await cog.create_room_for_member(member, is_private=is_private)
            if vc:
                room_type = "Private" if is_private else "Public"
                emb = success_embed(
                    f"🎙️ {room_type} Room Created",
                    f"Your temporary voice room **<#{vc.id}>** has been provisioned!\n\n"
                    f"• Click the room link above to connect.\n"
                    f"• Use the interactive controls posted in this channel to manage your room.",
                )
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=emb, ephemeral=True)
                else:
                    await interaction.followup.send(embed=emb, ephemeral=True)
            else:
                emb = warning_embed(
                    "Room Creation Notice",
                    "Could not create a room at this time. You may already have an active room or be on a brief cooldown.",
                )
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=emb, ephemeral=True)
                else:
                    await interaction.followup.send(embed=emb, ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating dynamic room from hub for {member}: {e}", exc_info=True)
            emb = error_embed("Creation Failed", f"An error occurred while creating your room: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=emb, ephemeral=True)
            else:
                await interaction.followup.send(embed=emb, ephemeral=True)

        return True

    @classmethod
    async def handle_interaction(cls, bot: SentinelBot, interaction: discord.Interaction) -> bool:
        """Central gateway router for all dynamic voice room button & select interactions."""
        cid = interaction.data.get("custom_id", "")
        parts = cid.split(":")

        prefix = parts[0]
        action = parts[1] if len(parts) > 1 else ""

        # 0. MASTER HUB GATEWAY
        if prefix == "rai_vc_hub":
            return await cls._dispatch_hub_action(bot, interaction, action)

        if len(parts) < 3:
            return False

        # 1. KNOCK/WAITING ROOM GATEWAY
        if prefix == "rai_vc_knock":
            return await cls._dispatch_knock_action(bot, interaction, action, parts[2])

        # 2. EMERGENCY ADMIN CONTROLS GATEWAY
        elif prefix == "rai_vc_admin":
            return await cls._dispatch_admin_emergency_action(bot, interaction, action)

        try:
            target_vc_id = int(parts[2])
        except ValueError:
            return False

        # Verify Room in Database
        room = await bot.db.get_dynamic_room(target_vc_id)
        if not room:
            # Self-healing: Delete obsolete control panel message if present
            try:
                if interaction.message and interaction.message.channel:
                    await interaction.message.delete()
            except Exception:
                pass

            # Self-healing: Delete orphaned VC if it exists on Discord and is empty
            if interaction.guild:
                orphan_vc = interaction.guild.get_channel(target_vc_id)
                if isinstance(orphan_vc, discord.VoiceChannel) and len(orphan_vc.members) == 0:
                    try:
                        await orphan_vc.delete(reason="Rai Dynamic VC: Cleaned up orphaned voice channel")
                    except Exception:
                        pass

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=info_embed(
                        "Room Closed & Cleared",
                        "This temporary room is no longer active. Its obsolete panel and channel have been cleaned up.",
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    embed=info_embed(
                        "Room Closed & Cleared",
                        "This temporary room is no longer active. Its obsolete panel and channel have been cleaned up.",
                    ),
                    ephemeral=True,
                )
            return True

        guild = interaction.guild
        if not guild:
            return False

        vc = guild.get_channel(target_vc_id)
        if not isinstance(vc, discord.VoiceChannel):
            await interaction.response.send_message(
                embed=error_embed(
                    "Voice Channel Missing",
                    "The associated temporary voice channel no longer exists on Discord.",
                ),
                ephemeral=True,
            )
            await cls.delete_room_panel(bot, guild, target_vc_id)
            return True

        # STRICT AUTHORIZATION CHECK
        is_owner = interaction.user.id == room.owner_id
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id
        is_cohost = interaction.user.id in (room.co_host_ids or [])
        is_dj = interaction.user.id in (room.dj_ids or [])

        owner_admin_only_actions = {"rename", "privacy", "limit", "customize", "transfer", "delete", "cohost", "dj", "lock_toggle", "manage"}
        cohost_allowed_actions = {"members", "mute", "disconnect", "clear", "invite", "remove", "lock_toggle", "manage"}
        dj_allowed_actions = {"music_play", "music_pause", "music_toggle", "music_skip", "music_queue"}

        if action in owner_admin_only_actions:
            if not (is_owner or is_admin):
                await interaction.response.send_message(
                    embed=error_embed("Unauthorized", "❌ You are not the owner of this room."),
                    ephemeral=True,
                )
                return True
        elif action in cohost_allowed_actions:
            if not (is_owner or is_admin or is_cohost):
                await interaction.response.send_message(
                    embed=error_embed("Unauthorized", "❌ You do not control this room."),
                    ephemeral=True,
                )
                return True
        elif action in dj_allowed_actions:
            if not (is_owner or is_admin or is_cohost or is_dj):
                await interaction.response.send_message(
                    embed=error_embed("Unauthorized", "❌ You must be the room owner, co-host, or DJ to control music."),
                    ephemeral=True,
                )
                return True
        else:
            if not (is_owner or is_admin or is_cohost):
                await interaction.response.send_message(
                    embed=error_embed("Unauthorized", "❌ You are not the owner of this room."),
                    ephemeral=True,
                )
                return True

        # DISPATCH ACTIONS
        if prefix == "rai_vc":
            return await cls._dispatch_main_action(bot, interaction, room, vc, action)
        elif prefix == "rai_vc_priv":
            return await cls._dispatch_privacy_action(bot, interaction, room, vc, action)
        elif prefix == "rai_vc_confirm":
            return await cls._dispatch_confirm_action(bot, interaction, room, vc, action)
        elif prefix == "rai_vc_tpl":
            return await cls._dispatch_template_action(bot, interaction, room, vc, action)

        return False

    @classmethod
    async def _dispatch_hub_action(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
        action: str,
    ) -> bool:
        """Handles permanent Master Hub interactions (Create Room / Private Room)."""
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            return False

        temp_cog = bot.cogs.get("TempVoiceCog")
        if not temp_cog:
            await interaction.response.send_message(
                "❌ Dynamic voice service is currently unavailable.", ephemeral=True
            )
            return True

        is_private = (action == "create_private")
        existing = await bot.db.get_dynamic_room_by_owner(guild.id, member.id)
        if existing and existing.status != "deleted":
            vc = guild.get_channel(existing.voice_channel_id)
            if isinstance(vc, discord.VoiceChannel):
                await interaction.response.send_message(
                    f"⚠️ You already own an active voice room: {vc.mention} (`{vc.name}`).",
                    ephemeral=True,
                )
                return True

        await interaction.response.defer(ephemeral=True)
        try:
            created_vc = await temp_cog.create_room_for_member(member, is_private=is_private)
            if created_vc:
                await interaction.followup.send(
                    f"🎉 Your {'private' if is_private else 'temporary'} voice room {created_vc.mention} has been created!\n"
                    f"Join {created_vc.mention} now.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "❌ Could not create voice room. Please try again or join a trigger voice channel.",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error handling hub room creation: {e}")
            await interaction.followup.send(
                f"❌ Error creating room: {e}", ephemeral=True
            )
        return True

    @classmethod
    async def _dispatch_main_action(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
        room: DynamicRoom,
        vc: discord.VoiceChannel,
        action: str,
    ) -> bool:
        """Executes the specific control panel action requested by the room owner."""
        guild = interaction.guild or vc.guild

        # 0. MANAGE ROOM -> Management Center View
        if action == "manage":
            view = DynamicManageView(vc.id)
            await interaction.response.send_message(
                embed=create_embed(
                    title=f"⚙️ Manage Room — {vc.name}",
                    description=(
                        f"Advanced customization & moderation options for **{vc.name}**:\n\n"
                        f"• 🔐 **Privacy** — Switch between Public, Locked, Invite-Only & Owner-Only\n"
                        f"• 🎨 **Templates** — Apply instant themes (Gaming, Chill, Music, etc.)\n"
                        f"• 👑 **Transfer Owner** — Hand ownership to another occupant\n"
                        f"• 🔇 **Voice Moderation** — Mute or deafen members\n"
                        f"• 🚪 **Disconnect** — Disconnect a member\n"
                        f"• 🧹 **Clear Room** — Disconnect all other members"
                    ),
                    color=Colors.PRIMARY,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 0.1 LOCK TOGGLE -> Direct Lock / Unlock
        elif action == "lock_toggle":
            new_locked = not room.locked
            room.locked = new_locked
            new_mode = "locked" if new_locked else "public"
            room.privacy_mode = new_mode

            if guild:
                try:
                    overwrite = vc.overwrites_for(guild.default_role)
                    overwrite.connect = False if new_locked else None
                    await vc.set_permissions(
                        guild.default_role,
                        overwrite=overwrite,
                        reason=f"Rai Dynamic VC: {'Locked' if new_locked else 'Unlocked'} by {interaction.user}",
                    )
                except Exception as e:
                    logger.warning(f"Failed to update VC permissions for lock_toggle: {e}")

            await bot.db.update_dynamic_room(vc.id, locked=new_locked, privacy_mode=new_mode)
            await bot.db.record_room_event(vc.id, "lock" if new_locked else "unlock", interaction.user.id)
            if guild:
                await cls.update_room_panel(bot, guild, vc.id)

            status_msg = f"🔒 **{vc.name}** is now locked. New members cannot join." if new_locked else f"🔓 **{vc.name}** is now unlocked. Public members can join."
            await interaction.response.send_message(status_msg, ephemeral=True)
            return True

        # 0.2 INVITE -> Instant Friend Selector View
        elif action == "invite":
            view = DynamicInviteView(vc)
            await interaction.response.send_message(
                embed=create_embed(
                    title=f"👥 Invite Friends — {vc.name}",
                    description="Select a member from the server below to grant them instant view & join access:",
                    color=Colors.PRIMARY,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 1. RENAME -> Modal
        elif action == "rename":
            await interaction.response.send_modal(DynamicRenameModal(vc.id, room.owner_id))
            return True

        # 2. USER LIMIT -> Modal
        elif action == "limit":
            await interaction.response.send_modal(DynamicLimitModal(vc.id, room.owner_id))
            return True

        # 3. PRIVACY -> Interactive Selector View
        elif action == "privacy":
            view = DynamicPrivacySelectorView(vc.id, room.privacy_mode)
            await interaction.response.send_message(
                embed=create_embed(
                    title="🔐 Room Privacy Settings",
                    description=(
                        f"Choose the visibility and join permissions for **{vc.name}**:\n\n"
                        f"• 🌐 **Public:** Anyone in the server can view and connect.\n"
                        f"• 🔒 **Locked:** Prevent new joins. Current members stay.\n"
                        f"• 👥 **Invite Only:** Only invited members can view and join.\n"
                        f"• 👑 **Owner Only:** Complete privacy. Only you can enter."
                    ),
                    color=Colors.PRIMARY,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 4. MEMBERS -> Member Management View
        elif action == "members":
            view = DynamicMembersView(vc)
            await interaction.response.send_message(
                embed=create_embed(
                    title=f"👥 Member Management — {vc.name}",
                    description=(
                        f"Manage occupants inside your room:\n"
                        f"Current Members: **{len(vc.members)}**\n\n"
                        f"Select an occupant below to mute, deafen, or disconnect them, "
                        f"or click **Invite Member** to grant a friend access."
                    ),
                    color=Colors.INFO,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 5. CUSTOMIZE / TEMPLATES
        elif action == "customize":
            view = DynamicCustomizeView(vc.id)
            await interaction.response.send_message(
                embed=create_embed(
                    title="🎨 Room Templates & Customization",
                    description=(
                        f"Apply a ready-to-use template to instantly configure **{vc.name}**:\n\n"
                        + "\n".join(
                            f"• **{name}**: {data['label']}"
                            for name, data in BUILTIN_TEMPLATES.items()
                        )
                    ),
                    color=Colors.PRIMARY,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 6. TRANSFER OWNER
        elif action == "transfer":
            view = DynamicTransferSelectView(vc)
            await interaction.response.send_message(
                embed=create_embed(
                    title="👑 Transfer Room Ownership",
                    description=(
                        "Select a member currently in your room to hand over complete ownership.\n\n"
                        "⚠️ **Note:** Once transferred, they will control the room and you will "
                        "relinquish room ownership."
                    ),
                    color=Colors.WARNING,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 7. MUTE / UNMUTE ALL NON-OWNERS
        elif action == "mute":
            view = DynamicMuteSelectView(vc)
            await interaction.response.send_message(
                embed=create_embed(
                    title="🔇 Voice Moderation",
                    description="Select a member currently in your voice room to toggle server mute/deafen:",
                    color=Colors.PRIMARY,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 8. DISCONNECT
        elif action == "disconnect":
            view = DynamicDisconnectSelectView(vc)
            await interaction.response.send_message(
                embed=create_embed(
                    title="🚪 Disconnect Member",
                    description="Select a member currently inside your room to disconnect from the voice channel:",
                    color=Colors.WARNING,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 9. CLEAR ROOM
        elif action == "clear":
            view = DynamicConfirmClearView(vc.id)
            await interaction.response.send_message(
                embed=warning_embed(
                    "Clear Room Confirmation",
                    f"Are you sure you want to disconnect **all other occupants** from **{vc.name}**?",
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 10. DELETE ROOM
        elif action == "delete":
            view = DynamicConfirmDeleteView(vc.id)
            await interaction.response.send_message(
                embed=error_embed(
                    "Delete Room Confirmation",
                    f"Are you sure you want to permanently delete **{vc.name}** and remove its controls?",
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 11. CO-HOST DELEGATION
        elif action == "cohost":
            view = DynamicCoHostView(vc, room)
            cohosts = [f"<@{uid}>" for uid in (room.co_host_ids or [])]
            cohost_str = ", ".join(cohosts) if cohosts else "None assigned"
            await interaction.response.send_message(
                embed=create_embed(
                    title=f"🤝 Manage Room Co-Hosts — {vc.name}",
                    description=(
                        f"**Current Co-Hosts:** {cohost_str}\n\n"
                        f"Co-hosts can manage members, invite friends, mute, and disconnect occupants.\n"
                        f"Select a member below to add or remove them as Co-Host."
                    ),
                    color=Colors.PRIMARY,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 12. DJ DELEGATION
        elif action == "dj":
            view = DynamicDJView(vc, room)
            djs = [f"<@{uid}>" for uid in (room.dj_ids or [])]
            dj_str = ", ".join(djs) if djs else "None assigned"
            await interaction.response.send_message(
                embed=create_embed(
                    title=f"🎧 Manage Room DJs — {vc.name}",
                    description=(
                        f"**Current DJs:** {dj_str}\n\n"
                        f"DJs can play, pause, skip, and manage music in your room.\n"
                        f"Select a member below to add or remove them as Room DJ."
                    ),
                    color=Colors.PRIMARY,
                ),
                view=view,
                ephemeral=True,
            )
            return True

        # 13. MUSIC PLAY / RESUME
        elif action == "music_play":
            music_cog = bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players"):
                player = music_cog.players.get(interaction.guild_id)
                if player and player.voice_client and player.voice_client.channel and player.voice_client.channel.id == vc.id:
                    if getattr(player, "is_paused", False):
                        await player.resume()
                        await interaction.response.send_message("▶️ Resumed music playback.", ephemeral=True)
                        await cls.update_room_panel(bot, interaction.guild, vc.id)
                        return True
            await interaction.response.send_modal(DynamicMusicPlayModal(vc.id))
            return True

        # 14. MUSIC PAUSE
        elif action == "music_pause":
            music_cog = bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players"):
                player = music_cog.players.get(interaction.guild_id)
                if player and player.voice_client and player.voice_client.channel and player.voice_client.channel.id == vc.id:
                    await player.pause()
                    await interaction.response.send_message("⏸️ Paused music playback.", ephemeral=True)
                    await cls.update_room_panel(bot, interaction.guild, vc.id)
                    return True
            await interaction.response.send_message("🎵 No active music session connected to this voice room.", ephemeral=True)
            return True

        # 15. MUSIC TOGGLE (LEGACY)
        elif action == "music_toggle":
            music_cog = bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players"):
                player = music_cog.players.get(interaction.guild_id)
                if player and player.voice_client and player.voice_client.channel and player.voice_client.channel.id == vc.id:
                    if getattr(player, "is_paused", False):
                        await player.resume()
                        await interaction.response.send_message("▶️ Resumed music playback.", ephemeral=True)
                    else:
                        await player.pause()
                        await interaction.response.send_message("⏸️ Paused music playback.", ephemeral=True)
                    await cls.update_room_panel(bot, interaction.guild, vc.id)
                    return True
            await interaction.response.send_message("🎵 No active music session connected to this voice room.", ephemeral=True)
            return True

        elif action == "music_skip":
            music_cog = bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players"):
                player = music_cog.players.get(interaction.guild_id)
                if player and player.voice_client and player.voice_client.channel and player.voice_client.channel.id == vc.id:
                    await player.skip()
                    await interaction.response.send_message("⏭️ Skipped current track.", ephemeral=True)
                    await cls.update_room_panel(bot, interaction.guild, vc.id)
                    return True
            await interaction.response.send_message("🎵 No active music session connected to this voice room.", ephemeral=True)
            return True

        elif action == "music_queue":
            music_cog = bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players"):
                player = music_cog.players.get(interaction.guild_id)
                if player and player.voice_client and player.voice_client.channel and player.voice_client.channel.id == vc.id:
                    queue_list = getattr(player, "queue", [])
                    current = getattr(player, "current", None)
                    curr_str = f"**{getattr(current, 'title', 'Track')}**" if current else "None"
                    lines = [f"🎵 **Now Playing:** {curr_str}\n"]
                    if queue_list:
                        lines.append(f"**Upcoming ({len(queue_list)}):**")
                        for idx, item in enumerate(queue_list[:5], 1):
                            lines.append(f"`{idx}.` {getattr(item, 'title', 'Track')}")
                    else:
                        lines.append("Queue is empty.")
                    await interaction.response.send_message(
                        embed=create_embed(title="📋 Room Music Queue", description="\n".join(lines), color=Colors.PRIMARY),
                        ephemeral=True,
                    )
                    return True
            await interaction.response.send_message("🎵 No active music session connected to this voice room.", ephemeral=True)
            return True

        return False

    @classmethod
    async def _dispatch_privacy_action(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
        room: DynamicRoom,
        vc: discord.VoiceChannel,
        mode: str,
    ) -> bool:
        """Applies real Discord permission overwrites for privacy modes."""
        guild = interaction.guild
        owner = guild.get_member(room.owner_id) if guild else None

        try:
            if mode == "public":
                # Everyone can view and connect
                await vc.set_permissions(guild.default_role, view_channel=True, connect=True)
                await bot.db.update_dynamic_room(vc.id, privacy_mode="public", locked=0)
                resp = "🌐 **Room is now Public.** Anyone in the server can view and join."

            elif mode == "locked":
                # Everyone can view, but cannot connect. Existing members remain.
                await vc.set_permissions(guild.default_role, connect=False)
                await bot.db.update_dynamic_room(vc.id, privacy_mode="locked", locked=1)
                resp = "🔒 **Room is now Locked.** New members cannot connect. Existing occupants remain."

            elif mode == "invite":
                # Everyone cannot view or connect. Explicit members can.
                await vc.set_permissions(guild.default_role, view_channel=False, connect=False)
                if owner:
                    await vc.set_permissions(owner, view_channel=True, connect=True)
                # Re-apply explicit room members
                members = await bot.db.get_room_members(vc.id)
                for m in members:
                    member_obj = guild.get_member(m.user_id)
                    if member_obj and m.permission_type == "invited":
                        await vc.set_permissions(member_obj, view_channel=True, connect=True)
                await bot.db.update_dynamic_room(vc.id, privacy_mode="invite_only", locked=1)
                resp = "👥 **Room is now Invite Only.** Only you and explicitly invited members can see and join."

            elif mode == "owner":
                # Only owner can view or connect
                await vc.set_permissions(guild.default_role, view_channel=False, connect=False)
                if owner:
                    await vc.set_permissions(owner, view_channel=True, connect=True)
                # Deny any other role/member overwrites
                await bot.db.update_dynamic_room(vc.id, privacy_mode="owner_only", locked=1)
                resp = "👑 **Room is now Owner Only.** Strictly hidden from all server members."
            else:
                resp = "Invalid privacy mode."

            await interaction.response.send_message(embed=success_embed("Privacy Updated", resp), ephemeral=True)
            await cls.update_room_panel(bot, guild, vc.id)
            OwnerReporter.send_room_report(
                bot,
                guild.id,
                event="Room Privacy Changed",
                user=interaction.user,
                action_taken=f"Set privacy mode to **{mode.upper()}** on #{vc.name}",
                details={"Voice Channel ID": f"`{vc.id}`", "New Mode": f"`{mode}`"},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update room privacy: {e}")
            await interaction.response.send_message(
                embed=error_embed("Permission Error", f"Failed to apply privacy permissions: {e}"),
                ephemeral=True,
            )
            return True

    @classmethod
    async def _dispatch_confirm_action(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
        room: DynamicRoom,
        vc: discord.VoiceChannel,
        confirm_type: str,
    ) -> bool:
        """Executes confirmed dangerous room actions (clear or delete)."""
        guild = interaction.guild

        if confirm_type == "clear":
            count = 0
            for member in list(vc.members):
                if member.id != room.owner_id and not member.bot:
                    try:
                        await member.move_to(None, reason="Rai Dynamic VC: Owner cleared room")
                        count += 1
                    except Exception:
                        pass
            await interaction.response.send_message(
                embed=success_embed("Room Cleared", f"🧹 Disconnected **{count}** occupants from your room."),
                ephemeral=True,
            )
            await cls.update_room_panel(bot, guild, vc.id)
            return True

        elif confirm_type == "delete":
            await interaction.response.send_message(
                embed=success_embed("Room Deleting", "🗑️ Deleting temporary voice room and cleaning up controls..."),
                ephemeral=True,
            )
            try:
                await vc.delete(reason=f"Rai Dynamic VC: Deleted by owner {interaction.user}")
            except Exception as e:
                logger.warning(f"Could not delete VC {vc.id}: {e}")

            await cls.delete_room_panel(bot, guild, vc.id)
            OwnerReporter.send_room_report(
                bot,
                guild.id,
                event="Dynamic Voice Room Deleted",
                user=interaction.user,
                action_taken=f"Owner deleted temporary room **#{vc.name}**",
                details={"Voice Channel ID": f"`{vc.id}`"},
            )
            return True

        return False

    @classmethod
    async def _dispatch_template_action(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
        room: DynamicRoom,
        vc: discord.VoiceChannel,
        template_name: str,
    ) -> bool:
        """Applies a built-in room template to the target VC."""
        tpl = BUILTIN_TEMPLATES.get(template_name)
        if not tpl:
            await interaction.response.send_message(
                embed=error_embed("Template Error", "Selected template was not found."),
                ephemeral=True,
            )
            return True

        guild = interaction.guild
        owner = guild.get_member(room.owner_id) if guild else None
        clean_name = f"{tpl['prefix']}{interaction.user.display_name}'s Room"[:32]
        limit = tpl["user_limit"]
        mode = tpl["privacy"]

        try:
            # Edit Discord VC
            await vc.edit(name=clean_name, user_limit=limit)

            # Apply Privacy
            if mode == "public":
                await vc.set_permissions(guild.default_role, view_channel=True, connect=True)
            elif mode == "invite_only":
                await vc.set_permissions(guild.default_role, view_channel=False, connect=False)
                if owner:
                    await vc.set_permissions(owner, view_channel=True, connect=True)
            elif mode == "owner_only":
                await vc.set_permissions(guild.default_role, view_channel=False, connect=False)
                if owner:
                    await vc.set_permissions(owner, view_channel=True, connect=True)

            # Update DB
            await bot.db.update_dynamic_room(
                vc.id,
                user_limit=limit,
                privacy_mode=mode,
                template_id=template_name,
            )
            await cls.update_room_panel(bot, guild, vc.id)

            await interaction.response.send_message(
                embed=success_embed(
                    "Template Applied",
                    f"🎨 Configured room with **{template_name}** template:\n"
                    f"• **Name:** {clean_name}\n"
                    f"• **Capacity:** `{limit or 'Unlimited'}`\n"
                    f"• **Privacy:** `{mode.upper()}`",
                ),
                ephemeral=True,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to apply template: {e}")
            await interaction.response.send_message(
                embed=error_embed("Error", f"Failed to apply template: {e}"),
                ephemeral=True,
            )
            return True

    @classmethod
    async def _dispatch_knock_action(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
        action: str,
        param: str,
    ) -> bool:
        """Handles knock/waiting room requests and approvals."""
        guild = interaction.guild
        if not guild:
            return False

        if action == "request":
            try:
                target_vc_id = int(param)
            except ValueError:
                return False
            room = await bot.db.get_dynamic_room(target_vc_id)
            if not room:
                await interaction.response.send_message("❌ Room does not exist or has been deleted.", ephemeral=True)
                return True
            vc = guild.get_channel(target_vc_id)
            if not isinstance(vc, discord.VoiceChannel):
                await interaction.response.send_message("❌ Room voice channel no longer exists.", ephemeral=True)
                return True

            if interaction.user.id == room.owner_id or (getattr(interaction.user, "voice", None) and interaction.user.voice.channel == vc):
                await interaction.response.send_message("You already have access to this room.", ephemeral=True)
                return True

            existing = await bot.db.get_pending_knock_request(room.voice_channel_id, interaction.user.id)
            if existing:
                await interaction.response.send_message(
                    "⏳ You already have a pending access request for this room. Please wait for the owner to respond.",
                    ephemeral=True,
                )
                return True

            req = await bot.db.create_room_knock_request(room.voice_channel_id, interaction.user.id, expires_in_seconds=120)

            owner = guild.get_member(room.owner_id)
            if owner:
                req_embed = create_embed(
                    title="🚪 ROOM ACCESS REQUEST",
                    description=(
                        f"👤 **User:** {interaction.user.mention} (`{interaction.user}`)\n"
                        f"🔐 **Room:** **{vc.name}**\n"
                        f"⏱️ **Expires:** in 2 minutes\n\n"
                        f"Would you like to grant this user access to your room?"
                    ),
                    color=Colors.PRIMARY,
                )
                view = DynamicKnockRequestView(req.id)
                try:
                    await owner.send(embed=req_embed, view=view)
                except Exception:
                    try:
                        _, _, _, ctrl_ch = await cls.ensure_dynamic_vc_structure(guild)
                        if ctrl_ch:
                            await ctrl_ch.send(
                                content=f"{owner.mention} Access request for your room **{vc.name}**:",
                                embed=req_embed,
                                view=view,
                            )
                    except Exception:
                        pass

            await interaction.response.send_message(
                embed=success_embed(
                    "Request Sent",
                    f"🔔 Your access request for **{vc.name}** has been sent to the room owner. You'll be notified when they respond.",
                ),
                ephemeral=True,
            )
            return True

        elif action in ("allow", "decline"):
            try:
                request_id = int(param)
            except ValueError:
                return False

            req = await bot.db.get_room_knock_request(request_id)
            if not req or req.status != "pending":
                await interaction.response.send_message(
                    embed=error_embed("Handled", "This access request has already been processed or does not exist."),
                    ephemeral=True,
                )
                return True

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if req.expires_at <= now_iso:
                await bot.db.update_room_knock_request_status(req.id, "expired")
                await interaction.response.send_message(
                    embed=error_embed("Expired", "This access request has expired."),
                    ephemeral=True,
                )
                return True

            room = await bot.db.get_dynamic_room(req.room_id)
            if not room:
                await interaction.response.send_message(
                    embed=error_embed("Missing Room", "The dynamic room no longer exists."),
                    ephemeral=True,
                )
                return True

            is_owner = interaction.user.id == room.owner_id
            is_cohost = interaction.user.id in (room.co_host_ids or [])
            is_admin = False
            if isinstance(interaction.user, discord.Member):
                is_admin = interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id

            if not (is_owner or is_cohost or is_admin):
                await interaction.response.send_message(
                    embed=error_embed("Unauthorized", "❌ Only the room owner or co-hosts can respond to access requests."),
                    ephemeral=True,
                )
                return True

            target_member = guild.get_member(req.user_id)
            vc = guild.get_channel(room.voice_channel_id)

            if action == "allow":
                await bot.db.update_room_knock_request_status(req.id, "allowed")
                await bot.db.add_room_member(room.voice_channel_id, req.user_id, "invited")
                if isinstance(vc, discord.VoiceChannel) and target_member:
                    try:
                        await vc.set_permissions(target_member, view_channel=True, connect=True)
                    except Exception as e:
                        logger.warning(f"Failed to set knock permissions: {e}")

                    if target_member.voice and target_member.voice.channel:
                        try:
                            await target_member.move_to(vc, reason=f"Rai Dynamic VC: Access approved by {interaction.user}")
                        except Exception:
                            pass

                    try:
                        await target_member.send(
                            f"✅ Your access request to join **{vc.name}** was approved by {interaction.user.display_name}!"
                        )
                    except Exception:
                        pass

                await bot.db.record_room_event(room.voice_channel_id, "knock_allowed", req.user_id)
                await cls.update_room_panel(bot, guild, room.voice_channel_id)
                try:
                    await interaction.response.edit_message(
                        embed=success_embed(
                            "Access Granted",
                            f"✅ Allowed {target_member.mention if target_member else f'<@{req.user_id}>'} into the room.",
                        ),
                        view=None,
                    )
                except Exception:
                    await interaction.response.send_message("✅ Access granted.", ephemeral=True)
                return True

            elif action == "decline":
                await bot.db.update_room_knock_request_status(req.id, "declined")
                if target_member and isinstance(vc, discord.VoiceChannel):
                    try:
                        await target_member.send(f"❌ Your access request to join **{vc.name}** was declined.")
                    except Exception:
                        pass
                await bot.db.record_room_event(room.voice_channel_id, "knock_declined", req.user_id)
                try:
                    await interaction.response.edit_message(
                        embed=warning_embed(
                            "Access Declined",
                            f"❌ Declined access request from {target_member.mention if target_member else f'<@{req.user_id}>'}.",
                        ),
                        view=None,
                    )
                except Exception:
                    await interaction.response.send_message("❌ Access request declined.", ephemeral=True)
                return True

        return False

    @classmethod
    async def _dispatch_admin_emergency_action(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
        action: str,
    ) -> bool:
        """Handles emergency administrative master controls."""
        guild = interaction.guild
        if not guild:
            return False

        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id
        if not is_admin:
            await interaction.response.send_message(
                embed=error_embed("Unauthorized", "❌ You must be a server administrator to use emergency controls."),
                ephemeral=True,
            )
            return True

        rooms = await bot.db.get_all_dynamic_rooms(guild.id)

        if action == "lock_all":
            count = 0
            for r in rooms:
                vc = guild.get_channel(r.voice_channel_id)
                if isinstance(vc, discord.VoiceChannel):
                    try:
                        await vc.set_permissions(guild.default_role, connect=False)
                        await bot.db.update_dynamic_room(vc.id, locked=1, privacy_mode="locked")
                        await cls.update_room_panel(bot, guild, vc.id)
                        count += 1
                    except Exception:
                        pass
            await interaction.response.send_message(
                embed=warning_embed("Emergency Lockdown", f"🔒 Locked **{count}** dynamic voice rooms across the server."),
                ephemeral=True,
            )
            return True

        elif action == "stop_music":
            vc_client = guild.voice_client
            if vc_client and vc_client.is_connected():
                try:
                    await vc_client.disconnect(force=True)
                except Exception:
                    pass
            music_cog = bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players") and guild.id in music_cog.players:
                p = music_cog.players[guild.id]
                p.queue.clear()
                p.current = None
            await interaction.response.send_message(
                embed=success_embed("Music Halted", "🛑 Disconnected bot music streams and cleared audio queues."),
                ephemeral=True,
            )
            return True

        elif action == "cleanup_empty":
            purged = 0
            for r in rooms:
                vc = guild.get_channel(r.voice_channel_id)
                if not isinstance(vc, discord.VoiceChannel):
                    await cls.delete_room_panel(bot, guild, r.voice_channel_id)
                    purged += 1
                elif len(vc.members) == 0:
                    try:
                        await vc.delete(reason="Rai Dynamic VC: Admin emergency empty cleanup")
                    except Exception:
                        pass
                    await cls.delete_room_panel(bot, guild, r.voice_channel_id)
                    purged += 1
            await interaction.response.send_message(
                embed=success_embed("Cleanup Complete", f"🧹 Purged **{purged}** empty dynamic rooms and stale panels."),
                ephemeral=True,
            )
            return True

        elif action == "rebuild_perms":
            rebuilt = 0
            for r in rooms:
                vc = guild.get_channel(r.voice_channel_id)
                if isinstance(vc, discord.VoiceChannel):
                    owner = guild.get_member(r.owner_id)
                    try:
                        if r.privacy_mode in ("invite_only", "owner_only"):
                            await vc.set_permissions(guild.default_role, view_channel=False, connect=False)
                        elif r.privacy_mode == "locked":
                            await vc.set_permissions(guild.default_role, view_channel=True, connect=False)
                        else:
                            await vc.set_permissions(guild.default_role, view_channel=True, connect=True)

                        if owner:
                            await vc.set_permissions(owner, view_channel=True, connect=True, manage_channels=True, move_members=True, mute_members=True)

                        for co_id in (r.co_host_ids or []):
                            co = guild.get_member(co_id)
                            if co:
                                await vc.set_permissions(co, view_channel=True, connect=True, move_members=True, mute_members=True)

                        rebuilt += 1
                    except Exception:
                        pass
            await interaction.response.send_message(
                embed=success_embed("Permissions Reconciled", f"🔄 Reconciled permissions for **{rebuilt}** rooms against database state."),
                ephemeral=True,
            )
            return True

        elif action == "health":
            active_rooms = len([r for r in rooms if r.status == "active"])
            empty_rooms = len([r for r in rooms if r.status == "empty_countdown"])
            embed = create_embed(
                title="❤️ Dynamic Voice Subsystem Health",
                description=(
                    f"• **Active Voice Rooms:** `{active_rooms}`\n"
                    f"• **Pending Cleanup Grace:** `{empty_rooms}`\n"
                    f"• **Total DB Records:** `{len(rooms)}`\n"
                    f"• **Database Engine:** `SQLite WAL (Connected)`\n"
                    f"• **Status:** 🟢 Operational"
                ),
                color=Colors.SUCCESS,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return True

        elif action == "status":
            lines = []
            for r in rooms[:15]:
                vc = guild.get_channel(r.voice_channel_id)
                name = vc.name if vc else f"Room #{r.voice_channel_id}"
                members = len(vc.members) if vc else 0
                lines.append(f"• **{name}** | <@{r.owner_id}> | `{members} users` | `{r.privacy_mode}`")
            desc = "\n".join(lines) if lines else "No active dynamic voice rooms."
            embed = create_embed(
                title="📋 Dynamic Voice Rooms Inventory",
                description=desc,
                color=Colors.INFO,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return True

        return False


# =============================================================================
# MODALS & SELECTOR VIEWS
# =============================================================================

class DynamicRenameModal(ui.Modal):
    """Modal allowing the room owner to specify a new channel name."""

    def __init__(self, voice_channel_id: int, owner_id: int):
        super().__init__(title="Rename Your Room")
        self.voice_channel_id = voice_channel_id
        self.owner_id = owner_id

        self.room_name = ui.TextInput(
            label="New Room Name",
            placeholder="e.g. Rai's Squad Sanctum",
            min_length=1,
            max_length=32,
            required=True,
        )
        self.add_item(self.room_name)

    async def on_submit(self, interaction: discord.Interaction):
        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        vc = guild.get_channel(self.voice_channel_id) if guild else None

        if not isinstance(vc, discord.VoiceChannel):
            await interaction.response.send_message(
                embed=error_embed("Error", "Target voice room no longer exists."),
                ephemeral=True,
            )
            return

        new_name = self.room_name.value.strip()
        # Keep emoji prefix if not provided
        if not any(new_name.startswith(p) for p in ["🎙️", "🔊", "🔐", "🎮", "🌙", "🎵", "🎨", "🎬"]):
            new_name = f"🎙️・{new_name}"

        new_name = new_name[:32]
        try:
            await vc.edit(name=new_name, reason=f"Rai Dynamic VC: Renamed by owner {interaction.user}")
            await bot.db.record_room_event(vc.id, "rename", interaction.user.id, metadata=f'{{"name": "{new_name}"}}')
            await DynamicVCControlManager.update_room_panel(bot, guild, vc.id)

            await interaction.response.send_message(
                embed=success_embed("Room Renamed", f"✏️ Channel renamed to **{new_name}**."),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed("Rename Failed", f"Could not rename channel: {e}"),
                ephemeral=True,
            )


class DynamicLimitModal(ui.Modal):
    """Modal allowing the room owner to set numerical user limits."""

    def __init__(self, voice_channel_id: int, owner_id: int):
        super().__init__(title="Configure User Limit")
        self.voice_channel_id = voice_channel_id
        self.owner_id = owner_id

        self.limit_val = ui.TextInput(
            label="Maximum Users (0 for Unlimited)",
            placeholder="Enter a number between 0 and 99",
            min_length=1,
            max_length=2,
            required=True,
        )
        self.add_item(self.limit_val)

    async def on_submit(self, interaction: discord.Interaction):
        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        vc = guild.get_channel(self.voice_channel_id) if guild else None

        if not isinstance(vc, discord.VoiceChannel):
            await interaction.response.send_message(
                embed=error_embed("Error", "Target voice room no longer exists."),
                ephemeral=True,
            )
            return

        try:
            limit = int(self.limit_val.value.strip())
            if limit < 0 or limit > 99:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Invalid Limit", "Please provide a valid number between 0 and 99."),
                ephemeral=True,
            )
            return

        try:
            await vc.edit(user_limit=limit, reason=f"Rai Dynamic VC: Limit updated by owner {interaction.user}")
            await bot.db.update_dynamic_room(vc.id, user_limit=limit)
            await DynamicVCControlManager.update_room_panel(bot, guild, vc.id)

            await interaction.response.send_message(
                embed=success_embed("Capacity Updated", f"🔢 User limit set to **{limit or 'Unlimited'}**."),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed("Update Failed", f"Could not set capacity limit: {e}"),
                ephemeral=True,
            )


class DynamicPrivacySelectorView(ui.View):
    """Ephemeral view allowing instant selection of room privacy mode."""

    def __init__(self, voice_channel_id: int, current_mode: str):
        super().__init__(timeout=60)
        self.voice_channel_id = voice_channel_id

        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.success if current_mode == "public" else discord.ButtonStyle.secondary,
                label="Public",
                emoji="🌐",
                custom_id=f"rai_vc_priv:public:{voice_channel_id}",
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.primary if current_mode == "locked" else discord.ButtonStyle.secondary,
                label="Locked",
                emoji="🔒",
                custom_id=f"rai_vc_priv:locked:{voice_channel_id}",
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.primary if current_mode == "invite_only" else discord.ButtonStyle.secondary,
                label="Invite Only",
                emoji="👥",
                custom_id=f"rai_vc_priv:invite:{voice_channel_id}",
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.danger if current_mode == "owner_only" else discord.ButtonStyle.secondary,
                label="Owner Only",
                emoji="👑",
                custom_id=f"rai_vc_priv:owner:{voice_channel_id}",
            )
        )


class DynamicCustomizeView(ui.View):
    """Ephemeral view displaying quick built-in templates."""

    def __init__(self, voice_channel_id: int):
        super().__init__(timeout=60)
        self.voice_channel_id = voice_channel_id

        for name, data in BUILTIN_TEMPLATES.items():
            self.add_item(
                ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=name,
                    emoji=data["prefix"].replace("・", ""),
                    custom_id=f"rai_vc_tpl:{name}:{voice_channel_id}",
                )
            )


class DynamicMembersView(ui.View):
    """View to manage members currently inside the VC or invite new ones."""

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__(timeout=120)
        self.vc = vc

        # User selector to invite someone new
        user_select = ui.UserSelect(
            placeholder="Select a friend to invite to this room...",
            min_values=1,
            max_values=1,
            custom_id=f"rai_vc_member_invite:{vc.id}",
        )
        user_select.callback = self._invite_callback
        self.add_item(user_select)

    async def _invite_callback(self, interaction: discord.Interaction):
        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        selected_user = interaction.data["values"][0]  # type: ignore
        member = guild.get_member(int(selected_user)) if guild else None

        if not member:
            await interaction.response.send_message("❌ Member not found in server.", ephemeral=True)
            return

        try:
            # Grant View and Connect permissions
            await self.vc.set_permissions(member, view_channel=True, connect=True)
            await bot.db.add_room_member(self.vc.id, member.id, permission_type="invited")
            await interaction.response.send_message(
                embed=success_embed(
                    "Member Invited",
                    f"👥 Granted access to {member.mention}. They can now view and join **{self.vc.name}**.",
                ),
                ephemeral=True,
            )
            OwnerReporter.send_room_report(
                bot,
                guild.id,
                event="Room Member Invited",
                user=interaction.user,
                action_taken=f"Granted voice room access to **{member.display_name}**",
                details={"Voice Channel": f"`{self.vc.name}`", "Invited User ID": f"`{member.id}`"},
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to invite member: {e}", ephemeral=True)


class DynamicInviteView(ui.View):
    """View to select a friend and grant instant access to a private or locked room."""

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__(timeout=120)
        self.vc = vc

        user_select = ui.UserSelect(
            placeholder="Select a friend to invite to this room...",
            min_values=1,
            max_values=1,
            custom_id=f"rai_vc_invite_sel:{vc.id}",
        )
        user_select.callback = self._invite_callback
        self.add_item(user_select)

    async def _invite_callback(self, interaction: discord.Interaction):
        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        selected_user = interaction.data["values"][0]  # type: ignore
        member = guild.get_member(int(selected_user)) if guild else None

        if not member:
            await interaction.response.send_message("❌ Member not found in server.", ephemeral=True)
            return

        try:
            await self.vc.set_permissions(member, view_channel=True, connect=True)
            await bot.db.add_room_member(self.vc.id, member.id, permission_type="invited")
            await interaction.response.send_message(
                embed=success_embed(
                    "Member Invited",
                    f"👥 Granted access to {member.mention}. They can now view and join **{self.vc.name}**.",
                ),
                ephemeral=True,
            )
            OwnerReporter.send_room_report(
                bot,
                guild.id if guild else 0,
                event="Room Member Invited",
                user=interaction.user,
                action_taken=f"Granted voice room access to **{member.display_name}**",
                details={"Voice Channel": f"`{self.vc.name}`", "Invited User ID": f"`{member.id}`"},
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to invite member: {e}", ephemeral=True)


class DynamicManageView(ui.View):
    """Ephemeral room management center for advanced customization & moderation."""

    def __init__(self, voice_channel_id: int):
        super().__init__(timeout=120)
        self.voice_channel_id = voice_channel_id

        # Row 0: Privacy, Templates, Transfer
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Privacy",
                emoji="🔐",
                custom_id=f"rai_vc:privacy:{voice_channel_id}",
                row=0,
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Templates",
                emoji="🎨",
                custom_id=f"rai_vc:customize:{voice_channel_id}",
                row=0,
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Transfer Owner",
                emoji="👑",
                custom_id=f"rai_vc:transfer:{voice_channel_id}",
                row=0,
            )
        )

        # Row 1: Moderation
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Voice Moderation",
                emoji="🔇",
                custom_id=f"rai_vc:mute:{voice_channel_id}",
                row=1,
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Disconnect",
                emoji="🚪",
                custom_id=f"rai_vc:disconnect:{voice_channel_id}",
                row=1,
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Clear Room",
                emoji="🧹",
                custom_id=f"rai_vc:clear:{voice_channel_id}",
                row=1,
            )
        )


class DynamicTransferSelectView(ui.View):
    """View to select a member inside the VC to transfer ownership to."""

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.vc = vc

        members = [m for m in vc.members if not m.bot]
        if members:
            options = [
                discord.SelectOption(label=m.display_name, value=str(m.id), emoji="👤")
                for m in members[:25]
            ]
            select = ui.Select(placeholder="Select new room owner...", options=options)
            select.callback = self._select_callback
            self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        target_id = int(interaction.data["values"][0])  # type: ignore
        new_owner = guild.get_member(target_id) if guild else None

        if not new_owner:
            await interaction.response.send_message("❌ Selected member not found.", ephemeral=True)
            return

        # Hand over ownership in DB
        await bot.db.update_dynamic_room(self.vc.id, owner_id=new_owner.id)

        # Grant owner Discord permissions
        await self.vc.set_permissions(new_owner, manage_channels=True, move_members=True, mute_members=True)
        # Demote old owner to standard
        await self.vc.set_permissions(interaction.user, manage_channels=None, move_members=None, mute_members=None)

        await DynamicVCControlManager.update_room_panel(bot, guild, self.vc.id)

        await interaction.response.send_message(
            embed=success_embed(
                "Ownership Transferred",
                f"👑 Transferred room ownership to {new_owner.mention}. They now control **{self.vc.name}**.",
            ),
            ephemeral=True,
        )
        OwnerReporter.send_room_report(
            bot,
            guild.id,
            event="Room Ownership Transferred",
            user=interaction.user,
            action_taken=f"Transferred room ownership to **{new_owner.display_name}**",
            details={"Voice Channel": f"`{self.vc.name}`", "New Owner ID": f"`{new_owner.id}`"},
        )


class DynamicMuteSelectView(ui.View):
    """Select member to toggle mute/deafen."""

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.vc = vc

        members = [m for m in vc.members if not m.bot]
        if members:
            options = [
                discord.SelectOption(
                    label=m.display_name,
                    value=str(m.id),
                    description="Muted" if m.voice and m.voice.mute else "Unmuted",
                    emoji="🔇" if m.voice and m.voice.mute else "🔊",
                )
                for m in members[:25]
            ]
            select = ui.Select(placeholder="Select member to mute/unmute...", options=options)
            select.callback = self._select_callback
            self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        target_id = int(interaction.data["values"][0])  # type: ignore
        target = guild.get_member(target_id) if guild else None

        if not target or not target.voice:
            await interaction.response.send_message("❌ Member is no longer in this voice room.", ephemeral=True)
            return

        is_muted = target.voice.mute
        try:
            await target.edit(mute=not is_muted, reason=f"Rai Dynamic VC: Mute toggled by owner {interaction.user}")
            status_str = "unmuted" if is_muted else "muted"
            await interaction.response.send_message(
                embed=success_embed("Member Moderated", f"🔇 Successfully {status_str} {target.mention}."),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed("Error", f"Failed to mute member (Missing permissions): {e}"),
                ephemeral=True,
            )


class DynamicDisconnectSelectView(ui.View):
    """Select member to disconnect from the voice channel."""

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.vc = vc

        members = [m for m in vc.members if not m.bot]
        if members:
            options = [
                discord.SelectOption(label=m.display_name, value=str(m.id), emoji="🚪")
                for m in members[:25]
            ]
            select = ui.Select(placeholder="Select member to disconnect...", options=options)
            select.callback = self._select_callback
            self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        target_id = int(interaction.data["values"][0])  # type: ignore
        target = guild.get_member(target_id) if guild else None

        if not target or not target.voice or target.voice.channel != self.vc:
            await interaction.response.send_message("❌ Member is no longer in this voice room.", ephemeral=True)
            return

        try:
            await target.move_to(None, reason=f"Rai Dynamic VC: Disconnected by owner {interaction.user}")
            await interaction.response.send_message(
                embed=success_embed("Member Disconnected", f"🚪 Disconnected {target.mention} from your room."),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed("Error", f"Failed to disconnect member: {e}"),
                ephemeral=True,
            )


class DynamicConfirmClearView(ui.View):
    """Confirmation buttons for clearing all other members from the room."""

    def __init__(self, voice_channel_id: int):
        super().__init__(timeout=30)
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.danger,
                label="Confirm Clear Room",
                emoji="🧹",
                custom_id=f"rai_vc_confirm:clear:{voice_channel_id}",
            )
        )


class DynamicConfirmDeleteView(ui.View):
    """Confirmation buttons for permanently deleting the room."""

    def __init__(self, voice_channel_id: int):
        super().__init__(timeout=30)
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.danger,
                label="Confirm Delete Room",
                emoji="🗑️",
                custom_id=f"rai_vc_confirm:delete:{voice_channel_id}",
            )
        )


class DynamicCoHostView(ui.View):
    """Select member to toggle room co-host status."""

    def __init__(self, vc: discord.VoiceChannel, room: DynamicRoom):
        super().__init__(timeout=60)
        self.vc = vc
        self.room = room

        members = [m for m in vc.guild.members if not m.bot and m.id != room.owner_id]
        if not members:
            members = [m for m in vc.members if not m.bot and m.id != room.owner_id]

        if members:
            options = []
            for m in members[:25]:
                is_co = m.id in (room.co_host_ids or [])
                options.append(
                    discord.SelectOption(
                        label=m.display_name,
                        value=str(m.id),
                        description="Co-Host (Click to revoke)" if is_co else "Member (Click to promote)",
                        emoji="🤝" if is_co else "👤",
                    )
                )
            select = ui.Select(placeholder="Select member to add/remove Co-Host...", options=options)
            select.callback = self._select_callback
            self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        target_id = int(interaction.data["values"][0])  # type: ignore
        target = guild.get_member(target_id) if guild else None

        current_cohosts = list(self.room.co_host_ids or [])
        if target_id in current_cohosts:
            current_cohosts.remove(target_id)
            msg = f"🤝 Removed {target.mention if target else f'<@{target_id}>'} from Co-Hosts."
            if target:
                try:
                    await self.vc.set_permissions(target, mute_members=None, move_members=None)
                except Exception:
                    pass
        else:
            current_cohosts.append(target_id)
            msg = f"🤝 Granted Co-Host privileges to {target.mention if target else f'<@{target_id}>'}!"
            if target:
                try:
                    await self.vc.set_permissions(target, view_channel=True, connect=True, mute_members=True, move_members=True)
                except Exception:
                    pass

        self.room.co_host_ids = current_cohosts
        await bot.db.update_dynamic_room(self.vc.id, co_host_ids=current_cohosts)
        await bot.db.record_room_event(self.vc.id, "cohost_toggled", target_id)
        await DynamicVCControlManager.update_room_panel(bot, guild, self.vc.id)

        await interaction.response.send_message(
            embed=success_embed("Co-Host Delegation Updated", msg),
            ephemeral=True,
        )


class DynamicDJView(ui.View):
    """Select member to toggle room DJ status."""

    def __init__(self, vc: discord.VoiceChannel, room: DynamicRoom):
        super().__init__(timeout=60)
        self.vc = vc
        self.room = room

        members = [m for m in vc.guild.members if not m.bot and m.id != room.owner_id]
        if not members:
            members = [m for m in vc.members if not m.bot and m.id != room.owner_id]

        if members:
            options = []
            for m in members[:25]:
                is_dj = m.id in (room.dj_ids or [])
                options.append(
                    discord.SelectOption(
                        label=m.display_name,
                        value=str(m.id),
                        description="Room DJ (Click to revoke)" if is_dj else "Listener (Click to promote)",
                        emoji="🎧" if is_dj else "🎵",
                    )
                )
            select = ui.Select(placeholder="Select member to add/remove Room DJ...", options=options)
            select.callback = self._select_callback
            self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        target_id = int(interaction.data["values"][0])  # type: ignore
        target = guild.get_member(target_id) if guild else None

        current_djs = list(self.room.dj_ids or [])
        if target_id in current_djs:
            current_djs.remove(target_id)
            msg = f"🎧 Removed {target.mention if target else f'<@{target_id}>'} from Room DJs."
        else:
            current_djs.append(target_id)
            msg = f"🎧 Granted Room DJ privileges to {target.mention if target else f'<@{target_id}>'}!"

        self.room.dj_ids = current_djs
        await bot.db.update_dynamic_room(self.vc.id, dj_ids=current_djs)
        await bot.db.record_room_event(self.vc.id, "dj_toggled", target_id)
        await DynamicVCControlManager.update_room_panel(bot, guild, self.vc.id)

        await interaction.response.send_message(
            embed=success_embed("Room DJ Updated", msg),
            ephemeral=True,
        )


class DynamicMusicPlayModal(ui.Modal):
    """Modal allowing the room owner or DJ to search and stream music."""

    def __init__(self, voice_channel_id: int):
        super().__init__(title="Stream Music in Your Room")
        self.voice_channel_id = voice_channel_id

        self.query_input = ui.TextInput(
            label="Song Title, Artist, or URL",
            placeholder="e.g. Lofi hip hop or YouTube URL",
            min_length=1,
            max_length=200,
            required=True,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        vc = guild.get_channel(self.voice_channel_id) if guild else None

        if not isinstance(vc, discord.VoiceChannel):
            await interaction.response.send_message("❌ Target voice room no longer exists.", ephemeral=True)
            return

        music_cog = bot.cogs.get("Music")
        if not music_cog:
            await interaction.response.send_message(
                "🎵 Music is powered by the independent **Rai Music Bot**. Join your voice room and use `/music play` or `/play`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        voice_client = guild.voice_client
        if not voice_client:
            try:
                voice_client = await vc.connect()
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to connect to room voice: {e}", ephemeral=True)
                return
        elif voice_client.channel != vc:
            try:
                await voice_client.move_to(vc)
            except Exception as e:
                await interaction.followup.send(f"❌ Could not move bot to room: {e}", ephemeral=True)
                return

        query = self.query_input.value.strip()
        from cogs.music import Song
        song = await Song.create(query, interaction.user)
        if not song:
            await interaction.followup.send(f"❌ No audio track found for: `{query}`", ephemeral=True)
            return

        await music_cog._enqueue_and_play(interaction, song)
        await DynamicVCControlManager.update_room_panel(bot, guild, vc.id)


class DynamicKnockRequestView(ui.View):
    """Access request action buttons for the room owner."""

    def __init__(self, request_id: int):
        super().__init__(timeout=120)
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.success,
                label="Allow",
                emoji="✅",
                custom_id=f"rai_vc_knock:allow:{request_id}",
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.danger,
                label="Decline",
                emoji="❌",
                custom_id=f"rai_vc_knock:decline:{request_id}",
            )
        )


class DynamicAdminEmergencyView(ui.View):
    """Emergency master administrative control view for 👑・admin-control."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.danger,
                label="Lock All Rooms",
                emoji="🔒",
                custom_id="rai_vc_admin:lock_all:0",
                row=0,
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.danger,
                label="Stop All Music",
                emoji="🛑",
                custom_id="rai_vc_admin:stop_music:0",
                row=0,
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Cleanup Empty Rooms",
                emoji="🧹",
                custom_id="rai_vc_admin:cleanup_empty:0",
                row=0,
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.primary,
                label="Rebuild Permissions",
                emoji="🔄",
                custom_id="rai_vc_admin:rebuild_perms:0",
                row=1,
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.success,
                label="Health Check",
                emoji="❤️",
                custom_id="rai_vc_admin:health:0",
                row=1,
            )
        )
        self.add_item(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="System Status",
                emoji="📋",
                custom_id="rai_vc_admin:status:0",
                row=1,
            )
        )

