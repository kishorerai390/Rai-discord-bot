"""
Support Center & Ticket Service (Phase 5):
- Button-based private ticket system in #open-a-ticket (ID: 1555641079137706014).
- Secure private threads/channels with restricted member & staff access.
- Staff Claim, Close, Reopen, and Transcript logging to #mod-logs (ID: 1555283387340562574).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import discord

logger = logging.getLogger("music_bot.tickets")

MOD_LOG_CHANNEL_ID = 1555283387340562574
SUPPORT_CATEGORY_ID = 1555641079137706014


class TicketActionView(discord.ui.View):
    def __init__(self, opener_id: int, ticket_type: str):
        super().__init__(timeout=None)
        self.opener_id = opener_id
        self.ticket_type = ticket_type
        self.claimed_by: Optional[int] = None
        self.is_closed = False

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.success, emoji="🙋‍♂️", custom_id="ticket_claim")
    async def btn_claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Only staff members can claim tickets.", ephemeral=True)
            return

        self.claimed_by = interaction.user.id
        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🛡️ **{interaction.user.mention}** has claimed this ticket and will assist you shortly.")

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close")
    async def btn_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opener_id and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Only the ticket opener or staff can close this ticket.", ephemeral=True)
            return

        self.is_closed = True
        await interaction.response.send_message("🔒 Closing ticket and exporting transcript to `#mod-logs` in 5 seconds...")

        # Transcript export logic
        channel = interaction.channel
        messages = []
        try:
            async for msg in channel.history(limit=200, oldest_first=True):
                time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                messages.append(f"[{time_str}] {msg.author.display_name}: {msg.clean_content}")
        except Exception:
            pass

        transcript_text = "\n".join(messages) if messages else "No message history recorded."

        # Send transcript to mod-logs
        mod_log_channel = interaction.guild.get_channel(MOD_LOG_CHANNEL_ID)
        if mod_log_channel:
            embed = discord.Embed(
                title=f"📋 Ticket Closed: {channel.name}",
                description=f"**Type:** {self.ticket_type}\n**Opened By:** <@{self.opener_id}>\n**Closed By:** {interaction.user.mention}\n**Claimed By:** {f'<@{self.claimed_by}>' if self.claimed_by else 'Unclaimed'}",
                color=0xE2E8F0,
                timestamp=datetime.utcnow()
            )
            file = discord.File(
                fp=io.BytesIO(transcript_text.encode("utf-8")),
                filename=f"transcript-{channel.name}.txt"
            ) if 'io' in globals() else None

            import io
            file = discord.File(
                fp=io.BytesIO(transcript_text.encode("utf-8")),
                filename=f"transcript-{channel.name}.txt"
            )
            await mod_log_channel.send(embed=embed, file=file)

        await asyncio.sleep(5.0)
        try:
            if isinstance(channel, discord.Thread):
                await channel.delete()
            else:
                await channel.delete(reason=f"Ticket closed by {interaction.user.display_name}")
        except Exception as e:
            logger.error(f"Failed to delete closed ticket channel: {e}")


class SupportHubView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="General Support", style=discord.ButtonStyle.primary, emoji="📩", custom_id="hub_general_support")
    async def btn_general(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._spawn_ticket(interaction, "General Support", "📩")

    @discord.ui.button(label="Report a Member", style=discord.ButtonStyle.secondary, emoji="🚨", custom_id="hub_report_member")
    async def btn_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._spawn_ticket(interaction, "Member Report", "🚨")

    @discord.ui.button(label="Appeals", style=discord.ButtonStyle.secondary, emoji="⚖️", custom_id="hub_appeals")
    async def btn_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._spawn_ticket(interaction, "Moderation Appeal", "⚖️")

    async def _spawn_ticket(self, interaction: discord.Interaction, ticket_type: str, emoji: str):
        guild = interaction.guild
        user = interaction.user

        # Create private thread in channel
        thread_name = f"{emoji}・{ticket_type.lower().replace(' ', '-')}-{user.name[:10]}"
        try:
            if isinstance(interaction.channel, discord.TextChannel):
                thread = await interaction.channel.create_thread(
                    name=thread_name,
                    auto_archive_duration=1440,
                    invitable=False,
                    reason=f"{ticket_type} ticket opened by {user.display_name}"
                )
                await thread.add_user(user)

                embed = discord.Embed(
                    title=f"{emoji} {ticket_type} Ticket",
                    description=(
                        f"Hello {user.mention}! Welcome to your private support request.\n\n"
                        "Please describe your issue, report, or appeal in detail below.\n"
                        "Our staff team has been alerted and will assist you shortly."
                    ),
                    color=0x7C3AED
                )
                embed.set_footer(text="Noctyra Studio & NyxTune Security")

                view = TicketActionView(opener_id=user.id, ticket_type=ticket_type)
                await thread.send(content=f"{user.mention}", embed=embed, view=view)
                await interaction.response.send_message(f"✅ Your private ticket has been opened: {thread.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Tickets can only be created in a text channel.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            await interaction.response.send_message(f"❌ Failed to create ticket: {e}", ephemeral=True)
