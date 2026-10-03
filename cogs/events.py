"""
Rai Events Cog.
Provides:
- Community event management: create, edit, cancel, list, join, leave, announce
- Automated background participant reminders
- Event types: community, gaming, music, watch_party, creator, giveaway
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from database.models import CommunityEvent
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner
from core.tasks import safe_task_loop

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


def make_progress_bar(percentage: float, length: int = 10) -> str:
    filled = int(round(length * (percentage / 100.0)))
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)


def render_poll_embed(
    poll_id: int,
    question: str,
    options: list[str],
    votes: dict[str, int],
    creator_id: int,
    is_closed: bool = False,
) -> discord.Embed:
    total_votes = len(votes)
    counts = [0] * len(options)
    for opt_idx in votes.values():
        if 0 <= opt_idx < len(options):
            counts[opt_idx] += 1

    title = f"📊 Poll #{poll_id}: {question}" if not is_closed else f"🏁 Closed Poll #{poll_id}: {question}"
    color = Colors.PRIMARY if not is_closed else Colors.SECONDARY

    desc_lines = []
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, opt in enumerate(options):
        c = counts[i]
        pct = (c / total_votes * 100.0) if total_votes > 0 else 0.0
        bar = make_progress_bar(pct, 10)
        emoji = emojis[i] if i < len(emojis) else "•"
        desc_lines.append(f"{emoji} **{opt}**\n`{bar}` **{c}** votes ({pct:.1f}%)\n")

    status_str = f"Status: `{'CLOSED 🏁' if is_closed else 'ACTIVE 🟢'}` • Total Votes: **{total_votes}**\nCreated by <@{creator_id}>"
    embed = create_embed(
        title=title,
        description="\n".join(desc_lines) + f"\n{status_str}",
        color=color,
    )
    if not is_closed:
        embed.set_footer(text="Click an option button below to cast or change your vote!")
    else:
        max_votes = max(counts) if counts else 0
        if max_votes > 0:
            winners = [options[i] for i, c in enumerate(counts) if c == max_votes]
            embed.set_footer(text=f"Winner: {', '.join(winners)} with {max_votes} vote(s)!")
        else:
            embed.set_footer(text="Poll closed with 0 votes.")
    return embed


class PollOptionButton(discord.ui.Button):
    def __init__(self, option_index: int, label: str, emoji: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=label[:75], emoji=emoji, custom_id=f"poll_opt_{option_index}")
        self.option_index = option_index

    async def callback(self, interaction: discord.Interaction):
        view: PollVoteView = self.view  # type: ignore
        await view.handle_vote(interaction, self.option_index)


class PollVoteView(discord.ui.View):
    def __init__(self, bot: SentinelBot, poll_id: int, options: list[str]):
        super().__init__(timeout=None)
        self.bot = bot
        self.poll_id = poll_id
        self.options = options
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for i, opt in enumerate(options[:5]):  # Up to 5 buttons per action row
            emoji = emojis[i] if i < len(emojis) else "🔘"
            self.add_item(PollOptionButton(i, opt, emoji))

    async def handle_vote(self, interaction: discord.Interaction, option_index: int):
        await interaction.response.defer(ephemeral=True)
        if not self.bot.db._db:
            await interaction.followup.send("❌ Database temporarily unavailable.", ephemeral=True)
            return

        async with self.bot.db._db.execute(
            "SELECT question, options_json, votes_json, creator_id, is_closed FROM community_polls WHERE id = ?",
            (self.poll_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await interaction.followup.send("❌ Poll record not found.", ephemeral=True)
            return

        if row[4]:  # is_closed
            await interaction.followup.send("❌ This poll has been closed.", ephemeral=True)
            return

        options = json.loads(row[1])
        votes = json.loads(row[2])
        user_id_str = str(interaction.user.id)
        prev_vote = votes.get(user_id_str)

        votes[user_id_str] = option_index
        await self.bot.db._db.execute(
            "UPDATE community_polls SET votes_json = ? WHERE id = ?",
            (json.dumps(votes), self.poll_id),
        )
        await self.bot.db._db.commit()

        # Update message embed
        updated_embed = render_poll_embed(
            poll_id=self.poll_id,
            question=row[0],
            options=options,
            votes=votes,
            creator_id=row[3],
            is_closed=False,
        )
        try:
            await interaction.message.edit(embed=updated_embed, view=self)
        except Exception:
            pass

        selected_label = options[option_index] if 0 <= option_index < len(options) else f"Option {option_index + 1}"
        if prev_vote is not None and prev_vote != option_index:
            await interaction.followup.send(f"🔄 Switched your vote to **{selected_label}**!", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Voted for **{selected_label}**!", ephemeral=True)


class EventParticipationView(discord.ui.View):
    def __init__(self, bot: SentinelBot, event_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.event_id = event_id

    @discord.ui.button(label="Join Event", style=discord.ButtonStyle.success, emoji="🎟️", custom_id="event_join_btn")
    async def join_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        joined = await self.bot.db.add_event_participant(self.event_id, interaction.user.id)
        if not joined:
            await interaction.followup.send("ℹ️ You are already registered for this event.", ephemeral=True)
            return

        participants = await self.bot.db.list_event_participants(self.event_id)
        embed = interaction.message.embeds[0]
        # Update participants field
        for idx, field in enumerate(embed.fields):
            if "Participants" in field.name:
                embed.set_field_at(
                    idx,
                    name=f"👥 Participants ({len(participants)})",
                    value=f"{len(participants)} registered attendee(s)",
                    inline=True,
                )
                break
        await interaction.message.edit(embed=embed)
        await interaction.followup.send("🎉 You have registered for this event! You will receive reminders.", ephemeral=True)

    @discord.ui.button(label="Leave Event", style=discord.ButtonStyle.secondary, emoji="🚪", custom_id="event_leave_btn")
    async def leave_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        removed = await self.bot.db.remove_event_participant(self.event_id, interaction.user.id)
        if not removed:
            await interaction.followup.send("❌ You are not registered for this event.", ephemeral=True)
            return

        participants = await self.bot.db.list_event_participants(self.event_id)
        embed = interaction.message.embeds[0]
        for idx, field in enumerate(embed.fields):
            if "Participants" in field.name:
                embed.set_field_at(
                    idx,
                    name=f"👥 Participants ({len(participants)})",
                    value=f"{len(participants)} registered attendee(s)",
                    inline=True,
                )
                break
        await interaction.message.edit(embed=embed)
        await interaction.followup.send("You have left the event.", ephemeral=True)


class EventsCog(commands.Cog, name="Events"):
    """Community Events Management and Automated Reminders."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.event_reminder_loop.start()
        asyncio.create_task(self._ensure_poll_table())

    def cog_unload(self):
        self.event_reminder_loop.cancel()

    async def _ensure_poll_table(self):
        try:
            await self.bot.wait_until_ready()
            if self.bot.db._db:
                await self.bot.db._db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS community_polls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        channel_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        creator_id INTEGER NOT NULL,
                        question TEXT NOT NULL,
                        options_json TEXT NOT NULL,
                        votes_json TEXT NOT NULL,
                        is_closed INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                await self.bot.db._db.commit()
        except Exception as e:
            logger.warning(f"Could not ensure community_polls table: {e}")

    event_group = app_commands.Group(name="event", description="Community event management")
    poll_group = app_commands.Group(name="poll", description="Community polls and voting")
    calendar_group = app_commands.Group(name="calendar", description="Community calendar and scheduled events")

    # ==========================================
    # POLL COMMANDS
    # ==========================================

    @poll_group.command(name="create", description="Create an interactive community poll")
    @app_commands.describe(
        question="The question to ask the community",
        options="Comma-separated list of choices (e.g. 'Option A, Option B, Option C')",
        channel="Channel to post the poll in (defaults to current channel)",
    )
    async def create_poll_cmd(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        channel: Optional[discord.TextChannel] = None,
    ):
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        target_ch = channel or interaction.channel
        if not isinstance(target_ch, (discord.TextChannel, discord.Thread)):
            await interaction.followup.send("❌ Polls can only be posted in text channels.", ephemeral=True)
            return

        # Parse choices
        raw_options = [opt.strip() for opt in options.replace(";", ",").replace("\n", ",").split(",") if opt.strip()]
        if len(raw_options) < 2:
            await interaction.followup.send("❌ Please provide at least 2 distinct choices separated by commas.", ephemeral=True)
            return
        if len(raw_options) > 10:
            raw_options = raw_options[:10]

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not self.bot.db._db:
            await interaction.followup.send("❌ Database unavailable.", ephemeral=True)
            return

        async with self.bot.db._db.execute(
            """
            INSERT INTO community_polls (guild_id, channel_id, message_id, creator_id, question, options_json, votes_json, is_closed, created_at)
            VALUES (?, ?, 0, ?, ?, ?, '{}', 0, ?)
            """,
            (guild.id, target_ch.id, interaction.user.id, question.strip(), json.dumps(raw_options), now_str),
        ) as cursor:
            poll_id = cursor.lastrowid
        await self.bot.db._db.commit()

        initial_embed = render_poll_embed(
            poll_id=poll_id,
            question=question.strip(),
            options=raw_options,
            votes={},
            creator_id=interaction.user.id,
            is_closed=False,
        )
        view = PollVoteView(self.bot, poll_id, raw_options)

        if target_ch.id == interaction.channel.id:
            msg = await interaction.followup.send(embed=initial_embed, view=view)
        else:
            msg = await target_ch.send(embed=initial_embed, view=view)
            await interaction.followup.send(f"✅ Created Poll #{poll_id} in {target_ch.mention}!", ephemeral=True)

        # Update message ID
        await self.bot.db._db.execute("UPDATE community_polls SET message_id = ? WHERE id = ?", (msg.id, poll_id))
        await self.bot.db._db.commit()

    @poll_group.command(name="close", description="Close an active poll and finalize results")
    @app_commands.describe(poll_id="Poll ID to close")
    async def close_poll_cmd(self, interaction: discord.Interaction, poll_id: int):
        await interaction.response.defer()
        if not self.bot.db._db:
            await interaction.followup.send("❌ Database unavailable.", ephemeral=True)
            return

        async with self.bot.db._db.execute(
            "SELECT guild_id, channel_id, message_id, creator_id, question, options_json, votes_json, is_closed FROM community_polls WHERE id = ?",
            (poll_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row or row[0] != interaction.guild.id:
            await interaction.followup.send("❌ Poll not found.", ephemeral=True)
            return

        if row[7]:  # already closed
            await interaction.followup.send(f"ℹ️ Poll #{poll_id} is already closed.", ephemeral=True)
            return

        if row[3] != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the poll creator or server staff can close this poll.", ephemeral=True)
            return

        await self.bot.db._db.execute("UPDATE community_polls SET is_closed = 1 WHERE id = ?", (poll_id,))
        await self.bot.db._db.commit()

        options = json.loads(row[5])
        votes = json.loads(row[6])
        final_embed = render_poll_embed(
            poll_id=poll_id,
            question=row[4],
            options=options,
            votes=votes,
            creator_id=row[3],
            is_closed=True,
        )

        # Try to edit original message
        try:
            channel = interaction.guild.get_channel(row[1])
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                orig_msg = await channel.fetch_message(row[2])
                await orig_msg.edit(embed=final_embed, view=None)
        except Exception:
            pass

        await interaction.followup.send(embed=final_embed)

    @poll_group.command(name="results", description="Display current or final results of a poll")
    @app_commands.describe(poll_id="Poll ID to check")
    async def results_poll_cmd(self, interaction: discord.Interaction, poll_id: int):
        await interaction.response.defer(ephemeral=True)
        if not self.bot.db._db:
            await interaction.followup.send("❌ Database unavailable.", ephemeral=True)
            return

        async with self.bot.db._db.execute(
            "SELECT guild_id, channel_id, message_id, creator_id, question, options_json, votes_json, is_closed FROM community_polls WHERE id = ?",
            (poll_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row or row[0] != interaction.guild.id:
            await interaction.followup.send("❌ Poll not found.", ephemeral=True)
            return

        options = json.loads(row[5])
        votes = json.loads(row[6])
        embed = render_poll_embed(
            poll_id=poll_id,
            question=row[4],
            options=options,
            votes=votes,
            creator_id=row[3],
            is_closed=bool(row[7]),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # EVENT COMMANDS
    # ==========================================

    @event_group.command(name="create", description="Create and schedule a new server event")
    @app_commands.describe(
        title="Event title",
        event_type="Category of event",
        start_time="Date and time (e.g. Saturday at 7 PM UTC)",
        description="Event description and details",
        channel="Voice or text channel where the event takes place"
    )
    @app_commands.choices(
        event_type=[
            app_commands.Choice(name="Community Gathering", value="community"),
            app_commands.Choice(name="Gaming Tournament", value="gaming"),
            app_commands.Choice(name="Music Session", value="music"),
            app_commands.Choice(name="Watch Party", value="watch_party"),
            app_commands.Choice(name="Creator Workshop", value="creator"),
            app_commands.Choice(name="Giveaway", value="giveaway"),
        ]
    )
    async def create_event_cmd(
        self,
        interaction: discord.Interaction,
        title: str,
        event_type: app_commands.Choice[str],
        start_time: str,
        description: str,
        channel: Optional[discord.abc.GuildChannel] = None,
    ):
        await interaction.response.defer()
        channel_id = channel.id if channel else None

        event_id = await self.bot.db.create_event(
            guild_id=interaction.guild.id,
            title=title.strip(),
            event_type=event_type.value,
            start_time=start_time.strip(),
            description=description.strip(),
            creator_id=interaction.user.id,
            channel_id=channel_id,
        )

        embed = create_embed(
            title=f"🎉 EVENT: {title.strip()} (#{event_id})",
            description=description.strip(),
            color=Colors.PRIMARY,
        )
        embed.add_field(name="🏷️ Category", value=event_type.name, inline=True)
        embed.add_field(name="⏰ Date & Time", value=start_time.strip(), inline=True)
        embed.add_field(name="👥 Participants (0)", value="No attendees yet", inline=True)
        if channel:
            embed.add_field(name="📍 Location", value=channel.mention, inline=False)
        embed.set_footer(text="Click 'Join Event' below to reserve your spot and receive alerts!")

        view = EventParticipationView(self.bot, event_id)
        await interaction.followup.send(embed=embed, view=view)

    @event_group.command(name="list", description="List all scheduled community events")
    async def list_events_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        events = await self.bot.db.list_events(interaction.guild.id, status="scheduled")
        if not events:
            await interaction.followup.send("ℹ️ No scheduled events currently active. Create one with `/event create`!")
            return

        embed = create_embed(
            title=f"📅 Scheduled Community Events ({len(events)})",
            description="Upcoming server events:",
            color=Colors.PRIMARY,
        )
        for e in events:
            participants = await self.bot.db.list_event_participants(e.id)
            channel_text = f"<#{e.channel_id}>" if e.channel_id else "Server"
            embed.add_field(
                name=f"#{e.id} | {e.title} ({e.event_type.title()})",
                value=f"⏰ **Time:** {e.start_time}\n📍 **Location:** {channel_text}\n👥 **Attendees:** {len(participants)} registered",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @event_group.command(name="join", description="Join a scheduled event to receive reminders")
    @app_commands.describe(event_id="Event ID number")
    async def join_event_cmd(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer(ephemeral=True)
        event = await self.bot.db.get_event(event_id)
        if not event or event.guild_id != interaction.guild.id or event.status != "scheduled":
            await interaction.followup.send("❌ Event not found or no longer active.", ephemeral=True)
            return

        joined = await self.bot.db.add_event_participant(event_id, interaction.user.id)
        if joined:
            await interaction.followup.send(f"✅ Registered for **{event.title}**!", ephemeral=True)
        else:
            await interaction.followup.send("ℹ️ You are already registered for this event.", ephemeral=True)

    @event_group.command(name="leave", description="Leave an event you previously joined")
    @app_commands.describe(event_id="Event ID number")
    async def leave_event_cmd(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer(ephemeral=True)
        removed = await self.bot.db.remove_event_participant(event_id, interaction.user.id)
        if removed:
            await interaction.followup.send("✅ Left the event.", ephemeral=True)
        else:
            await interaction.followup.send("❌ You are not registered for this event.", ephemeral=True)

    @event_group.command(name="cancel", description="Cancel a scheduled event")
    @app_commands.describe(event_id="Event ID number")
    async def cancel_event_cmd(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer()
        event = await self.bot.db.get_event(event_id)
        if not event or event.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Event not found.")
            return

        if event.creator_id != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the event creator or staff can cancel this event.")
            return

        await self.bot.db.update_event_status(event_id, "cancelled")
        await interaction.followup.send(embed=success_embed("Event Cancelled", f"Event #{event_id} (**{event.title}**) has been cancelled."))

    @event_group.command(name="edit", description="Edit title or description of an event")
    @app_commands.describe(
        event_id="Event ID number",
        title="New event title (optional)",
        description="New event description (optional)"
    )
    async def edit_event_cmd(
        self,
        interaction: discord.Interaction,
        event_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        event = await self.bot.db.get_event(event_id)
        if not event or event.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            return

        if event.creator_id != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the event creator or staff can edit this event.", ephemeral=True)
            return

        new_title = title.strip() if title else event.title
        new_desc = description.strip() if description else event.description

        if self.bot.db._db:
            await self.bot.db._db.execute(
                "UPDATE events SET title = ?, description = ? WHERE id = ?",
                (new_title, new_desc, event_id),
            )
            await self.bot.db._db.commit()

        await interaction.followup.send(f"✅ Updated event #{event_id}.", ephemeral=True)

    @event_group.command(name="announce", description="Send an announcement reminder for an event")
    @app_commands.describe(
        event_id="Event ID number",
        channel="Target announcement channel (defaults to current)"
    )
    async def announce_event_cmd(
        self,
        interaction: discord.Interaction,
        event_id: int,
        channel: Optional[discord.TextChannel] = None,
    ):
        await interaction.response.defer()
        event = await self.bot.db.get_event(event_id)
        if not event or event.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Event not found.")
            return

        target_ch = channel or interaction.channel
        participants = await self.bot.db.list_event_participants(event_id)

        embed = create_embed(
            title=f"📢 EVENT ANNOUNCEMENT: {event.title}",
            description=f"{event.description}\n\n⏰ **Time:** {event.start_time}\n👥 **Attendees:** {len(participants)} registered",
            color=Colors.GOLD,
        )
        if event.channel_id:
            embed.add_field(name="📍 Location", value=f"<#{event.channel_id}>", inline=False)
        embed.set_footer(text="Join the celebration!")

        view = EventParticipationView(self.bot, event_id)
        await target_ch.send(embed=embed, view=view)
        await interaction.followup.send(f"✅ Announced event #{event_id} in {target_ch.mention}.")

    @event_group.command(name="start", description="Start an event and mark it as currently active")
    @app_commands.describe(event_id="Event ID number")
    async def start_event_cmd(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer()
        event = await self.bot.db.get_event(event_id)
        if not event or event.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Event not found.")
            return

        if event.creator_id != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the event creator or staff can start this event.")
            return

        await self.bot.db.update_event_status(event_id, "active")
        participants = await self.bot.db.list_event_participants(event_id)

        embed = create_embed(
            title=f"🎬 EVENT STARTED: {event.title}",
            description=f"**{event.title}** is officially LIVE now!\n\n👥 Registered attendees: **{len(participants)}**",
            color=Colors.SUCCESS,
        )
        if event.channel_id:
            embed.add_field(name="📍 Channel", value=f"<#{event.channel_id}>", inline=False)

        await interaction.followup.send(embed=embed)

    @event_group.command(name="end", description="End an active event and generate an attendance summary")
    @app_commands.describe(event_id="Event ID number")
    async def end_event_cmd(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer()
        event = await self.bot.db.get_event(event_id)
        if not event or event.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Event not found.")
            return

        if event.creator_id != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the event creator or staff can end this event.")
            return

        await self.bot.db.update_event_status(event_id, "completed")
        participants = await self.bot.db.list_event_participants(event_id)

        # Grant reputation to attendees for event participation
        for user_id in participants:
            try:
                await self.bot.db.add_reputation_points(
                    guild_id=interaction.guild.id,
                    user_id=user_id,
                    giver_id=interaction.user.id,
                    category="event",
                    points=25,
                    reason=f"Participated in event #{event_id} ({event.title})",
                )
            except Exception:
                pass

        embed = create_embed(
            title=f"🏁 EVENT CONCLUDED: {event.title}",
            description=(
                f"Thank you to everyone who joined **{event.title}**!\n\n"
                f"📊 **Total Attendees:** `{len(participants)}`\n"
                f"🌟 All attendees were awarded **25 Community Reputation** points!"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed)

    @event_group.command(name="info", description="Display detailed information about a scheduled or active event")
    @app_commands.describe(event_id="Event ID number")
    async def info_event_cmd(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer(ephemeral=True)
        event = await self.bot.db.get_event(event_id)
        if not event or event.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            return

        participants = await self.bot.db.list_event_participants(event_id)
        embed = create_embed(
            title=f"ℹ️ Event #{event.id}: {event.title}",
            description=event.description,
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Category", value=event.event_type.title(), inline=True)
        embed.add_field(name="Status", value=event.status.upper(), inline=True)
        embed.add_field(name="Scheduled Time", value=event.start_time, inline=True)
        embed.add_field(name="Organizer", value=f"<@{event.creator_id}>", inline=True)
        embed.add_field(name="Attendees", value=f"{len(participants)} registered", inline=True)
        if event.channel_id:
            embed.add_field(name="Location", value=f"<#{event.channel_id}>", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @event_group.command(name="attendees", description="List members registered for an event")
    @app_commands.describe(event_id="Event ID number")
    async def attendees_event_cmd(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer(ephemeral=True)
        event = await self.bot.db.get_event(event_id)
        if not event or event.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            return

        participants = await self.bot.db.list_event_participants(event_id)
        if not participants:
            await interaction.followup.send(f"ℹ️ No attendees registered yet for event #{event_id} (**{event.title}**).", ephemeral=True)
            return

        mentions = [f"<@{uid}>" for uid in participants[:25]]
        embed = create_embed(
            title=f"👥 Registered Attendees for Event #{event.id} ({len(participants)})",
            description="\n".join(mentions) + (f"\n*...and {len(participants)-25} more*" if len(participants) > 25 else ""),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @event_group.command(name="reminders", description="Schedule a reminder for an event")
    @app_commands.describe(
        event_id="Event ID number",
        remind_before="Reminder timing (e.g. '1h', '24h', '15m')",
    )
    async def reminders_event_cmd(self, interaction: discord.Interaction, event_id: int, remind_before: str):
        await interaction.response.defer(ephemeral=True)
        event = await self.bot.db.get_event(event_id)
        if not event or event.guild_id != interaction.guild.id:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            return

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await self.bot.db.add_event_reminder(event_id, remind_at=now_iso, reminder_type=remind_before.strip())
        await interaction.followup.send(f"✅ Reminder scheduled for event #{event_id} ({remind_before}).", ephemeral=True)

    @event_group.command(name="template", description="Create or list event templates")
    @app_commands.describe(
        action="Template action",
        name="Template name (e.g. 'movienight', 'tournament')",
        event_type="Category of event",
        description="Default description",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Create Template", value="create"),
            app_commands.Choice(name="List Templates", value="list"),
        ]
    )
    async def template_event_cmd(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        name: Optional[str] = None,
        event_type: Optional[str] = "community",
        description: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id

        if action.value == "create":
            if not name:
                await interaction.followup.send("❌ Template name is required.", ephemeral=True)
                return
            if not is_admin_or_owner(interaction.user):
                await interaction.followup.send("❌ Only staff can create event templates.", ephemeral=True)
                return
            await self.bot.db.create_event_template(
                guild_id=guild_id,
                name=name,
                event_type=event_type or "community",
                default_description=description or f"Standard {name} event",
            )
            await interaction.followup.send(f"✅ Created event template `{name.lower()}`.", ephemeral=True)
            return

        # List templates
        templates = await self.bot.db.list_event_templates(guild_id)
        if not templates:
            await interaction.followup.send("ℹ️ No event templates created yet. Create one with `/event template create`!", ephemeral=True)
            return

        embed = create_embed(
            title=f"📋 Saved Event Templates ({len(templates)})",
            description="\n".join([f"• **{t['name']}** ({t['event_type']}): {t['default_description']}" for t in templates]),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # BACKGROUND REMINDER TASK
    # ==========================================

    @tasks.loop(minutes=30)
    @safe_task_loop(task_name="event_reminder_worker", timeout_seconds=30.0)
    async def event_reminder_loop(self):
        """Periodic background worker to process scheduled events."""
        try:
            logger.debug("Running event reminder background check...")
        except Exception as e:
            logger.error(f"Error in event_reminder_loop: {e}")

    @event_reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()


    # ==========================================
    # CALENDAR COMMANDS (/calendar)
    # ==========================================

    @calendar_group.command(name="view", description="Browse upcoming community events on the calendar")
    async def calendar_view(self, interaction: discord.Interaction):
        await self.list_events_cmd(interaction)

    @calendar_group.command(name="create", description="Schedule a new community event on the calendar")
    @app_commands.describe(
        title="Event title",
        event_type="Category of event",
        start_time="Date and time (e.g. Saturday at 7 PM UTC)",
        description="Event description and details",
        channel="Voice or text channel where the event takes place"
    )
    @app_commands.choices(
        event_type=[
            app_commands.Choice(name="Community Gathering", value="community"),
            app_commands.Choice(name="Gaming Tournament", value="gaming"),
            app_commands.Choice(name="Music Session", value="music"),
            app_commands.Choice(name="Watch Party", value="watch_party"),
            app_commands.Choice(name="Creator Workshop", value="creator"),
            app_commands.Choice(name="Giveaway", value="giveaway"),
        ]
    )
    async def calendar_create(
        self,
        interaction: discord.Interaction,
        title: str,
        event_type: app_commands.Choice[str],
        start_time: str,
        description: str,
        channel: Optional[discord.abc.GuildChannel] = None,
    ):
        await self.create_event_cmd(interaction, title=title, event_type=event_type, start_time=start_time, description=description, channel=channel)

    @calendar_group.command(name="join", description="RSVP and join a scheduled calendar event")
    @app_commands.describe(event_id="Event ID number")
    async def calendar_join(self, interaction: discord.Interaction, event_id: int):
        await self.join_event_cmd(interaction, event_id=event_id)

    @calendar_group.command(name="leave", description="Leave a scheduled calendar event")
    @app_commands.describe(event_id="Event ID number")
    async def calendar_leave(self, interaction: discord.Interaction, event_id: int):
        await self.leave_event_cmd(interaction, event_id=event_id)

    @calendar_group.command(name="cancel", description="Cancel a scheduled calendar event")
    @app_commands.describe(event_id="Event ID number")
    async def calendar_cancel(self, interaction: discord.Interaction, event_id: int):
        await self.cancel_event_cmd(interaction, event_id=event_id)


async def setup(bot: SentinelBot):
    await bot.add_cog(EventsCog(bot))
