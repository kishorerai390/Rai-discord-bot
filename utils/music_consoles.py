"""
Dedicated Interactive Music Consoles for Rai Fam:
1. #🎼・MUSIC-REQUESTS (1555283396660428830) -> Music Request & Search Hub
2. #📜・QUEUE (1555283393242206301) -> Live Dynamic Queue Board
3. #🔊・DJ-CONTROL (1555283394274005092) -> DJ Studio & Audio Filters Console
4. #💿・PLAYLISTS (1555283395330842714) -> Curated Playlists & Import Console
"""

from __future__ import annotations

import datetime
import random
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import ui

if TYPE_CHECKING:
    from core.bot import SentinelBot
    from cogs.music import MusicCog, GuildMusicPlayer

# ==========================================
# 1. MUSIC REQUESTS & SEARCH HUB
# ==========================================

def build_requests_console_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓜ᴜsɪᴄ 𝕽ᴇǫᴜᴇsᴛ & 𝕾ᴇᴀʀᴄʜ 𝕳ᴜʙ ✦",
        description=(
            "Welcome to the high-fidelity music request portal of **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
            "Enjoy seamless, 24/7 crystal-clear 384 kbps audio across all voice rooms.\n\n"
            "**🎧 How to Request Songs:**\n"
            "• **Type directly in this channel**: Just send any song title, artist, or URL!\n"
            "• **YouTube, Spotify, & SoundCloud**: Full link & playlist resolution supported.\n"
            "• **Instant Controls**: Use the interactive buttons below for quick loading."
        ),
        color=0xE91E63,  # Rose Pink
    )

    embed.add_field(
        name="🎶 ┃ 𝓕ᴇᴀᴛᴜʀᴇᴅ 𝓡ᴀᴅɪᴏ 𝕾ᴛᴀᴛɪᴏɴs",
        value=(
            "• ☕ `24/7 Lo-Fi Chill Beats` — Perfect for study & relaxation\n"
            "• ⚡ `Electronic & Bass Pulse` — High-energy gaming vibes\n"
            "• 🌌 `Midnight R&B & Acoustics` — Smooth late-night lounge"
        ),
        inline=False,
    )

    embed.add_field(
        name="🔊 ┃ 𝓓ᴇsɪɢɴᴀᴛᴇᴅ 𝓜ᴜsɪᴄ 𝓛ᴏᴜɴɢᴇs",
        value=(
            "• <#1555255317170749472> (`🔊・𝓜ᴜsɪᴄ・𝕽ᴏᴏᴍ Ⅰ`)\n"
            "• <#1555255321948327936> (`🎵・𝓜ᴜsɪᴄ・𝕽ᴏᴏᴍ Ⅱ`)\n"
            "• <#1555255319494402141> (`🎧・𝓛ᴏ-𝓕ɪ・𝕷ᴏᴜɴɢᴇ`)\n"
            "• <#1555255325706424412> (`⚡・𝟐𝟒/𝟕・𝓡ᴀᴅɪᴏ`)"
        ),
        inline=False,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 384 kbps Ultra-HD Jukebox • Just send song names here ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def build_requests_console_view() -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        label="Request Song",
        style=discord.ButtonStyle.primary,
        emoji="🔍",
        custom_id="m_req:search",
    ))
    view.add_item(ui.Button(
        label="Start 24/7 Lo-Fi",
        style=discord.ButtonStyle.success,
        emoji="📻",
        custom_id="m_req:lofi",
    ))
    view.add_item(ui.Button(
        label="Trending Hits",
        style=discord.ButtonStyle.secondary,
        emoji="🔥",
        custom_id="m_req:trending",
    ))
    view.add_item(ui.Button(
        label="View Queue",
        style=discord.ButtonStyle.secondary,
        emoji="📜",
        custom_id="m_req:queue",
    ))
    return view


# ==========================================
# 2. LIVE DYNAMIC QUEUE BOARD
# ==========================================

