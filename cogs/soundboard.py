"""
RAI — SOUNDBOARD COG.
Provides:
- Commands: /soundboard play, list, stop, stop-all, settings, add, remove, and /sound quick play.
- Safe automatic timeout enforcement (default 8s, 1-30s range).
- Cooldowns: user cooldown (3s), sound cooldown (5s), overlapping controls.
- Voice channel state tracking: stops if requester leaves, stops if channel is empty.
- Multi-source voice session coordination: pauses music cleanly and restores upon completion.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from services.soundboard_service import SoundboardService
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.SoundboardCog")


class SoundboardCog(commands.Cog, name="Soundboard"):
    """Smart Soundboard with Automatic Timeout Enforcement and Voice Coordination."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.service = SoundboardService.get_instance(bot)

    soundboard_group = app_commands.Group(
        name="soundboard",
        description="Smart soundboard with automatic timeout controls",
    )

    async def sound_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        sounds = self.service.list_available_sounds(interaction.guild_id)
        filtered = [s for s in sounds if current.lower() in s.lower()][:25]
        return [app_commands.Choice(name=s.title(), value=s) for s in filtered]

    @soundboard_group.command(name="play", description="Play a sound clip in your voice channel")
    @app_commands.describe(sound="Name of the sound clip")
    @app_commands.autocomplete(sound=sound_autocomplete)
    async def play_cmd(self, interaction: discord.Interaction, sound: str):
        await interaction.response.defer(ephemeral=True)
        ok, msg = await self.service.play_sound(interaction, sound)
        if ok:
            embed = success_embed("🔊 Soundboard", msg)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = error_embed("Soundboard Error", msg)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="sound", description="Quickly play or stop a sound clip in your voice channel")
    @app_commands.describe(sound="Name of the sound clip to play, or 'stop' to halt playback")
    @app_commands.autocomplete(sound=sound_autocomplete)
    async def sound_alias_cmd(self, interaction: discord.Interaction, sound: str):
        if sound.strip().lower() == "stop":
            await self.stop_cmd(interaction)
            return
        await self.play_cmd(interaction, sound)

    @soundboard_group.command(name="list", description="List all available soundboard clips")
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        sounds = self.service.list_available_sounds(interaction.guild_id)
        if not sounds:
            await interaction.followup.send("ℹ️ No soundboard clips currently available.", ephemeral=True)
            return

        formatted = "\n".join([f"• `🔊 {s}`" for s in sounds])
        cfg = self.service.get_settings(interaction.guild_id or 0)
        embed = create_embed(
            title="🎵 SOUNDBOARD LIBRARY",
            description=(
                f"**Available Clips ({len(sounds)}):**\n{formatted}\n\n"
                f"⏱️ **Timeout Limit:** `{cfg.get('timeout', 8)}s` | ⏳ **Cooldown:** `{cfg.get('user_cooldown', 3)}s`\n"
                f"Use `/soundboard play <sound>` or `/sound <sound>` to play in your voice room!"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @soundboard_group.command(name="stop", description="Stop the currently playing sound")
    async def stop_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return
        ok, msg = await self.service.stop_sound(interaction.guild, interaction.user)
        if ok:
            await interaction.followup.send(embed=info_embed("Soundboard Stopped", msg), ephemeral=True)
        else:
            await interaction.followup.send(embed=error_embed("Soundboard", msg), ephemeral=True)

    @soundboard_group.command(name="stop-all", description="Stop all soundboard playback in the server")
    async def stop_all_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only administrators or server staff can use stop-all.", ephemeral=True)
            return
        ok, msg = await self.service.stop_sound(interaction.guild, interaction.user, force=True)
        await interaction.followup.send(embed=info_embed("Soundboard Emergency Stop", msg), ephemeral=True)

    @soundboard_group.command(name="settings", description="Configure soundboard duration timeout, cooldowns, and limits")
    @app_commands.describe(
        timeout="Max duration in seconds (1-30)",
        cooldown="User cooldown in seconds",
        sound_cooldown="Same sound cooldown in seconds",
        overlapping="Allow overlapping sounds",
        max_concurrent="Maximum simultaneous sounds if overlapping is enabled",
        enable="Enable or disable soundboard on this server",
    )
    async def settings_cmd(
        self,
        interaction: discord.Interaction,
        timeout: Optional[app_commands.Range[int, 1, 30]] = None,
        cooldown: Optional[int] = None,
        sound_cooldown: Optional[int] = None,
        overlapping: Optional[bool] = None,
        max_concurrent: Optional[app_commands.Range[int, 1, 3]] = None,
        enable: Optional[bool] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Administrator or staff permissions required.", ephemeral=True)
            return

        updates = {}
        if timeout is not None:
            updates["timeout"] = timeout
        if cooldown is not None:
            updates["user_cooldown"] = cooldown
        if sound_cooldown is not None:
            updates["sound_cooldown"] = sound_cooldown
        if overlapping is not None:
            updates["allow_overlapping"] = overlapping
        if max_concurrent is not None:
            updates["max_concurrent"] = max_concurrent
        if enable is not None:
            updates["enabled"] = enable

        new_cfg = self.service.update_settings(interaction.guild.id, **updates)
        embed = create_embed(
            title="⚙️ Soundboard Configuration",
            description=(
                f"• **Status:** `{'ENABLED 🟢' if new_cfg['enabled'] else 'DISABLED 🔴'}`\n"
                f"• **Timeout Duration:** `{new_cfg['timeout']}s` (max limit enforced)\n"
                f"• **User Cooldown:** `{new_cfg['user_cooldown']}s`\n"
                f"• **Sound Cooldown:** `{new_cfg['sound_cooldown']}s`\n"
                f"• **Allow Overlapping:** `{'Yes' if new_cfg['allow_overlapping'] else 'No'}`\n"
                f"• **Max Concurrent:** `{new_cfg['max_concurrent']}`\n\n"
                "✅ Soundboard settings updated successfully."
            ),
            color=Colors.SUCCESS,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @soundboard_group.command(name="add", description="Add a sound to the server soundboard library")
    @app_commands.describe(
        name="Name for the sound clip (letters, numbers, underscores only)",
        file="Audio file to upload (WAV or MP3, max 1MB)",
    )
    async def add_sound_cmd(self, interaction: discord.Interaction, name: str, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Administrator or staff permissions required to add sounds.", ephemeral=True)
            return

        clean_name = name.strip().lower()
        if not clean_name.isalnum() and "_" not in clean_name:
            await interaction.followup.send("❌ Sound name may only contain alphanumeric characters and underscores.", ephemeral=True)
            return

        if not any(file.filename.lower().endswith(ext) for ext in (".wav", ".mp3")):
            await interaction.followup.send("❌ Only `.wav` and `.mp3` audio files are supported.", ephemeral=True)
            return

        if file.size > 1024 * 1024:  # 1MB limit
            await interaction.followup.send("❌ File size exceeds 1MB limit for soundboard clips.", ephemeral=True)
            return

        from services.soundboard_service import SOUNDBOARD_DIR
        dest_path = SOUNDBOARD_DIR / f"{clean_name}{file.filename[-4:].lower()}"
        try:
            await file.save(dest_path)
            await interaction.followup.send(embed=success_embed("Sound Added", f"Added **{clean_name}** to soundboard library!"), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=error_embed("Upload Failed", str(e)), ephemeral=True)

    @soundboard_group.command(name="remove", description="Remove a sound from the server soundboard library")
    @app_commands.describe(name="Name of the sound clip to remove")
    async def remove_sound_cmd(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Administrator or staff permissions required.", ephemeral=True)
            return

        from services.soundboard_service import SOUNDBOARD_DIR
        clean_name = name.strip().lower()
        target = SOUNDBOARD_DIR / f"{clean_name}.wav"
        if not target.exists():
            target = SOUNDBOARD_DIR / f"{clean_name}.mp3"

        if not target.exists():
            await interaction.followup.send(f"❌ Sound **{clean_name}** not found.", ephemeral=True)
            return

        try:
            target.unlink()
            await interaction.followup.send(embed=success_embed("Sound Removed", f"Sound **{clean_name}** was deleted from library."), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=error_embed("Delete Failed", str(e)), ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Handles leave-voice behavior: stop sound if requester leaves, or if channel is empty."""
        if before.channel and before.channel != after.channel:
            # Check if requester left
            await self.service.handle_user_left_vc(member, before.channel)

            # Check if channel became empty (only bots or 0 members)
            human_members = [m for m in before.channel.members if not m.bot]
            if len(human_members) == 0:
                await self.service.handle_empty_vc(before.channel)


async def setup(bot: SentinelBot):
    cog = SoundboardCog(bot)
    await bot.add_cog(cog)
