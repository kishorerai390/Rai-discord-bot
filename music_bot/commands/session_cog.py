"""
Persistent Music Session Command Suite (/music-session & /session).
Provides Rythm-style persistent session memory:
1. /music-session save [name] — Persist live playback, current track, queue, and position.
2. /music-session restore [id/name] — Rebuild queue, resume playback at exact position.
3. /music-session status — View active checkpoint state, elapsed position, and recovery mode.
4. /music-session list — Browse saved sessions with interactive 1-click restore.
5. /music-session forget [id/name] — Remove saved session with permission verification.
6. /music-session mode [MANUAL/AUTO_RESUME/QUEUE_ONLY] — Configure guild recovery policy.
7. /music-session cleanup — Purge expired persistent session records.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from music_bot.config import (
    COLOR_ELECTRIC_CYAN,
    COLOR_MIDNIGHT_BLACK,
    COLOR_NEON_BLUE,
    COLOR_WHITE,
)
from music_bot.database.models import PersistentMusicSession
from music_bot.services.player_service import format_duration
from music_bot.services.session_memory_service import MusicSessionMemoryService
from music_bot.services.session_service import GuildMusicSession, SessionManager

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("RaiMusic.SessionCog")


class SessionRestoreSelect(discord.ui.Select):
    """Interactive dropdown allowing one-click restoration of any saved session."""

    def __init__(self, cog: MusicSessionCog, sessions: List[PersistentMusicSession]):
        options = []
        for s in sessions[:25]:
            q_cnt = len(s.queue)
            track_name = (s.current_track_title[:40] if s.current_track_title else "No Active Track")
            pos_str = format_duration(s.last_known_position, is_position=True)
            options.append(
                discord.SelectOption(
                    label=f"{s.session_name[:30]} ({s.session_id})",
                    description=f"{track_name} • {pos_str} • {q_cnt} in queue",
                    value=s.session_id,
                    emoji="💾",
                )
            )

        super().__init__(
            placeholder="Select a saved session to restore immediately...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog.ensure_deferred(interaction, ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.edit_original_response(
                content="❌ You must be connected to a voice channel to restore music playback.",
                view=None,
            )
            return

        target_id = self.values[0]
        success, msg, _ = await MusicSessionMemoryService.restore_session(
            bot=self.cog.bot,
            guild=guild,
            target_voice_channel=member.voice.channel,
            text_channel=interaction.channel,  # type: ignore
            session_id_or_name=target_id,
            requested_by_user=member,
        )

        embed = discord.Embed(
            title="🔄 MUSIC SESSION RESTORED" if success else "❌ RESTORATION FAILED",
            description=msg,
            color=COLOR_ELECTRIC_CYAN if success else 0xED4245,
        )
        await interaction.edit_original_response(embed=embed, view=None)


class SessionRestoreView(discord.ui.View):
    """Container view holding the session restoration selection menu."""

    def __init__(self, cog: MusicSessionCog, sessions: List[PersistentMusicSession]):
        super().__init__(timeout=120)
        self.add_item(SessionRestoreSelect(cog, sessions))


class MusicSessionCog(commands.Cog, name="SessionMemory"):
    """Rythm-style persistent session memory management."""

    def __init__(self, bot: RaiMusicBot):
        self.bot = bot
        self.session_manager = SessionManager.get_instance()

    @staticmethod
    async def ensure_deferred(interaction: discord.Interaction, ephemeral: bool = False) -> bool:
        """Safely acknowledges interaction within Discord's 3.0s deadline."""
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=ephemeral)
                return True
            except Exception as e:
                logger.debug(f"[SessionMemory] Defer notice: {e}")
                return False
        return True

    # =========================================================================
    # SLASH COMMAND GROUP: /music-session
    # =========================================================================

    session_group = app_commands.Group(
        name="music-session",
        description="Rythm-Style persistent music session memory & auto-resume",
    )

    @session_group.command(name="save", description="Save current music playback, queue, and position to memory")
    @app_commands.describe(name="Optional custom label for this session (e.g. 'Chill Night')")
    async def cmd_save(self, interaction: discord.Interaction, name: Optional[str] = None) -> None:
        """Saves current playing session into database."""
        await self.ensure_deferred(interaction, ephemeral=False)
        if not interaction.guild:
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        session = await self.session_manager.get_session(interaction.guild.id)
        if not session.current_track and len(session.queue) == 0:
            await interaction.edit_original_response(content="❌ Nothing is currently playing or queued to save.")
            return

        session_name = name.strip() if name and name.strip() else f"Session {datetime.now(timezone.utc).strftime('%b %d %H:%M')}"
        success, msg, pers = await MusicSessionMemoryService.save_named_session(
            bot=self.bot,
            session=session,
            name=session_name,
            user=interaction.user,
        )

        if not success or not pers:
            await interaction.edit_original_response(content=f"❌ {msg}")
            return

        track_title = pers.current_track_title or "No Track"
        pos_str = format_duration(pers.last_known_position, is_position=True)
        dur_str = format_duration(pers.track_duration)
        q_count = len(pers.queue)

        embed = discord.Embed(
            title="💾 MUSIC SESSION SAVED",
            description=(
                f"**{pers.session_name}** (`{pers.session_id}`)\n\n"
                f"• **Current Track:** {track_title}\n"
                f"• **Playback Position:** `{pos_str} / {dur_str}` {'⏸️ (Paused)' if pers.is_paused else '▶️ (Playing)'}\n"
                f"• **Preserved Queue:** `{q_count}` upcoming tracks in exact order\n"
                f"• **Volume & Loop:** `{pers.volume}%` • `{pers.loop_mode.title()}`\n"
                f"• **Saved By:** {interaction.user.mention}\n"
                f"• **Retained Until:** <t:{int(datetime.fromisoformat(pers.expires_at).timestamp())}:R>"
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        embed.set_footer(text=f"Restore later anytime using: /music-session restore query:{pers.session_id}")
        await interaction.edit_original_response(embed=embed)

    @session_group.command(name="restore", description="Restore a saved session, resurrect queue, and resume playback")
    @app_commands.describe(query="Session ID or name to restore (leave empty to resume latest saved session)")
    async def cmd_restore(self, interaction: discord.Interaction, query: Optional[str] = None) -> None:
        """Restores a saved session."""
        await self.ensure_deferred(interaction, ephemeral=False)
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        if not member.voice or not member.voice.channel:
            await interaction.edit_original_response(content="❌ You must join a voice channel first to restore music playback.")
            return

        success, msg, pers = await MusicSessionMemoryService.restore_session(
            bot=self.bot,
            guild=guild,
            target_voice_channel=member.voice.channel,
            text_channel=interaction.channel,  # type: ignore
            session_id_or_name=query,
            requested_by_user=member,
        )

        embed = discord.Embed(
            title="🔄 MUSIC SESSION RESTORED" if success else "❌ RESTORATION FAILED",
            description=msg,
            color=COLOR_ELECTRIC_CYAN if success else 0xED4245,
        )
        await interaction.edit_original_response(embed=embed)

    @session_group.command(name="status", description="View current music session memory and active checkpoint metrics")
    async def cmd_status(self, interaction: discord.Interaction) -> None:
        """Displays session memory health, current position, and recovery settings."""
        await self.ensure_deferred(interaction, ephemeral=True)
        if not interaction.guild:
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        session = await self.session_manager.get_session(interaction.guild.id)
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        latest = await self.bot.db.get_persistent_session(interaction.guild.id)

        rec_mode = getattr(settings, "recovery_mode", "MANUAL")
        chk_interval = getattr(settings, "checkpoint_interval", 10)
        ret_days = getattr(settings, "session_retention_days", 7)

        cur_pos = session.progress_seconds
        dur = session.current_track.duration if session.current_track else 0
        pos_str = f"{format_duration(cur_pos, is_position=True)} / {format_duration(dur)}" if dur else "00:00"

        embed = discord.Embed(
            title="🧠 MUSIC SESSION MEMORY DASHBOARD",
            description=(
                f"**Server:** {interaction.guild.name}\n"
                f"**Active Session ID:** `{session.session_id}`\n"
                f"**Current State:** `{session.state.value}` • **Position:** `{pos_str}`\n"
                f"**Queue Count:** `{len(session.queue)}` tracks • **History:** `{len(session.history)}` tracks\n\n"
                f"⚙️ **Recovery & Retention Policies:**\n"
                f"• **Recovery Mode:** `{rec_mode}` *(MANUAL / AUTO_RESUME / QUEUE_ONLY)*\n"
                f"• **Checkpoint Frequency:** Every `{chk_interval}` seconds (and on every track change)\n"
                f"• **Retention Period:** `{ret_days}` days\n\n"
                f"💾 **Latest Checkpoint in Storage:**\n"
                f"{f'• **Name:** {latest.session_name} (`{latest.session_id}`)' if latest else '• No saved checkpoint recorded yet'}\n"
                f"{f'• **Last Checkpoint:** <t:{int(datetime.fromisoformat(latest.last_checkpoint).timestamp())}:R>' if latest else ''}\n"
                f"{f'• **Saved Track:** {latest.current_track_title}' if latest and latest.current_track_title else ''}"
            ),
            color=COLOR_NEON_BLUE,
        )
        embed.set_footer(text="Use /music-session save to explicitly save current playback anytime")
        await interaction.edit_original_response(embed=embed)

    @session_group.command(name="list", description="List all saved sessions for this server with 1-click restore")
    async def cmd_list(self, interaction: discord.Interaction) -> None:
        """Lists saved sessions for the guild."""
        await self.ensure_deferred(interaction, ephemeral=False)
        if not interaction.guild:
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        sessions = await self.bot.db.list_persistent_sessions(interaction.guild.id, limit=15)
        if not sessions:
            await interaction.edit_original_response(
                content="🐾 No saved sessions found for this server. Use `/music-session save` to save your current queue!"
            )
            return

        lines = []
        for i, s in enumerate(sessions, 1):
            created_ts = int(datetime.fromisoformat(s.created_at).timestamp())
            track_desc = s.current_track_title or "Empty Queue"
            pos_desc = format_duration(s.last_known_position, is_position=True)
            pin_badge = "📌 " if s.is_pinned else ""
            lines.append(
                f"`{i}.` {pin_badge}**{s.session_name}** (`{s.session_id}`)\n"
                f"   └ 🎵 {track_desc} (`{pos_desc}`) • `{len(s.queue)}` in queue • <t:{created_ts}:R>"
            )

        embed = discord.Embed(
            title=f"💾 SAVED MUSIC SESSIONS — {interaction.guild.name}",
            description="\n\n".join(lines),
            color=COLOR_ELECTRIC_CYAN,
        )
        embed.set_footer(text="Select a session below to restore immediately, or run /music-session restore <id>")
        view = SessionRestoreView(self, sessions)
        await interaction.edit_original_response(embed=embed, view=view)

    @session_group.command(name="forget", description="Delete a saved music session from storage")
    @app_commands.describe(query="Session ID or name to delete")
    async def cmd_forget(self, interaction: discord.Interaction, query: str) -> None:
        """Deletes a saved session record with permission validation."""
        await self.ensure_deferred(interaction, ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        # Look up session
        target = await self.bot.db.get_persistent_session(guild.id, query.strip())
        if not target:
            target = await self.bot.db.get_persistent_session_by_name(guild.id, query.strip())

        if not target:
            await interaction.edit_original_response(content=f"❌ No session found matching `{query}`.")
            return

        # Permission check: Creator, DJ, or Administrator
        is_creator = target.created_by_user_id == member.id
        is_admin = member.guild_permissions.administrator or member.guild_permissions.manage_guild
        dj_settings = await self.bot.db.get_dj_settings(guild.id)
        has_dj = dj_settings.dj_role_id and any(r.id == dj_settings.dj_role_id for r in member.roles)

        if not (is_creator or is_admin or has_dj):
            await interaction.edit_original_response(
                content="❌ You do not have permission to delete this session (must be session creator, DJ, or Admin)."
            )
            return

        deleted = await self.bot.db.delete_persistent_session(guild.id, target.session_id)
        if deleted:
            await interaction.edit_original_response(
                content=f"🗑️ Successfully deleted session **{target.session_name}** (`{target.session_id}`)."
            )
        else:
            await interaction.edit_original_response(content="❌ Could not delete session record.")

    @session_group.command(name="mode", description="Configure server session recovery policy (MANUAL / AUTO_RESUME / QUEUE_ONLY)")
    @app_commands.describe(mode="Recovery policy to apply")
    @app_commands.choices(mode=[
        app_commands.Choice(name="MANUAL — Never auto-join; users restore manually via /music-session restore", value="MANUAL"),
        app_commands.Choice(name="AUTO_RESUME — Automatically reconnect and resume on bot restart", value="AUTO_RESUME"),
        app_commands.Choice(name="QUEUE_ONLY — Restore queue order on restart without auto-playing audio", value="QUEUE_ONLY"),
    ])
    async def cmd_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        """Configures server recovery mode."""
        await self.ensure_deferred(interaction, ephemeral=True)
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.edit_original_response(content="❌ You need **Manage Server** permission to modify recovery policies.")
            return

        settings = await self.bot.db.get_guild_settings(interaction.guild.id)
        settings.recovery_mode = mode.value
        await self.bot.db.update_guild_settings(settings)

        embed = discord.Embed(
            title="⚙️ RECOVERY POLICY UPDATED",
            description=(
                f"Server session recovery policy set to: **{mode.name}**\n\n"
                f"• **Behavior:** {'Resumes audio stream where it left off after unexpected restarts.' if mode.value == 'AUTO_RESUME' else ('Reconstructs queue without starting playback.' if mode.value == 'QUEUE_ONLY' else 'Waits for member to run /music-session restore.')}"
            ),
            color=COLOR_ELECTRIC_CYAN,
        )
        await interaction.edit_original_response(embed=embed)

    @session_group.command(name="cleanup", description="Purge expired persistent session records (Admin only)")
    async def cmd_cleanup(self, interaction: discord.Interaction) -> None:
        """Purges expired sessions."""
        await self.ensure_deferred(interaction, ephemeral=True)
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.edit_original_response(content="❌ This command must be used in a server.")
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.edit_original_response(content="❌ You need **Administrator** permission to run cleanup.")
            return

        purged = await MusicSessionMemoryService.cleanup_expired_sessions(self.bot)
        await interaction.edit_original_response(content=f"🧹 Purged **{purged}** expired session records from database.")

    # =========================================================================
    # SHORTCUT ALIAS GROUP: /session (Matches Rythm UX)
    # =========================================================================

    alias_group = app_commands.Group(name="session", description="Shortcut for /music-session commands")

    @alias_group.command(name="save", description="Save current music playback, queue, and position (Shortcut)")
    @app_commands.describe(name="Optional custom label for this session")
    async def alias_save(self, interaction: discord.Interaction, name: Optional[str] = None) -> None:
        await self.cmd_save(interaction, name)

    @alias_group.command(name="restore", description="Restore a saved session, resurrect queue, and resume playback (Shortcut)")
    @app_commands.describe(query="Session ID or name to restore")
    async def alias_restore(self, interaction: discord.Interaction, query: Optional[str] = None) -> None:
        await self.cmd_restore(interaction, query)

    @alias_group.command(name="status", description="View current music session memory and active checkpoint metrics (Shortcut)")
    async def alias_status(self, interaction: discord.Interaction) -> None:
        await self.cmd_status(interaction)

    @alias_group.command(name="list", description="List all saved sessions for this server (Shortcut)")
    async def alias_list(self, interaction: discord.Interaction) -> None:
        await self.cmd_list(interaction)

    @alias_group.command(name="forget", description="Delete a saved music session from storage (Shortcut)")
    @app_commands.describe(query="Session ID or name to delete")
    async def alias_forget(self, interaction: discord.Interaction, query: str) -> None:
        await self.cmd_forget(interaction, query)


async def setup(bot: RaiMusicBot) -> None:
    await bot.add_cog(MusicSessionCog(bot))