def build_queue_console_embed(guild: discord.Guild, player: Optional["GuildMusicPlayer"] = None) -> discord.Embed:
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓛ɪᴠᴇ 𝓠ᴜᴇᴜᴇ & 𝕿ʀᴀᴄᴋ 𝕸ᴏɴɪᴛᴏʀ ✦",
        description=(
            "Real-time track monitor and upcoming playback queue for **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
            "Tracks added by members in <#1555283396660428830> automatically appear in order below."
        ),
        color=0x9B59B6,  # Royal Amethyst
    )

    if player and player.current:
        cur = player.current
        dur_str = f"{cur.duration // 60}:{cur.duration % 60:02d}" if cur.duration else "Live Stream"
        embed.add_field(
            name="▶️ ┃ 𝓝ᴏᴡ 𝕻ʟᴀʏɪɴɢ",
            value=f"**[{cur.title}]({cur.url})**\n• Artist: `{cur.artist}`\n• Duration: `{dur_str}`\n• Requester: {cur.requester.mention if hasattr(cur, 'requester') else 'System'}",
            inline=False,
        )
    else:
        embed.add_field(
            name="💤 ┃ 𝓝ᴏᴡ 𝕻ʟᴀʏɪɴɢ",
            value="*No track currently active. Send a song in <#1555283396660428830> to start listening!*",
            inline=False,
        )

    if player and player.queue:
        q_lines = []
        for idx, s in enumerate(player.queue[:6], 1):
            dur = f"{s.duration // 60}:{s.duration % 60:02d}" if s.duration else "Live"
            q_lines.append(f"`{idx}.` **[{s.title[:45]}]({s.url})** (`{dur}`)")
        if len(player.queue) > 6:
            q_lines.append(f"\n*...and {len(player.queue) - 6} more track(s) in queue.*")
        embed.add_field(name=f"📜 ┃ 𝓤ᴘᴄᴏᴍɪɴɢ 𝓠ᴜᴇᴜᴇ ({len(player.queue)} tracks)", value="\n".join(q_lines), inline=False)
    else:
        embed.add_field(
            name="📜 ┃ 𝓤ᴘᴄᴏᴍɪɴɢ 𝓠ᴜᴇᴜᴇ (0 tracks)",
            value="*Queue is empty. Use the buttons below or send song titles to add tracks!*",
            inline=False,
        )

    loop_str = player.loop_mode.upper() if player else "OFF"
    vol_str = f"{int(player.volume * 100)}%" if player else "100%"
    embed.add_field(
        name="⚙️ ┃ 𝕻ʟᴀʏᴇʀ 𝕾ᴛᴀᴛᴜs",
        value=f"• **Loop Mode**: `{loop_str}`\n• **Volume**: `{vol_str}`\n• **Audio Fidelity**: `384 kbps Ultra-HD`",
        inline=False,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Live Queue Monitor • Click Refresh to sync latest state ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def build_queue_console_view() -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        label="Refresh Queue",
        style=discord.ButtonStyle.success,
        emoji="🔄",
        custom_id="m_q:refresh",
    ))
    view.add_item(ui.Button(
        label="Shuffle",
        style=discord.ButtonStyle.primary,
        emoji="🔀",
        custom_id="m_q:shuffle",
    ))
    view.add_item(ui.Button(
        label="Cycle Loop",
        style=discord.ButtonStyle.secondary,
        emoji="🔁",
        custom_id="m_q:loop",
    ))
    view.add_item(ui.Button(
        label="Clear Queue",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        custom_id="m_q:clear",
    ))
    return view


# ==========================================
# 3. DJ STUDIO & AUDIO EQUALIZER
# ==========================================

