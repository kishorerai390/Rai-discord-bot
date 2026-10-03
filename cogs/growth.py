"""
Rai Growth & Viral Server Automation Cog.
Features:
- Comprehensive invite tracker: detects who invited new members, leaves, and fake accounts
- /invites [member]: Inspect individual invite statistics
- /invites leaderboard: Top server ambassadors leaderboard
- /vote: Top.gg upvote portal with automatic 1,000 Rai Coins instant reward
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Dict, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class GrowthCog(commands.Cog, name="Growth"):
    """Community Growth, Invite Tracking & Voting Rewards."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # guild_id -> {code: uses}
        self.invites_cache: Dict[int, Dict[str, int]] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        """Cache all guild invites for join comparison."""
        await self.cache_all_invites()

    async def cache_all_invites(self):
        """Refresh local cache of invite codes and uses."""
        for guild in self.bot.guilds:
            try:
                invs = await guild.invites()
                self.invites_cache[guild.id] = {inv.code: inv.uses for inv in invs}
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild and invite.guild.id in self.invites_cache:
            self.invites_cache[invite.guild.id][invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild and invite.guild.id in self.invites_cache:
            self.invites_cache[invite.guild.id].pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Detect which invite code was used by matching use count increments."""
        if member.bot:
            return

        guild = member.guild
        old_cache = self.invites_cache.get(guild.id, {})

        try:
            current_invites = await guild.invites()
            matched_inviter_id: Optional[int] = None

            for inv in current_invites:
                prev_uses = old_cache.get(inv.code, 0)
                if inv.uses and inv.uses > prev_uses:
                    if inv.inviter:
                        matched_inviter_id = inv.inviter.id
                    break

            # Update cache
            self.invites_cache[guild.id] = {inv.code: inv.uses for inv in current_invites}

            if matched_inviter_id:
                # Check for fake account (e.g. account created < 24h ago)
                age = datetime.datetime.now(datetime.timezone.utc) - member.created_at
                is_fake = age.total_seconds() < 86400

                await self.bot.db.increment_member_invites(
                    guild_id=guild.id,
                    inviter_id=matched_inviter_id,
                    regular=0 if is_fake else 1,
                    fake=1 if is_fake else 0,
                )
                logger.info(f"Invite recorded: Member {member} invited by ID {matched_inviter_id}")
        except Exception as e:
            logger.debug(f"Failed to process join invite for {member}: {e}")

    # ==========================================
    # SLASH COMMANDS: /INVITES
    # ==========================================

    invites_group = app_commands.Group(name="invites", description="Inspect member invites and server growth stats")

    @invites_group.command(name="check", description="Check invite metrics for yourself or another member")
    @app_commands.describe(member="Member whose invites to inspect")
    async def invites_check(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """View member invite breakdown."""
        target = member or interaction.user
        stats = await self.bot.db.get_member_invites(interaction.guild.id, target.id)

        embed = discord.Embed(
            title=f"💌 Invite Dossier — {target.display_name}",
            color=0x5865F2,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="✨ Total Effective Invites", value=f"**{stats.total}**", inline=False)
        embed.add_field(name="📥 Regular", value=f"`{stats.regular}`", inline=True)
        embed.add_field(name="🚪 Left", value=f"`{stats.leaves}`", inline=True)
        embed.add_field(name="🎁 Bonus", value=f"`{stats.bonus}`", inline=True)
        embed.add_field(name="⚠️ Suspicious / Fake", value=f"`{stats.fake}`", inline=True)
        embed.set_footer(text="Rai Growth Automation • RAI FAM💗")
        await interaction.response.send_message(embed=embed)

    @invites_group.command(name="leaderboard", description="View the top 10 community inviters")
    async def invites_leaderboard(self, interaction: discord.Interaction):
        """Show top server inviters."""
        top_list = await self.bot.db.get_top_inviters(interaction.guild.id, limit=10)
        if not top_list:
            await interaction.response.send_message(
                embed=info_embed("Invite Leaderboard", "No member invites recorded yet! Start sharing your server invite link."),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🏆 Invite Hall of Fame — Top Ambassadors",
            color=0xF1C40F,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for rank, (inviter_id, total) in enumerate(top_list, 1):
            badge = medals[rank - 1] if rank <= 3 else f"`#{rank}`"
            lines.append(f"{badge} <@{inviter_id}> — **{total}** invites")

        embed.description = "\n".join(lines)
        embed.set_footer(text="Top server growth champions • RAI FAM💗")
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # SLASH COMMAND: /VOTE
    # ==========================================

    @app_commands.command(name="vote", description="Vote for Rai on Top.gg and claim 1,000 instant Rai Coins!")
    async def vote(self, interaction: discord.Interaction):
        """Vote link with automatic currency reward."""
        await interaction.response.defer()

        # Check last vote timestamp to enforce 12h cooldown
        votes_info = await self.bot.db.get_member_votes(interaction.user.id, interaction.guild.id)
        now = datetime.datetime.now(datetime.timezone.utc)
        can_claim = True

        if votes_info.last_voted:
            try:
                last_dt = datetime.datetime.fromisoformat(votes_info.last_voted)
                if (now - last_dt).total_seconds() < 43200:  # 12 hours
                    can_claim = False
                    remaining_hours = round((43200 - (now - last_dt).total_seconds()) / 3600, 1)
            except Exception:
                pass

        if can_claim:
            new_total = await self.bot.db.record_vote(interaction.user.id, interaction.guild.id)
            # Credit 1,000 coins to economy
            eco = await self.bot.db.get_or_create_user_economy(interaction.guild.id, interaction.user.id)
            await self.bot.db.update_user_economy(
                interaction.guild.id,
                interaction.user.id,
                coins=eco.coins + 1000,
            )

            embed = discord.Embed(
                title="🗳️ Top.gg Upvote & Reward Granted!",
                description=(
                    f"Thank you for supporting **The Raivora**!\n\n"
                    f"💎 **Reward:** `+1,000 Rai Coins` credited to your wallet!\n"
                    f"⭐ **Lifetime Votes:** `{new_total}`\n\n"
                    f"[Click here to vote on Top.gg](https://top.gg/bot/1554732669072445532/vote)"
                ),
                color=0x57F287,
                timestamp=now,
            )
            embed.set_footer(text="You can vote and claim rewards every 12 hours!")
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Vote on Top.gg", url="https://top.gg/bot/1554732669072445532/vote", style=discord.ButtonStyle.link, emoji="🗳️"))
            await interaction.followup.send(embed=embed, view=view)
        else:
            embed = discord.Embed(
                title="⏳ Voting Reward on Cooldown",
                description=(
                    f"You have already claimed your voting bonus recently!\n"
                    f"You can claim again in **{remaining_hours} hours**.\n\n"
                    f"⭐ **Lifetime Votes:** `{votes_info.total_votes}`\n\n"
                    f"[Click here to vote on Top.gg anyway!](https://top.gg/bot/1554732669072445532/vote)"
                ),
                color=0xFEE75C,
                timestamp=now,
            )
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Vote on Top.gg", url="https://top.gg/bot/1554732669072445532/vote", style=discord.ButtonStyle.link, emoji="🗳️"))
            await interaction.followup.send(embed=embed, view=view)


async def setup(bot: SentinelBot):
    await bot.add_cog(GrowthCog(bot))
