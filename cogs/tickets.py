"""
Interactive Ticket System with Persistent UI Buttons.
Features:
- Dedicated private ticket channels
- Interactive Create, Close, and Delete buttons
- Support role and category configuration
- Automatic message transcripts saved to disk and logged to staff channels
"""

from __future__ import annotations

import datetime
import io
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors, TRANSCRIPTS_DIR
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


# ==========================================
# INTERACTIVE TICKET UI BUTTONS
# ==========================================

class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="General Support",
                description="Questions about the community, roles, or bot features",
                emoji="❓",
                value="general",
            ),
            discord.SelectOption(
                label="Bug Reports",
                description="Report bugs, errors, or technical glitches",
                emoji="🐛",
                value="bug",
            ),
            discord.SelectOption(
                label="Staff Applications",
                description="Apply for moderator or event coordinator staff",
                emoji="📋",
                value="staff",
            ),
            discord.SelectOption(
                label="Partnership Requests",
                description="Server cross-promotions, affiliations, or collabs",
                emoji="🤝",
                value="partnership",
            ),
            discord.SelectOption(
                label="Private Support",
                description="Confidential matters or sensitive reports",
                emoji="🔒",
                value="private",
            ),
        ]
        super().__init__(
            placeholder="Select a support category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="sentinel_ticket_category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        await TicketPanelView.create_ticket_for_user(interaction, self.values[0])


class TicketPanelView(discord.ui.View):
    """Persistent panel for users to open categorized tickets."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())

    @discord.ui.button(
        label="General Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="sentinel_ticket_create",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_for_user(interaction, "general")

    @staticmethod
    async def create_ticket_for_user(interaction: discord.Interaction, category_choice: str = "general"):
        guild = interaction.guild
        bot: SentinelBot = interaction.client  # type: ignore

        # Rate limit: 1 ticket creation per 30s per user
        from utils.cooldowns import CooldownScope
        is_limited, retry_after = await bot.cooldowns.check_and_reserve(
            scope=CooldownScope.USER_GUILD_CMD,
            command="ticket_create",
            user_id=interaction.user.id,
            guild_id=guild.id,
            cooldown_seconds=30.0,
        )
        if is_limited:
            await interaction.response.send_message(
                f"Please wait {retry_after}s before creating another ticket.", ephemeral=True
            )
            return

        cfg = await bot.db.get_ticket_config(guild.id)
        category = guild.get_channel(cfg.category_id) if cfg.category_id else None
        if category and not isinstance(category, discord.CategoryChannel):
            category = None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True, embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True, manage_messages=True
            ),
        }

        if cfg.support_role_id:
            role = guild.get_role(cfg.support_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, attach_files=True
                )

        prefix_map = {
            "general": "ticket",
            "bug": "bug",
            "staff": "staff-app",
            "partnership": "partner",
            "private": "private",
        }
        prefix = prefix_map.get(category_choice, "ticket")
        clean_user = interaction.user.name[:10].replace(" ", "-")
        channel_name = f"{prefix}-{clean_user}-{str(interaction.user.id)[-4:]}"

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"[{category_choice.upper()}] Ticket by {interaction.user} ({interaction.user.id})",
            )
        except Exception as e:
            await bot.cooldowns.cancel_cooldown(
                CooldownScope.USER_GUILD_CMD, "ticket_create", interaction.user.id, guild.id
            )
            await interaction.response.send_message(
                embed=error_embed("Failed to Create Ticket", f"Missing permissions: {e}"), ephemeral=True
            )
            return

        ticket_id = await bot.db.create_ticket(guild.id, ticket_channel.id, interaction.user.id)

        category_titles = {
            "general": "General Support",
            "bug": "Bug Report",
            "staff": "Staff Application",
            "partnership": "Partnership Request",
            "private": "Private Support",
        }
        cat_title = category_titles.get(category_choice, "Support Ticket")

        embed = create_embed(
            title=f"🎫 {cat_title} #{ticket_id}",
            description=(
                f"Welcome {interaction.user.mention}!\n"
                f"Category: **{cat_title}**\n\n"
                "Please describe your request in detail. Staff will respond shortly.\n"
                "Use the buttons below to close or manage this ticket."
            ),
            color=Colors.PRIMARY,
        )
        if cfg.support_role_id:
            embed.add_field(name="Assigned Support", value=f"<@&{cfg.support_role_id}>", inline=True)

        view = TicketControlView()
        await ticket_channel.send(content=interaction.user.mention, embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True
        )


class TicketControlView(discord.ui.View):
    """Buttons displayed inside ticket channel to close or delete it."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="sentinel_ticket_close",
    )
    async def close_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot: SentinelBot = interaction.client  # type: ignore
        channel = interaction.channel

        await interaction.response.defer()

        # Check DB
        ticket = await bot.db.get_ticket_by_channel(channel.id)
        if not ticket or ticket.status != "open":
            await interaction.followup.send("This channel is not an active registered ticket.", ephemeral=True)
            return

        # Process transcript & DM dispatch
        await process_ticket_closure(bot, channel, interaction.user, interaction.guild)

        # Disable buttons and notify in ticket
        for child in self.children:
            child.disabled = True
        await interaction.followup.send(
            embed=warning_embed("Ticket Closed", f"Closed by {interaction.user.mention}. This channel will delete in 5 seconds.")
        )
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except (discord.Forbidden, discord.HTTPException):
            pass


