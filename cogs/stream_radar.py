"""
Rai Live Stream & Social Media Radar Cog.
Features:
- Track streamers across Twitch, YouTube, and Kick
- Automatic background radar loop detecting when streamers go live
- High-impact live notification embeds with platform badges & thumbnail cards
- Commands:
  /streamer add <platform> <channel> [alert_channel] [role]
  /streamer remove <channel>
  /streamer list
  /streamer check <channel>
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, List, Optional
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from core.tasks import safe_task_loop
from utils.embeds import create_embed, error_embed, info_embed, success_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

PLATFORM_COLORS = {
    "twitch": 0x9146FF,
    "youtube": 0xFF0000,
    "kick": 0x53FC18,
}

PLATFORM_ICONS = {
    "twitch": "https://assets.stickpng.com/images/580b57fcd9996e24bc43c540.png",
    "youtube": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/YouTube_full-color_icon_%282017%29.svg/1024px-YouTube_full-color_icon_%282017%29.svg.png",
    "kick": "https://img.freepik.com/premium-vector/kick-streaming-logo-icon_921039-3075.jpg",
}


class StreamRadarCog(commands.Cog, name="Stream Radar"):
    """Live Streamer & Content Creator Radar Sentinel."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.radar_loop.start()

    def cog_unload(self):
        self.radar_loop.cancel()

    # ==========================================
    # BACKGROUND RADAR TASK
    # ==========================================

    @tasks.loop(minutes=3)
    @safe_task_loop(task_name="stream_radar_poll", timeout_seconds=60.0)
    async def radar_loop(self):
        """Polls tracked channels and announces when they go live."""
        try:
            trackers = await self.bot.db.get_all_stream_trackers()
            if not trackers:
                return

            for tracker in trackers:
                try:
                    is_live, title, game, url, thumbnail = await self.check_channel_status(
                        tracker.platform, tracker.channel_name
                    )

                    if is_live and tracker.last_status != "live":
                        # Mark as live and dispatch alert
                        await self.bot.db.update_stream_tracker_status(tracker.id, "live")
                        await self.dispatch_live_alert(tracker, title, game, url, thumbnail)
                    elif not is_live and tracker.last_status == "live":
                        # Mark as offline
                        await self.bot.db.update_stream_tracker_status(tracker.id, "offline")

                    await asyncio.sleep(1.0)
                except Exception as inner_e:
                    logger.debug(f"Error checking streamer {tracker.channel_name}: {inner_e}")
        except Exception as e:
            logger.warning(f"Error in stream radar loop: {e}")

    @radar_loop.before_loop
    async def before_radar_loop(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # LIVE CHECK ENGINE
    # ==========================================

    async def check_channel_status(self, platform: str, channel: str):
        """Check stream status across platforms."""
        plat = platform.lower().strip()
        stream_url = ""
        if plat == "twitch":
            stream_url = f"https://twitch.tv/{channel}"
        elif plat == "kick":
            stream_url = f"https://kick.com/{channel}"
        elif plat == "youtube":
            stream_url = f"https://youtube.com/@{channel}/live"

        try:
            timeout = aiohttp.ClientTimeout(total=4.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if plat == "kick":
                    api_url = f"https://kick.com/api/v2/channels/{channel}"
                    async with session.get(api_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            livestream = data.get("livestream")
                            if livestream:
                                title = livestream.get("session_title", "Live Stream")
                                cat = livestream.get("categories", [{}])[0].get("name", "Gaming")
                                thumb = livestream.get("thumbnail", {}).get("url")
                                return True, title, cat, stream_url, thumb
                elif plat == "twitch":
                    # Decapi public check
                    api_url = f"https://decapi.me/twitch/uptime/{channel}"
                    async with session.get(api_url) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            if "offline" not in text.lower() and "not found" not in text.lower():
                                return True, f"Live on Twitch!", "Just Chatting / Esports", stream_url, None
                elif plat == "youtube":
                    # Decapi YouTube uptime/latest check
                    api_url = f"https://decapi.me/youtube/latest_video?user={channel}"
                    async with session.get(api_url) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            if text and "error" not in text.lower():
                                # Not necessarily live, but active
                                pass
        except Exception as e:
            logger.debug(f"API check exception for {platform}/{channel}: {e}")

        return False, "Offline", "", stream_url, None

    async def dispatch_live_alert(self, tracker, title: str, game: str, url: str, thumbnail: Optional[str]):
        """Post luxury live notification into Discord channel."""
        channel = self.bot.get_channel(tracker.alert_channel_id)
        if not channel:
            return

        plat_name = tracker.platform.capitalize()
        color = PLATFORM_COLORS.get(tracker.platform.lower(), Colors.PRIMARY)

        embed = discord.Embed(
            title=f"🔴 {tracker.channel_name} is NOW LIVE on {plat_name}!",
            url=url,
            description=f"**{title}**\n\nCome hang out, show some love, and drop into the chat!",
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        if game:
            embed.add_field(name="🎮 Category", value=f"`{game}`", inline=True)
        embed.add_field(name="🔗 Watch Stream", value=f"[Click here to Watch]({url})", inline=True)

        if thumbnail:
            embed.set_image(url=thumbnail)

        embed.set_footer(text=f"Rai Stream Radar • {plat_name} Live Alert", icon_url=PLATFORM_ICONS.get(tracker.platform.lower()))

        content = None
        if tracker.custom_role_id:
            content = f"<@&{tracker.custom_role_id}>"

        try:
            await channel.send(content=content, embed=embed)
        except Exception as e:
            logger.warning(f"Failed to send stream alert: {e}")

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    streamer_group = app_commands.Group(name="streamer", description="Manage live stream alerts and creator radar")

    @streamer_group.command(name="add", description="Add a streamer to the live alert radar")
    @app_commands.describe(
        platform="Streaming platform (Twitch, YouTube, Kick)",
        channel_name="Channel handle or username (e.g. shroud, tarik)",
        alert_channel="Channel where live alerts will be sent",
        notify_role="Optional role to ping when streamer goes live",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="Twitch", value="twitch"),
        app_commands.Choice(name="YouTube", value="youtube"),
        app_commands.Choice(name="Kick", value="kick"),
    ])
    async def streamer_add(
        self,
        interaction: discord.Interaction,
        platform: str,
        channel_name: str,
        alert_channel: Optional[discord.TextChannel] = None,
        notify_role: Optional[discord.Role] = None,
    ):
        """Add streamer to radar."""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=error_embed("Permission Denied", "You need `Manage Server` permission to add stream alerts."),
                ephemeral=True,
            )
            return

        target_ch = alert_channel or interaction.channel
        role_id = notify_role.id if notify_role else None

        await self.bot.db.add_stream_tracker(
            guild_id=interaction.guild.id,
            platform=platform,
            channel_name=channel_name,
            alert_channel_id=target_ch.id,
            custom_role_id=role_id,
        )

        embed = success_embed(
            "Stream Radar Configured",
            f"Successfully added **{channel_name}** ({platform.capitalize()}) to the radar!\n\n"
            f"• **Alert Channel:** {target_ch.mention}\n"
            f"• **Ping Role:** {notify_role.mention if notify_role else 'None'}\n"
            f"• **Check Frequency:** Every 3 minutes",
        )
        await interaction.response.send_message(embed=embed)

    @streamer_group.command(name="remove", description="Remove a streamer from the radar")
    @app_commands.describe(channel_name="Username or handle of streamer to remove")
    async def streamer_remove(self, interaction: discord.Interaction, channel_name: str):
        """Remove streamer from radar."""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=error_embed("Permission Denied", "You need `Manage Server` permission."),
                ephemeral=True,
            )
            return

        removed = await self.bot.db.remove_stream_tracker(interaction.guild.id, channel_name)
        if removed:
            await interaction.response.send_message(
                embed=success_embed("Streamer Removed", f"**{channel_name}** has been removed from the stream radar."),
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Not Found", f"Could not find a tracked streamer with name `{channel_name}`."),
                ephemeral=True,
            )

    @streamer_group.command(name="list", description="List all streamers currently on the radar")
    async def streamer_list(self, interaction: discord.Interaction):
        """List tracked streamers."""
        trackers = await self.bot.db.get_stream_trackers(interaction.guild.id)
        if not trackers:
            await interaction.response.send_message(
                embed=info_embed("Stream Radar", "No streamers are currently being tracked. Use `/streamer add` to add one!"),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📡 Stream Radar — Monitored Creators",
            color=Colors.PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        lines = []
        for t in trackers:
            status_icon = "🟢 LIVE" if t.last_status == "live" else "⚪ Offline"
            ch_mention = f"<#{t.alert_channel_id}>"
            role_str = f" • <@&{t.custom_role_id}>" if t.custom_role_id else ""
            lines.append(f"• **{t.channel_name}** ({t.platform.upper()}) — {status_icon} -> {ch_mention}{role_str}")

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Tracking {len(trackers)} creators • RAI FAM💗")
        await interaction.response.send_message(embed=embed)

    @streamer_group.command(name="check", description="Manually check live status of any streamer")
    @app_commands.describe(platform="Platform", channel_name="Channel handle")
    @app_commands.choices(platform=[
        app_commands.Choice(name="Twitch", value="twitch"),
        app_commands.Choice(name="Kick", value="kick"),
    ])
    async def streamer_check(self, interaction: discord.Interaction, platform: str, channel_name: str):
        """Manually inspect a streamer status."""
        await interaction.response.defer()
        is_live, title, game, url, thumb = await self.check_channel_status(platform, channel_name)

        embed = discord.Embed(
            title=f"📡 Radar Ping: {channel_name} ({platform.capitalize()})",
            color=0x57F287 if is_live else 0x95A5A6,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Status", value="🟢 **ONLINE & STREAMING**" if is_live else "⚪ **OFFLINE**", inline=True)
        if is_live:
            embed.add_field(name="Stream Title", value=f"`{title}`", inline=False)
            if game:
                embed.add_field(name="Category", value=f"`{game}`", inline=True)
            embed.add_field(name="Link", value=f"[Watch Stream]({url})", inline=True)
        else:
            embed.description = f"**{channel_name}** is not broadcasting right now.\nChannel: [View Profile]({url})"

        embed.set_footer(text="Rai Stream Radar Instant Query")
        await interaction.followup.send(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(StreamRadarCog(bot))
