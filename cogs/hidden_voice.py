"""
Personal Hidden Voice Channel System for Rai.
Implements genuine Discord permission-level invisibility for owner-only temporary voice rooms.
Provides owner controls via slash commands (/private) and interactive UI buttons/modals.
Ensures zero leaks into public logs, autocomplete, server stats, or public bot responses.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from database.models import HiddenVoiceConfig, HiddenVoiceRoom
from utils.embeds import (
    create_embed,
    error_embed,
    info_embed,
    success_embed,
    warning_embed,
)
from utils.permissions import is_admin_or_owner
from core.tasks import safe_task_loop

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


# ==========================================
# MODALS & VIEWS FOR INTERACTIVE UI
# ==========================================

class RenameModal(discord.ui.Modal, title="Rename Private Room"):
    new_name = discord.ui.TextInput(
        label="Room Name",
        placeholder="e.g. Kishore's Sanctum",
        min_length=1,
        max_length=50,
        required=True,
    )

    def __init__(self, cog: "HiddenVoiceCog", channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name_val = f"🔒・{self.new_name.value.strip()}"
        try:
            await self.channel.edit(name=name_val, reason=f"Private room renamed by {interaction.user}")
            await self.cog.bot.db.update_hidden_voice_room(self.channel.id, name=name_val)
            await interaction.followup.send(f"✅ Room renamed to **{name_val}**.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to rename room: {e}", ephemeral=True)


class LimitModal(discord.ui.Modal, title="Set User Limit"):
    limit = discord.ui.TextInput(
        label="User Limit (0 = Unlimited, max 99)",
        placeholder="0",
        min_length=1,
        max_length=2,
        required=True,
    )

    def __init__(self, cog: "HiddenVoiceCog", channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            val = int(self.limit.value.strip())
            if not (0 <= val <= 99):
                raise ValueError()
        except ValueError:
            await interaction.followup.send("❌ Please enter a valid number between 0 and 99.", ephemeral=True)
            return

        try:
            await self.channel.edit(user_limit=val, reason=f"Private room limit changed by {interaction.user}")
            await self.cog.bot.db.update_hidden_voice_room(self.channel.id, user_limit=val)
            msg = "unlimited" if val == 0 else f"{val} members"
            await interaction.followup.send(f"✅ User limit set to **{msg}**.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to set limit: {e}", ephemeral=True)


class TransferConfirmView(discord.ui.View):
    def __init__(self, cog: "HiddenVoiceCog", channel: discord.VoiceChannel, current_owner: discord.Member, target: discord.Member):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.channel = channel
        self.current_owner = current_owner
        self.target = target
        self.value: Optional[bool] = None

    @discord.ui.button(label="Confirm Transfer", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.current_owner.id:
            await interaction.response.send_message("❌ Only the current owner can confirm.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        self.value = True
        self.stop()
        await self.cog._execute_ownership_transfer(interaction, self.channel, self.current_owner, self.target)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.current_owner.id:
            await interaction.response.send_message("❌ Only the current owner can cancel.", ephemeral=True)
            return

        self.value = False
        self.stop()
        await interaction.response.send_message("Transfer cancelled.", ephemeral=True)


class PrivateRoomControlView(discord.ui.View):
    """Interactive control panel sent to the private room's text chat."""

    def __init__(self, cog: "HiddenVoiceCog", channel_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id

    async def _verify_owner(self, interaction: discord.Interaction) -> Optional[HiddenVoiceRoom]:
        room = await self.cog.bot.db.get_hidden_voice_room(self.channel_id)
        if not room:
            await interaction.response.send_message("❌ This private room is no longer tracked.", ephemeral=True)
            return None
        if room.owner_id != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ You are not the owner of this private room.", ephemeral=True)
            return None
        return room

    @discord.ui.button(label="Lock / Unlock", style=discord.ButtonStyle.primary, emoji="🔐", custom_id="pv_toggle_lock")
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        room = await self._verify_owner(interaction)
        if not room:
            return
        channel = interaction.guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("❌ Voice channel not found.", ephemeral=True)
            return

        new_locked = not room.is_locked
        try:
            # When locked, deny connect to default role
            overwrites = channel.overwrites
            everyone_ow = overwrites.get(interaction.guild.default_role, discord.PermissionOverwrite())
            everyone_ow.connect = False
            overwrites[interaction.guild.default_role] = everyone_ow
            await channel.edit(overwrites=overwrites)

            await self.cog.bot.db.update_hidden_voice_room(channel.id, is_locked=new_locked)
            state_text = "locked 🔒" if new_locked else "unlocked 🔓"
            await interaction.response.send_message(f"Room has been **{state_text}**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to toggle lock: {e}", ephemeral=True)

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="pv_rename")
    async def rename_room(self, interaction: discord.Interaction, button: discord.ui.Button):
        room = await self._verify_owner(interaction)
        if not room:
            return
        channel = interaction.guild.get_channel(self.channel_id)
        if isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_modal(RenameModal(self.cog, channel))
        else:
            await interaction.response.send_message("❌ Voice channel not found.", ephemeral=True)

    @discord.ui.button(label="User Limit", style=discord.ButtonStyle.secondary, emoji="🔢", custom_id="pv_limit")
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        room = await self._verify_owner(interaction)
        if not room:
            return
        channel = interaction.guild.get_channel(self.channel_id)
        if isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_modal(LimitModal(self.cog, channel))
        else:
            await interaction.response.send_message("❌ Voice channel not found.", ephemeral=True)

    @discord.ui.button(label="Delete Room", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="pv_delete")
    async def delete_room(self, interaction: discord.Interaction, button: discord.ui.Button):
        room = await self._verify_owner(interaction)
        if not room:
            return
        channel = interaction.guild.get_channel(self.channel_id)
        await interaction.response.send_message("Deleting room...", ephemeral=True)
        if channel:
            try:
                await channel.delete(reason="Private room deleted by owner")
            except Exception:
                pass
        await self.cog.bot.db.delete_hidden_voice_room(self.channel_id)


