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
from collections import defaultdict
from datetime import datetime, timezone, timedelta
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
    """Autonomous Server Stats Voice Counter Channels & Self-Driving Background Loops."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._update_locks: dict[int, float] = {}
        self._daily_activity_tracker: dict[tuple[int, int], int] = defaultdict(int)
        self._member_birthdays: dict[tuple[int, int], tuple[int, int]] = {}
        self.stats_sync_loop.start()
        self.realtime_consoles_sync_loop.start()
        self.chatter_of_the_day_loop.start()
        self.expired_invites_loop.start()
        self.birthday_check_loop.start()
        self.db_maintenance_loop.start()
        self.invite_health_monitor_loop.start()

    def cog_unload(self) -> None:
        self.stats_sync_loop.cancel()
        self.realtime_consoles_sync_loop.cancel()
        self.chatter_of_the_day_loop.cancel()
        self.expired_invites_loop.cancel()
        self.birthday_check_loop.cancel()
        self.db_maintenance_loop.cancel()
        self.invite_health_monitor_loop.cancel()

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
        online_members = sum(1 for m in guild.members if m.status != discord.Status.offline)

        # Active VC metrics
        active_vcs = [
            vc for vc in guild.voice_channels
            if len(vc.members) > 0 and vc.id not in (cfg.all_members_channel_id, cfg.members_channel_id, cfg.bots_channel_id)
        ]
        vc_users = sum(len(vc.members) for vc in active_vcs)

        updated_any = False

        # 1. Update Server Status Channel (Dual-metric matching reference: 🦋 {online} online 🦋 {total} members)
        if cfg.all_members_channel_id:
            ch_all = guild.get_channel(cfg.all_members_channel_id)
            if ch_all and isinstance(ch_all, discord.VoiceChannel):
                expected_name = f"🦋 {online_members} online 🦋 {total_members} members"
                if ch_all.name != expected_name:
                    try:
                        await ch_all.edit(name=expected_name, reason="Rai ServerStats: Aesthetic count sync")
                        updated_any = True
                    except discord.HTTPException as e:
                        logger.warning(f"Rate limited or failed updating Server Status on {guild.name}: {e}")

        # 2. Update VC Status Channel (Dual-metric matching reference: 🦋 {vc_users} vc user 🦋 {len(active_vcs)} Active vc)
        if cfg.members_channel_id:
            ch_mem = guild.get_channel(cfg.members_channel_id)
            if ch_mem and isinstance(ch_mem, discord.VoiceChannel):
                expected_name = f"🦋 {vc_users} vc user 🦋 {len(active_vcs)} Active vc"
                if ch_mem.name != expected_name:
                    try:
                        await ch_mem.edit(name=expected_name, reason="Rai ServerStats: Aesthetic count sync")
                        updated_any = True
                    except discord.HTTPException as e:
                        logger.warning(f"Rate limited or failed updating VC Status on {guild.name}: {e}")

        # 3. Update Bots / Boosts Channel (if still configured)
        if cfg.bots_channel_id:
            ch_bot = guild.get_channel(cfg.bots_channel_id)
            if ch_bot and isinstance(ch_bot, discord.VoiceChannel):
                if getattr(guild, "premium_subscription_count", 0) > 0:
                    expected_name = f"🔒・💎・𝓑ᴏᴏsᴛs: {guild.premium_subscription_count} (Tier {guild.premium_tier})"
                else:
                    expected_name = f"🔒・🤖・𝓑ᴏᴛs: {bots}"
                if ch_bot.name != expected_name:
                    try:
                        await ch_bot.edit(name=expected_name, reason="Rai ServerStats: Auto count sync")
                        updated_any = True
                    except discord.HTTPException as e:
                        logger.warning(f"Rate limited or failed updating Bots/Boosts on {guild.name}: {e}")

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
        if getattr(guild, "premium_subscription_count", 0) > 0:
            name_bot = f"🔒・💎・𝓑ᴏᴏsᴛs: {guild.premium_subscription_count} (Tier {guild.premium_tier})"
        else:
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

    # ==========================================
    # AUTONOMOUS BACKGROUND ENGINES (ZERO CLUTTER)
    # ==========================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Tracks daily member activity for Chatter of the Day."""
        if message.author.bot or not message.guild:
            return
        key = (message.guild.id, message.author.id)
        self._daily_activity_tracker[key] = self._daily_activity_tracker.get(key, 0) + 1

    @tasks.loop(hours=24)
    async def chatter_of_the_day_loop(self) -> None:
        """Automatically calculates and awards Chatter of the Day every 24 hours."""
        for guild in self.bot.guilds:
            try:
                guild_scores = {
                    uid: pts for (gid, uid), pts in self._daily_activity_tracker.items() if gid == guild.id
                }
                if not guild_scores:
                    continue
                top_uid = max(guild_scores, key=guild_scores.get)
                winner = guild.get_member(top_uid)
                if not winner:
                    continue

                role = discord.utils.get(guild.roles, name="✦ Chatter of the Day ✦")
                if not role and guild.me.guild_permissions.manage_roles:
                    try:
                        role = await guild.create_role(
                            name="✦ Chatter of the Day ✦",
                            color=discord.Color.gold(),
                            hoist=False,
                            reason="Autonomous: Auto-created Chatter of the Day role",
                        )
                    except Exception:
                        role = None

                role_pos = getattr(role, "position", 0)
                bot_pos = getattr(guild.me.top_role, "position", 0)
                if role and guild.me.guild_permissions.manage_roles and role_pos < bot_pos:
                    for prev_member in list(role.members):
                        if prev_member.id != winner.id:
                            try:
                                await prev_member.remove_roles(role, reason="Chatter of the Day 24h rotation")
                            except Exception:
                                pass
                    try:
                        await winner.add_roles(role, reason="Awarded Chatter of the Day")
                    except Exception:
                        pass

                general_ch = guild.get_channel(1545502730699808768) or guild.system_channel
                if isinstance(general_ch, discord.TextChannel):
                    pts = guild_scores[top_uid]
                    embed = discord.Embed(
                        title="👑 ✦ 𝓒ʜᴀᴛᴛᴇʀ ᴏғ ᴛʜᴇ 𝓓ᴀʏ ✦ 👑",
                        description=(
                            f"Congratulations to {winner.mention} ({winner.display_name})!\n\n"
                            f"They earned **{pts} activity points** in the last 24 hours and have been awarded the **✦ Chatter of the Day ✦** role! 🌟"
                        ),
                        color=0xF1C40F,
                    )
                    if winner.display_avatar:
                        embed.set_thumbnail(url=winner.display_avatar.url)
                    embed.set_footer(text="✦ ʀᴀɪ Autonomous Ecosystem • Daily Activity Engine ✦")
                    await general_ch.send(embed=embed)
            except Exception as e:
                logger.debug(f"chatter_of_the_day_loop error for {guild.id}: {e}")

        # Reset scores for next cycle
        self._daily_activity_tracker.clear()

    @chatter_of_the_day_loop.before_loop
    async def before_chatter_loop(self) -> None:
        try:
            ready_call = self.bot.wait_until_ready()
            if asyncio.iscoroutine(ready_call):
                await ready_call
        except Exception:
            pass

    @tasks.loop(hours=6)
    async def expired_invites_loop(self) -> None:
        """Autonomously purges expired and dead invite links."""
        for guild in self.bot.guilds:
            if not guild.me.guild_permissions.manage_guild:
                continue
            try:
                invites = await guild.invites()
                now = datetime.now(timezone.utc)
                for inv in invites:
                    max_age = getattr(inv, "max_age", 0)
                    created_at = getattr(inv, "created_at", None)
                    max_uses = getattr(inv, "max_uses", 0)
                    uses = getattr(inv, "uses", 0)
                    is_expired_time = isinstance(max_age, (int, float)) and max_age > 0 and created_at and (created_at + timedelta(seconds=max_age) <= now)
                    is_expired_uses = isinstance(max_uses, int) and max_uses > 0 and isinstance(uses, int) and uses >= max_uses
                    if is_expired_time or is_expired_uses:
                        try:
                            await inv.delete(reason="Auto Invites Purge: Invite has expired or exceeded maximum uses")
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"expired_invites_loop error in {guild.id}: {e}")

    @expired_invites_loop.before_loop
    async def before_invites_loop(self) -> None:
        try:
            ready_call = self.bot.wait_until_ready()
            if asyncio.iscoroutine(ready_call):
                await ready_call
        except Exception:
            pass

    @tasks.loop(hours=24)
    async def birthday_check_loop(self) -> None:
        """Checks and celebrates member birthdays in #general-chat."""
        now = datetime.now(timezone.utc)
        today_month = now.month
        today_day = now.day

        for guild in self.bot.guilds:
            general_ch = guild.get_channel(1545502730699808768) or guild.system_channel
            if not isinstance(general_ch, discord.TextChannel):
                continue

            for (gid, uid), (b_m, b_d) in self._member_birthdays.items():
                if gid == guild.id and b_m == today_month and b_d == today_day:
                    member = guild.get_member(uid)
                    if member:
                        embed = discord.Embed(
                            title="🎂 ✦ 𝓗ᴀᴘᴘʏ 𝓑ɪʀᴛʜᴅᴀʏ! ✦ 🎂",
                            description=(
                                f"Wishing a very **Happy Birthday** to {member.mention}! 🎉\n\n"
                                f"Drop your warm wishes and celebrate their special day! 🍰🎈"
                            ),
                            color=0xFF69B4,
                        )
                        if member.display_avatar:
                            embed.set_thumbnail(url=member.display_avatar.url)
                        embed.set_footer(text="✦ ʀᴀɪ Autonomous Ecosystem • Birthday Celebrations ✦")
                        try:
                            await general_ch.send(embed=embed)
                        except Exception:
                            pass

    @birthday_check_loop.before_loop
    async def before_birthday_loop(self) -> None:
        try:
            ready_call = self.bot.wait_until_ready()
            if asyncio.iscoroutine(ready_call):
                await ready_call
        except Exception:
            pass

    @tasks.loop(hours=24)
    async def db_maintenance_loop(self) -> None:
        """Performs nightly SQLite database VACUUM & self-healing maintenance."""
        try:
            db_conn = getattr(self.bot.db, "_db", None)
            if db_conn:
                await db_conn.execute("VACUUM")
                await db_conn.execute("PRAGMA optimize")
                logger.info("Autonomous DB Maintenance: Executed VACUUM and PRAGMA optimize successfully.")
        except Exception as e:
            logger.debug(f"db_maintenance_loop notice: {e}")

    @db_maintenance_loop.before_loop
    async def before_db_maintenance_loop(self) -> None:
        try:
            ready_call = self.bot.wait_until_ready()
            if asyncio.iscoroutine(ready_call):
                await ready_call
        except Exception:
            pass

    @tasks.loop(hours=12)
    async def invite_health_monitor_loop(self) -> None:
        """Monitors that guilds have at least one permanent active invite link."""
        for guild in self.bot.guilds:
            if not guild.me.guild_permissions.manage_guild:
                continue
            try:
                invites = await guild.invites()
                permanent_invites = [inv for inv in invites if inv.max_age == 0 and inv.max_uses == 0]
                if not permanent_invites:
                    from utils.owner_reporter import OwnerReporter
                    OwnerReporter.send_security_report(
                        self.bot,
                        guild.id,
                        event="Invite Link Health Warning",
                        user=None,
                        action_taken="Owner Notification",
                        severity="MEDIUM",
                        details={
                            "Warning": "No permanent invite links detected",
                            "Recommendation": "Create a permanent invite link to avoid losing prospective members",
                        },
                    )
            except Exception as e:
                logger.debug(f"invite_health_monitor_loop error in {guild.id}: {e}")

    @invite_health_monitor_loop.before_loop
    async def before_invite_health_loop(self) -> None:
        try:
            ready_call = self.bot.wait_until_ready()
            if asyncio.iscoroutine(ready_call):
                await ready_call
        except Exception:
            pass

    birthday_group = app_commands.Group(
        name="birthday",
        description="Birthday registry and automatic celebration shoutouts",
    )

    @birthday_group.command(name="set", description="Register your birthday for an automatic server shoutout")
    @app_commands.describe(month="Month (1-12)", day="Day (1-31)")
    async def birthday_set(self, interaction: discord.Interaction, month: int, day: int) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        if month < 1 or month > 12 or day < 1 or day > 31:
            await interaction.response.send_message("❌ Invalid date. Please enter a valid month (1-12) and day (1-31).", ephemeral=True)
            return

        self._member_birthdays[(interaction.guild.id, interaction.user.id)] = (month, day)
        embed = discord.Embed(
            title="🎂 Birthday Registered",
            description=f"Your birthday is set to **{month:02d}/{day:02d}**!\nWe will automatically celebrate you in **#general-chat** on your special day! 🎉",
            color=0xFF69B4,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @birthday_group.command(name="check", description="Check registered birthday")
    @app_commands.describe(member="Member to check (defaults to yourself)")
    async def birthday_check(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        target = member or interaction.user
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        bday = self._member_birthdays.get((guild.id, target.id))
        if bday:
            m, d = bday
            await interaction.response.send_message(f"🎂 **{target.display_name}**'s birthday is **{m:02d}/{d:02d}**.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ No birthday registered for **{target.display_name}**. Use `/birthday set` to register!", ephemeral=True)


async def setup(bot: SentinelBot) -> None:
    await bot.add_cog(ServerStatsCog(bot))