async def process_ticket_closure(
    bot: SentinelBot,
    channel: discord.TextChannel,
    closer: discord.User | discord.Member,
    guild: discord.Guild,
) -> None:
    """Closes ticket in DB, generates HTML + TXT transcripts, logs to staff channel and DMs opener."""
    from utils.transcript_html import generate_html_transcript

    ticket_record = await bot.db.get_ticket_by_channel(channel.id)
    await bot.db.close_ticket(channel.id, closer.id)

    # 1. Plain text transcript
    transcript_text = await generate_transcript(channel)
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    txt_path = TRANSCRIPTS_DIR / f"transcript-{channel.name}-{now_str}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    # 2. Dark-mode HTML transcript
    html_text = await generate_html_transcript(channel, closer)
    html_path = TRANSCRIPTS_DIR / f"transcript-{channel.name}-{now_str}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_text)

    # 3. Staff channel dispatch
    cfg = await bot.db.get_ticket_config(guild.id)
    target_channel_id = cfg.log_channel_id or 1555641079137706014  # Default to #support-desk
    log_channel = guild.get_channel(target_channel_id)
    if log_channel and isinstance(log_channel, discord.TextChannel):
        embed = info_embed(
            f"Ticket Closed: #{channel.name}",
            f"Closed by {closer.mention}.\nDark-mode HTML transcript and raw log attached below.",
        )
        file_html = discord.File(str(html_path), filename=f"transcript-{channel.name}.html")
        file_txt = discord.File(str(txt_path), filename=f"transcript-{channel.name}.txt")
        try:
            await log_channel.send(embed=embed, files=[file_html, file_txt])
        except (discord.Forbidden, discord.HTTPException):
            pass

    # 4. DM ticket opener their copy
    if ticket_record and ticket_record.user_id:
        try:
            opener = guild.get_member(ticket_record.user_id) or await bot.fetch_user(ticket_record.user_id)
            if opener and not getattr(opener, "bot", False):
                dm_embed = discord.Embed(
                    title=f"✦ Support Ticket Closed ╏ #{channel.name} ✦",
                    description=(
                        f"Hello {opener.display_name},\n\n"
                        f"Your support ticket on **{guild.name}** has been completed and closed by {closer.mention}.\n\n"
                        "We have attached your official dark-mode HTML transcript below so you can retain a copy offline."
                    ),
                    color=0x2ECC71,
                )
                dm_file = discord.File(str(html_path), filename=f"transcript-{channel.name}.html")
                await opener.send(embed=dm_embed, file=dm_file)
        except (discord.Forbidden, discord.HTTPException):
            pass