# ==========================================
# MAIN HIDDEN VOICE COG
# ==========================================

class HiddenVoiceCog(commands.Cog, name="HiddenVoice"):
    """
    Genuine Discord permission-hidden voice room manager.
    Owner-only visibility by default. Explicit invitation required for others to see and join.
    """

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.cleanup_task = self._cleanup_worker.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    private_group = app_commands.Group(
        name="private",
        description="Hidden personal voice room management",
    )
    # ==========================================
    # VOICE STATE MONITOR
    # ==========================================

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        if member.bot:
            return
        guild = member.guild
        cfg = await self.bot.db.get_hidden_voice_config(guild.id)
        if not cfg.enabled:
            return

        # 1. Member joined the Entry Channel -> Create Hidden VC
        if after.channel and cfg.entry_channel_id and after.channel.id == cfg.entry_channel_id:
            await self._handle_entry_join(member, cfg)

        # 2. Member left a Hidden VC -> Check if empty and handle grace period
        if before.channel and before.channel != after.channel:
            await self._handle_room_leave(before.channel, member, cfg)

        # 3. Member rejoined a pending cleanup room -> Cancel grace period
        if after.channel:
            room = await self.bot.db.get_hidden_voice_room(after.channel.id)
            if room and room.grace_period_until:
                await self.bot.db.update_hidden_voice_room(
                    after.channel.id, grace_period_until=None, room_status="active"
                )

    async def _handle_entry_join(self, member: discord.Member, cfg: HiddenVoiceConfig) -> None:
        guild = member.guild

        # Check maximum rooms per user
        active_user_rooms = await self.bot.db.get_hidden_voice_rooms_by_owner(guild.id, member.id)
        if len(active_user_rooms) >= cfg.max_rooms_per_user:
            try:
                await member.move_to(None, reason="Max hidden rooms limit reached")
                await member.send(
                    f"⚠️ You already have an active hidden room in **{guild.name}**. "
                    f"Please delete your current room before creating a new one."
                )
            except Exception:
                pass
            return

        category = guild.get_channel(cfg.category_id) if cfg.category_id else None

        # Build genuine permission overwrites
        # @everyone: completely denied view and connect
        # creator: completely granted view, connect, speak, stream, manage_channels
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
                connect=False,
            ),
            member: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
                use_embedded_activities=True,
                manage_channels=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
            ),
        }

        # Staff visibility: Only if staff_can_view_hidden_rooms is explicitly enabled
        if cfg.staff_can_view_hidden_rooms:
            # Grant to roles with administrator or manage_guild
            for role in guild.roles:
                if role.permissions.administrator or role.permissions.manage_guild:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, connect=True)

        room_name = cfg.room_name_format.replace("{username}", member.name).replace("{display_name}", member.display_name)
        if not room_name.startswith("🔒"):
            room_name = f"🔒・{room_name}"

        try:
            new_vc = await guild.create_voice_channel(
                name=room_name[:100],
                category=category,
                user_limit=cfg.max_users_per_room if cfg.max_users_per_room < 99 else 0,
                overwrites=overwrites,
                reason=f"Rai Private Room created for {member}",
            )

            # Persist in SQLite
            await self.bot.db.create_hidden_voice_room(
                channel_id=new_vc.id,
                guild_id=guild.id,
                owner_id=member.id,
                name=new_vc.name,
                user_limit=new_vc.user_limit,
            )

            # Move creator to new private room
            await member.move_to(new_vc, reason="Rai: Moved creator into private room")

            # Post Control Panel embed inside text-in-voice chat
            embed = create_embed(
                title=f"🔐 Private Room — Control Panel",
                description=(
                    f"Welcome to your hidden room, {member.mention}!\n\n"
                    f"• **Visibility:** Owner-only (invisible to everyone else)\n"
                    f"• **Invite Friends:** Use `/private invite @user` or buttons below\n"
                    f"• **Manage:** Rename, lock, change limit, or delete anytime\n\n"
                    f"*The room will automatically be cleaned up after all members leave.*"
                ),
                color=Colors.PRIMARY,
            )
            embed.set_footer(text="Rai Private Voice • Privacy Protected")
            view = PrivateRoomControlView(self, new_vc.id)
            await new_vc.send(embed=embed, view=view)
            logger.info(f"Created hidden voice room {new_vc.name} ({new_vc.id}) for {member}")
        except Exception as e:
            logger.error(f"Failed to create hidden room for {member}: {e}")
            try:
                await member.move_to(None)
            except Exception:
                pass

    async def _handle_room_leave(
        self, channel: discord.VoiceChannel, member: discord.Member, cfg: HiddenVoiceConfig
    ) -> None:
        room = await self.bot.db.get_hidden_voice_room(channel.id)
        if not room:
            return

        remaining_members = [m for m in channel.members if not m.bot]

        # Case 1: Room is completely empty
        if len(remaining_members) == 0:
            if cfg.empty_grace_period <= 0:
                # Immediate cleanup
                await self._delete_room_safely(channel, "Empty room immediate cleanup")
            else:
                grace_until = (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(seconds=cfg.empty_grace_period)
                ).isoformat()
                await self.bot.db.update_hidden_voice_room(
                    channel.id,
                    grace_period_until=grace_until,
                    room_status="cleanup_pending",
                )
            return

        # Case 2: Owner left but other invited members remain
        if member.id == room.owner_id and len(remaining_members) > 0:
            if cfg.automatic_owner_transfer:
                new_owner = remaining_members[0]
                # Transfer ownership automatically
                await self._execute_auto_transfer(channel, room, new_owner)
            else:
                # Room stays open under original owner
                await self.bot.db.update_hidden_voice_room(
                    channel.id, last_activity=datetime.datetime.now(datetime.timezone.utc).isoformat()
                )

    async def _execute_auto_transfer(
        self, channel: discord.VoiceChannel, room: HiddenVoiceRoom, new_owner: discord.Member
    ) -> None:
        try:
            overwrites = channel.overwrites
            # Give new owner full permissions
            overwrites[new_owner] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
                manage_channels=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
            )
            await channel.edit(overwrites=overwrites)
            await self.bot.db.update_hidden_voice_room(
                channel.id, owner_id=new_owner.id, transferred_from=room.owner_id
            )
            embed = info_embed(
                "👑 Ownership Transferred",
                f"Previous owner left. Room ownership automatically transferred to {new_owner.mention}.",
            )
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed auto transfer for hidden room {channel.id}: {e}")

    async def _delete_room_safely(self, channel: discord.VoiceChannel, reason: str) -> None:
        try:
            await self.bot.db.delete_hidden_voice_room(channel.id)
            await channel.delete(reason=f"Rai HiddenVoice: {reason}")
            logger.info(f"Cleaned up hidden voice room {channel.id} ({reason})")
        except Exception as e:
            logger.warning(f"Could not delete hidden room {channel.id}: {e}")

    # ==========================================
    # BACKGROUND CLEANUP WORKER
    # ==========================================

    @tasks.loop(seconds=15.0)
    @safe_task_loop(task_name="hidden_voice_cleanup", timeout_seconds=15.0)
    async def _cleanup_worker(self):
        """Dedicated background task to safely delete empty rooms after grace period."""
        now = datetime.datetime.now(datetime.timezone.utc)
        all_rooms = await self.bot.db.get_all_hidden_voice_rooms()
        for room in all_rooms:
            if not room.grace_period_until:
                continue

            try:
                expire_dt = datetime.datetime.fromisoformat(room.grace_period_until)
                if expire_dt.tzinfo is None:
                    expire_dt = expire_dt.replace(tzinfo=datetime.timezone.utc)

                if now >= expire_dt:
                    guild = self.bot.get_guild(room.guild_id)
                    if guild:
                        channel = guild.get_channel(room.channel_id)
                        if channel and isinstance(channel, discord.VoiceChannel):
                            # Double check if any human member is inside
                            human_members = [m for m in channel.members if not m.bot]
                            if len(human_members) == 0:
                                await self._delete_room_safely(channel, "Grace period expired")
                                continue
                            else:
                                # Room is no longer empty, reset grace period
                                await self.bot.db.update_hidden_voice_room(
                                    room.channel_id, grace_period_until=None, room_status="active"
                                )
                                continue
                    # If channel no longer exists on Discord, clean DB
                    await self.bot.db.delete_hidden_voice_room(room.channel_id)
            except Exception as e:
                logger.error(f"Error checking grace period for room {room.channel_id}: {e}")

    @_cleanup_worker.before_loop
    async def _before_cleanup(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # HELPER: GET USER'S CURRENT ROOM
    # ==========================================

    async def _get_managed_room(self, interaction: discord.Interaction) -> Optional[discord.VoiceChannel]:
        """Finds the hidden room owned or currently occupied by user."""
        if not interaction.guild:
            return None

        # 1. If user is in a voice channel, check if they own it
        if interaction.user.voice and interaction.user.voice.channel:
            ch = interaction.user.voice.channel
            room = await self.bot.db.get_hidden_voice_room(ch.id)
            if room:
                if room.owner_id == interaction.user.id or is_admin_or_owner(interaction.user):
                    return ch

        # 2. Check all rooms owned by user in this guild
        owned_rooms = await self.bot.db.get_hidden_voice_rooms_by_owner(interaction.guild.id, interaction.user.id)
        if owned_rooms:
            ch = interaction.guild.get_channel(owned_rooms[0].channel_id)
            if isinstance(ch, discord.VoiceChannel):
                return ch

        return None

    # ==========================================
    # SLASH COMMANDS: /private
    # ==========================================

    @private_group.command(name="invite", description="Grant a user access to see and join your private room")
    @app_commands.describe(member="Member to invite")
    async def invite(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_managed_room(interaction)
        if not channel:
            await interaction.followup.send("❌ You do not have an active private room to manage.", ephemeral=True)
            return

        room = await self.bot.db.get_hidden_voice_room(channel.id)
        if not room or (room.owner_id != interaction.user.id and not is_admin_or_owner(interaction.user)):
            await interaction.followup.send("❌ You are not the owner of this room.", ephemeral=True)
            return

        if member.id == interaction.user.id:
            await interaction.followup.send("❌ You already have access to your own room.", ephemeral=True)
            return

        try:
            # Grant View Channel and Connect to the invited member
            overwrites = channel.overwrites
            overwrites[member] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
            )
            await channel.edit(overwrites=overwrites, reason=f"Invited by room owner {interaction.user}")

            # Update DB invited list
            invited = list(set(room.invited_members + [member.id]))
            await self.bot.db.update_hidden_voice_room(channel.id, invited_members=invited)

            # Send DM notification to invited member
            dm_sent = False
            try:
                invite_embed = create_embed(
                    title="🔔 Private Voice Room Invitation",
                    description=(
                        f"You have been invited to a private voice room by {interaction.user.mention} "
                        f"in **{interaction.guild.name}**!\n\n"
                        f"**Room:** {channel.name}\n"
                        f"Click below or locate the channel to join."
                    ),
                    color=Colors.SUCCESS,
                )
                await member.send(embed=invite_embed)
                dm_sent = True
            except Exception:
                dm_sent = False

            notice = f"✅ Invited {member.mention} to your private room!"
            if not dm_sent:
                notice += " *(Could not DM user, but access was granted)*"
            await interaction.followup.send(notice, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to invite member: {e}", ephemeral=True)

    @private_group.command(name="remove", description="Revoke access to your private room from a member")
    @app_commands.describe(member="Member to remove")
    async def remove_user(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_managed_room(interaction)
        if not channel:
            await interaction.followup.send("❌ You do not have an active private room.", ephemeral=True)
            return

        room = await self.bot.db.get_hidden_voice_room(channel.id)
        if not room or (room.owner_id != interaction.user.id and not is_admin_or_owner(interaction.user)):
            await interaction.followup.send("❌ You are not the owner of this room.", ephemeral=True)
            return

        if member.id == room.owner_id:
            await interaction.followup.send("❌ You cannot remove the owner of the room.", ephemeral=True)
            return

        try:
            # Revoke permission overwrites
            overwrites = channel.overwrites
            overwrites[member] = discord.PermissionOverwrite(view_channel=False, connect=False)
            await channel.edit(overwrites=overwrites, reason=f"Access revoked by owner {interaction.user}")

            # Update DB invited list
            invited = [uid for uid in room.invited_members if uid != member.id]
            await self.bot.db.update_hidden_voice_room(channel.id, invited_members=invited)

            # If member is currently inside the VC, safely disconnect them
            if member in channel.members:
                await member.move_to(None, reason="Removed from private voice room by owner")

            await interaction.followup.send(
                f"✅ Removed access from {member.mention}. They can no longer see or join this room.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to remove member: {e}", ephemeral=True)

    @private_group.command(name="lock", description="Lock the private room to prevent new connections")
    async def lock_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_managed_room(interaction)
        if not channel:
            await interaction.followup.send("❌ You do not have an active private room.", ephemeral=True)
            return

        try:
            overwrites = channel.overwrites
            everyone_ow = overwrites.get(interaction.guild.default_role, discord.PermissionOverwrite())
            everyone_ow.connect = False
            overwrites[interaction.guild.default_role] = everyone_ow
            await channel.edit(overwrites=overwrites)
            await self.bot.db.update_hidden_voice_room(channel.id, is_locked=True)
            await interaction.followup.send("🔒 Room is now **locked**.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to lock room: {e}", ephemeral=True)

    @private_group.command(name="unlock", description="Unlock the private room")
    async def unlock_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_managed_room(interaction)
        if not channel:
            await interaction.followup.send("❌ You do not have an active private room.", ephemeral=True)
            return

        try:
            await self.bot.db.update_hidden_voice_room(channel.id, is_locked=False)
            await interaction.followup.send("🔓 Room is now **unlocked**.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to unlock room: {e}", ephemeral=True)

    @private_group.command(name="rename", description="Rename your private room")
    @app_commands.describe(name="New room name")
    async def rename_cmd(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_managed_room(interaction)
        if not channel:
            await interaction.followup.send("❌ You do not have an active private room.", ephemeral=True)
            return

        cleaned_name = name.strip()
        if not cleaned_name.startswith("🔒"):
            cleaned_name = f"🔒・{cleaned_name}"

        try:
            await channel.edit(name=cleaned_name[:100], reason=f"Renamed by {interaction.user}")
            await self.bot.db.update_hidden_voice_room(channel.id, name=cleaned_name[:100])
            await interaction.followup.send(f"✅ Renamed room to **{cleaned_name}**.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to rename room: {e}", ephemeral=True)

    @private_group.command(name="limit", description="Set user limit for your room (0 = unlimited)")
    @app_commands.describe(count="Maximum number of users allowed (0-99)")
    async def limit_cmd(self, interaction: discord.Interaction, count: app_commands.Range[int, 0, 99]):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_managed_room(interaction)
        if not channel:
            await interaction.followup.send("❌ You do not have an active private room.", ephemeral=True)
            return

        try:
            await channel.edit(user_limit=count, reason=f"Limit set by {interaction.user}")
            await self.bot.db.update_hidden_voice_room(channel.id, user_limit=count)
            msg = "unlimited" if count == 0 else f"{count} members"
            await interaction.followup.send(f"✅ User limit set to **{msg}**.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to set limit: {e}", ephemeral=True)

    @private_group.command(name="transfer", description="Transfer room ownership to another member")
    @app_commands.describe(member="Member to make the new owner")
    async def transfer_cmd(self, interaction: discord.Interaction, member: discord.Member):
        channel = await self._get_managed_room(interaction)
        if not channel:
            await interaction.response.send_message("❌ You do not have an active private room.", ephemeral=True)
            return

        room = await self.bot.db.get_hidden_voice_room(channel.id)
        if not room or room.owner_id != interaction.user.id:
            await interaction.response.send_message("❌ Only the room owner can transfer ownership.", ephemeral=True)
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ You already own this room.", ephemeral=True)
            return

        if member.bot:
            await interaction.response.send_message("❌ You cannot transfer ownership to a bot.", ephemeral=True)
            return

        # Show confirmation view as required
        embed = warning_embed(
            "⚠️ Transfer Ownership Confirmation",
            (
                f"Are you sure you want to transfer ownership of **{channel.name}**?\n\n"
                f"• **Current Owner:** {interaction.user.mention}\n"
                f"• **New Owner:** {member.mention}\n\n"
                f"**Important:** After transfer, you will lose owner controls and will lose "
                f"visibility unless you remain on the invited list."
            ),
        )
        view = TransferConfirmView(self, channel, interaction.user, member)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _execute_ownership_transfer(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        old_owner: discord.Member,
        new_owner: discord.Member,
    ) -> None:
        room = await self.bot.db.get_hidden_voice_room(channel.id)
        if not room:
            await interaction.followup.send("❌ Room record not found.", ephemeral=True)
            return

        try:
            overwrites = channel.overwrites

            # 1. Grant new owner full room control permissions
            overwrites[new_owner] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
                manage_channels=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
            )

            # 2. Update previous owner permissions
            # If previous owner is explicitly in invited list, retain normal member access
            if old_owner.id in room.invited_members:
                overwrites[old_owner] = discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    stream=True,
                )
            else:
                # Loses View Channel completely
                overwrites[old_owner] = discord.PermissionOverwrite(
                    view_channel=False,
                    connect=False,
                )

            await channel.edit(overwrites=overwrites, reason=f"Ownership transferred from {old_owner} to {new_owner}")

            # 3. Update SQLite record
            await self.bot.db.update_hidden_voice_room(
                channel.id,
                owner_id=new_owner.id,
                transferred_from=old_owner.id,
            )

            # 4. If previous owner is inside and lost access, safely disconnect them
            if old_owner in channel.members and old_owner.id not in room.invited_members:
                try:
                    await old_owner.move_to(None, reason="Transferred room without retaining invite")
                except Exception:
                    pass

            await interaction.followup.send(
                f"👑 Ownership successfully transferred to {new_owner.mention}.",
                ephemeral=True,
            )

            # Notify room text channel
            embed = success_embed(
                "👑 Ownership Transferred",
                f"Room ownership transferred from {old_owner.mention} to {new_owner.mention}.",
            )
            await channel.send(embed=embed)
            logger.info(f"Ownership of hidden room {channel.id} transferred: {old_owner} -> {new_owner}")
        except Exception as e:
            logger.error(f"Failed to execute ownership transfer: {e}")
            await interaction.followup.send(f"❌ Failed to transfer ownership: {e}", ephemeral=True)

    @private_group.command(name="delete", description="Permanently delete your private room")
    async def delete_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_managed_room(interaction)
        if not channel:
            await interaction.followup.send("❌ You do not have an active private room.", ephemeral=True)
            return

        room = await self.bot.db.get_hidden_voice_room(channel.id)
        if not room or (room.owner_id != interaction.user.id and not is_admin_or_owner(interaction.user)):
            await interaction.followup.send("❌ Only the owner can delete this room.", ephemeral=True)
            return

        await self._delete_room_safely(channel, f"Deleted by owner {interaction.user}")
        await interaction.followup.send("🗑️ Private room deleted.", ephemeral=True)

    @private_group.command(name="mute", description="Server mute a member inside your room")
    @app_commands.describe(member="Member in your voice room to mute")
    async def mute_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_managed_room(interaction)
        if not channel or member not in channel.members:
            await interaction.followup.send("❌ That member is not currently inside your room.", ephemeral=True)
            return
        try:
            await member.edit(mute=True, reason=f"Muted by room owner {interaction.user}")
            await interaction.followup.send(f"🔇 Muted {member.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to mute member: {e}", ephemeral=True)

    @private_group.command(name="deafen", description="Server deafen a member inside your room")
    @app_commands.describe(member="Member in your voice room to deafen")
    async def deafen_cmd(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        channel = await self._get_managed_room(interaction)
        if not channel or member not in channel.members:
            await interaction.followup.send("❌ That member is not currently inside your room.", ephemeral=True)
            return
        try:
            await member.edit(deafen=True, reason=f"Deafened by room owner {interaction.user}")
            await interaction.followup.send(f"Deafened {member.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to deafen member: {e}", ephemeral=True)

    @private_group.command(name="kick", description="Disconnect a member from your room")
    @app_commands.describe(member="Member in your voice room to disconnect")
    async def kick_cmd(self, interaction: discord.Interaction, member: discord.Member):
        # Alias for remove
        await self.remove_user.callback(self, interaction, member)




async def setup(bot: SentinelBot):
    await bot.add_cog(HiddenVoiceCog(bot))