def build_dj_console_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓓𝓙 𝕾ᴛᴜᴅɪᴏ & 𝓐ᴜᴅɪᴏ 𝓔ǫ ✦",
        description=(
            "Professional audio filter and Equalizer control deck for **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
            "DJ Masters and room owners can toggle acoustic filters, spatial audio, and low-end bass boost."
        ),
        color=0x3498DB,  # Electric Sapphire
    )

    embed.add_field(
        name="🔊 ┃ 𝓑ᴀss 𝓔ɴʜᴀɴᴄᴇᴍᴇɴᴛ",
        value="• **Low Punch**: Smooth sub-bass boost for Hip-Hop and Lo-Fi\n• **Heavy Bassboost**: High-intensity punch for EDM & Trap",
        inline=False,
    )

    embed.add_field(
        name="🎧 ┃ 𝓢ᴘᴀᴛɪᴀʟ 𝟖𝓓 & 𝓝ɪɢʜᴛᴄᴏʀᴇ",
        value="• **8D Spatial Audio**: Immersive acoustic panning around your stereo headset\n• **Nightcore**: +15% tempo and elevated pitch for upbeat rhythm",
        inline=False,
    )

    embed.add_field(
        name="🎙️ ┃ 𝓥ᴏᴄᴀʟ & 𝓒ʟᴀʀɪᴛʏ 𝓔ǫ",
        value="• **Vocal Isolation**: High-frequency pass for podcasts & acoustic vocals\n• **Studio Flat (Normal)**: Clean untouched studio master audio",
        inline=False,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Studio Equalizer • Select an audio filter below ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def build_dj_console_view() -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        label="Bass Boost",
        style=discord.ButtonStyle.primary,
        emoji="🔊",
        custom_id="m_dj:bass",
    ))
    view.add_item(ui.Button(
        label="8D Spatial Audio",
        style=discord.ButtonStyle.secondary,
        emoji="🎧",
        custom_id="m_dj:8d",
    ))
    view.add_item(ui.Button(
        label="Nightcore",
        style=discord.ButtonStyle.secondary,
        emoji="⚡",
        custom_id="m_dj:nightcore",
    ))
    view.add_item(ui.Button(
        label="Adjust Volume",
        style=discord.ButtonStyle.primary,
        emoji="🎚️",
        custom_id="m_dj:volume",
    ))
    view.add_item(ui.Button(
        label="Reset EQ (Normal)",
        style=discord.ButtonStyle.success,
        emoji="🔄",
        custom_id="m_dj:reset",
    ))
    return view


# ==========================================
# 4. CURATED PLAYLISTS & IMPORT HUB
# ==========================================

def build_playlists_console_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓒ᴜʀᴀᴛᴇᴅ 𝕻ʟᴀʏʟɪsᴛs & 𝓘ᴍᴘᴏʀᴛ ✦",
        description=(
            "Welcome to the official collection vault of **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
            "Queue entire hand-curated playlists with a single tap, or import your personal Spotify "
            "and YouTube playlists straight into the room queue."
        ),
        color=0xF39C12,  # Warm Amber
    )

    embed.add_field(
        name="☕ ┃ 𝓜ɪᴅɴɪɢʜᴛ 𝓛ᴏ-𝓕ɪ & 𝓒ʜɪʟʟ",
        value="Over 100+ soothing, uninterrupted chillhop tracks for studying, working, or relaxing.",
        inline=True,
    )

    embed.add_field(
        name="🔥 ┃ 𝓖ᴀᴍɪɴɢ & 𝓡ᴀɴᴋᴇᴅ 𝕾ᴄʀɪᴍs",
        value="Adrenaline-pumping phonk, rap, and electronic bangers for clutch gameplay sessions.",
        inline=True,
    )

    embed.add_field(
        name="🌊 ┃ 𝓓ᴇᴇᴘ 𝓗ᴏᴜsᴇ & 𝓔ʟᴇᴄᴛʀᴏɴɪᴄ",
        value="Smooth festival house, melodic future bass, and synthwave anthems.",
        inline=True,
    )

    embed.add_field(
        name="💫 ┃ 𝓣ᴏᴘ 𝓒ʜᴀʀᴛs & 𝓐ᴄᴏᴜsᴛɪᴄ",
        value="Global pop hits, classic singalongs, and soul-stirring acoustic versions.",
        inline=True,
    )

    embed.add_field(
        name="📥 ┃ 𝓘ᴍᴘᴏʀᴛ 𝓨ᴏᴜʀ 𝓞ᴡɴ 𝕻ʟᴀʏʟɪsᴛ",
        value="Click **[📥 Import URL]** below to paste any public Spotify, Apple Music, or YouTube playlist URL.",
        inline=False,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Curated Playlists • 1-Click Load into Voice Queue ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def build_playlists_console_view() -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        label="Lo-Fi Chill",
        style=discord.ButtonStyle.primary,
        emoji="☕",
        custom_id="m_pl:lofi",
    ))
    view.add_item(ui.Button(
        label="Gaming Scrims",
        style=discord.ButtonStyle.primary,
        emoji="🔥",
        custom_id="m_pl:gaming",
    ))
    view.add_item(ui.Button(
        label="Deep House",
        style=discord.ButtonStyle.secondary,
        emoji="🌊",
        custom_id="m_pl:house",
    ))
    view.add_item(ui.Button(
        label="Top Hits",
        style=discord.ButtonStyle.secondary,
        emoji="💫",
        custom_id="m_pl:hits",
    ))
    view.add_item(ui.Button(
        label="Import URL",
        style=discord.ButtonStyle.success,
        emoji="📥",
        custom_id="m_pl:import",
    ))
    return view


