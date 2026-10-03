"""
Rai Fast Gaming Matchmaker Cog.
Features:
- Instant Squad Finder for BGMI, Free Fire, Valorant, Apex Legends, & Casual Gaming.
- Interactive persistent matchmaking panel with dynamic queues.
- Automated squad formation: When full, moves players into Rai Suites voice channels.
- Match history logging and notifications.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Set
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

GAME_PRESETS = {
    "bgmi_duo": {"game": "BGMI / PUBG Mobile", "mode": "Duo", "size": 2, "emoji": "🔫"},
    "bgmi_squad": {"game": "BGMI / PUBG Mobile", "mode": "Squad", "size": 4, "emoji": "🔫"},
    "ff_duo": {"game": "Free Fire", "mode": "Duo", "size": 2, "emoji": "🔥"},
    "ff_squad": {"game": "Free Fire", "mode": "Squad", "size": 4, "emoji": "🔥"},
    "val_duo": {"game": "Valorant", "mode": "Duo", "size": 2, "emoji": "🎯"},
    "val_trio": {"game": "Valorant", "mode": "Trio", "size": 3, "emoji": "🎯"},
    "val_full": {"game": "Valorant", "mode": "5-Stack", "size": 5, "emoji": "🎯"},
    "apex_trio": {"game": "Apex Legends", "mode": "Trio", "size": 3, "emoji": "⚡"},
    "casual_squad": {"game": "Casual Arcade", "mode": "Party of 4", "size": 4, "emoji": "🎮"},
}


class MatchmakerQueueManager:
    """In-memory active queues: (guild_id, preset_key) -> set of user_ids."""

    def __init__(self):
        self._queues: Dict[tuple[int, str], List[int]] = {}
        self._lock = asyncio.Lock()

    async def add_player(self, guild_id: int, preset_key: str, user_id: int) -> tuple[List[int], bool]:
        """
        Adds player to queue. Returns (current_queue_players, is_full).
        Removes player from any other queue in the guild.
        """
        async with self._lock:
            # Remove from other queues in same guild
            for k in list(self._queues.keys()):
                if k[0] == guild_id and user_id in self._queues[k]:
                    self._queues[k].remove(user_id)

            key = (guild_id, preset_key)
            if key not in self._queues:
                self._queues[key] = []

            if user_id not in self._queues[key]:
                self._queues[key].append(user_id)

            target_size = GAME_PRESETS[preset_key]["size"]
            if len(self._queues[key]) >= target_size:
                matched_players = self._queues[key][:target_size]
                # Remove matched players from queue
                self._queues[key] = self._queues[key][target_size:]
                return matched_players, True

            return list(self._queues[key]), False

    async def remove_player(self, guild_id: int, user_id: int) -> Optional[str]:
        """Removes player from all queues in guild. Returns preset_key if removed."""
        async with self._lock:
            for k in list(self._queues.keys()):
                if k[0] == guild_id and user_id in self._queues[k]:
                    self._queues[k].remove(user_id)
                    return k[1]
            return None

    async def get_queue_status(self, guild_id: int) -> Dict[str, List[int]]:
        """Returns snapshot of all active queues in guild."""
        async with self._lock:
            status = {}
            for (g_id, p_key), users in self._queues.items():
                if g_id == guild_id and users:
                    status[p_key] = list(users)
            return status


QUEUE_MANAGER = MatchmakerQueueManager()


class QueueSelectModal(discord.ui.View):
    def __init__(self, bot: SentinelBot):
        super().__init__(timeout=60)
        self.bot = bot

        options = []
        for key, p in GAME_PRESETS.items():
            options.append(
                discord.SelectOption(
                    label=f"{p['game']} ({p['mode']})",
                    description=f"Party Size: {p['size']} players",
                    value=key,
                    emoji=p["emoji"],
                )
            )

        select = discord.ui.Select(
            placeholder="Select a game & party size to queue for...",
            min_values=1,
            max_values=1,
            options=options,
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        preset_key = interaction.data["values"][0]
        preset = GAME_PRESETS[preset_key]
        guild = interaction.guild
        user = interaction.user

        matched, is_full = await QUEUE_MANAGER.add_player(guild.id, preset_key, user.id)

        if not is_full:
            current_count = len(matched)
            target = preset["size"]
            await interaction.response.send_message(
                embed=info_embed(
                    f"Joined {preset['game']} Queue",
                    f"🎮 You are queued for **{preset['game']} ({preset['mode']})**!\n\n"
                    f"👥 **Waiting:** `{current_count}/{target}` players\n"
                    f"⚡ We will ping you and move you to a Rai Suite as soon as the squad fills!",
                ),
                ephemeral=True,
            )
            return

        # SQUAD IS FULL! Execute pairing
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            embed=success_embed(
                "Squad Matched!",
                f"🎉 Your **{preset['game']} ({preset['mode']})** team is ready! Check the announcement below.",
            ),
            ephemeral=True,
        )

        # Execute match dispatch in channel
        await dispatch_matched_squad(self.bot, interaction.channel, guild, preset_key, matched)


class MatchmakerPanelView(discord.ui.View):
    def __init__(self, bot: SentinelBot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Find Squad / Match", style=discord.ButtonStyle.primary, emoji="🎮", custom_id="rai_mm_find")
    async def find_squad_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = QueueSelectModal(self.bot)
        await interaction.response.send_message("Select your game to enter the matchmaking lobby:", view=view, ephemeral=True)

    @discord.ui.button(label="Active Queues", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="rai_mm_status")
    async def status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        status = await QUEUE_MANAGER.get_queue_status(interaction.guild_id)
        if not status:
            await interaction.response.send_message(
                embed=info_embed("Lobby Status", "No active matchmaking queues right now.\nClick **[Find Squad / Match]** to be the first!"),
                ephemeral=True,
            )
            return

        lines = []
        for key, uids in status.items():
            preset = GAME_PRESETS[key]
            lines.append(f"• {preset['emoji']} **{preset['game']} ({preset['mode']}):** `{len(uids)}/{preset['size']}` players waiting")

        embed = create_embed(
            title="🎮 Active Matchmaker Queues",
            description="\n".join(lines),
            color=Colors.PRIMARY,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Leave Queue", style=discord.ButtonStyle.danger, emoji="❌", custom_id="rai_mm_leave")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        removed_key = await QUEUE_MANAGER.remove_player(interaction.guild_id, interaction.user.id)
        if removed_key:
            preset = GAME_PRESETS[removed_key]
            await interaction.response.send_message(
                embed=info_embed("Left Queue", f"You left the queue for **{preset['game']} ({preset['mode']})**."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("ℹ️ You were not in any active queue.", ephemeral=True)


async def dispatch_matched_squad(
    bot: SentinelBot,
    channel: discord.TextChannel | discord.Thread,
    guild: discord.Guild,
    preset_key: str,
    player_ids: List[int],
):
    """Handles channel announcement and automated voice suite allocation."""
    preset = GAME_PRESETS[preset_key]
    mentions = [f"<@{uid}>" for uid in player_ids]

    # Look for an available Suite in '🍸 ┃ RAI SUITES'
    suites_cat = discord.utils.get(guild.categories, name="🍸 ┃ RAI SUITES")
    assigned_vc = None
    if suites_cat:
        for vc in suites_cat.voice_channels:
            if len(vc.members) == 0:
                assigned_vc = vc
                break

    # If all suites full, look in casual gaming or create temp
    if not assigned_vc:
        for vc in guild.voice_channels:
            if "Suite" in vc.name or "Lounge" in vc.name:
                if len(vc.members) == 0:
                    assigned_vc = vc
                    break

    # Move voice-connected players automatically
    moved_count = 0
    if assigned_vc:
        for uid in player_ids:
            member = guild.get_member(uid)
            if member and member.voice and member.voice.channel:
                try:
                    await member.move_to(assigned_vc, reason="Rai Matchmaker: Squad assembled")
                    moved_count += 1
                except Exception:
                    pass

    # Record to DB
    try:
        await bot.db.record_matchmaker_history(
            guild_id=guild.id,
            game=preset["game"],
            mode=preset["mode"],
            player_ids=player_ids,
            voice_channel_id=assigned_vc.id if assigned_vc else None,
        )
    except Exception as e:
        logger.warning(f"Failed to log matchmaker history: {e}")

    # Build Announcement Embed
    embed = discord.Embed(
        title=f"⚔️ {preset['emoji']} Squad Match Found! — {preset['game']}",
        description=(
            f"🎉 Team formed for **{preset['game']} ({preset['mode']})**!\n\n"
            f"👥 **Roster:**\n" + "\n".join(f"• {m}" for m in mentions) + "\n\n"
            + (f"🍸 **Allocated Voice Suite:** {assigned_vc.mention} ({moved_count} moved automatically)\n" if assigned_vc else "🎙️ *Please hop into any open Voice Suite in `🍸 ┃ RAI SUITES`!*\n")
            + "⚡ *Good luck and bring home the victory!*"
        ),
        color=Colors.SUCCESS,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_footer(text="Rai Gaming Matchmaker • RAI FAM💗")

    try:
        await channel.send(content=" ".join(mentions), embed=embed)
    except Exception as e:
        logger.warning(f"Could not send matchmaker announcement: {e}")


class MatchmakerCog(commands.Cog, name="Matchmaker"):
    """Gaming Squad Finder & Matchmaker."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    matchmaker_group = app_commands.Group(
        name="matchmaker",
        description="Fast Gaming Squad Finder & Matchmaking Hub",
    )

    @matchmaker_group.command(name="panel", description="Post the interactive Gaming Matchmaker Lobby Panel")
    @is_admin_or_owner()
    @app_commands.describe(channel="Target channel to deploy panel into (default: current)")
    async def deploy_panel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Deploy panel."""
        target_ch = channel or interaction.channel
        if not isinstance(target_ch, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("❌ Target must be a text channel.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚔️ RAI FAM — Gaming Matchmaker Lobby",
            description=(
                "Looking for a Duo partner or full Squad?\n"
                "Queue up with server members for competitive & casual games!\n\n"
                "**Supported Titles:**\n"
                "• 🔫 **BGMI / PUBG Mobile** (Duo & Squad)\n"
                "• 🔥 **Free Fire** (Duo & Squad)\n"
                "• 🎯 **Valorant** (Duo, Trio & 5-Stack)\n"
                "• ⚡ **Apex Legends** (Trio)\n"
                "• 🎮 **Casual Arcade & Party**\n\n"
                "⚡ **How it works:**\n"
                "1. Click **[Find Squad / Match]** and select your game.\n"
                "2. When your team fills, Rai instantly pings you and moves your party into a private **Rai Suite**!\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x5865F2,
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text="RAI FAM💗 • 24/7 Matchmaking Engine")

        view = MatchmakerPanelView(self.bot)
        await target_ch.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Matchmaker Lobby Panel deployed to {target_ch.mention}!", ephemeral=True)

    @matchmaker_group.command(name="queue", description="Quickly join a matchmaking queue")
    @app_commands.describe(game="Game to queue for")
    @app_commands.choices(
        game=[
            app_commands.Choice(name="🔫 BGMI (Duo)", value="bgmi_duo"),
            app_commands.Choice(name="🔫 BGMI (Squad)", value="bgmi_squad"),
            app_commands.Choice(name="🔥 Free Fire (Duo)", value="ff_duo"),
            app_commands.Choice(name="🔥 Free Fire (Squad)", value="ff_squad"),
            app_commands.Choice(name="🎯 Valorant (Duo)", value="val_duo"),
            app_commands.Choice(name="🎯 Valorant (Trio)", value="val_trio"),
            app_commands.Choice(name="🎯 Valorant (5-Stack)", value="val_full"),
            app_commands.Choice(name="⚡ Apex Legends (Trio)", value="apex_trio"),
            app_commands.Choice(name="🎮 Casual Arcade", value="casual_squad"),
        ]
    )
    async def quick_queue(self, interaction: discord.Interaction, game: app_commands.Choice[str]):
        """Direct queue command."""
        preset_key = game.value
        preset = GAME_PRESETS[preset_key]
        guild = interaction.guild
        user = interaction.user

        matched, is_full = await QUEUE_MANAGER.add_player(guild.id, preset_key, user.id)

        if not is_full:
            await interaction.response.send_message(
                embed=info_embed(
                    f"Queued for {preset['game']}",
                    f"🎮 You are now waiting in **{preset['game']} ({preset['mode']})**!\n"
                    f"👥 `{len(matched)}/{preset['size']}` players ready.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message("🎉 Squad assembled! Directing party...", ephemeral=True)
        await dispatch_matched_squad(self.bot, interaction.channel, guild, preset_key, matched)

    @matchmaker_group.command(name="leave", description="Leave any active matchmaking queues")
    async def leave_queue(self, interaction: discord.Interaction):
        removed = await QUEUE_MANAGER.remove_player(interaction.guild_id, interaction.user.id)
        if removed:
            await interaction.response.send_message("✅ You have left the matchmaking queue.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ You were not in any queue.", ephemeral=True)

    @matchmaker_group.command(name="status", description="Check players currently waiting in matchmaking queues")
    async def check_status(self, interaction: discord.Interaction):
        status = await QUEUE_MANAGER.get_queue_status(interaction.guild_id)
        if not status:
            await interaction.response.send_message(
                embed=info_embed("Matchmaker Status", "No players currently queued."),
                ephemeral=True,
            )
            return

        lines = []
        for key, uids in status.items():
            p = GAME_PRESETS[key]
            lines.append(f"• {p['emoji']} **{p['game']} ({p['mode']}):** `{len(uids)}/{p['size']}` waiting")

        embed = create_embed(title="🎮 Active Queues", description="\n".join(lines), color=Colors.PRIMARY)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(MatchmakerCog(bot))
