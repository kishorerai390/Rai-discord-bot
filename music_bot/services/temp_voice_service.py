"""
Temporary Voice Rooms Service (Phase 4):
- Detects member joins to "➕ Create a Room" (ID: 1557461916144767046).
- Creates dynamic custom voice room under "04. VOICE LOUNGE".
- Provides interactive Room Control View (Lock/Unlock, Limit, Rename, Transfer).
- Auto-cleans rooms when empty after grace period.
- Protects permanent voice channels from deletion.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, Set
import discord

logger = logging.getLogger("music_bot.temp_voice")

CREATE_ROOM_CHANNEL_ID = 1557461916144767046
VOICE_LOUNGE_CATEGORY_ID = 1554891379174416474  # Or dynamic lookup

# Permanent voice channels that MUST NEVER BE DELETED
PERMANENT_VC_IDS: Set[int] = {
    1557461916144767046,  # Create a Room
    1554905807240302652,  # Solo
    1554905810574774286,  # Duo
    1554905813737545770,  # Trio
    1554905842300485642,  # Squad
    1554905829033902151,  # Game Lobby
    1554905836768469032,  # Ranked Grind
    1554905825544241302,  # Chill Gaming
    1554905899414454446,  # Editing Studio
    1554905874437513248,  # Creator Collaboration
    1554905803666751590,  # Music Lounge
    1554905870817689600,  # Movie Theater
    1554891485818921042,  # AFK
}

class TempVoiceRoomManager:
    # Maps channel_id -> {owner_id: int, task: asyncio.Task, created_at: float}
    _active_rooms: Dict[int, dict] = {}
    _deletion_tasks: Dict[int, asyncio.Task] = {}

    @classmethod
    def is_permanent(cls, channel_id: int) -> bool:
        return channel_id in PERMANENT_VC_IDS

    @classmethod
    async def handle_voice_state_update(
        cls,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        # 1. Member joined the "Create a Room" generator
        if after.channel and after.channel.id == CREATE_ROOM_CHANNEL_ID:
            await cls._create_dynamic_room(member, after.channel)

        # 2. Member left a voice channel
        if before.channel and before.channel.id not in PERMANENT_VC_IDS:
            if before.channel.id in cls._active_rooms or before.channel.name.endswith("Room"):
                # If channel is now empty, schedule deletion with 30s grace period
                if len(before.channel.members) == 0:
                    cls._schedule_room_deletion(before.channel)

        # 3. Member rejoined a pending-deletion room
        if after.channel and after.channel.id in cls._deletion_tasks:
            cls._cancel_room_deletion(after.channel.id)

    @classmethod
    async def _create_dynamic_room(cls, member: discord.Member, trigger_channel: discord.VoiceChannel) -> Optional[discord.VoiceChannel]:
        guild = member.guild
        category = trigger_channel.category

        room_name = f"🎧・{member.display_name}'s Room"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True, speak=True, view_channel=True),
            member: discord.PermissionOverwrite(connect=True, speak=True, manage_channels=True, move_members=True),
        }

        try:
            new_channel = await guild.create_voice_channel(
                name=room_name,
                category=category,
                overwrites=overwrites,
                bitrate=min(trigger_channel.bitrate, guild.bitrate_limit),
                user_limit=0,
                reason=f"Temporary voice room for {member.display_name}"
            )

            cls._active_rooms[new_channel.id] = {
                "owner_id": member.id,
                "guild_id": guild.id,
                "created_at": asyncio.get_event_loop().time(),
            }

            # Move user into the new channel
            await member.move_to(new_channel, reason="Moved into generated temporary voice room")

            logger.info(
                "Created temporary voice room",
                extra={"channel_id": new_channel.id, "owner_id": member.id, "guild_id": guild.id}
            )
            return new_channel
        except Exception as e:
            logger.error(f"Failed to create temporary voice room for {member.display_name}: {e}")
            return None

    @classmethod
    def _schedule_room_deletion(cls, channel: discord.VoiceChannel) -> None:
        cls._cancel_room_deletion(channel.id)

        async def _delete_worker():
            try:
                await asyncio.sleep(30.0)  # 30-second grace period
                if len(channel.members) == 0:
                    cls._active_rooms.pop(channel.id, None)
                    cls._deletion_tasks.pop(channel.id, None)
                    await channel.delete(reason="Temporary voice room empty after grace period")
                    logger.info(f"Deleted empty temporary voice room: {channel.name} ({channel.id})")
            except discord.NotFound:
                cls._active_rooms.pop(channel.id, None)
                cls._deletion_tasks.pop(channel.id, None)
            except Exception as e:
                logger.error(f"Error during room deletion worker for {channel.id}: {e}")

        task = asyncio.create_task(_delete_worker(), name=f"temp_vc_del_{channel.id}")
        cls._deletion_tasks[channel.id] = task

    @classmethod
    def _cancel_room_deletion(cls, channel_id: int) -> None:
        task = cls._deletion_tasks.pop(channel_id, None)
        if task and not task.done():
            task.cancel()


class RenameRoomModal(discord.ui.Modal, title="✏️ Rename Voice Room"):
    new_name = discord.ui.TextInput(
        label="New Room Name",
        placeholder="e.g. Chill & Beats Lounge",
        min_length=2,
        max_length=50,
        required=True
    )

    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await self.channel.edit(name=self.new_name.value, reason=f"Renamed by {interaction.user.display_name}")
        await interaction.response.send_message(f"✅ Room renamed to **{self.new_name.value}**", ephemeral=True)


class RoomControlView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel, owner_id: int):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ Only the room owner or staff can manage this room.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Lock", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="vc_lock")
    async def btn_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = self.channel.overwrites
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=False)
        await self.channel.edit(overwrites=overwrites, reason="Room locked by owner")
        await interaction.response.send_message("🔒 Room is now **LOCKED** to other members.", ephemeral=True)

    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.secondary, emoji="🔓", custom_id="vc_unlock")
    async def btn_unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = self.channel.overwrites
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=True)
        await self.channel.edit(overwrites=overwrites, reason="Room unlocked by owner")
        await interaction.response.send_message("🔓 Room is now **UNLOCKED** for everyone.", ephemeral=True)

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="vc_rename")
    async def btn_rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameRoomModal(self.channel))

    @discord.ui.select(
        placeholder="👥 Set Room Capacity",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Solo (1 User)", value="1", emoji="👤"),
            discord.SelectOption(label="Duo (2 Users)", value="2", emoji="👥"),
            discord.SelectOption(label="Trio (3 Users)", value="3", emoji="👥"),
            discord.SelectOption(label="Squad (4 Users)", value="4", emoji="👥"),
            discord.SelectOption(label="Small Group (6 Users)", value="6", emoji="🧸"),
            discord.SelectOption(label="Full Lobby (Unlimited)", value="0", emoji="♾️"),
        ],
        custom_id="vc_capacity"
    )
    async def select_capacity(self, interaction: discord.Interaction, select: discord.ui.Select):
        limit = int(select.values[0])
        await self.channel.edit(user_limit=limit, reason=f"Capacity set to {limit} by owner")
        desc = f"limit of **{limit} members**" if limit > 0 else "**Unlimited capacity**"
        await interaction.response.send_message(f"👥 Room capacity updated to {desc}.", ephemeral=True)

