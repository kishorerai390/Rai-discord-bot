"""
RAI — COMMUNITY REPUTATION SYSTEM COG.
Provides:
- Configurable positive reputation tracking (helpful actions, events, voice participation, feedback).
- Anti-abuse safeguards: self-interaction blocks, rate limits, cooldowns, voice AFK protections.
- Commands:
  /reputation profile [user]
  /reputation leaderboard
  /reputation give <user> <reason>
  /reputation history [user]
  /reputation settings
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.ReputationCog")


class ReputationCog(commands.Cog, name="Reputation"):
    """Community Reputation System."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._give_cooldowns: dict[tuple[int, int], float] = {}

    rep_group = app_commands.Group(name="reputation", description="Community reputation and appreciation system")
    profile_group = app_commands.Group(name="profile", description="Member community profile and identity")
    collab_group = app_commands.Group(name="collab", description="Collaboration matcher and creative networking")

    @rep_group.command(name="profile", description="View a member's community reputation profile and accomplishments")
    @app_commands.describe(user="The server member (defaults to yourself)")
    async def profile_cmd(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=False)
        target = user or interaction.user
        profile = await self.bot.db.get_or_create_reputation_profile(interaction.guild.id, target.id)

        embed = create_embed(
            title=f"⭐ Community Reputation — {target.display_name}",
            description=(
                f"**Level:** `Level {profile['level']}`\n"
                f"**Reputation Points:** `{profile['points']}`\n\n"
                f"🤝 **Helpful Contributions:** `{profile['helpful_count']}`\n"
                f"🎟️ **Events Attended:** `{profile['event_count']}`\n"
                f"🎙️ **Active Voice Minutes:** `{profile['voice_minutes']} mins`"
            ),
            color=Colors.GOLD,
        )
        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)
        embed.set_footer(text="Earn reputation through helpfulness, voice participation, and community events!")
        await interaction.followup.send(embed=embed)

    @rep_group.command(name="give", description="Give positive reputation points to a helpful community member")
    @app_commands.describe(
        user="The member to thank",
        reason="Why are you awarding reputation to this member?",
    )
    async def give_cmd(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        await interaction.response.defer()
        guild_id = interaction.guild.id

        # Anti-abuse 1: No self-reputation
        if user.id == interaction.user.id:
            await interaction.followup.send("❌ You cannot give reputation to yourself.", ephemeral=True)
            return

        # Anti-abuse 2: No bot reputation
        if user.bot:
            await interaction.followup.send("❌ Bots cannot receive reputation points.", ephemeral=True)
            return

        # Anti-abuse 3: Cooldown between giving to the same member
        key = (interaction.user.id, user.id)
        last_time = self._give_cooldowns.get(key, 0.0)
        cooldown_window = 300.0  # 5 minutes
        if time.time() - last_time < cooldown_window:
            remaining = int(cooldown_window - (time.time() - last_time))
            await interaction.followup.send(f"⏳ Cooldown: You can give reputation to {user.display_name} again in {remaining}s.", ephemeral=True)
            return

        self._give_cooldowns[key] = time.time()
        awarded_points = 15

        res = await self.bot.db.add_reputation_points(
            guild_id=guild_id,
            user_id=user.id,
            giver_id=interaction.user.id,
            category="helpful",
            points=awarded_points,
            reason=reason.strip(),
        )

        embed = create_embed(
            title="⭐ Community Reputation Awarded!",
            description=(
                f"{interaction.user.mention} awarded **+{awarded_points} Reputation** to {user.mention}!\n\n"
                f"💬 **Reason:** *\"{reason.strip()}\"*\n"
                f"📈 {user.display_name} is now **Level {res['level']}** (`{res['points']} pts`)"
            ),
            color=Colors.SUCCESS,
        )
        await interaction.followup.send(embed=embed)

    @rep_group.command(name="leaderboard", description="View the server's top reputation leaders")
    async def leaderboard_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        leaders = await self.bot.db.get_reputation_leaderboard(interaction.guild.id, limit=10)

        embed = create_embed(
            title=f"🏆 Reputation Leaderboard — {interaction.guild.name}",
            description="Our most helpful and active community members:",
            color=Colors.GOLD,
        )

        if not leaders:
            embed.description = "No reputation points awarded yet. Be the first with `/reputation give`!"
        else:
            medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
            lines = []
            for idx, row in enumerate(leaders):
                medal = medals[idx]
                lines.append(f"{medal} **#{idx+1}** <@{row['user_id']}> — `{row['points']} pts` (Level {row['level']})")
            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed)

    @rep_group.command(name="history", description="View recent reputation awards received by a member")
    @app_commands.describe(user="The member (defaults to yourself)")
    async def history_cmd(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=True)
        target = user or interaction.user
        history = await self.bot.db.get_reputation_history(interaction.guild.id, target.id, limit=10)

        embed = create_embed(
            title=f"📜 Reputation History — {target.display_name}",
            description=f"Recent reputation log for {target.mention}:",
            color=Colors.PRIMARY,
        )

        if not history:
            embed.description = f"No reputation events recorded yet for {target.mention}."
        else:
            for ev in history:
                giver_str = f"<@{ev['giver_id']}>" if ev.get("giver_id") else "System"
                reason_str = ev.get("reason") or "Helpful participation"
                pts = ev.get("points", 0)
                embed.add_field(
                    name=f"+{pts} pts [{ev['category'].upper()}]",
                    value=f"From: {giver_str}\n*{reason_str}*",
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @rep_group.command(name="settings", description="Configure reputation system rules (Staff only)")
    @app_commands.describe(
        category="Category to configure (helpful, event, voice)",
        points="Points awarded per occurrence",
        cooldown_seconds="Cooldown period in seconds",
        enabled="Whether this category is enabled",
    )
    async def settings_cmd(
        self,
        interaction: discord.Interaction,
        category: str,
        points: int,
        cooldown_seconds: int = 300,
        enabled: bool = True,
    ):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only staff can configure reputation rules.", ephemeral=True)
            return

        cat = category.strip().lower()
        await self.bot.db.set_reputation_rule(
            guild_id=interaction.guild.id,
            category=cat,
            points=points,
            cooldown_seconds=cooldown_seconds,
            is_enabled=enabled,
        )
        await interaction.followup.send(f"✅ Reputation rule updated for `{cat}`: {points} points, {cooldown_seconds}s cooldown.", ephemeral=True)

    # ==========================================
    # /profile COMMAND SUITE
    # ==========================================

    @profile_group.command(name="view", description="View a member's community profile, gaming, skills, and reputation")
    @app_commands.describe(member="Member to view (defaults to you)")
    async def profile_view(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = member or interaction.user

        # Fetch reputation, user profile, gaming profile, and events count
        rep = await self.bot.db.get_or_create_reputation_profile(interaction.guild.id, target.id)
        u_prof = await self.bot.db.get_or_create_user_profile(interaction.guild.id, target.id)
        g_prof = await self.bot.db.get_or_create_gaming_profile(interaction.guild.id, target.id)

        if not u_prof.get("is_visible", 1) and target.id != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("🔒 This user has set their profile to private.", ephemeral=True)
            return

        embed = create_embed(
            title=f"👤 MEMBER PROFILE — {target.display_name}",
            description=u_prof.get("bio") or f"Community member of **{interaction.guild.name}**",
            color=Colors.PRIMARY,
        )
        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)

        # Games
        games = g_prof.get("games")
        if games:
            embed.add_field(name="🎮 Games", value=games, inline=False)

        # Skills
        skills = u_prof.get("skills")
        if skills:
            embed.add_field(name="🎨 Skills", value=skills, inline=False)

        # Interests
        interests = u_prof.get("interests")
        if interests:
            embed.add_field(name="🎵 Interests", value=interests, inline=False)

        # Events attended
        embed.add_field(name="🏆 Events Joined", value=str(rep.get("event_count", 0)), inline=True)

        # Reputation points
        embed.add_field(name="⭐ Reputation", value=str(rep.get("points", 0)), inline=True)

        embed.set_footer(text="Edit your profile with `/profile edit`")
        await interaction.followup.send(embed=embed)

    @profile_group.command(name="edit", description="Update your optional community profile information")
    @app_commands.describe(
        skills="Creative or technical skills (e.g. Video Editing, Thumbnail Design)",
        interests="Music, hobbies, or community interests (e.g. Tamil Music, Hip-Hop)",
        bio="Brief bio or headline",
        visible="Whether your profile is visible to other members",
    )
    async def profile_edit(
        self,
        interaction: discord.Interaction,
        skills: Optional[str] = None,
        interests: Optional[str] = None,
        bio: Optional[str] = None,
        visible: bool = True,
    ):
        await interaction.response.defer(ephemeral=True)
        updates = {}
        if skills is not None:
            updates["skills"] = skills.strip()[:150]
        if interests is not None:
            updates["interests"] = interests.strip()[:150]
        if bio is not None:
            updates["bio"] = bio.strip()[:200]
        updates["is_visible"] = 1 if visible else 0

        await self.bot.db.update_user_profile(interaction.guild.id, interaction.user.id, **updates)
        await interaction.followup.send("✅ Profile updated! View your profile with `/profile view`.", ephemeral=True)

    @profile_group.command(name="setup", description="Initial guided setup of your community profile")
    @app_commands.describe(
        skills="Creative or technical skills (e.g. Video Editing, Sound Design)",
        interests="Music, hobbies, or community interests (e.g. Gaming, Anime, Production)",
        bio="Brief bio or headline",
        visible="Whether your profile is visible to other members",
    )
    async def profile_setup(
        self,
        interaction: discord.Interaction,
        skills: Optional[str] = None,
        interests: Optional[str] = None,
        bio: Optional[str] = None,
        visible: bool = True,
    ):
        await self.profile_edit(interaction, skills, interests, bio, visible)

    @app_commands.command(name="profile", description="Quickly view your or another member's community profile")
    @app_commands.describe(member="Member to view (defaults to you)")
    async def profile_top_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        await self.profile_view(interaction, member)

    # ==========================================
    # /collab COMMAND SUITE
    # ==========================================

    @collab_group.command(name="find", description="Find potential collaborators by skill or creative role")
    @app_commands.describe(skill="Target skill (e.g. Video Editing, Motion Graphics, Audio)")
    async def collab_find(self, interaction: discord.Interaction, skill: Optional[str] = None):
        await interaction.response.defer()
        rows = []
        if self.bot.db and self.bot.db._db:
            try:
                query = "SELECT user_id, skills, interests FROM community_user_profiles WHERE guild_id = ? AND is_visible = 1 AND skills != ''"
                cur = await self.bot.db._db.execute(query, (interaction.guild.id,))
                rows = await cur.fetchall()
            except Exception:
                pass

        if skill:
            q = skill.lower()
            rows = [r for r in rows if q in r[1].lower()]

        if not rows:
            msg = f"ℹ️ No active members found matching skill '{skill}'." if skill else "ℹ️ No collaboration profiles registered yet. Set yours via `/collab profile`!"
            await interaction.followup.send(msg)
            return

        embed = create_embed(
            title="🎨 COLLABORATION MATCHES",
            description=f"Looking for: **{skill or 'Any Skill'}**\n\nPossible matches:",
            color=Colors.PRIMARY,
        )
        for r in rows[:6]:
            u_id, sk, inte = r
            embed.add_field(
                name=f"👤 <@{u_id}>",
                value=f"**Skills:** {sk}\n**Interests:** {inte or 'Not specified'}\n*Send request: `/collab request member:<@{u_id}> skill:{sk.split(',')[0]}`*",
                inline=False,
            )
        embed.set_footer(text="Opt in or edit your skills with /collab profile")
        await interaction.followup.send(embed=embed)

    @collab_group.command(name="profile", description="Set or update your creative collaboration profile and opt-in status")
    @app_commands.describe(
        skills="Skills you can contribute to projects",
        interests="Interests or creative genres you enjoy",
        opt_in="Allow others to discover you in collaboration matches",
    )
    async def collab_profile(
        self,
        interaction: discord.Interaction,
        skills: Optional[str] = None,
        interests: Optional[str] = None,
        opt_in: bool = True,
    ):
        await self.profile_edit(interaction, skills=skills, interests=interests, visible=opt_in)

    @collab_group.command(name="request", description="Send a collaboration request to another member")
    @app_commands.describe(
        member="Target creator to invite",
        skill="Skill or role needed for the collaboration",
        note="Project idea or details",
    )
    async def collab_request(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        skill: str,
        note: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if member.id == interaction.user.id:
            await interaction.followup.send("❌ You cannot send a collaboration request to yourself.", ephemeral=True)
            return
        if member.bot:
            await interaction.followup.send("❌ Cannot collaborate with bot accounts.", ephemeral=True)
            return

        req_id = await self.bot.db.create_collaboration_request(
            guild_id=interaction.guild.id,
            requester_id=interaction.user.id,
            target_id=member.id,
            skill=skill.strip(),
            note=note,
        )

        # Notify target if possible
        try:
            embed = create_embed(
                title="🎨 New Collaboration Request",
                description=(
                    f"**From:** {interaction.user.mention} (in {interaction.guild.name})\n"
                    f"**Skill / Role:** `{skill.strip()}`\n"
                    f"**Details:** {note or 'No details specified.'}\n\n"
                    f"Accept with `/collab accept request_id:{req_id}`\n"
                    f"Decline with `/collab decline request_id:{req_id}`"
                ),
                color=Colors.PRIMARY,
            )
            await member.send(embed=embed)
        except Exception:
            pass

        await interaction.followup.send(f"✅ Collaboration request #{req_id} sent to {member.mention}!", ephemeral=True)

    @collab_group.command(name="accept", description="Accept an incoming collaboration request")
    @app_commands.describe(request_id="ID of the collaboration request")
    async def collab_accept(self, interaction: discord.Interaction, request_id: int):
        await interaction.response.defer(ephemeral=True)
        success = await self.bot.db.update_collaboration_status(request_id, "ACCEPTED")
        if success:
            await interaction.followup.send(f"🤝 Accepted collaboration request #{request_id}!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Collaboration request not found.", ephemeral=True)

    @collab_group.command(name="decline", description="Decline an incoming collaboration request")
    @app_commands.describe(request_id="ID of the collaboration request")
    async def collab_decline(self, interaction: discord.Interaction, request_id: int):
        await interaction.response.defer(ephemeral=True)
        success = await self.bot.db.update_collaboration_status(request_id, "DECLINED")
        if success:
            await interaction.followup.send(f"Declined collaboration request #{request_id}.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Collaboration request not found.", ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(ReputationCog(bot))
