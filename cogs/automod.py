"""
Automated Moderation (AutoMod) Cog.
Detects:
- Spam and message flooding
- Excessive mentions
- Repeated messages
- Custom banned words and regex filters
- Discord invite links
- Suspicious and phishing links
- Excessive emojis and uppercase characters
Applies configurable actions: delete message, warn, or timeout, and logs violations.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

# Invite link regex
INVITE_REGEX = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[a-zA-Z0-9]+", re.IGNORECASE)
# Suspicious links regex (free nitro, steam scams, etc.)
SUSPICIOUS_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:steamcomm[a-z0-9-]*\.com|discorcd[a-z0-9-]*\.com|dlscord[a-z0-9-]*\.com|discord-nitro[a-z0-9-]*\.[a-z]+|gift-nitro[a-z0-9-]*\.[a-z]+|free-nitro[a-z0-9-]*\.[a-z]+)",
    re.IGNORECASE
)
# Custom emoji regex (<:name:id> or <a:name:id>)
EMOJI_REGEX = re.compile(r"<a?:[a-zA-Z0-9_]+:[0-9]+>")
# Unicode emoji regex
UNICODE_EMOJI_REGEX = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50\u2b55]"
)


class AutoModCog(commands.Cog, name="AutoMod"):
    """Automated Moderation and Content Filtering."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # In-memory spam tracking: (guild_id, user_id) -> list of monotonic timestamps
        self._spam_tracker: Dict[tuple[int, int], List[float]] = defaultdict(list)
        # Duplicate message tracking: (guild_id, user_id) -> (last_msg_content, timestamp)
        self._last_message: Dict[tuple[int, int], tuple[str, float]] = {}

    automod_group = app_commands.Group(
        name="automod",
        description="Automated moderation rules and filters",
        default_permissions=discord.Permissions(administrator=True),
    )

    # ==========================================
    # MESSAGE LISTENER
    # ==========================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore webhooks, bots, DMs
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return

        guild = message.guild
        member = message.author

        # Exemption checks: Owner, Administrator, Bot, or Whitelisted
        if member.id == guild.owner_id or member.id == self.bot.user.id or member.guild_permissions.administrator:
            return

        role_ids = [r.id for r in member.roles]
        if await self.bot.db.is_whitelisted(guild.id, member.id, role_ids):
            return

        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        if not guild_cfg.automod_enabled:
            return

        auto_cfg = await self.bot.db.get_automod_config(guild.id)

        # 1. Spam / Flood Detection
        if auto_cfg.spam_detection:
            now = time.monotonic()
            key = (guild.id, member.id)
            timestamps = self._spam_tracker[key]
            # prune older than window
            cutoff = now - auto_cfg.spam_window
            self._spam_tracker[key] = [t for t in timestamps if t > cutoff]
            self._spam_tracker[key].append(now)

            if len(self._spam_tracker[key]) > auto_cfg.spam_limit:
                await self._enforce_automod(message, "Message Flooding / Spam", auto_cfg.action)
                self._spam_tracker[key].clear()
                return

        # 2. Repeated Messages
        key = (guild.id, member.id)
        now = time.monotonic()
        last_content, last_time = self._last_message.get(key, ("", 0.0))
        if message.content and message.content == last_content and (now - last_time) < 10.0:
            await self._enforce_automod(message, "Repeated Message Spam", auto_cfg.action)
            self._last_message[key] = ("", 0.0)
            return
        if message.content:
            self._last_message[key] = (message.content, now)

        # 3. Excessive Mentions
        if len(message.mentions) > auto_cfg.mention_limit:
            await self._enforce_automod(message, f"Excessive Mentions ({len(message.mentions)}/{auto_cfg.mention_limit})", auto_cfg.action)
            return

        # 4. Invite Links
        if auto_cfg.invite_links_block and INVITE_REGEX.search(message.content):
            await self._enforce_automod(message, "Discord Invite Link", auto_cfg.action)
            return

        # 5. Suspicious / Phishing Links
        if auto_cfg.suspicious_links_block and SUSPICIOUS_REGEX.search(message.content):
            await self._enforce_automod(message, "Suspicious / Phishing Link", "timeout")
            return

        # 6. Banned Words
        if auto_cfg.banned_words_enabled and auto_cfg.banned_words:
            banned_list = [w.strip().lower() for w in auto_cfg.banned_words.split(",") if w.strip()]
            lower_content = message.content.lower()
            for word in banned_list:
                if re.search(rf"\b{re.escape(word)}\b", lower_content):
                    await self._enforce_automod(message, "Word Filter Violation", auto_cfg.action)
                    return

        # 7. Excessive Emojis
        if auto_cfg.excessive_emojis_block:
            custom_emojis = len(EMOJI_REGEX.findall(message.content))
            unicode_emojis = len(UNICODE_EMOJI_REGEX.findall(message.content))
            total_emojis = custom_emojis + unicode_emojis
            if total_emojis > auto_cfg.emoji_limit:
                await self._enforce_automod(message, f"Emoji Spam ({total_emojis} emojis)", auto_cfg.action)
                return

        # 8. Excessive Caps
        if auto_cfg.excessive_caps_block and len(message.content) > 15:
            letters = [c for c in message.content if c.isalpha()]
            if letters:
                caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
                if (caps_ratio * 100) >= auto_cfg.caps_percentage:
                    await self._enforce_automod(message, f"Excessive Caps ({int(caps_ratio * 100)}%)", auto_cfg.action)
                    return

    async def _enforce_automod(self, message: discord.Message, reason: str, action: str) -> None:
        """Applies configured enforcement action and sends notification."""
        guild = message.guild
        member = message.author

        # 1. Delete message
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

        # 2. Punish member if configured
        punishment_str = "Deleted Message"
        action_word = None
        if action == "kick":
            try:
                await member.kick(reason=f"AutoMod ({reason})")
                action_word = "KICKED"
                punishment_str = "Kicked from Server"
            except (discord.Forbidden, discord.HTTPException):
                action_word = "FLAGGED"
        elif action == "timeout":
            try:
                until = discord.utils.utcnow() + datetime.timedelta(minutes=10)
                await member.timeout(until, reason=f"AutoMod ({reason})")
                action_word = "MUTED"
                punishment_str = "Deleted Message + 10m Timeout"
            except (discord.Forbidden, discord.HTTPException):
                action_word = "FLAGGED"
        elif action == "warn":
            await self.bot.db.add_warning(guild.id, member.id, self.bot.user.id, f"AutoMod: {reason}")
            action_word = "WARNED"
            punishment_str = "Deleted Message + Logged Warning"

        # 3. Public Channel Notice (Matches exact AutoMod format from screenshots)
        if action_word:
            try:
                await message.channel.send(
                    f"🚫 **{member.name}** was **{action_word}** by AutoMod ({reason})."
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

        # 4. Log to AutoMod channel
        log_cfg = await self.bot.db.get_logging_config(guild.id)
        channel_id = log_cfg.automod_channel_id or log_cfg.moderation_channel_id or log_cfg.general_channel_id
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                embed = warning_embed("AutoMod Violation", f"**User:** {member.mention} (`{member.id}`)\n**Channel:** {message.channel.mention}")
                embed.add_field(name="Reason", value=reason, inline=True)
                embed.add_field(name="Action Taken", value=punishment_str, inline=True)
                if message.content:
                    content_preview = message.content[:500] + ("..." if len(message.content) > 500 else "")
                    embed.add_field(name="Original Content", value=f"```{content_preview}```", inline=False)
                try:
                    await channel.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

        # 5. Dispatch confidential report to owner mod-report channel
        try:
            from utils.owner_reporter import OwnerReporter
            OwnerReporter.send_mod_report(
                self.bot,
                guild.id,
                event="AutoMod Sanction",
                user=member,
                reason=reason,
                action_taken=punishment_str,
                severity="HIGH" if action == "kick" else "MEDIUM",
                details={"Channel": message.channel.mention, "Content": message.content[:200] if message.content else "N/A"},
            )
        except Exception:
            pass

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @automod_group.command(name="enable", description="Enable the AutoMod system")
    @is_admin_or_owner()
    async def automod_enable(self, interaction: discord.Interaction):
        await self.bot.db.update_guild_config(interaction.guild.id, automod_enabled=True)
        await interaction.response.send_message(embed=success_embed("AutoMod Enabled", "Automated moderation filters are now active."), ephemeral=True)

    @automod_group.command(name="disable", description="Disable the AutoMod system")
    @is_admin_or_owner()
    async def automod_disable(self, interaction: discord.Interaction):
        await self.bot.db.update_guild_config(interaction.guild.id, automod_enabled=False)
        await interaction.response.send_message(embed=info_embed("AutoMod Disabled", "Automated moderation filters are now paused."), ephemeral=True)

    @automod_group.command(name="setup", description="Quick setup for AutoMod features and actions")
    @is_admin_or_owner()
    @app_commands.describe(
        action="Action to take when a rule is triggered",
        block_invites="Block Discord invite links",
        block_suspicious_links="Block phishing and scam links",
        block_caps="Block excessive uppercase messages",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Delete Only", value="delete"),
            app_commands.Choice(name="Delete & Warn", value="warn"),
            app_commands.Choice(name="Delete & Timeout (10m)", value="timeout"),
            app_commands.Choice(name="Delete & Kick from Server", value="kick"),
        ]
    )
    async def automod_setup(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        block_invites: Optional[bool] = None,
        block_suspicious_links: Optional[bool] = None,
        block_caps: Optional[bool] = None,
    ):
        updates = {"action": action.value}
        if block_invites is not None:
            updates["invite_links_block"] = int(block_invites)
        if block_suspicious_links is not None:
            updates["suspicious_links_block"] = int(block_suspicious_links)
        if block_caps is not None:
            updates["excessive_caps_block"] = int(block_caps)

        await self.bot.db.update_automod_config(interaction.guild.id, **updates)
        await self.bot.db.update_guild_config(interaction.guild.id, automod_enabled=True)

        embed = success_embed(
            "AutoMod Configuration Updated",
            f"**Action:** {action.name}\n"
            f"**Block Invites:** {'Yes' if updates.get('invite_links_block', True) else 'No'}\n"
            f"**Block Suspicious Links:** {'Yes' if updates.get('suspicious_links_block', True) else 'No'}\n"
            f"**Block Caps:** {'Yes' if updates.get('excessive_caps_block', True) else 'No'}"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @automod_group.command(name="words", description="Manage banned words list")
    @is_admin_or_owner()
    @app_commands.describe(
        action="Add, remove, or view banned words",
        words="Comma-separated list of words (e.g. word1, word2)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Add Words", value="add"),
            app_commands.Choice(name="Remove Words", value="remove"),
            app_commands.Choice(name="List Words", value="list"),
            app_commands.Choice(name="Clear All", value="clear"),
        ]
    )
    async def automod_words(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        words: Optional[str] = None,
    ):
        cfg = await self.bot.db.get_automod_config(interaction.guild.id)
        existing = [w.strip().lower() for w in cfg.banned_words.split(",") if w.strip()]

        if action.value == "list":
            if not existing:
                await interaction.response.send_message(embed=info_embed("Banned Words", "No banned words currently configured."), ephemeral=True)
                return
            formatted = ", ".join(f"`{w}`" for w in existing)
            await interaction.response.send_message(embed=info_embed(f"Banned Words ({len(existing)})", formatted), ephemeral=True)
            return

        if action.value == "clear":
            await self.bot.db.update_automod_config(interaction.guild.id, banned_words="")
            await interaction.response.send_message(embed=success_embed("Banned Words Cleared", "All banned words have been removed."), ephemeral=True)
            return

        if not words:
            await interaction.response.send_message(embed=error_embed("Missing Words", "Please provide comma-separated words."), ephemeral=True)
            return

        input_words = [w.strip().lower() for w in words.split(",") if w.strip()]

        if action.value == "add":
            combined = set(existing).union(input_words)
            new_str = ",".join(combined)
            await self.bot.db.update_automod_config(interaction.guild.id, banned_words=new_str)
            await interaction.response.send_message(embed=success_embed("Words Added", f"Added {len(input_words)} word(s) to the filter."), ephemeral=True)
        elif action.value == "remove":
            remaining = [w for w in existing if w not in input_words]
            new_str = ",".join(remaining)
            await self.bot.db.update_automod_config(interaction.guild.id, banned_words=new_str)
            await interaction.response.send_message(embed=success_embed("Words Removed", f"Removed {len(input_words)} word(s) from the filter."), ephemeral=True)

    @automod_group.command(name="status", description="Display full AutoMod status and active rules")
    @is_admin_or_owner()
    async def automod_status(self, interaction: discord.Interaction):
        guild_cfg = await self.bot.db.get_or_create_guild_config(interaction.guild.id)
        auto_cfg = await self.bot.db.get_automod_config(interaction.guild.id)

        embed = create_embed(
            title=f"🤖 AutoMod Status — {interaction.guild.name}",
            color=Colors.SUCCESS if guild_cfg.automod_enabled else Colors.DARK,
        )
        embed.add_field(name="Module Enabled", value="🟢 Yes" if guild_cfg.automod_enabled else "🔴 No", inline=True)
        embed.add_field(name="Punishment Action", value=auto_cfg.action.capitalize(), inline=True)
        embed.add_field(name="Spam Limit", value=f"{auto_cfg.spam_limit} msgs / {auto_cfg.spam_window}s", inline=True)
        embed.add_field(name="Mention Limit", value=f"Max {auto_cfg.mention_limit} mentions", inline=True)
        embed.add_field(name="Invite Links Filter", value="Active" if auto_cfg.invite_links_block else "Off", inline=True)
        embed.add_field(name="Suspicious Links Filter", value="Active" if auto_cfg.suspicious_links_block else "Off", inline=True)
        embed.add_field(name="Caps Filter", value=f"{auto_cfg.caps_percentage}%" if auto_cfg.excessive_caps_block else "Off", inline=True)
        embed.add_field(name="Emoji Filter", value=f"Max {auto_cfg.emoji_limit}" if auto_cfg.excessive_emojis_block else "Off", inline=True)

        banned_count = len([w for w in auto_cfg.banned_words.split(",") if w.strip()])
        embed.add_field(name="Banned Words Count", value=str(banned_count), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(AutoModCog(bot))