async def generate_transcript(channel: discord.TextChannel) -> str:
    """Generates plain text transcript of messages in the channel."""
    lines = [
        f"=== TRANSCRIPT FOR #{channel.name} ===",
        f"Generated At: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        f"Guild: {channel.guild.name} ({channel.guild.id})",
        "=" * 40,
        "",
    ]
    async for msg in channel.history(limit=500, oldest_first=True):
        time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{time_str}] {msg.author} ({msg.author.id}):")
        if msg.content:
            lines.append(f"  {msg.content}")
        for att in msg.attachments:
            lines.append(f"  [Attachment: {att.url}]")
        lines.append("")
    return "\n".join(lines)


class TicketsCog(commands.Cog, name="Tickets"):
    """Ticket Management Cog."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # Register persistent views so buttons work across bot restarts
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketControlView())

    ticket_group = app_commands.Group(
        name="ticket",
        description="Ticket support system commands",
    )

    @ticket_group.command(name="setup", description="Deploy the ticket creation panel embed with buttons")
    @is_admin_or_owner()
    @app_commands.describe(
        category="Category channel to organize new tickets in",
        support_role="Staff role with access to view/respond to tickets",
        log_channel="Channel where ticket transcripts and closure logs will be sent",
    )
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        category: Optional[discord.CategoryChannel] = None,
        support_role: Optional[discord.Role] = None,
        log_channel: Optional[discord.TextChannel] = None,
    ):
        updates = {}
        if category:
            updates["category_id"] = category.id
        if support_role:
            updates["support_role_id"] = support_role.id
        if log_channel:
            updates["log_channel_id"] = log_channel.id

        await self.bot.db.update_ticket_config(interaction.guild.id, **updates)
        await self.bot.db.update_guild_config(interaction.guild.id, tickets_enabled=True)

        embed = create_embed(
            title="📩 Need Support? Open a Ticket!",
            description=(
                "Click the button below to open a private support ticket with our server staff team.\n\n"
                "• A private channel will be created exclusively for you.\n"
                "• Please describe your inquiry clearly upon opening."
            ),
            color=Colors.PRIMARY,
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        panel_view = TicketPanelView()
        await interaction.channel.send(embed=embed, view=panel_view)
        await interaction.response.send_message(
            embed=success_embed("Ticket Panel Created", "The support ticket panel has been posted in this channel."),
            ephemeral=True,
        )

    @ticket_group.command(name="close", description="Close the current ticket channel and generate a transcript")
    async def ticket_close(self, interaction: discord.Interaction):
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket or ticket.status != "open":
            await interaction.response.send_message(
                embed=error_embed("Not a Ticket", "This channel is not an active registered support ticket."),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        await process_ticket_closure(self.bot, interaction.channel, interaction.user, interaction.guild)

        await interaction.followup.send(embed=warning_embed("Ticket Closed", "This channel will be deleted in 5 seconds."))
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Closed by {interaction.user}")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @ticket_group.command(name="add", description="Add another user to this ticket channel")
    @app_commands.describe(user="The user to add to the ticket")
    async def ticket_add(self, interaction: discord.Interaction, user: discord.Member):
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket or ticket.status != "open":
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This channel is not an active support ticket."), ephemeral=True)
            return

        channel: discord.TextChannel = interaction.channel  # type: ignore
        await channel.set_permissions(user, read_messages=True, send_messages=True, attach_files=True)
        await interaction.response.send_message(embed=success_embed("User Added", f"Added {user.mention} to this ticket."))

    @ticket_group.command(name="remove", description="Remove a user from this ticket channel")
    @app_commands.describe(user="The user to remove from the ticket")
    async def ticket_remove(self, interaction: discord.Interaction, user: discord.Member):
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket or ticket.status != "open":
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This channel is not an active support ticket."), ephemeral=True)
            return

        channel: discord.TextChannel = interaction.channel  # type: ignore
        await channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(embed=success_embed("User Removed", f"Removed {user.mention} from this ticket."))

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Fallback listener for custom_id='create_ticket_btn'."""
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if custom_id == "create_ticket_btn":
            view = TicketPanelView()
            await view.create_ticket(interaction, None)  # type: ignore


async def setup(bot: SentinelBot):
    bot.add_view(TicketPanelView())
    await bot.add_cog(TicketsCog(bot))