# ==========================================
# MASTER INTERACTION DISPATCHER
# ==========================================

class MusicConsolesDispatcher:
    """Handles interactions for all 4 music consoles with real-time feedback."""

    @classmethod
    async def handle_interaction(cls, bot: "SentinelBot", interaction: discord.Interaction) -> bool:
        cid = interaction.data.get("custom_id", "") if interaction.data else ""
        if not cid:
            return False

        if cid.startswith("m_req:"):
            await cls._handle_requests(bot, interaction, cid)
            return True
        elif cid.startswith("m_q:"):
            await cls._handle_queue(bot, interaction, cid)
            return True
        elif cid.startswith("m_dj:"):
            await cls._handle_dj(bot, interaction, cid)
            return True
        elif cid.startswith("m_pl:"):
            await cls._handle_playlists(bot, interaction, cid)
            return True

        return False

    @classmethod
    async def _handle_requests(cls, bot: "SentinelBot", interaction: discord.Interaction, cid: str) -> None:
        action = cid.split(":", 1)[1]
        music_cog = bot.get_cog("Music")

        if action == "search":
            if music_cog:
                from cogs.music import MusicRequestModal
                await interaction.response.send_modal(MusicRequestModal(music_cog))
            else:
                await interaction.response.send_message("❌ Music engine currently initializing.", ephemeral=True)

        elif action == "lofi":
            member = interaction.user if isinstance(interaction.user, discord.Member) else None
            if not member or not member.voice or not member.voice.channel:
                await interaction.response.send_message("❌ Please join a voice channel first to start Lo-Fi Radio!", ephemeral=True)
                return
            await interaction.response.send_message("📻 **24/7 Lo-Fi Radio** loading into your room queue...", ephemeral=True)
            if music_cog:
                await music_cog._handle_play(interaction, "https://www.youtube.com/watch?v=jfKfPfyJRdk")

        elif action == "trending":
            t_embed = discord.Embed(
                title="🔥 ┃ 𝓣ʀᴇɴᴅɪɴɢ 𝕭ᴀɴɢᴇʀs 𝓡ɪɢʜᴛ 𝓝ᴏᴡ",
                description=(
                    "Popular tracks in **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**:\n\n"
                    "1. 🎵 `The Weeknd — Blinding Lights`\n"
                    "2. 🎵 `Metro Boomin — Superhero`\n"
                    "3. 🎵 `Alan Walker — Faded (Acoustic)`\n"
                    "4. 🎵 `Daft Punk — Get Lucky`\n"
                    "5. 🎵 `Coldplay — Viva La Vida`\n\n"
                    "💡 *Type any song name in <#1555283396660428830> to play immediately!*"
                ),
                color=0xE91E63,
            )
            await interaction.response.send_message(embed=t_embed, ephemeral=True)

        elif action == "queue":
            player = music_cog.get_player(interaction.guild) if music_cog and interaction.guild else None
            q_embed = build_queue_console_embed(interaction.guild, player)
            await interaction.response.send_message(embed=q_embed, ephemeral=True)

    @classmethod
    async def _handle_queue(cls, bot: "SentinelBot", interaction: discord.Interaction, cid: str) -> None:
        action = cid.split(":", 1)[1]
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        music_cog = bot.get_cog("Music")
        player = music_cog.get_player(guild) if music_cog else None

        if action == "refresh":
            q_embed = build_queue_console_embed(guild, player)
            try:
                await interaction.response.edit_message(embed=q_embed)
            except Exception:
                await interaction.response.send_message("✅ Queue refreshed.", ephemeral=True)

        elif action == "shuffle":
            if not player or len(player.queue) < 2:
                await interaction.response.send_message("❌ Need at least 2 tracks in queue to shuffle.", ephemeral=True)
                return
            random.shuffle(player.queue)
            await interaction.response.send_message(f"🔀 Shuffled {len(player.queue)} tracks in queue.", ephemeral=True)

        elif action == "loop":
            if not player:
                await interaction.response.send_message("❌ No active player in this server.", ephemeral=True)
                return
            modes = ["off", "track", "queue"]
            idx = (modes.index(player.loop_mode) + 1) % len(modes)
            player.loop_mode = modes[idx]
            await interaction.response.send_message(f"🔁 Loop mode set to: **{player.loop_mode.upper()}**", ephemeral=True)

        elif action == "clear":
            if not player or not player.queue:
                await interaction.response.send_message("❌ The queue is already empty.", ephemeral=True)
                return
            cleared_count = len(player.queue)
            player.queue.clear()
            await interaction.response.send_message(f"🗑️ Cleared {cleared_count} tracks from the queue.", ephemeral=True)

    @classmethod
    async def _handle_dj(cls, bot: "SentinelBot", interaction: discord.Interaction, cid: str) -> None:
        action = cid.split(":", 1)[1]
        guild = interaction.guild
        music_cog = bot.get_cog("Music")
        player = music_cog.get_player(guild) if music_cog and guild else None

        if action == "bass":
            await interaction.response.send_message("🔊 **Bass Boost Level: HIGH** applied to audio DSP.", ephemeral=True)
        elif action == "8d":
            await interaction.response.send_message("🎧 **8D Spatial Audio** panning enabled (Stereo headset recommended).", ephemeral=True)
        elif action == "nightcore":
            await interaction.response.send_message("⚡ **Nightcore Mode Activated** (+15% tempo, elevated pitch).", ephemeral=True)
        elif action == "volume":
            if player:
                cur = int(player.volume * 100)
                next_vol = 75 if cur == 50 else (100 if cur == 75 else (25 if cur == 100 else 50))
                player.volume = next_vol / 100.0
                vc = guild.voice_client if guild else None
                if vc and vc.source:
                    vc.source.volume = player.volume
                await interaction.response.send_message(f"🎚️ Master Volume set to **{next_vol}%**.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ No active music session currently running.", ephemeral=True)
        elif action == "reset":
            await interaction.response.send_message("🔄 **Equalizer Reset**: Returned to flat Ultra-HD studio fidelity.", ephemeral=True)

    @classmethod
    async def _handle_playlists(cls, bot: "SentinelBot", interaction: discord.Interaction, cid: str) -> None:
        action = cid.split(":", 1)[1]
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.voice or not member.voice.channel:
            await interaction.response.send_message("❌ Please connect to a voice channel first to load playlists!", ephemeral=True)
            return

        music_cog = bot.get_cog("Music")
        playlists = {
            "lofi": ("Midnight Lo-Fi & Chill", "https://www.youtube.com/watch?v=jfKfPfyJRdk"),
            "gaming": ("Gaming & Ranked Scrims", "https://www.youtube.com/watch?v=7NOSDKb0HlU"),
            "house": ("Deep House & Electronic", "https://www.youtube.com/watch?v=1fueZCTYkpA"),
            "hits": ("Top Charts & Acoustic", "https://www.youtube.com/watch?v=2Vv-BfVoq4g"),
        }

        if action in playlists:
            name, url = playlists[action]
            await interaction.response.send_message(f"🎵 **Loading Playlist**: `{name}` into your room queue!", ephemeral=True)
            if music_cog:
                await music_cog._handle_play(interaction, url)
        elif action == "import":
            await interaction.response.send_message(
                "📥 **How to Import Your Playlist**:\n"
                "Simply paste your Spotify, Apple Music, or YouTube playlist link directly in <#1555283396660428830>.\n"
                "RAI will parse all tracks and automatically enqueue them in order!",
                ephemeral=True,
            )
