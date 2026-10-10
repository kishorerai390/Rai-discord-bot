"""
Server Statistics Counter Cog for Rai Bot.
Creates and automatically maintains locked voice channel counters for:
- 📊 SERVER STATS 📊 (Category)
  🔒 All Members: {count}
  🔒 Members: {count}
  🔒 Bots: {count}
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.embeds import create_embed, error_embed, success_embed, info_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class ServerStatsCog(commands.Cog, name="ServerStats"):
    """Autonomous Server Stats Voice Counter Channels."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._update_locks: dict[int, float] = {}
        self.stats_sync_loop.start()
        self.realtime_consoles_sync_loop.start()

    def cog_unload(self) -> None:
        self.stats_sync_loop.cancel()
        self.realtime_consoles_sync_loop.cancel()

    stats_group = app_commands.Group(
        name="serverstats",
        description="Autonomous Server Stats voice counter channel management",
    )

    # ==========================================
    # BACKGROUND SYNC LOOPS
    # ==========================================

    @tasks.loop(seconds=60)
    async def realtime_consoles_sync_loop(self) -> None:
        """Periodically refreshes active real-time consoles with fresh telemetry and timestamps."""
        try:
            from utils.realtime_consoles import (
                REALTIME_CHANNELS,
                build_server_dashboard_payload,
                build_system_health_payload,
                build_admin_control_payload,
                build_gaming_hub_payload,
            )
            for guild in self.bot.guilds:
                # Update Server Dashboard
                dash_ch = guild.get_channel(REALTIME_CHANNELS.get("server_dashboard", 0))
                if isinstance(dash_ch, discord.TextChannel):
                    try:
                        async for msg in dash_ch.history(limit=5):
                            if msg.author.id == self.bot.user.id and msg.type == discord.MessageType.default:
                                p = build_server_dashboard_payload(guild, self.bot)
                                await msg.edit(embed=discord.Embed.from_dict(p["embeds"][0]))
                                break
                    except Exception:
                        pass

                # Update System Health
                health_ch = guild.get_channel(REALTIME_CHANNELS.get("system_health", 0))
                if isinstance(health_ch, discord.TextChannel):
                    try:
                        async for msg in health_ch.history(limit=5):
                            if msg.author.id == self.bot.user.id and msg.type == discord.MessageType.default:
                                p = build_system_health_payload(guild, self.bot)
                                await msg.edit(embed=discord.Embed.from_dict(p["embeds"][0]))
                                break
                    except Exception:
                        pass

                # Update Gaming Hub
                game_ch = guild.get_channel(REALTIME_CHANNELS.get("gaming_hub", 0))
                if isinstance(game_ch, discord.TextChannel):
                    try:
                        async for msg in game_ch.history(limit=5):
                            if msg.author.id == self.bot.user.id and msg.type == discord.MessageType.default:
                                p = build_gaming_hub_payload(guild, self.bot)
                                await msg.edit(embed=discord.Embed.from_dict(p["embeds"][0]))
                                break
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"realtime_consoles_sync_loop notice: {e}")

    @realtime_consoles_sync_loop.before_loop
    async def before_realtime_sync(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass

    @tasks.loop(minutes=10)
    async def stats_sync_loop(self) -> None:
        """Periodically synchronizes all server stats counters respecting Discord rate limits."""
        for guild in self.bot.guilds:
            try:
                await self.update_guild_stats(guild)
            except Exception as e:
                logger.error(f"Error in stats_sync_loop for {guild.name} ({guild.id}): {e}")

    @stats_sync_loop.before_loop
    async def before_stats_sync(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass

    # ==========================================
    # EVENT LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Debounced counter update when a member joins."""
        await self._debounced_update(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Debounced counter update when a member leaves."""
        await self._debounced_update(member.guild)

    async def _debounced_update(self, guild: discord.Guild) -> None:
        """Schedules a safe delayed update to avoid Discord 2-renames-per-10-min rate limits."""
        now = asyncio.get_event_loop().time()
        last_update = self._update_locks.get(guild.id, 0.0)

        # Discord rate limits channel renames to 2 per 10 minutes.
        # We debounce and throttle rapid joins/leaves.
        if now - last_update >= 300.0:  # 5 minutes minimum between automated renames
            self._update_locks[guild.id] = now
            await self.update_guild_stats(guild)

    # ==========================================
    # CORE SYNC LOGIC
    # ==========================================

    async def update_guild_stats(self, guild: discord.Guild) -> bool:
        """Updates the counter channel names for a guild."""
        cfg = await self.bot.db.get_or_create_server_stats_config(guild.id)
        if not cfg.enabled:
            return False

        # Calculate accurate member numbers
        # If guild members cache is not full, fetch
        if guild.member_count and len(guild.members) < guild.member_count:
            try:
                await guild.chunk()
            except Exception:
                pass

        total_members = guild.member_count or len(guild.members)
        bots = sum(1 for m in guild.members if m.bot)
        humans = total_members - bots

        updated_any = False

        # 1. Update All Members Channel
        if cfg.all_members_channel_id:
            ch_all = guild.get_channel(cfg.all_members_channel_id)
            if ch_all and isinstance(ch_all, discord.VoiceChannel):
                expected_name = f"🔒・👥・𝓐ʟʟ・𝓜ᴇᴍʙᴇʀs: {total_members}"
                if ch_all.name != expected_name:
                    try:
                        await ch_all.edit(name=expected_name, reason="Rai ServerStats: Auto count sync")
                        updated_any = True
                    except discord.HTTPException as e:
                        logger.warning(f"Rate limited or failed updating All Members on {guild.name}: {e}")

        # 2. Update Members Channel
        if cfg.members_channel_id:
            ch_mem = guild.get_channel(cfg.members_channel_id)
            if ch_mem and isinstance(ch_mem, discord.VoiceChannel):
                expected_name = f"🔒・👤・𝓜ᴇᴍʙᴇʀs: {humans}"
                if ch_mem.name != expected_name:
                    try:
                        await ch_mem.edit(name=expected_name, reason="Rai ServerStats: Auto count sync")
                        updated_any = True
                    except discord.HTTPException as e:
                        logger.warning(f"Rate limited or failed updating Members on {guild.name}: {e}")

        # 3. Update Bots Channel
        if cfg.bots_channel_id:
            ch_bot = guild.get_channel(cfg.bots_channel_id)
            if ch_bot and isinstance(ch_bot, discord.VoiceChannel):
                expected_name = f"🔒・🤖・𝓑ᴏᴛs: {bots}"
                if ch_bot.name != expected_name:
                    try:
                        await ch_bot.edit(name=expected_name, reason="Rai ServerStats: Auto count sync")
                        updated_any = True
                    except discord.HTTPException as e:
                        logger.warning(f"Rate limited or failed updating Bots on {guild.name}: {e}")

        return updated_any

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @stats_group.command(name="setup", description="Deploy or link the locked Server Stats counter channels")
    @app_commands.default_permissions(administrator=True)
    async def stats_setup(self, interaction: discord.Interaction) -> None:
        """Deploys or refreshes the locked voice counter channels."""
        if not interaction.guild:
            await interaction.response.send_message(
                embed=error_embed("This command can only be used in a server."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        if not guild.me.guild_permissions.manage_channels:
            await interaction.followup.send(
                embed=error_embed("Rai lacks the **Manage Channels** permission to create or edit counters."),
                ephemeral=True,
            )
            return

        cfg = await self.bot.db.get_or_create_server_stats_config(guild.id)

        # Permission overwrites: Locked voice channel (no connect for @everyone)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True),
        }

        # Find or create category
        category = None
        if cfg.category_id:
            category = guild.get_channel(cfg.category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            # Check if one already exists named 'SERVER STATS'
            for cat in guild.categories:
                if "server" in cat.name.lower() and "stat" in cat.name.lower():
                    category = cat
                    break

        cat_title = "╭━━━ 📊 ╏ 𝓢ᴇʀᴠᴇʀ・𝕾ᴛᴀᴛs ━━━╮"
        if not category:
            category = await guild.create_category(
                name=cat_title,
                position=0,
                reason="Rai ServerStats: Created stats category",
            )
        else:
            if category.name != cat_title:
                await category.edit(name=cat_title)

        total_members = guild.member_count or len(guild.members)
        bots = sum(1 for m in guild.members if m.bot)
        humans = total_members - bots

        # 1. All Members channel
        ch_all = None
        if cfg.all_members_channel_id:
            ch_all = guild.get_channel(cfg.all_members_channel_id)
        if not ch_all or not isinstance(ch_all, discord.VoiceChannel):
            for vc in category.voice_channels:
                if "all" in vc.name.lower():
                    ch_all = vc
                    break
        name_all = f"🔒・👥・𝓐ʟʟ・𝓜ᴇᴍʙᴇʀs: {total_members}"
        if not ch_all:
            ch_all = await guild.create_voice_channel(
                name=name_all,
                category=category,
                overwrites=overwrites,
                reason="Rai ServerStats: Created All Members counter",
            )
        else:
            await ch_all.edit(name=name_all, overwrites=overwrites)

        # 2. Members channel
        ch_mem = None
        if cfg.members_channel_id:
            ch_mem = guild.get_channel(cfg.members_channel_id)
        if not ch_mem or not isinstance(ch_mem, discord.VoiceChannel):
            for vc in category.voice_channels:
                if "members" in vc.name.lower() and "all" not in vc.name.lower():
                    ch_mem = vc
                    break
        name_mem = f"🔒・👤・𝓜ᴇᴍʙᴇʀs: {humans}"
        if not ch_mem:
            ch_mem = await guild.create_voice_channel(
                name=name_mem,
                category=category,
                overwrites=overwrites,
                reason="Rai ServerStats: Created Members counter",
            )
        else:
            await ch_mem.edit(name=name_mem, overwrites=overwrites)

        # 3. Bots channel
        ch_bot = None
        if cfg.bots_channel_id:
            ch_bot = guild.get_channel(cfg.bots_channel_id)
        if not ch_bot or not isinstance(ch_bot, discord.VoiceChannel):
            for vc in category.voice_channels:
                if "bots" in vc.name.lower() or "bot" in vc.name.lower():
                    ch_bot = vc
                    break
        name_bot = f"🔒・🤖・𝓑ᴏᴛs: {bots}"
        if not ch_bot:
            ch_bot = await guild.create_voice_channel(
                name=name_bot,
                category=category,
                overwrites=overwrites,
                reason="Rai ServerStats: Created Bots counter",
            )
        else:
            await ch_bot.edit(name=name_bot, overwrites=overwrites)

        # Save IDs to DB
        await self.bot.db.update_server_stats_config(
            guild.id,
            enabled=1,
            category_id=category.id,
            all_members_channel_id=ch_all.id,
            members_channel_id=ch_mem.id,
            bots_channel_id=ch_bot.id,
        )

        embed = success_embed(
            "📊 Server Stats Configured",
            f"Successfully setup locked server statistics counters:\n\n"
            f"• **Category**: `{category.name}`\n"
            f"• 🔒 **All Members**: `{ch_all.name}`\n"
            f"• 🔒 **Members**: `{ch_mem.name}`\n"
            f"• 🔒 **Bots**: `{ch_bot.name}`\n\n"
            f"*Counters automatically synchronize when members join/leave and on a 10-minute heartbeat.*",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @stats_group.command(name="update", description="Force an immediate refresh of server statistics counters")
    @app_commands.default_permissions(administrator=True)
    async def stats_update(self, interaction: discord.Interaction) -> None:
        """Forces an immediate synchronization of the counter channels."""
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        await self.update_guild_stats(interaction.guild)
        await interaction.followup.send(
            embed=success_embed("Updated", "Server statistics counters have been refreshed."),
            ephemeral=True,
        )

    @stats_group.command(name="disable", description="Disable automatic server statistics counter updates")
    @app_commands.default_permissions(administrator=True)
    async def stats_disable(self, interaction: discord.Interaction) -> None:
        """Disables the stats counter updates."""
        if not interaction.guild:
            return
        await self.bot.db.update_server_stats_config(interaction.guild.id, enabled=0)
        await interaction.response.send_message(
            embed=info_embed("Disabled", "Server statistics counters have been disabled."),
            ephemeral=True,
        )


async def setup(bot: SentinelBot) -> None:
    await bot.add_cog(ServerStatsCog(bot))
