"""Rem music welcome panel with quick resume and song search controls."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import voicelink
from voicelink import MongoDBHandler

logger = logging.getLogger("Rem.MusicHome")


class SongSearchModal(discord.ui.Modal, title="Search for a song"):
    query = discord.ui.TextInput(
        label="Song name or link",
        placeholder="e.g. Kalyani, anime opening, or a YouTube URL",
        min_length=1,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Acknowledge before voice connection or provider resolution can take time.
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            member = interaction.user
            channel = getattr(getattr(member, "voice", None), "channel", None)
            if channel is None:
                await interaction.followup.send(
                    "Join a voice channel first, then search again. 💜", ephemeral=True
                )
                return

            player = interaction.guild.voice_client
            if player is None:
                player = await voicelink.connect_channel(interaction, channel)
            elif getattr(player, "channel", None) and player.channel.id != channel.id:
                move_to = getattr(player, "move_to", None)
                if not callable(move_to):
                    await interaction.followup.send(
                        f"I'm already connected to {player.channel.mention}; I left current playback untouched.",
                        ephemeral=True,
                    )
                    return
                await move_to(channel)

            tracks = await player.get_tracks(str(self.query.value).strip(), requester=member)
            if not tracks:
                await interaction.followup.send(
                    "I couldn't find a playable match. Try the song title or a direct link. 🎵",
                    ephemeral=True,
                )
                return

            if isinstance(tracks, voicelink.Playlist):
                position = await player.add_track(tracks.tracks)
                label = f"Added **{len(tracks.tracks)} tracks** from **{tracks.name}** to the queue."
            else:
                track = tracks[0]
                position = await player.add_track(track)
                label = f"Added **{track.title}** by **{track.author}** to the queue."

            if not player.is_playing:
                await player.do_next()

            await interaction.followup.send(f"🎶 {label}", ephemeral=True)
        except Exception:
            logger.exception("Music home song search failed")
            await interaction.followup.send(
                "❌ I couldn't start that request. Check the bot's voice permissions and try again.",
                ephemeral=True,
            )


class MusicHomeView(discord.ui.View):
    """Persistent-looking quick actions for Rem's music home panel."""

    def __init__(self) -> None:
        super().__init__(timeout=900)
        self._notifications: dict[int, bool] = {}

    @discord.ui.button(
        label="Continue where I left off",
        style=discord.ButtonStyle.success,
        emoji="▶️",
        row=0,
    )
    async def continue_listening(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            player = interaction.guild.voice_client
            if player and getattr(player, "current", None):
                if getattr(player, "is_paused", False):
                    await player.set_pause(False, requester=interaction.user)
                    message = "▶️ Resumed the current track."
                else:
                    message = f"🎶 Already playing **{player.current.title}**."
                await interaction.followup.send(message, ephemeral=True)
                return

            channel = getattr(getattr(interaction.user, "voice", None), "channel", None)
            if channel is None:
                await interaction.followup.send(
                    "Join a voice channel first so I know where to play your music. 💜",
                    ephemeral=True,
                )
                return

            history = await MongoDBHandler.get_user(interaction.user.id, d_type="history")
            if not history:
                await interaction.followup.send(
                    "No recent listening history was found yet. Use **Search for song** to start a queue! 🎵",
                    ephemeral=True,
                )
                return

            recent = voicelink.Track.decode(history[-1])
            uri = recent.get("uri") if isinstance(recent, dict) else None
            if not uri:
                await interaction.followup.send(
                    "I couldn't restore your last track. Search for it by name instead. 🎵",
                    ephemeral=True,
                )
                return

            player = interaction.guild.voice_client
            if player is None:
                player = await voicelink.connect_channel(interaction, channel)
            tracks = await player.get_tracks(uri, requester=interaction.user)
            if not tracks:
                await interaction.followup.send(
                    "Your last track isn't available right now. Try searching for it again. 🎵",
                    ephemeral=True,
                )
                return

            selected = tracks[0] if not isinstance(tracks, voicelink.Playlist) else tracks.tracks[0]
            await player.add_track(selected)
            if not player.is_playing:
                await player.do_next()
            await interaction.followup.send(
                f"💜 Restored **{selected.title}** to your queue.", ephemeral=True
            )
        except Exception:
            logger.exception("Music home resume failed")
            await interaction.followup.send(
                "❌ I couldn't resume your music. Please try Search for a Song instead.",
                ephemeral=True,
            )

    @discord.ui.button(
        label="Search for song",
        style=discord.ButtonStyle.primary,
        emoji="🔎",
        row=0,
    )
    async def search_song(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(SongSearchModal())

    @discord.ui.button(
        label="Notifications off",
        style=discord.ButtonStyle.secondary,
        emoji="🔕",
        row=1,
    )
    async def toggle_notifications(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        enabled = not self._notifications.get(interaction.user.id, False)
        self._notifications[interaction.user.id] = enabled
        button.label = "Notifications on" if enabled else "Notifications off"
        button.emoji = "🔔" if enabled else "🔕"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"{'🔔 Music notifications enabled' if enabled else '🔕 Music notifications muted'} for this panel session.",
            ephemeral=True,
        )


class MusicHome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.panel_view = MusicHomeView()

    @app_commands.command(name="music-home", description="Open Rem's music welcome panel.")
    async def music_home(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🎵 Jump back in",
            description=(
                "Your music, right where you left off. 💜\n\n"
                "▶️ **Continue where I left off** — resume a current track or restore your latest listen.\n"
                "🔎 **Search for song** — find a track and add it to the queue.\n"
                "🔕 **Notifications off** — toggle this panel's session-only notification preference."
            ),
            colour=discord.Colour.from_rgb(105, 82, 230),
        )
        if self.bot.user:
            embed.set_author(
                name="Rem 🎧 · Your Anime Music Companion",
                icon_url=self.bot.user.display_avatar.url,
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Rem MusicMaid · Made for your next vibe 💜")

        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=self.panel_view)
        else:
            await interaction.followup.send(embed=embed, view=self.panel_view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicHome(bot))
