"""
Comprehensive Suggestion System with Persistent Voting and Thread Discussions.
Features:
- /suggest command with length validation, rate-limiting & auto-formatting
- Interactive persistent UI buttons: Upvote, Downvote, Discuss Thread
- Atomic, race-condition safe voting (1 vote per user, toggleable/switchable)
- Staff decision commands: /suggestion approve, reject, implement, archive, reopen, delete, view
- Automatic discussion threads and author DM notifications
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.cooldowns import CooldownScope
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

STATUS_METADATA = {
    "pending": {"label": "🟡 Pending Review", "color": Colors.WARNING},
    "approved": {"label": "🟢 Approved", "color": Colors.SUCCESS},
    "rejected": {"label": "🔴 Rejected", "color": Colors.ERROR},
    "implemented": {"label": "🟣 Implemented", "color": 0x9B59B6},
    "archived": {"label": "⚫ Archived", "color": Colors.DARK},
}


def create_suggestion_embed(
    suggestion_id: int,
    content: str,
    author: discord.User | discord.Member,
    status: str = "pending",
    upvotes: int = 0,
    downvotes: int = 0,
    reason: Optional[str] = None,
    reviewed_by: Optional[int] = None,
    created_at_dt: Optional[datetime.datetime] = None,
) -> discord.Embed:
    meta = STATUS_METADATA.get(status, STATUS_METADATA["pending"])
    embed = discord.Embed(
        title=f"💡 Suggestion #{suggestion_id}",
        description=content,
        color=meta["color"],
        timestamp=created_at_dt or discord.utils.utcnow(),
    )
    embed.set_author(name=f"Submitted by {author.name}", icon_url=author.display_avatar.url)
    embed.add_field(name="📌 Status", value=meta["label"], inline=True)
    embed.add_field(name="📊 Votes", value=f"👍 **{upvotes}**  |  👎 **{downvotes}**", inline=True)

    if reason:
        reviewer_text = f"<@{reviewed_by}>" if reviewed_by else "Staff"
        embed.add_field(name="Staff Response", value=f"**By:** {reviewer_text}\n> {reason}", inline=False)

    embed.set_footer(text=f"Suggestion ID: {suggestion_id} • Rai Suggestions")
    return embed


class SuggestionView(discord.ui.View):
    """Persistent voting and discussion view for suggestion messages."""

    def __init__(self, suggestion_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.suggestion_id = suggestion_id

    @discord.ui.button(
        label="Upvote",
        style=discord.ButtonStyle.success,
        emoji="👍",
        custom_id="sentinel_suggestion_upvote",
    )
    async def upvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_vote(interaction, "upvote")

    @discord.ui.button(
        label="Downvote",
        style=discord.ButtonStyle.danger,
        emoji="👎",
        custom_id="sentinel_suggestion_downvote",
    )
    async def downvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_vote(interaction, "downvote")

    @discord.ui.button(
        label="Discuss",
        style=discord.ButtonStyle.secondary,
        emoji="💬",
        custom_id="sentinel_suggestion_discuss",
    )
    async def discuss(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = interaction.message
        if not msg:
            await interaction.response.send_message("Cannot locate suggestion message.", ephemeral=True)
            return

        if msg.thread:
            await interaction.response.send_message(
                f"Discussion thread: {msg.thread.mention}", ephemeral=True
            )
        else:
            bot: SentinelBot = interaction.client  # type: ignore
            # Locate suggestion ID
            s_id = None
            if msg.embeds and msg.embeds[0].footer and msg.embeds[0].footer.text:
                parts = msg.embeds[0].footer.text.split("•")[0].strip().split()
                if len(parts) >= 3 and parts[2].isdigit():
                    s_id = int(parts[2])

            if s_id:
                try:
                    thread = await msg.create_thread(name=f"Suggestion #{s_id} Discussion")
                    await bot.db.update_suggestion_thread(s_id, thread.id)
                    await interaction.response.send_message(
                        f"Created discussion thread: {thread.mention}", ephemeral=True
                    )
                except Exception as e:
                    await interaction.response.send_message(f"Could not create thread: {e}", ephemeral=True)
            else:
                await interaction.response.send_message("Thread discussion is currently unavailable.", ephemeral=True)

    async def _process_vote(self, interaction: discord.Interaction, vote_type: str) -> None:
        if interaction.user.bot:
            return

        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        msg = interaction.message
        if not msg:
            return

        # Extract suggestion ID from footer or embed title
        s_id = None
        if msg.embeds and msg.embeds[0].footer and msg.embeds[0].footer.text:
            text = msg.embeds[0].footer.text
            for token in text.replace("#", " ").split():
                if token.isdigit():
                    s_id = int(token)
                    break

        if not s_id:
            await interaction.response.send_message("Could not identify suggestion record.", ephemeral=True)
            return

        suggestion = await bot.db.get_suggestion(s_id)
        if not suggestion:
            await interaction.response.send_message("Suggestion not found in database.", ephemeral=True)
            return

        if suggestion.status in ("archived", "rejected", "implemented"):
            await interaction.response.send_message(
                f"Voting is closed because this suggestion is marked as **{suggestion.status.capitalize()}**.",
                ephemeral=True,
            )
            return

        # Cast atomic vote
        upvotes, downvotes, action_taken = await bot.db.cast_vote(
            guild_id=guild.id,
            suggestion_id=s_id,
            user_id=interaction.user.id,
            vote_type=vote_type,
        )

        # Update message embed
        try:
            old_embed = msg.embeds[0]
            author_user = guild.get_member(suggestion.author_id) or await bot.fetch_user(suggestion.author_id)
            updated_embed = create_suggestion_embed(
                suggestion_id=s_id,
                content=suggestion.content,
                author=author_user,
                status=suggestion.status,
                upvotes=upvotes,
                downvotes=downvotes,
                reason=suggestion.reason,
                reviewed_by=suggestion.reviewed_by,
                created_at_dt=msg.created_at,
            )
            await msg.edit(embed=updated_embed)
        except Exception as e:
            logger.error(f"Failed to update suggestion embed for #{s_id}: {e}")

        # Ephemeral feedback
        if action_taken == "added":
            await interaction.response.send_message(f"✅ Your **{vote_type}** was recorded!", ephemeral=True)
        elif action_taken == "switched":
            await interaction.response.send_message(f"🔄 Switched your vote to **{vote_type}**!", ephemeral=True)
        else:
            await interaction.response.send_message("❎ Removed your previous vote.", ephemeral=True)


class SuggestionsCog(commands.Cog, name="Suggestions"):
    """Community suggestions, voting, and staff review system."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # Register persistent view
        self.bot.add_view(SuggestionView())

    suggestion_group = app_commands.Group(
        name="suggestion",
        description="Suggestion system staff commands",
    )
    idea_group = app_commands.Group(
        name="idea",
        description="Community idea board and proposal tracking",
    )

    # ==========================================
    # USER SUBMISSION COMMAND
    # ==========================================

    @app_commands.command(name="suggest", description="Submit a suggestion for server improvement")
    @app_commands.describe(suggestion="Your suggestion text")
    async def suggest(self, interaction: discord.Interaction, suggestion: str):
        guild = interaction.guild
        cfg = await self.bot.db.get_suggestion_config(guild.id)

        if not cfg.suggestion_channel_id:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Suggestions Not Configured",
                    "The suggestion system has not been set up yet. An administrator must run `/suggestion setup`.",
                ),
                ephemeral=True,
            )
            return

        channel = guild.get_channel(cfg.suggestion_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Channel Unavailable", "The configured suggestions channel does not exist."),
                ephemeral=True,
            )
            return

        # Sanitize mentions
        sanitized = suggestion.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere").strip()

        # Length validation
        if len(sanitized) < cfg.minimum_length:
            await interaction.response.send_message(
                embed=error_embed("Suggestion Too Short", f"Your suggestion must be at least {cfg.minimum_length} characters."),
                ephemeral=True,
            )
            return
        if len(sanitized) > cfg.maximum_length:
            await interaction.response.send_message(
                embed=error_embed("Suggestion Too Long", f"Your suggestion cannot exceed {cfg.maximum_length} characters."),
                ephemeral=True,
            )
            return

        # Rate-limiting check
        is_limited, retry_after = await self.bot.cooldowns.check_and_reserve(
            scope=CooldownScope.USER_GUILD_CMD,
            command="suggest",
            user_id=interaction.user.id,
            guild_id=guild.id,
            cooldown_seconds=float(cfg.cooldown_seconds),
        )
        if is_limited:
            await interaction.response.send_message(
                f"⏳ Please wait `{retry_after}s` before submitting another suggestion.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Temporary message to reserve slot
        try:
            temp_msg = await channel.send("💡 Generating suggestion...")
            s_id = await self.bot.db.create_suggestion(
                guild_id=guild.id,
                channel_id=channel.id,
                message_id=temp_msg.id,
                author_id=interaction.user.id,
                content=sanitized,
            )

            # Build embed
            embed = create_suggestion_embed(
                suggestion_id=s_id,
                content=sanitized,
                author=interaction.user,
                status="pending",
                upvotes=0,
                downvotes=0,
            )
            view = SuggestionView(suggestion_id=s_id)
            await temp_msg.edit(content=None, embed=embed, view=view)

            # Create thread if enabled
            if cfg.discussion_enabled and channel.permissions_for(guild.me).create_public_threads:
                try:
                    thread = await temp_msg.create_thread(name=f"Suggestion #{s_id} Discussion")
                    await self.bot.db.update_suggestion_thread(s_id, thread.id)
                except Exception as e:
                    logger.warning(f"Could not create thread for suggestion #{s_id}: {e}")

            await interaction.followup.send(
                embed=success_embed(
                    "Suggestion Submitted!",
                    f"Your suggestion has been posted in {channel.mention} as **Suggestion #{s_id}**.",
                ),
                ephemeral=True,
            )
        except Exception as e:
            await self.bot.cooldowns.cancel_cooldown(
                CooldownScope.USER_GUILD_CMD, "suggest", interaction.user.id, guild.id
            )
            logger.error(f"Failed to submit suggestion: {e}")
            await interaction.followup.send(embed=error_embed("Submission Error", str(e)), ephemeral=True)

    # ==========================================
    # STAFF MANAGEMENT COMMANDS
    # ==========================================

    async def _check_staff_perms(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
            return True
        cfg = await self.bot.db.get_suggestion_config(interaction.guild.id)
        if cfg.staff_role_id:
            role = interaction.guild.get_role(cfg.staff_role_id)
            if role and role in interaction.user.roles:
                return True
        return interaction.user.guild_permissions.manage_guild

    @suggestion_group.command(name="setup", description="Configure suggestion channel, staff roles and rules")
    @is_admin_or_owner()
    @app_commands.describe(
        channel="Channel where suggestions are posted",
        staff_role="Staff role authorized to approve/reject suggestions",
        voting="Enable upvoting and downvoting buttons",
        discussions="Enable automatic discussion threads",
        cooldown="Cooldown between suggestions in seconds",
    )
    async def suggestion_setup(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        staff_role: Optional[discord.Role] = None,
        voting: Optional[bool] = None,
        discussions: Optional[bool] = None,
        cooldown: Optional[int] = None,
    ):
        updates = {}
        if channel:
            updates["suggestion_channel_id"] = channel.id
        if staff_role:
            updates["staff_role_id"] = staff_role.id
        if voting is not None:
            updates["voting_enabled"] = int(voting)
        if discussions is not None:
            updates["discussion_enabled"] = int(discussions)
        if cooldown is not None:
            updates["cooldown_seconds"] = max(5, min(cooldown, 86400))

        await self.bot.db.update_suggestion_config(interaction.guild.id, **updates)
        embed = success_embed(
            "Suggestion System Configured",
            f"**Channel:** {channel.mention if channel else 'Unchanged'}\n"
            f"**Staff Role:** {staff_role.mention if staff_role else 'Unchanged'}\n"
            f"**Voting Enabled:** {'Yes' if voting else 'Unchanged' if voting is None else 'No'}\n"
            f"**Discussion Threads:** {'Yes' if discussions else 'Unchanged' if discussions is None else 'No'}\n"
            f"**Cooldown:** {cooldown or 'Unchanged'}s",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _update_status_helper(
        self, interaction: discord.Interaction, suggestion_id: int, new_status: str, reason: Optional[str] = None
    ) -> None:
        if not await self._check_staff_perms(interaction):
            await interaction.response.send_message(
                embed=error_embed("Access Denied", "You do not have staff permissions to manage suggestions."),
                ephemeral=True,
            )
            return

        suggestion = await self.bot.db.get_suggestion(suggestion_id)
        if not suggestion or suggestion.guild_id != interaction.guild.id:
            await interaction.response.send_message(embed=error_embed("Not Found", f"Suggestion #{suggestion_id} does not exist."), ephemeral=True)
            return

        await self.bot.db.update_suggestion_status(suggestion_id, new_status, interaction.user.id, reason)

        # Update message in Discord
        ch = interaction.guild.get_channel(suggestion.channel_id)
        if ch and isinstance(ch, discord.TextChannel):
            try:
                msg = await ch.fetch_message(suggestion.message_id)
                author_user = interaction.guild.get_member(suggestion.author_id) or await self.bot.fetch_user(suggestion.author_id)
                new_embed = create_suggestion_embed(
                    suggestion_id=suggestion_id,
                    content=suggestion.content,
                    author=author_user,
                    status=new_status,
                    upvotes=suggestion.upvotes,
                    downvotes=suggestion.downvotes,
                    reason=reason,
                    reviewed_by=interaction.user.id,
                    created_at_dt=msg.created_at,
                )
                await msg.edit(embed=new_embed)
            except Exception as e:
                logger.warning(f"Could not edit suggestion message #{suggestion_id}: {e}")

        # Send DM notification to author if enabled
        cfg = await self.bot.db.get_suggestion_config(interaction.guild.id)
        if cfg.notifications_enabled:
            author_member = interaction.guild.get_member(suggestion.author_id)
            if author_member and not author_member.bot:
                try:
                    dm_embed = info_embed(
                        f"Suggestion #{suggestion_id} Update",
                        f"Your suggestion in **{interaction.guild.name}** was marked as **{new_status.capitalize()}** by {interaction.user.name}.\n"
                        f"> {suggestion.content[:200]}"
                    )
                    if reason:
                        dm_embed.add_field(name="Reason / Notes", value=reason, inline=False)
                    await author_member.send(embed=dm_embed)
                except Exception:
                    pass

        await interaction.response.send_message(
            embed=success_embed(
                f"Suggestion #{suggestion_id} {new_status.capitalize()}",
                f"Status updated to **{new_status.upper()}** by {interaction.user.mention}."
                + (f"\n**Reason:** {reason}" if reason else ""),
            ),
            ephemeral=True,
        )

    @suggestion_group.command(name="approve", description="Approve a submitted suggestion")
    @app_commands.describe(id="Suggestion ID number", reason="Optional approval notes")
    async def suggestion_approve(self, interaction: discord.Interaction, id: int, reason: Optional[str] = None):
        await self._update_status_helper(interaction, id, "approved", reason)

    @suggestion_group.command(name="reject", description="Reject a suggestion with a reason")
    @app_commands.describe(id="Suggestion ID number", reason="Reason for rejection")
    async def suggestion_reject(self, interaction: discord.Interaction, id: int, reason: str):
        await self._update_status_helper(interaction, id, "rejected", reason)

    @suggestion_group.command(name="implement", description="Mark a suggestion as implemented")
    @app_commands.describe(id="Suggestion ID number", reason="Optional notes on implementation")
    async def suggestion_implement(self, interaction: discord.Interaction, id: int, reason: Optional[str] = None):
        await self._update_status_helper(interaction, id, "implemented", reason)

    @suggestion_group.command(name="archive", description="Archive a suggestion and close voting")
    @app_commands.describe(id="Suggestion ID number", reason="Optional archival note")
    async def suggestion_archive(self, interaction: discord.Interaction, id: int, reason: Optional[str] = None):
        await self._update_status_helper(interaction, id, "archived", reason)

    @suggestion_group.command(name="reopen", description="Reopen an archived, approved, or rejected suggestion")
    @app_commands.describe(id="Suggestion ID number")
    async def suggestion_reopen(self, interaction: discord.Interaction, id: int):
        await self._update_status_helper(interaction, id, "pending", None)

    @suggestion_group.command(name="view", description="View details of a suggestion by ID")
    @app_commands.describe(id="Suggestion ID number")
    async def suggestion_view(self, interaction: discord.Interaction, id: int):
        suggestion = await self.bot.db.get_suggestion(id)
        if not suggestion or suggestion.guild_id != interaction.guild.id:
            await interaction.response.send_message(embed=error_embed("Not Found", f"Suggestion #{id} does not exist."), ephemeral=True)
            return

        author = interaction.guild.get_member(suggestion.author_id) or await self.bot.fetch_user(suggestion.author_id)
        embed = create_suggestion_embed(
            suggestion_id=id,
            content=suggestion.content,
            author=author,
            status=suggestion.status,
            upvotes=suggestion.upvotes,
            downvotes=suggestion.downvotes,
            reason=suggestion.reason,
            reviewed_by=suggestion.reviewed_by,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @suggestion_group.command(name="delete", description="Permanently delete a suggestion from the database and channel")
    @app_commands.describe(id="Suggestion ID number")
    async def suggestion_delete(self, interaction: discord.Interaction, id: int):
        if not await self._check_staff_perms(interaction):
            await interaction.response.send_message(embed=error_embed("Access Denied", "Staff permissions required."), ephemeral=True)
            return

        suggestion = await self.bot.db.get_suggestion(id)
        if not suggestion or suggestion.guild_id != interaction.guild.id:
            await interaction.response.send_message(embed=error_embed("Not Found", f"Suggestion #{id} does not exist."), ephemeral=True)
            return

        ch = interaction.guild.get_channel(suggestion.channel_id)
        if ch and isinstance(ch, discord.TextChannel):
            try:
                msg = await ch.fetch_message(suggestion.message_id)
                await msg.delete()
            except Exception:
                pass

        await self.bot.db.delete_suggestion(id)
        await interaction.response.send_message(
            embed=success_embed("Suggestion Deleted", f"Suggestion #{id} has been permanently deleted."),
            ephemeral=True,
        )

    # ==========================================
    # /idea COMMAND SUITE
    # ==========================================

    @idea_group.command(name="create", description="Submit a new community proposal or idea")
    @app_commands.describe(idea="Your idea description")
    async def idea_create(self, interaction: discord.Interaction, idea: str):
        await self.suggest.callback(self, interaction, suggestion=idea)

    @idea_group.command(name="list", description="List community ideas and proposals")
    async def idea_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = []
        if self.bot.db and self.bot.db._db:
            try:
                cur = await self.bot.db._db.execute(
                    "SELECT id, user_id, content, status, upvotes, downvotes FROM suggestions WHERE guild_id = ? ORDER BY id DESC LIMIT 10",
                    (interaction.guild.id,)
                )
                rows = await cur.fetchall()
            except Exception:
                pass

        if not rows:
            await interaction.followup.send("ℹ️ No community ideas submitted yet. Submit one with `/idea create`!")
            return

        embed = create_embed(
            title=f"💡 Community Ideas & Proposals — {interaction.guild.name}",
            description="Recent ideas submitted by the community:",
            color=Colors.PRIMARY,
        )
        for r in rows:
            s_id, author_id, content, status, upvotes, downvotes = r
            embed.add_field(
                name=f"#{s_id} • [{status.upper()}] 👍 {upvotes} | 👎 {downvotes}",
                value=f"{content[:150]}\n*Submitted by <@{author_id}> • View: `/idea view id:{s_id}`*",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @idea_group.command(name="view", description="View a specific idea by ID")
    @app_commands.describe(id="Idea ID number")
    async def idea_view(self, interaction: discord.Interaction, id: int):
        await self.suggestion_view.callback(self, interaction, id=id)

    @idea_group.command(name="vote", description="Vote on a community idea")
    @app_commands.describe(id="Idea ID number", vote="Your vote")
    @app_commands.choices(
        vote=[
            app_commands.Choice(name="👍 Upvote", value="upvote"),
            app_commands.Choice(name="👎 Downvote", value="downvote"),
        ]
    )
    async def idea_vote(self, interaction: discord.Interaction, id: int, vote: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        suggestion = await self.bot.db.get_suggestion(id)
        if not suggestion or suggestion.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Idea not found.", ephemeral=True)
            return

        if suggestion.status in ("archived", "rejected", "implemented"):
            await interaction.followup.send(f"⚠️ Voting on idea #{id} is closed ({suggestion.status}).", ephemeral=True)
            return

        existing_vote = await self.bot.db.get_user_vote(id, interaction.user.id)
        if existing_vote == vote.value:
            await interaction.followup.send(f"ℹ️ You already voted {vote.name} on idea #{id}.", ephemeral=True)
            return

        await self.bot.db.record_vote(id, interaction.user.id, vote.value)
        await interaction.followup.send(f"✅ Cast your {vote.name} on idea #{id}!", ephemeral=True)

    @idea_group.command(name="comment", description="Post a comment or discussion note on an idea thread")
    @app_commands.describe(id="Idea ID number", comment="Your comment")
    async def idea_comment(self, interaction: discord.Interaction, id: int, comment: str):
        await interaction.response.defer(ephemeral=True)
        suggestion = await self.bot.db.get_suggestion(id)
        if not suggestion or suggestion.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Idea not found.", ephemeral=True)
            return

        if suggestion.thread_id:
            thread = interaction.guild.get_thread(suggestion.thread_id)
            if thread:
                await thread.send(f"💬 **{interaction.user.display_name}**: {comment.strip()}")
                await interaction.followup.send(f"✅ Comment posted in idea thread {thread.mention}!", ephemeral=True)
                return

        await interaction.followup.send(f"💬 Recorded note on Idea #{id}: *{comment.strip()}*", ephemeral=True)

    @idea_group.command(name="status", description="Update status of an idea (Staff only)")
    @app_commands.describe(id="Idea ID number", status="New proposal status", reason="Status change notes")
    @app_commands.choices(
        status=[
            app_commands.Choice(name="🟡 Under Review", value="pending"),
            app_commands.Choice(name="🟢 Approved", value="approved"),
            app_commands.Choice(name="🟣 Planned / In Dev", value="implemented"),
            app_commands.Choice(name="🔴 Declined", value="rejected"),
            app_commands.Choice(name="⚫ Archived", value="archived"),
        ]
    )
    async def idea_status(
        self,
        interaction: discord.Interaction,
        id: int,
        status: app_commands.Choice[str],
        reason: Optional[str] = None,
    ):
        if not await self._check_staff_perms(interaction):
            await interaction.response.send_message(embed=error_embed("Access Denied", "Staff permissions required."), ephemeral=True)
            return

        if status.value == "approved":
            await self.suggestion_approve.callback(self, interaction, id=id, reason=reason)
        elif status.value == "rejected":
            await self.suggestion_reject.callback(self, interaction, id=id, reason=reason or "Declined by staff")
        elif status.value == "implemented":
            await self.suggestion_implement.callback(self, interaction, id=id, reason=reason)
        elif status.value == "archived":
            await self.suggestion_archive.callback(self, interaction, id=id, reason=reason)
        else:
            await self.suggestion_reopen.callback(self, interaction, id=id)


async def setup(bot: SentinelBot):
    await bot.add_cog(SuggestionsCog(bot))
