"""
Mention Notifications Cog.
DMs members when they are tagged/mentioned in a server channel, including:
- Sender name & mention
- Server & channel details
- Quoted message preview
- Direct Jump-to-Message link button
- Anti-spam cooldowns and user opt-in/opt-out preferences.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Dict, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, success_embed, info_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

# Blue accent matching Discord blurple / notification embed
NOTIFICATION_COLOR = 0x5865F2
COOLDOWN_SECONDS = 5.0


class MentionJumpView(discord.ui.View):
    """View with a direct link button jumping to the tagged message."""

    def __init__(self, jump_url: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Click Here to View Message",
                url=jump_url,
                style=discord.ButtonStyle.link,
                emoji="🔗",
            )
        )


class MentionNotificationsCog(commands.Cog, name="MentionNotifications"):
    """Sends clean DM notifications when users are tagged in the server."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # Map: recipient_id -> last_notification_timestamp
        self._user_cooldowns: Dict[int, float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Listens for mentions and sends formatted DM notifications."""
        # Ignore bot messages, DMs, and messages without mentions
        if not message.guild or message.author.bot or not message.mentions:
            return

        # Check guild-level setting
        try:
            guild_enabled = await self.bot.db.get_guild_mention_notification(message.guild.id)
        except Exception:
            guild_enabled = True

        if not guild_enabled:
            return

        now = time.time()
        channel = message.channel

        # Format channel path (e.g. "CATEGORY > #channel-name")
        category = getattr(channel, "category", None)
        if category:
            icon = "🔊" if isinstance(channel, discord.VoiceChannel) else "💬"
            channel_str = f"{category.name} > {icon} #{getattr(channel, 'name', 'general')}"
        else:
            channel_str = f"#{getattr(channel, 'name', 'general')}"

        # Format quoted message content
        raw_content = message.content.strip() if message.content else ""
        if not raw_content:
            if message.attachments:
                raw_content = "[Attachment / Media]"
            elif message.embeds:
                raw_content = "[Rich Embed]"
            elif message.stickers:
                raw_content = "[Sticker]"
            else:
                raw_content = "[Message Content]"

        # Truncate if exceptionally long
        if len(raw_content) > 500:
            raw_content = raw_content[:497] + "..."

        quoted_lines = "\n".join(f"> {line}" for line in raw_content.splitlines()) if raw_content else "> [No text]"

        # Process each mentioned user
        for recipient in message.mentions:
            # Skip bots and self-mentions
            if recipient.bot or recipient.id == message.author.id:
                continue

            # Anti-spam cooldown per recipient (5s window)
            last_sent = self._user_cooldowns.get(recipient.id, 0.0)
            if now - last_sent < COOLDOWN_SECONDS:
                continue

            # Check recipient preference
            try:
                user_enabled = await self.bot.db.get_user_mention_notification(recipient.id)
            except Exception:
                user_enabled = True

            if not user_enabled:
                continue

            # Build notification embed
            embed = discord.Embed(
                title=f"🔔 You were tagged in {message.guild.name}!",
                color=NOTIFICATION_COLOR,
                timestamp=message.created_at,
            )
            embed.description = (
                f"**Sender:** {message.author.name} ( {message.author.mention} )\n"
                f"**Server:** {message.guild.name}\n"
                f"**Channel:** {channel_str}\n\n"
                f"**Message Content:**\n"
                f"{quoted_lines}\n\n"
                f"**Jump to Message**\n"
                f"[Click Here to View Message]({message.jump_url})"
            )
            embed.set_footer(
                text=f"{message.guild.name} • Tag Notification | Use /mentiondm to toggle",
                icon_url=message.guild.icon.url if message.guild.icon else None,
            )

            view = MentionJumpView(message.jump_url)

            try:
                await recipient.send(embed=embed, view=view)
                self._user_cooldowns[recipient.id] = now
            except (discord.Forbidden, discord.HTTPException):
                # User has DMs closed or blocked the bot; safely ignore
                pass

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    mention_group = app_commands.Group(
        name="mentiondm",
        description="Configure mention DM notifications when tagged in chat",
    )

    @mention_group.command(name="toggle", description="Enable or disable mention DMs when you are tagged")
    async def mentiondm_toggle(self, interaction: discord.Interaction):
        """Toggle personal mention DM notifications."""
        current = await self.bot.db.get_user_mention_notification(interaction.user.id)
        new_state = not current
        await self.bot.db.set_user_mention_notification(interaction.user.id, new_state)

        state_text = "**enabled** (you will receive DMs when tagged)" if new_state else "**disabled** (no DMs when tagged)"
        await interaction.response.send_message(
            embed=success_embed(
                "Mention DM Notifications Updated",
                f"Mention notifications have been {state_text}.",
            ),
            ephemeral=True,
        )

    @mention_group.command(name="status", description="Check your current mention DM notification setting")
    async def mentiondm_status(self, interaction: discord.Interaction):
        """Check status of mention notifications."""
        user_state = await self.bot.db.get_user_mention_notification(interaction.user.id)
        guild_state = True
        if interaction.guild:
            guild_state = await self.bot.db.get_guild_mention_notification(interaction.guild.id)

        user_str = "🟢 Enabled" if user_state else "🔴 Disabled"
        guild_str = "🟢 Enabled" if guild_state else "🔴 Disabled"

        embed = create_embed(
            title="🔔 Mention DM Notifications Status",
            color=NOTIFICATION_COLOR,
        )
        embed.add_field(name="Your Preference", value=user_str, inline=True)
        if interaction.guild:
            embed.add_field(name="Server Setting", value=guild_str, inline=True)
        embed.set_footer(text="Use /mentiondm toggle to switch your personal setting.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @mention_group.command(name="server_toggle", description="Enable or disable mention DMs server-wide (Admin only)")
    @is_admin_or_owner()
    async def mentiondm_server_toggle(self, interaction: discord.Interaction):
        """Toggle mention DMs for the entire server."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        current = await self.bot.db.get_guild_mention_notification(interaction.guild.id)
        new_state = not current
        await self.bot.db.set_guild_mention_notification(interaction.guild.id, new_state)

        state_text = "**enabled**" if new_state else "**disabled**"
        await interaction.response.send_message(
            embed=success_embed(
                "Server Mention Notifications Updated",
                f"Mention notifications have been {state_text} server-wide.",
            ),
            ephemeral=True,
        )


async def setup(bot: SentinelBot):
    await bot.add_cog(MentionNotificationsCog(bot))
