"""
Rai Gaming Hub Cog.
Provides:
- LFG teammate finder with interactive join/leave/close buttons
- Temporary gaming room creation
- Gaming clips submission & community sharing
- Game recommendations across diverse genres
- Gaming tournament scheduling and announcement
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from database.models import GamingLFG
from utils.embeds import create_embed, error_embed, info_embed, success_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

GAME_RECOMMENDATIONS = {
    "action": [
        ("Helldivers 2", "Co-op shooter spreading managed democracy across the galaxy."),
        ("Apex Legends", "Fast-paced battle royale with movement mechanics and legendary abilities."),
        ("Monster Hunter: World", "Epic monster hunts with deep weapon masteries and co-op thrills."),
    ],
    "tactical": [
        ("Valorant", "5v5 tactical shooter with precise gunplay and agent abilities."),
        ("Rainbow Six Siege", "Destructive room-clearing tactical operator combat."),
        ("Counter-Strike 2", "Classic precision defusal and competitive esports action."),
    ],
    "rpg": [
        ("Baldur's Gate 3", "Story-rich D&D tactical turn-based masterpiece."),
        ("Elden Ring", "Challenging dark fantasy open-world action RPG."),
        ("Cyberpunk 2077", "High-octane futuristic story in neon Night City."),
    ],
    "coop": [
        ("It Takes Two", "Pure cooperative puzzle-platforming joy built for duos."),
        ("Deep Rock Galactic", "Dwarf miners digging and fighting alien swarms in procedural caves."),
        ("Lethal Company", "High-stress hilarious scavenging on eerie abandoned moons."),
    ],
    "chill": [
        ("Stardew Valley", "Peaceful farming, mining, and small-town friendship."),
        ("Minecraft", "Endless voxel building, exploring, and survival adventures."),
        ("Dave the Diver", "Catch fish by day, manage a bustling sushi bar by night."),
    ],
}


class LFGInteractiveView(discord.ui.View):
    def __init__(self, bot: SentinelBot, lfg_id: int, creator_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.lfg_id = lfg_id
        self.creator_id = creator_id

    @discord.ui.button(label="Join Team", style=discord.ButtonStyle.success, emoji="⚔️", custom_id="lfg_join_btn")
    async def join_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        lfg = await self.bot.db.get_gaming_lfg(self.lfg_id)
        if not lfg or lfg.status != "open":
            await interaction.followup.send("❌ This team recruitment is closed.", ephemeral=True)
            return

        if interaction.user.id in lfg.current_players:
            await interaction.followup.send("ℹ️ You are already on this team.", ephemeral=True)
            return

        if len(lfg.current_players) >= lfg.max_players:
            await interaction.followup.send("⚠️ This team is already full!", ephemeral=True)
            return

        lfg.current_players.append(interaction.user.id)
        status = "full" if len(lfg.current_players) >= lfg.max_players else "open"
        await self.bot.db.update_gaming_lfg_players(self.lfg_id, lfg.current_players, status)

        mentions = [f"<@{uid}>" for uid in lfg.current_players]
        needed = max(0, lfg.max_players - len(lfg.current_players))

        embed = interaction.message.embeds[0] if interaction.message.embeds else create_embed(title="LFG", description="")
        embed.set_field_at(
            2,
            name=f"👥 Roster ({len(lfg.current_players)}/{lfg.max_players})",
            value=", ".join(mentions) or "None",
            inline=False,
        )
        if status == "full":
            embed.color = Colors.SUCCESS
            embed.set_footer(text="Team Full! Ready to play.")
            from services.workspace_service import WorkspaceService, WorkspaceType
            try:
                creator = interaction.guild.get_member(self.creator_id) or interaction.user
                ws = await WorkspaceService.get_instance(self.bot).create_workspace(
                    guild=interaction.guild,
                    owner=creator,
                    workspace_type=WorkspaceType.GAMING,
                    name=f"{lfg.game} Squad",
                )
                if ws.chat_channel_id and ws.voice_channel_id:
                    embed.add_field(
                        name="🎮 Gaming Workspace Active",
                        value=f"💬 <#{ws.chat_channel_id}> | 🔊 <#{ws.voice_channel_id}>",
                        inline=False,
                    )
            except Exception as e:
                logger.warning(f"Could not auto-create gaming workspace: {e}")
        else:
            embed.set_footer(text=f"{needed} spot(s) still open. Click Join Team to participate.")

        await interaction.message.edit(embed=embed, view=self if status == "open" else None)
        await interaction.followup.send(f"✅ Joined **{lfg.game}** squad!", ephemeral=True)

    @discord.ui.button(label="Leave Team", style=discord.ButtonStyle.secondary, emoji="🚪", custom_id="lfg_leave_btn")
    async def leave_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        lfg = await self.bot.db.get_gaming_lfg(self.lfg_id)
        if not lfg or interaction.user.id not in lfg.current_players:
            await interaction.followup.send("❌ You are not on this team.", ephemeral=True)
            return

        if interaction.user.id == self.creator_id:
            await interaction.followup.send("⚠️ Team hosts cannot leave their own listing. Use Close LFG instead.", ephemeral=True)
            return

        lfg.current_players.remove(interaction.user.id)
        await self.bot.db.update_gaming_lfg_players(self.lfg_id, lfg.current_players, "open")

        mentions = [f"<@{uid}>" for uid in lfg.current_players]
        needed = max(0, lfg.max_players - len(lfg.current_players))

        embed = interaction.message.embeds[0]
        embed.set_field_at(
            2,
            name=f"👥 Roster ({len(lfg.current_players)}/{lfg.max_players})",
            value=", ".join(mentions) or "None",
            inline=False,
        )
        embed.color = Colors.PRIMARY
        embed.set_footer(text=f"{needed} spot(s) still open. Click Join Team to participate.")
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send("Left the team squad.", ephemeral=True)

    @discord.ui.button(label="Close LFG", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="lfg_close_btn")
    async def close_lfg(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.creator_id and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Only the host or staff can close this listing.", ephemeral=True)
            return

        await interaction.response.defer()
        lfg = await self.bot.db.get_gaming_lfg(self.lfg_id)
        if lfg:
            await self.bot.db.update_gaming_lfg_players(self.lfg_id, lfg.current_players, "closed")

        embed = interaction.message.embeds[0]
        embed.color = Colors.DARK_GRAY
        embed.set_footer(text="Recruitment closed by host.")
        await interaction.message.edit(embed=embed, view=None)
        await interaction.followup.send("🔒 Team listing has been closed.", ephemeral=True)


class GamingCog(commands.Cog, name="Gaming"):
    """Community Gaming Hub, LFG, Tournaments, and Clips."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    gaming_group = app_commands.Group(name="gaming", description="Community Gaming Hub & LFG commands")
    game_group = app_commands.Group(name="game", description="Community Gaming Hub, LFG, squads, and events")
    lfg_group = app_commands.Group(name="lfg", description="Looking for group teammate finder and squad coordinator")

    @gaming_group.command(name="findteam", description="Find teammates for any multiplayer game")
    @app_commands.describe(
        game="Name of the game",
        needed="Number of teammates needed (1-9)",
        role="Target role, mode, or rank (e.g. Diamond, Support, Casual)",
        note="Any requirements (e.g. Mic required, Discord VC, chill only)"
    )
    async def findteam(
        self,
        interaction: discord.Interaction,
        game: str,
        needed: app_commands.Range[int, 1, 9] = 3,
        role: Optional[str] = None,
        note: Optional[str] = None,
    ):
        await interaction.response.defer()
        total_slots = needed + 1

        lfg_id = await self.bot.db.create_gaming_lfg(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            game=game.strip(),
            role=role.strip() if role else None,
            note=note.strip() if note else None,
            max_players=total_slots,
            channel_id=interaction.channel_id,
        )

        embed = create_embed(
            title=f"🎮 Looking For Team — {game.strip()}",
            description=f"{interaction.user.mention} is forming a team for **{game.strip()}**!",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="🎯 Role / Mode", value=role or "Any / Open", inline=True)
        embed.add_field(name="📋 Requirements", value=note or "None specified", inline=True)
        embed.add_field(
            name=f"👥 Roster (1/{total_slots})",
            value=f"{interaction.user.mention}",
            inline=False,
        )
        embed.set_footer(text=f"{needed} spot(s) open. Click 'Join Team' below!")

        view = LFGInteractiveView(self.bot, lfg_id, interaction.user.id)
        msg = await interaction.followup.send(embed=embed, view=view)

        # Update message_id in database for persistence
        if self.bot.db._db:
            await self.bot.db._db.execute("UPDATE gaming_lfg SET message_id = ? WHERE id = ?", (msg.id, lfg_id))
            await self.bot.db._db.commit()

    @gaming_group.command(name="room", description="Create a temporary gaming voice channel")
    @app_commands.describe(
        game="Game being played",
        user_limit="Maximum voice capacity (0 for unlimited, 2-99)"
    )
    async def create_gaming_room(
        self,
        interaction: discord.Interaction,
        game: str,
        user_limit: app_commands.Range[int, 0, 99] = 5,
    ):
        await interaction.response.defer()
        guild = interaction.guild

        # Locate gaming category if exists
        category = discord.utils.find(lambda c: "GAMING" in c.name.upper(), guild.categories)
        channel_name = f"🎮・{game.strip()[:20]}"

        vc = await guild.create_voice_channel(
            name=channel_name,
            category=category,
            user_limit=user_limit,
            reason=f"Gaming voice room created by {interaction.user}",
        )

        # Move member if currently connected to voice
        if interaction.user.voice and interaction.user.voice.channel:
            try:
                await interaction.user.move_to(vc)
            except Exception:
                pass

        embed = success_embed(
            "Gaming Room Created",
            f"Created voice channel {vc.mention} for **{game}** (Max: {user_limit if user_limit > 0 else 'Unlimited'}).",
        )
        await interaction.followup.send(embed=embed)

    @gaming_group.command(name="clip", description="Share an epic gaming clip with the community")
    @app_commands.describe(
        title="Title or moment description",
        link="Video or clip URL (YouTube, Twitch, Medal.tv, Streamable, etc.)",
        game="Name of the game"
    )
    async def share_clip(
        self,
        interaction: discord.Interaction,
        title: str,
        link: str,
        game: Optional[str] = None,
    ):
        await interaction.response.defer()
        embed = create_embed(
            title=f"🎬 Epic Gaming Clip: {title.strip()}",
            description=f"**Game:** {game or 'Multi-game'}\n**Shared by:** {interaction.user.mention}\n\n🔗 **[Watch Clip Here]({link.strip()})**",
            color=Colors.SUCCESS,
        )
        embed.set_footer(text="React with 🔥 if this was a godly play!")
        msg = await interaction.followup.send(embed=embed)
        try:
            await msg.add_reaction("🔥")
            await msg.add_reaction("👑")
        except Exception:
            pass

    @gaming_group.command(name="recommend", description="Get top multiplayer or solo game recommendations")
    @app_commands.describe(genre="Genre category")
    @app_commands.choices(
        genre=[
            app_commands.Choice(name="Action / Shooters", value="action"),
            app_commands.Choice(name="Tactical / Competitive", value="tactical"),
            app_commands.Choice(name="RPG & Open World", value="rpg"),
            app_commands.Choice(name="Co-op / Multiplayer", value="coop"),
            app_commands.Choice(name="Chill & Cozy", value="chill"),
        ]
    )
    async def recommend(self, interaction: discord.Interaction, genre: app_commands.Choice[str]):
        await interaction.response.defer()
        recs = GAME_RECOMMENDATIONS.get(genre.value, [])
        embed = create_embed(
            title=f"🎯 Game Recommendations — {genre.name}",
            description="Hand-picked standout titles recommended for our gaming community:",
            color=Colors.PRIMARY,
        )
        for name, desc in recs:
            embed.add_field(name=f"🎮 {name}", value=desc, inline=False)
        await interaction.followup.send(embed=embed)

    @gaming_group.command(name="tournament", description="Announce or schedule a community tournament")
    @app_commands.describe(
        name="Tournament title",
        game="Tournament game",
        date_time="Date & time (e.g. Saturday at 8 PM UTC)",
        prize="Prize or bragging rights"
    )
    async def tournament(
        self,
        interaction: discord.Interaction,
        name: str,
        game: str,
        date_time: str,
        prize: Optional[str] = None,
    ):
        await interaction.response.defer()
        embed = create_embed(
            title=f"🏆 TOURNAMENT: {name.strip()}",
            description=f"Get your squad ready for the **{name.strip()}** tournament!",
            color=Colors.GOLD,
        )
        embed.add_field(name="🎮 Game", value=game, inline=True)
        embed.add_field(name="⏰ Date & Time", value=date_time, inline=True)
        if prize:
            embed.add_field(name="🎁 Prize Pool", value=prize, inline=False)
        embed.add_field(name="Organizer", value=interaction.user.mention, inline=False)
        embed.set_footer(text="React with ⚔️ to register your interest!")
        msg = await interaction.followup.send(embed=embed)
        try:
            await msg.add_reaction("⚔️")
        except Exception:
            pass

    # ==========================================
    # /game COMMAND SUITE (Native UX)
    # ==========================================

    @game_group.command(name="lfg", description="Find teammates and squads for any multiplayer game")
    @app_commands.describe(
        game="Name of the game",
        needed="Number of teammates needed (1-9)",
        role="Target role, mode, or rank (e.g. Diamond, Support, Casual)",
        note="Any requirements (e.g. Mic required, Discord VC, chill only)"
    )
    async def game_lfg(
        self,
        interaction: discord.Interaction,
        game: str,
        needed: app_commands.Range[int, 1, 9] = 3,
        role: Optional[str] = None,
        note: Optional[str] = None,
    ):
        await self.findteam(interaction, game=game, needed=needed, role=role, note=note)

    @gaming_group.command(name="lfg", description="Find teammates and squads for any multiplayer game (alias)")
    @app_commands.describe(
        game="Name of the game",
        needed="Number of teammates needed (1-9)",
        role="Target role, mode, or rank (e.g. Diamond, Support, Casual)",
        note="Any requirements (e.g. Mic required, Discord VC, chill only)"
    )
    async def gaming_lfg(
        self,
        interaction: discord.Interaction,
        game: str,
        needed: app_commands.Range[int, 1, 9] = 3,
        role: Optional[str] = None,
        note: Optional[str] = None,
    ):
        await self.findteam(interaction, game=game, needed=needed, role=role, note=note)

    @game_group.command(name="team", description="Find and form a squad or team for multiplayer gaming")
    @app_commands.describe(
        game="Name of the game",
        needed="Teammates needed (1-9)",
        role="Target role or rank",
        note="Requirements or playstyle"
    )
    async def game_team(
        self,
        interaction: discord.Interaction,
        game: str,
        needed: app_commands.Range[int, 1, 9] = 3,
        role: Optional[str] = None,
        note: Optional[str] = None,
    ):
        await self.findteam(interaction, game=game, needed=needed, role=role, note=note)

    @game_group.command(name="room", description="Create a temporary gaming voice channel with auto-cleanup")
    @app_commands.describe(
        game="Game being played",
        user_limit="Maximum voice capacity (0 for unlimited, 2-99)"
    )
    async def game_room(
        self,
        interaction: discord.Interaction,
        game: str,
        user_limit: app_commands.Range[int, 0, 99] = 5,
    ):
        await self.create_gaming_room(interaction, game=game, user_limit=user_limit)

    @game_group.command(name="event", description="Browse or schedule community gaming events and tournaments")
    @app_commands.describe(
        name="Tournament or event title",
        game="Game being played",
        date_time="Date & time of event",
        prize="Optional prize or recognition"
    )
    async def game_event(
        self,
        interaction: discord.Interaction,
        name: str,
        game: str,
        date_time: str,
        prize: Optional[str] = None,
    ):
        await self.tournament(interaction, name=name, game=game, date_time=date_time, prize=prize)

    @game_group.command(name="profile", description="View gaming profile, favorite games, and stats")
    @app_commands.describe(user="Target player (defaults to you)")
    async def game_profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = user or interaction.user
        embed = create_embed(
            title=f"🎮 Gaming Profile — {target.display_name}",
            description=f"Player profile and community engagement overview for {target.mention}.",
            color=Colors.PRIMARY,
        )
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)

        # Query recent LFGs created by user
        lfgs = []
        if self.bot.db and self.bot.db._db:
            try:
                cur = await self.bot.db._db.execute("SELECT game, role, status FROM gaming_lfg WHERE user_id = ? ORDER BY id DESC LIMIT 5", (target.id,))
                lfgs = await cur.fetchall()
            except Exception:
                pass

        if lfgs:
            games_played = ", ".join(set(row[0] for row in lfgs))
            embed.add_field(name="🎯 Recent Games", value=games_played[:100], inline=False)
            embed.add_field(name="⚔️ Squads Formed", value=str(len(lfgs)), inline=True)
        else:
            embed.add_field(name="🎯 Status", value="No recorded squads yet. Use `/game lfg` to start one!", inline=False)

        await interaction.followup.send(embed=embed)

    @game_group.command(name="stats", description="Display server-wide gaming and LFG statistics")
    async def game_stats(self, interaction: discord.Interaction):
        await interaction.response.defer()
        total_lfgs = 0
        if self.bot.db and self.bot.db._db:
            try:
                cur = await self.bot.db._db.execute("SELECT COUNT(*) FROM gaming_lfg WHERE guild_id = ?", (interaction.guild.id,))
                row = await cur.fetchone()
                total_lfgs = row[0] if row else 0
            except Exception:
                pass

        embed = create_embed(
            title=f"🎮 Community Gaming Telemetry — {interaction.guild.name}",
            description=(
                f"**Total Squads / LFGs Formed:** `{total_lfgs}`\n"
                f"**Gaming Voice System:** `Dynamic Auto-Cleanup Active`\n"
                f"**Tournaments Engine:** `Operational`\n\n"
                f"Jump into a squad with `/game lfg` or create a voice room with `/game room`."
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed)

    @game_group.command(name="profile-set", description="Set or update your community gaming profile")
    @app_commands.describe(
        games="Favorite games (comma separated, e.g. BGMI, Valorant, Apex)",
        rank="Current competitive rank or skill tier",
        preferred_modes="Favorite game modes (e.g. Squad, Ranked, Casual)",
        play_times="Usual play times (e.g. Evenings, Weekends)",
        mic_available="Do you use a microphone?",
    )
    async def game_profile_set(
        self,
        interaction: discord.Interaction,
        games: Optional[str] = None,
        rank: Optional[str] = None,
        preferred_modes: Optional[str] = None,
        play_times: Optional[str] = None,
        mic_available: bool = True,
    ):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if games is not None:
            updates["games"] = games.strip()[:100]
        if rank is not None:
            updates["rank"] = rank.strip()[:50]
        if preferred_modes is not None:
            updates["preferred_modes"] = preferred_modes.strip()[:50]
        if play_times is not None:
            updates["play_times"] = play_times.strip()[:50]
        updates["mic_available"] = 1 if mic_available else 0

        await self.bot.db.update_gaming_profile(interaction.guild.id, interaction.user.id, **updates)
        await interaction.followup.send("✅ Your gaming profile has been updated! View it with `/game profile`.", ephemeral=True)

    # ==========================================
    # /lfg COMMAND SUITE
    # ==========================================

    @lfg_group.command(name="create", description="Create an LFG team recruitment listing")
    @app_commands.describe(
        game="Name of the game",
        needed="Number of teammates needed (1-9)",
        role="Target role, mode, or rank (e.g. Diamond, Support, Casual)",
        note="Any requirements (e.g. Mic required, Discord VC, chill only)"
    )
    async def lfg_create(
        self,
        interaction: discord.Interaction,
        game: str,
        needed: app_commands.Range[int, 1, 9] = 3,
        role: Optional[str] = None,
        note: Optional[str] = None,
    ):
        await self.findteam(interaction, game=game, needed=needed, role=role, note=note)

    @lfg_group.command(name="list", description="List all open LFG squad recruitment listings")
    async def lfg_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = []
        if self.bot.db and self.bot.db._db:
            try:
                cur = await self.bot.db._db.execute(
                    "SELECT id, user_id, game, role, max_players, current_players_json FROM gaming_lfg WHERE guild_id = ? AND status = 'open' ORDER BY id DESC LIMIT 10",
                    (interaction.guild.id,)
                )
                rows = await cur.fetchall()
            except Exception:
                pass

        if not rows:
            await interaction.followup.send("ℹ️ No active LFG listings found. Start one with `/lfg create`!")
            return

        import json
        embed = create_embed(
            title=f"🎮 Active Squad Recruitments — {interaction.guild.name}",
            description="Open gaming teams seeking players:",
            color=Colors.PRIMARY,
        )
        for r in rows:
            lfg_id, host_id, game_name, role, max_p, players_json = r
            try:
                players = json.loads(players_json)
            except Exception:
                players = []
            needed = max(0, max_p - len(players))
            embed.add_field(
                name=f"#{lfg_id} • {game_name} ({len(players)}/{max_p})",
                value=f"Host: <@{host_id}>\nRole/Rank: {role or 'Any'}\nSpots Left: **{needed}**\nJoin via `/lfg join id:{lfg_id}`",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @lfg_group.command(name="join", description="Join an open LFG recruitment squad by ID")
    @app_commands.describe(lfg_id="ID number of the LFG listing")
    async def lfg_join(self, interaction: discord.Interaction, lfg_id: int):
        await interaction.response.defer()
        lfg = await self.bot.db.get_gaming_lfg(lfg_id)
        if not lfg or lfg.status != "open":
            await interaction.followup.send("❌ This team recruitment is closed or not found.", ephemeral=True)
            return

        if interaction.user.id in lfg.current_players:
            await interaction.followup.send("ℹ️ You are already part of this team.", ephemeral=True)
            return

        if len(lfg.current_players) >= lfg.max_players:
            await interaction.followup.send("⚠️ This team is already full!", ephemeral=True)
            return

        lfg.current_players.append(interaction.user.id)
        status = "full" if len(lfg.current_players) >= lfg.max_players else "open"
        await self.bot.db.update_gaming_lfg_players(lfg_id, lfg.current_players, status)

        # If team full, auto create workspace
        if status == "full":
            from services.workspace_service import WorkspaceService, WorkspaceType
            try:
                creator = interaction.guild.get_member(lfg.user_id) or interaction.user
                await WorkspaceService.get_instance(self.bot).create_workspace(
                    guild=interaction.guild,
                    owner=creator,
                    workspace_type=WorkspaceType.GAMING,
                    name=f"{lfg.game} Squad",
                )
            except Exception as e:
                logger.warning(f"Could not auto-create gaming workspace on /lfg join: {e}")

        await interaction.followup.send(f"✅ Successfully joined squad #{lfg_id} for **{lfg.game}**!")

    @lfg_group.command(name="leave", description="Leave an LFG squad you previously joined")
    @app_commands.describe(lfg_id="ID number of the LFG listing")
    async def lfg_leave(self, interaction: discord.Interaction, lfg_id: int):
        await interaction.response.defer()
        lfg = await self.bot.db.get_gaming_lfg(lfg_id)
        if not lfg or interaction.user.id not in lfg.current_players:
            await interaction.followup.send("❌ You are not in this squad.", ephemeral=True)
            return

        if interaction.user.id == lfg.user_id:
            await interaction.followup.send("⚠️ Hosts cannot leave their own listing. Use `/lfg close` instead.", ephemeral=True)
            return

        lfg.current_players.remove(interaction.user.id)
        await self.bot.db.update_gaming_lfg_players(lfg_id, lfg.current_players, "open")
        await interaction.followup.send(f"Left squad #{lfg_id} for **{lfg.game}**.")

    @lfg_group.command(name="info", description="View details of a specific LFG listing")
    @app_commands.describe(lfg_id="ID number of the LFG listing")
    async def lfg_info(self, interaction: discord.Interaction, lfg_id: int):
        await interaction.response.defer()
        lfg = await self.bot.db.get_gaming_lfg(lfg_id)
        if not lfg:
            await interaction.followup.send("❌ LFG listing not found.", ephemeral=True)
            return

        mentions = [f"<@{uid}>" for uid in lfg.current_players]
        needed = max(0, lfg.max_players - len(lfg.current_players))
        embed = create_embed(
            title=f"🎮 LFG #{lfg_id} — {lfg.game}",
            description=f"Status: `{lfg.status.upper()}` • Host: <@{lfg.user_id}>",
            color=Colors.SUCCESS if lfg.status == "open" else Colors.DARK_GRAY,
        )
        embed.add_field(name="🎯 Role / Mode", value=lfg.role or "Any", inline=True)
        embed.add_field(name="📋 Note", value=lfg.note or "None", inline=True)
        embed.add_field(name=f"👥 Roster ({len(lfg.current_players)}/{lfg.max_players})", value=", ".join(mentions) or "None", inline=False)
        embed.set_footer(text=f"{needed} spot(s) remaining.")
        await interaction.followup.send(embed=embed)

    @lfg_group.command(name="close", description="Close an active LFG recruitment squad")
    @app_commands.describe(lfg_id="ID number of the LFG listing")
    async def lfg_close(self, interaction: discord.Interaction, lfg_id: int):
        await interaction.response.defer()
        lfg = await self.bot.db.get_gaming_lfg(lfg_id)
        if not lfg:
            await interaction.followup.send("❌ LFG listing not found.", ephemeral=True)
            return

        if interaction.user.id != lfg.user_id and not interaction.user.guild_permissions.manage_messages:
            await interaction.followup.send("❌ Only the host or staff can close this listing.", ephemeral=True)
            return

        await self.bot.db.update_gaming_lfg_players(lfg_id, lfg.current_players, "closed")
        await interaction.followup.send(f"🔒 LFG #{lfg_id} for **{lfg.game}** has been closed.")


async def setup(bot: SentinelBot):
    await bot.add_cog(GamingCog(bot))
