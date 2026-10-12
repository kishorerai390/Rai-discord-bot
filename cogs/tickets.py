"""
Comprehensive Interactive Support, Report, and Ticket Management Cog.
Features:
- Dedicated private ticket channels with strict permission isolation
- Multi-category support (General, Bug Reports, Security Incidents, Appeals, Technical)
- Interactive buttons (Create, Claim, Close, Reopen, Transcript, Archive)
- Duplicate ticket prevention and configurable rate limits
- Dark-mode HTML and text transcripts logged to staff channels and DMed to users
- Top-level /report command for confidential user, bug, and incident reports
- Full integration with Centralized Logging (ticket-logs, report-logs, staff-logs)
"""

from __future__ import annotations

import asyncio
import datetime
import io
import logging
import os
import uuid
from typing import TYPE_CHECKING, Optional, List
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors, TRANSCRIPTS_DIR
from database.models import SupportTicket
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
                label="Security Incident",
                description="Report raids, vulnerabilities, or security concerns",
                emoji="🛡️",
                value="security",
            ),
            discord.SelectOption(
                label="Moderation Appeal",
                description="Appeal a timeout, kick, warning, or moderation action",
                emoji="⚖️",
                value="appeal",
            ),
            discord.SelectOption(
                label="Staff Applications",
                description="Apply for moderator or event coordinator staff",
                emoji="📋",
                value="staff",
            ),
            discord.SelectOption(
                label="Private Support",
                description="Confidential matters or sensitive management inquiries",
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
    async def create_ticket_for_user(
        interaction: discord.Interaction,
        category_choice: str = "general",
        subject: Optional[str] = None,
    ):
        guild = interaction.guild
        bot: SentinelBot = interaction.client  # type: ignore

        # 1. Rate limit: 1 ticket creation per 30s per user
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
                f"⏳ Please wait `{retry_after}s` before creating another ticket.", ephemeral=True
            )
            return

        # 2. Check for duplicate open tickets by this user in this server
        open_tickets = await bot.db.get_open_support_tickets_for_user(guild.id, interaction.user.id)
        if len(open_tickets) >= 3:
            await interaction.response.send_message(
                "⚠️ **Active Ticket Limit:** You already have 3 open support tickets in this server. "
                "Please close or wait for resolution of your existing tickets before opening a new one.",
                ephemeral=True,
            )
            return

        cfg = await bot.db.get_ticket_config(guild.id)
        category = guild.get_channel(cfg.category_id) if cfg.category_id else None
        if category and not isinstance(category, discord.CategoryChannel):
            category = None

        # 3. Secure permission overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True, embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True, manage_messages=True, embed_links=True, attach_files=True
            ),
        }

        if cfg.support_role_id:
            role = guild.get_role(cfg.support_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, attach_files=True, embed_links=True
                )

        prefix_map = {
            "general": "ticket",
            "bug": "bug",
            "security": "sec",
            "appeal": "appeal",
            "staff": "staff-app",
            "partnership": "partner",
            "private": "private",
        }
        prefix = prefix_map.get(category_choice, "ticket")
        clean_user = interaction.user.name[:10].replace(" ", "-")
        ticket_code = f"TIC-{uuid.uuid4().hex[:6].upper()}"
        channel_name = f"{prefix}-{clean_user}-{str(interaction.user.id)[-4:]}"

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"[{ticket_code}] {category_choice.upper()} • Opened by {interaction.user} ({interaction.user.id})",
            )
        except Exception as e:
            await bot.cooldowns.cancel_cooldown(
                CooldownScope.USER_GUILD_CMD, "ticket_create", interaction.user.id, guild.id
            )
            await interaction.response.send_message(
                embed=error_embed("Failed to Create Ticket", f"Missing permissions: {e}"), ephemeral=True
            )
            return

        # 4. Save to Database
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ticket_subject = subject or f"{category_choice.title()} Support Request"
        st_record = SupportTicket(
            ticket_id=ticket_code,
            guild_id=guild.id,
            channel_id=ticket_channel.id,
            creator_id=interaction.user.id,
            ticket_type=category_choice,
            subject=ticket_subject,
            status="open",
            created_at=now_iso,
        )
        await bot.db.create_support_ticket(st_record)
        # Legacy ticket record for backward compatibility
        legacy_id = await bot.db.create_ticket(guild.id, ticket_channel.id, interaction.user.id)

        category_titles = {
            "general": "General Support",
            "bug": "Bug Report",
            "security": "Security Incident",
            "appeal": "Moderation Appeal",
            "staff": "Staff Application",
            "partnership": "Partnership Request",
            "private": "Private Support",
        }
        cat_title = category_titles.get(category_choice, "Support Ticket")

        embed = create_embed(
            title=f"🎫 {cat_title} — #{ticket_code}",
            description=(
                f"Welcome {interaction.user.mention}!\n\n"
                f"• **Ticket ID:** `{ticket_code}`\n"
                f"• **Category:** `{cat_title}`\n"
                f"• **Subject:** {ticket_subject}\n\n"
                "Please describe your inquiry or issue in detail below. Staff will respond shortly.\n"
                "Use the buttons below to manage this ticket."
            ),
            color=Colors.PRIMARY,
        )
        if cfg.support_role_id:
            embed.add_field(name="Assigned Support Role", value=f"<@&{cfg.support_role_id}>", inline=True)

        view = TicketControlView()
        await ticket_channel.send(content=interaction.user.mention, embed=embed, view=view)

        # 5. Dispatch Centralized Audit Log
        log_cfg = await bot.db.get_logging_config(guild.id)
        ticket_log_cid = log_cfg.ticket_logs_channel_id or log_cfg.general_channel_id
        if ticket_log_cid:
            t_channel = guild.get_channel(ticket_log_cid)
            if t_channel and isinstance(t_channel, discord.TextChannel):
                audit_embed = create_embed(
                    title="🎫 Support Ticket Created",
                    description=(
                        f"**ID:** `{ticket_code}`\n"
                        f"**Channel:** {ticket_channel.mention}\n"
                        f"**Opener:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                        f"**Category:** `{cat_title}`\n"
                        f"**Subject:** {ticket_subject}"
                    ),
                    color=Colors.SUCCESS,
                )
                try:
                    await t_channel.send(embed=audit_embed)
                except Exception:
                    pass

        await interaction.response.send_message(
            f"✅ Ticket created: {ticket_channel.mention} (`{ticket_code}`)", ephemeral=True
        )


class TicketControlView(discord.ui.View):
    """Buttons displayed inside ticket channel to claim, transcript, or close it."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.primary,
        emoji="🙋",
        custom_id="sentinel_ticket_claim",
    )
    async def claim_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot: SentinelBot = interaction.client  # type: ignore
        guild = interaction.guild
        channel = interaction.channel

        # Staff validation: admin or manage_messages or support role
        cfg = await bot.db.get_ticket_config(guild.id)
        is_staff = (
            interaction.user.guild_permissions.manage_channels
            or interaction.user.guild_permissions.manage_messages
            or (cfg.support_role_id and any(r.id == cfg.support_role_id for r in getattr(interaction.user, "roles", [])))
            or is_admin_or_owner(interaction.user)
        )
        if not is_staff:
            await interaction.response.send_message(
                embed=error_embed("Staff Only", "Only authorized support staff or moderators can claim tickets."),
                ephemeral=True,
            )
            return

        st = await bot.db.get_support_ticket_by_channel(channel.id)
        if not st:
            await interaction.response.send_message("This channel is not an active support ticket.", ephemeral=True)
            return

        await bot.db.update_support_ticket(st.ticket_id, claimed_by=interaction.user.id, status="claimed")
        try:
            await channel.edit(topic=f"[{st.ticket_id}] Claimed by {interaction.user.display_name}")
        except Exception:
            pass

        claim_embed = success_embed(
            "Ticket Claimed",
            f"{interaction.user.mention} has claimed this ticket and will be assisting you shortly.",
        )
        await interaction.response.send_message(embed=claim_embed)

        # Log to ticket logs
        log_cfg = await bot.db.get_logging_config(guild.id)
        t_cid = log_cfg.ticket_logs_channel_id or log_cfg.general_channel_id
        if t_cid:
            t_ch = guild.get_channel(t_cid)
            if t_ch and isinstance(t_ch, discord.TextChannel):
                t_embed = info_embed(
                    "Ticket Claimed",
                    f"**Ticket:** {channel.mention} (`{st.ticket_id}`)\n**Claimed By:** {interaction.user.mention}",
                )
                try:
                    await t_ch.send(embed=t_embed)
                except Exception:
                    pass

    @discord.ui.button(
        label="Transcript",
        style=discord.ButtonStyle.secondary,
        emoji="📜",
        custom_id="sentinel_ticket_transcript",
    )
    async def transcript_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        html_file, txt_file = await create_transcript_files(channel, interaction.user)
        embed = info_embed(
            "Ticket Transcript Generated",
            f"Here is your official transcript for {channel.mention}."
        )
        await interaction.followup.send(embed=embed, files=[html_file, txt_file], ephemeral=True)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="sentinel_ticket_close",
    )
    async def close_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot: SentinelBot = interaction.client  # type: ignore
        channel = interaction.channel

        await interaction.response.defer()

        # Check DB
        ticket = await bot.db.get_ticket_by_channel(channel.id)
        st = await bot.db.get_support_ticket_by_channel(channel.id)
        if (not ticket or ticket.status != "open") and (not st or st.status not in ["open", "claimed"]):
            await interaction.followup.send("This channel is not an active registered ticket.", ephemeral=True)
            return

        # Process transcript & dispatch
        await process_ticket_closure(bot, channel, interaction.user, interaction.guild)

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


async def create_transcript_files(channel: discord.TextChannel, closer: discord.User | discord.Member):
    """Generates both dark-mode HTML and TXT transcript files for a channel."""
    from utils.transcript_html import generate_html_transcript

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")

    # 1. Plain text
    txt_content = await generate_transcript(channel)
    txt_path = TRANSCRIPTS_DIR / f"transcript-{channel.name}-{now_str}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_content)

    # 2. HTML
    html_content = await generate_html_transcript(channel, closer)
    html_path = TRANSCRIPTS_DIR / f"transcript-{channel.name}-{now_str}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    file_html = discord.File(str(html_path), filename=f"transcript-{channel.name}.html")
    file_txt = discord.File(str(txt_path), filename=f"transcript-{channel.name}.txt")
    return file_html, file_txt


async def process_ticket_closure(
    bot: SentinelBot,
    channel: discord.TextChannel,
    closer: discord.User | discord.Member,
    guild: discord.Guild,
) -> None:
    """Closes ticket in DB, generates HTML + TXT transcripts, logs to staff channel and DMs opener."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    ticket_record = await bot.db.get_ticket_by_channel(channel.id)
    await bot.db.close_ticket(channel.id, closer.id)

    st = await bot.db.get_support_ticket_by_channel(channel.id)
    if st:
        await bot.db.update_support_ticket(st.ticket_id, status="closed", closed_at=now_iso)

    # Generate transcripts
    file_html, file_txt = await create_transcript_files(channel, closer)

    # Staff log channel dispatch
    cfg = await bot.db.get_ticket_config(guild.id)
    log_cfg = await bot.db.get_logging_config(guild.id)
    target_channel_id = cfg.log_channel_id or log_cfg.ticket_logs_channel_id or log_cfg.general_channel_id
    if target_channel_id:
        log_channel = guild.get_channel(target_channel_id)
        if log_channel and isinstance(log_channel, discord.TextChannel):
            embed = info_embed(
                f"Ticket Closed: #{channel.name}",
                f"**Closed By:** {closer.mention}\n**Ticket ID:** `{st.ticket_id if st else 'N/A'}`\nTranscripts attached below.",
            )
            try:
                # Need fresh file objects for multiple sends
                f_html, f_txt = await create_transcript_files(channel, closer)
                await log_channel.send(embed=embed, files=[f_html, f_txt])
            except (discord.Forbidden, discord.HTTPException):
                pass

    # DM ticket opener
    target_user_id = st.creator_id if st else (ticket_record.user_id if ticket_record else None)
    if target_user_id:
        try:
            opener = guild.get_member(target_user_id) or await bot.fetch_user(target_user_id)
            if opener and not getattr(opener, "bot", False):
                dm_embed = discord.Embed(
                    title=f"✦ Support Ticket Closed ╏ #{channel.name} ✦",
                    description=(
                        f"Hello {opener.display_name},\n\n"
                        f"Your support ticket on **{guild.name}** (`{st.ticket_id if st else channel.name}`) has been closed by {closer.mention}.\n\n"
                        "We have attached your official dark-mode HTML transcript below so you can retain an offline record."
                    ),
                    color=0x2ECC71,
                )
                d_html, _ = await create_transcript_files(channel, closer)
                await opener.send(embed=dm_embed, file=d_html)
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
                "• Choose from General, Bug Reports, Security, or Appeals.\n"
                "• All transcripts are securely archived."
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

    @ticket_group.command(name="create", description="Create a new private support ticket directly")
    @app_commands.describe(
        category="Support category",
        subject="Brief summary of your inquiry or issue",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="General Support", value="general"),
            app_commands.Choice(name="Bug Report", value="bug"),
            app_commands.Choice(name="Security Incident", value="security"),
            app_commands.Choice(name="Moderation Appeal", value="appeal"),
            app_commands.Choice(name="Private / Confidential", value="private"),
        ]
    )
    async def ticket_create_cmd(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        subject: Optional[str] = None,
    ):
        await TicketPanelView.create_ticket_for_user(
            interaction=interaction,
            category_choice=category.value,
            subject=subject or f"{category.name} from {interaction.user.name}",
        )

    @ticket_group.command(name="claim", description="Assign yourself to handle the current support ticket")
    async def ticket_claim(self, interaction: discord.Interaction):
        st = await self.bot.db.get_support_ticket_by_channel(interaction.channel.id)
        if not st:
            await interaction.response.send_message(
                embed=error_embed("Not a Ticket", "This channel is not an active support ticket."),
                ephemeral=True,
            )
            return

        cfg = await self.bot.db.get_ticket_config(interaction.guild.id)
        is_staff = (
            interaction.user.guild_permissions.manage_channels
            or interaction.user.guild_permissions.manage_messages
            or (cfg.support_role_id and any(r.id == cfg.support_role_id for r in getattr(interaction.user, "roles", [])))
            or is_admin_or_owner(interaction.user)
        )
        if not is_staff:
            await interaction.response.send_message(
                embed=error_embed("Access Denied", "Only staff members can claim support tickets."),
                ephemeral=True,
            )
            return

        await self.bot.db.update_support_ticket(st.ticket_id, claimed_by=interaction.user.id, status="claimed")
        try:
            await interaction.channel.edit(topic=f"[{st.ticket_id}] Claimed by {interaction.user.display_name}")
        except Exception:
            pass

        embed = success_embed(
            "Ticket Claimed",
            f"{interaction.user.mention} has claimed ticket `{st.ticket_id}` and is handling your request.",
        )
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="close", description="Close the current ticket channel and generate a transcript")
    @app_commands.describe(reason="Optional reason for closing this ticket")
    async def ticket_close(self, interaction: discord.Interaction, reason: Optional[str] = "Resolved"):
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        st = await self.bot.db.get_support_ticket_by_channel(interaction.channel.id)
        if (not ticket or ticket.status != "open") and (not st or st.status not in ["open", "claimed"]):
            await interaction.response.send_message(
                embed=error_embed("Not a Ticket", "This channel is not an active registered support ticket."),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        await process_ticket_closure(self.bot, interaction.channel, interaction.user, interaction.guild)

        await interaction.followup.send(
            embed=warning_embed("Ticket Closed", f"Closed by {interaction.user.mention} ({reason}). Deleting channel in 5s...")
        )
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Closed by {interaction.user}: {reason}")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @ticket_group.command(name="reopen", description="Reopen an archived or closed ticket channel")
    async def ticket_reopen(self, interaction: discord.Interaction):
        st = await self.bot.db.get_support_ticket_by_channel(interaction.channel.id)
        if not st:
            await interaction.response.send_message(
                embed=error_embed("Not a Ticket", "This channel is not a recognized support ticket."),
                ephemeral=True,
            )
            return

        opener = interaction.guild.get_member(st.creator_id)
        channel: discord.TextChannel = interaction.channel  # type: ignore

        if opener:
            await channel.set_permissions(opener, read_messages=True, send_messages=True, attach_files=True)

        await self.bot.db.update_support_ticket(st.ticket_id, status="open", closed_at=None)
        embed = success_embed("Ticket Reopened", f"Ticket `{st.ticket_id}` has been reopened by {interaction.user.mention}.")
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="transcript", description="Export a complete HTML and text transcript of this ticket")
    async def ticket_transcript(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel: discord.TextChannel = interaction.channel  # type: ignore
        html_file, txt_file = await create_transcript_files(channel, interaction.user)
        embed = info_embed(
            "Ticket Transcript Exported",
            f"Here is the complete transcript for #{channel.name}."
        )
        await interaction.followup.send(embed=embed, files=[html_file, txt_file], ephemeral=True)

    @ticket_group.command(name="archive", description="Lock and archive this ticket channel")
    @is_admin_or_owner()
    async def ticket_archive(self, interaction: discord.Interaction):
        st = await self.bot.db.get_support_ticket_by_channel(interaction.channel.id)
        if not st:
            await interaction.response.send_message(
                embed=error_embed("Not a Ticket", "This channel is not an active support ticket."),
                ephemeral=True,
            )
            return

        channel: discord.TextChannel = interaction.channel  # type: ignore
        opener = interaction.guild.get_member(st.creator_id)
        if opener:
            # Revoke send permissions but keep read
            await channel.set_permissions(opener, read_messages=True, send_messages=False)

        await self.bot.db.update_support_ticket(st.ticket_id, status="archived")
        embed = warning_embed("Ticket Archived", f"Ticket `{st.ticket_id}` has been archived and locked by {interaction.user.mention}.")
        await interaction.response.send_message(embed=embed)

    @ticket_group.command(name="add", description="Add another member to this ticket channel")
    @app_commands.describe(user="The user to add to the ticket")
    async def ticket_add(self, interaction: discord.Interaction, user: discord.Member):
        st = await self.bot.db.get_support_ticket_by_channel(interaction.channel.id)
        if not st:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This channel is not an active support ticket."), ephemeral=True)
            return

        channel: discord.TextChannel = interaction.channel  # type: ignore
        await channel.set_permissions(user, read_messages=True, send_messages=True, attach_files=True)
        await interaction.response.send_message(embed=success_embed("User Added", f"Added {user.mention} to this ticket."))

    @ticket_group.command(name="remove", description="Remove a member from this ticket channel")
    @app_commands.describe(user="The user to remove from the ticket")
    async def ticket_remove(self, interaction: discord.Interaction, user: discord.Member):
        st = await self.bot.db.get_support_ticket_by_channel(interaction.channel.id)
        if not st:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", "This channel is not an active support ticket."), ephemeral=True)
            return

        channel: discord.TextChannel = interaction.channel  # type: ignore
        await channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(embed=success_embed("User Removed", f"Removed {user.mention} from this ticket."))

    @ticket_group.command(name="list", description="List all active support tickets in this server")
    @is_admin_or_owner()
    async def ticket_list(self, interaction: discord.Interaction):
        tickets = await self.bot.db.list_support_tickets(interaction.guild.id, limit=20)
        if not tickets:
            await interaction.response.send_message(embed=info_embed("Support Tickets", "No support tickets recorded in this server."), ephemeral=True)
            return

        lines = []
        for t in tickets:
            ch = interaction.guild.get_channel(t.channel_id)
            ch_str = ch.mention if ch else f"ID: `{t.channel_id}`"
            status_icon = "🟢" if t.status == "open" else ("🟡" if t.status == "claimed" else "🔒")
            lines.append(f"{status_icon} **`{t.ticket_id}`** • {ch_str} • <@{t.creator_id}> • `{t.status.upper()}`")

        embed = create_embed(
            title=f"📋 Active Support Tickets ({len(tickets)})",
            description="\n".join(lines[:15]),
            color=Colors.INFO,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # TOP-LEVEL /REPORT COMMAND
    # ==========================================

    @app_commands.command(name="report", description="Submit a confidential report (Member, Bug, Security, Appeal, or Technical)")
    @app_commands.describe(
        report_type="Type of report you are submitting",
        subject="Brief summary / title of the report",
        details="Detailed description of the issue or incident",
        target_user="User being reported (if submitting a member report)",
        evidence="Links to evidence, messages, or screenshots",
        open_private_ticket="Whether to open a private support ticket for staff investigation",
    )
    @app_commands.choices(
        report_type=[
            app_commands.Choice(name="Member Report", value="member"),
            app_commands.Choice(name="Bug Report", value="bug"),
            app_commands.Choice(name="Security Incident", value="security"),
            app_commands.Choice(name="Moderation Appeal", value="appeal"),
            app_commands.Choice(name="Technical Support", value="technical"),
        ]
    )
    async def report_command(
        self,
        interaction: discord.Interaction,
        report_type: app_commands.Choice[str],
        subject: str,
        details: str,
        target_user: Optional[discord.Member] = None,
        evidence: Optional[str] = None,
        open_private_ticket: bool = False,
    ):
        guild = interaction.guild
        rep_id = f"REP-{uuid.uuid4().hex[:6].upper()}"

        # 1. Dispatch to Centralized Logging
        log_cfg = await self.bot.db.get_logging_config(guild.id)

        # Route to appropriate channel: security-logs, moderation-logs, or report-logs
        if report_type.value == "security":
            log_cid = log_cfg.security_channel_id or log_cfg.report_logs_channel_id or log_cfg.general_channel_id
        elif report_type.value in ["member", "appeal"]:
            log_cid = log_cfg.moderation_channel_id or log_cfg.report_logs_channel_id or log_cfg.general_channel_id
        else:
            log_cid = log_cfg.report_logs_channel_id or log_cfg.staff_logs_channel_id or log_cfg.general_channel_id

        report_embed = create_embed(
            title=f"📢 New Report Submitted — #{rep_id}",
            description=(
                f"**Report Type:** `{report_type.name}`\n"
                f"**Reporter:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"**Subject:** {subject}\n\n"
                f"**Description:**\n```{details[:1000]}```"
            ),
            color=Colors.WARNING if report_type.value == "security" else Colors.PRIMARY,
        )
        if target_user:
            report_embed.add_field(name="Target User", value=f"{target_user.mention} (`{target_user.id}`)", inline=True)
        if evidence:
            report_embed.add_field(name="Evidence", value=evidence[:500], inline=False)
        report_embed.set_footer(text=f"Rai Incident & Report Dispatch • ID: {rep_id}")

        if log_cid:
            dest_ch = guild.get_channel(log_cid)
            if dest_ch and isinstance(dest_ch, discord.TextChannel):
                try:
                    await dest_ch.send(embed=report_embed)
                except Exception as e:
                    logger.warning(f"Failed to post report to {log_cid}: {e}")

        # 2. Also forward to report-logs if different
        if log_cfg.report_logs_channel_id and log_cfg.report_logs_channel_id != log_cid:
            rep_dest = guild.get_channel(log_cfg.report_logs_channel_id)
            if rep_dest and isinstance(rep_dest, discord.TextChannel):
                try:
                    await rep_dest.send(embed=report_embed)
                except Exception:
                    pass

        # 3. Optionally spin up a private ticket for follow-up
        ticket_msg = ""
        if open_private_ticket:
            try:
                await TicketPanelView.create_ticket_for_user(
                    interaction=interaction,
                    category_choice=report_type.value,
                    subject=f"Report #{rep_id}: {subject}",
                )
                ticket_msg = "\n\n🎫 A private support channel has also been created for follow-up."
                return  # interaction response already handled inside create_ticket_for_user
            except Exception as te:
                ticket_msg = f"\n\n⚠️ Could not automatically create private channel: {te}"

        ack_embed = success_embed(
            "Report Submitted Successfully",
            (
                f"Thank you {interaction.user.mention}. Your report has been securely transmitted to the server staff team.\n\n"
                f"• **Tracking ID:** `{rep_id}`\n"
                f"• **Category:** `{report_type.name}`\n"
                f"• **Status:** `PENDING STAFF REVIEW`\n\n"
                "Staff members have been alerted and will investigate promptly."
                + ticket_msg
            ),
        )
        await interaction.response.send_message(embed=ack_embed, ephemeral=True)

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
    bot.add_view(TicketControlView())
    await bot.add_cog(TicketsCog(bot))
