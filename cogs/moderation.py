"""
Comprehensive Server Moderation Cog.
Features:
- Ban, Unban, Kick, Timeout, Untimeout
- Warning system with persistent SQLite storage
- Channel Clear / Purge
- Channel Slowmode, Lock, and Unlock
- Full role hierarchy and permission validation
- Interactive confirmation dialogs for destructive actions
- Logging to configured moderation log channels
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.helpers import ConfirmView, PaginationView, parse_duration
from utils.permissions import can_moderate, is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class ModerationCog(commands.Cog, name="Moderation"):
    """Moderation tools for server staff."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    async def _log_mod_action(
        self,
        guild: discord.Guild,
        action: str,
        target: discord.User | discord.Member,
        moderator: discord.Member,
        reason: str,
        extra: Optional[str] = None,
    ) -> None:
        log_cfg = await self.bot.db.get_logging_config(guild.id)
        channel_id = log_cfg.moderation_channel_id or log_cfg.general_channel_id
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        embed = create_embed(
            title=f"🔨 Moderation: {action}",
            color=Colors.ERROR if "Ban" in action or "Kick" in action else Colors.WARNING,
        )
        embed.add_field(name="Target", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Moderator", value=f"{moderator.mention} (`{moderator.id}`)", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        if extra:
            embed.add_field(name="Details", value=extra, inline=False)

        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Dispatch confidential mod report to owner mod-report channel
        try:
            from utils.owner_reporter import OwnerReporter
            OwnerReporter.send_mod_report(
                self.bot,
                guild.id,
                event=f"Moderation {action}",
                user=target if isinstance(target, (discord.User, discord.Member)) else None,
                moderator=moderator,
                reason=reason,
                action_taken=f"{action} executed successfully",
                severity="HIGH" if action in ("Ban", "Kick") else "MEDIUM",
                details={"Details": extra} if extra else None,
            )
        except Exception:
            pass

    # ==========================================
    # MODERATION COMMANDS
    # ==========================================

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @is_admin_or_owner()
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for the ban",
        delete_messages_days="Days of messages to delete (0 to 7)",
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = "No reason provided",
        delete_messages_days: Optional[int] = 0,
    ):
        # Hierarchy checks
        can_mod, err = can_moderate(interaction.user, member, interaction.guild.me)
        if not can_mod:
            await interaction.response.send_message(embed=error_embed("Action Disallowed", err), ephemeral=True)
            return

        # Interactive confirmation
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=warning_embed(
                "Confirm Ban",
                f"Are you sure you want to ban {member.mention} (`{member.id}`)?\n**Reason:** {reason}",
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()

        if view.value is True:
            try:
                delete_seconds = min(7, max(0, delete_messages_days or 0)) * 86400
                await member.ban(reason=f"{reason} (Banned by {interaction.user})", delete_message_seconds=delete_seconds)
                await interaction.followup.send(embed=success_embed("Member Banned", f"Successfully banned {member.mention}."), ephemeral=True)
                await self._log_mod_action(interaction.guild, "Ban", member, interaction.user, reason)
            except Exception as e:
                await interaction.followup.send(embed=error_embed("Ban Failed", str(e)), ephemeral=True)

    @app_commands.command(name="unban", description="Unban a previously banned user by ID")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @is_admin_or_owner()
    @app_commands.describe(user_id="Discord ID of the banned user", reason="Reason for the unban")
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = "No reason provided"):
        if not user_id.isdigit():
            await interaction.response.send_message(embed=error_embed("Invalid ID", "Please provide a valid numeric Discord user ID."), ephemeral=True)
            return

        user_obj = discord.Object(id=int(user_id))
        try:
            await interaction.guild.unban(user_obj, reason=f"{reason} (Unbanned by {interaction.user})")
            await interaction.response.send_message(embed=success_embed("User Unbanned", f"Successfully unbanned user ID `{user_id}`."), ephemeral=True)
            await self._log_mod_action(interaction.guild, "Unban", user_obj, interaction.user, reason)
        except discord.NotFound:
            await interaction.response.send_message(embed=error_embed("Not Found", "User is not banned or does not exist."), ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(embed=error_embed("Unban Failed", str(e)), ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @is_admin_or_owner()
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
        can_mod, err = can_moderate(interaction.user, member, interaction.guild.me)
        if not can_mod:
            await interaction.response.send_message(embed=error_embed("Action Disallowed", err), ephemeral=True)
            return

        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=warning_embed(
                "Confirm Kick",
                f"Are you sure you want to kick {member.mention} (`{member.id}`)?\n**Reason:** {reason}",
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()

        if view.value is True:
            try:
                await member.kick(reason=f"{reason} (Kicked by {interaction.user})")
                await interaction.followup.send(embed=success_embed("Member Kicked", f"Successfully kicked {member.mention}."), ephemeral=True)
                await self._log_mod_action(interaction.guild, "Kick", member, interaction.user, reason)
            except Exception as e:
                await interaction.followup.send(embed=error_embed("Kick Failed", str(e)), ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout/mute a member for a duration (e.g. 10m, 1h, 1d)")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(
        member="The member to timeout",
        duration="Duration string (e.g., 5m, 1h, 1d, 7d)",
        reason="Reason for the timeout",
    )
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: Optional[str] = "No reason provided",
    ):
        can_mod, err = can_moderate(interaction.user, member, interaction.guild.me)
        if not can_mod:
            await interaction.response.send_message(embed=error_embed("Action Disallowed", err), ephemeral=True)
            return

        seconds = parse_duration(duration)
        if not seconds or seconds < 10 or seconds > (28 * 86400):
            await interaction.response.send_message(
                embed=error_embed("Invalid Duration", "Provide a duration between 10 seconds and 28 days (e.g. `10m`, `2h`, `1d`)."),
                ephemeral=True,
            )
            return

        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        try:
            await member.timeout(until, reason=f"{reason} (Timed out by {interaction.user})")
            await interaction.response.send_message(
                embed=success_embed("Member Timed Out", f"{member.mention} timed out for **{duration}**.\n**Reason:** {reason}"),
                ephemeral=True,
            )
            await self._log_mod_action(interaction.guild, "Timeout", member, interaction.user, reason, extra=f"Duration: {duration}")
        except Exception as e:
            await interaction.response.send_message(embed=error_embed("Timeout Failed", str(e)), ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove timeout from a member")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="The member to untimeout", reason="Reason for removing timeout")
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
        can_mod, err = can_moderate(interaction.user, member, interaction.guild.me)
        if not can_mod:
            await interaction.response.send_message(embed=error_embed("Action Disallowed", err), ephemeral=True)
            return

        try:
            await member.timeout(None, reason=f"{reason} (Timeout removed by {interaction.user})")
            await interaction.response.send_message(embed=success_embed("Timeout Removed", f"Removed timeout from {member.mention}."), ephemeral=True)
            await self._log_mod_action(interaction.guild, "Remove Timeout", member, interaction.user, reason)
        except Exception as e:
            await interaction.response.send_message(embed=error_embed("Failed", str(e)), ephemeral=True)

    @app_commands.command(name="warn", description="Issue a formal warning to a member")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        can_mod, err = can_moderate(interaction.user, member, interaction.guild.me)
        if not can_mod:
            await interaction.response.send_message(embed=error_embed("Action Disallowed", err), ephemeral=True)
            return

        warning_id = await self.bot.db.add_warning(interaction.guild.id, member.id, interaction.user.id, reason)
        warnings = await self.bot.db.get_warnings(interaction.guild.id, member.id)

        embed = success_embed(
            "Warning Issued",
            f"Warned {member.mention} (`Warning #{warning_id}`).\n"
            f"**Reason:** {reason}\n"
            f"**Total Warnings:** {len(warnings)}"
        )
        await interaction.response.send_message(embed=embed)
        await self._log_mod_action(interaction.guild, f"Warn (#{warning_id})", member, interaction.user, reason)

        # Notify warned user in DM
        try:
            dm_embed = warning_embed(
                f"Warning in {interaction.guild.name}",
                f"You received a warning from staff.\n**Reason:** {reason}\n**Total Warnings:** {len(warnings)}",
            )
            await member.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @app_commands.command(name="warnings", description="View warnings for a member")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="The member whose warnings to inspect")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = await self.bot.db.get_warnings(interaction.guild.id, member.id)
        if not warns:
            await interaction.response.send_message(embed=info_embed("No Warnings", f"{member.mention} has a clean record with 0 warnings."), ephemeral=True)
            return

        lines = [
            f"`#{w.id}` — **{w.reason}** (by <@{w.moderator_id}> on {w.created_at[:10]})"
            for w in warns
        ]

        embed = create_embed(
            title=f"⚠️ Warnings for {member.name} ({len(warns)})",
            description="\n".join(lines),
            color=Colors.WARNING,
            thumbnail_url=member.display_avatar.url,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clear", description="Purge a specified number of messages in the channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(amount="Number of messages to delete (1-100)", member="Filter messages from a specific user")
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: int,
        member: Optional[discord.Member] = None,
    ):
        if not (1 <= amount <= 100):
            await interaction.response.send_message(embed=error_embed("Invalid Amount", "Please specify an amount between 1 and 100."), ephemeral=True)
            return

        if not hasattr(interaction.channel, "purge"):
            await interaction.response.send_message(
                embed=error_embed("Purge Unavailable", "Messages cannot be purged in this channel type (e.g. direct messages)."),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        def check(m: discord.Message) -> bool:
            return member is None or m.author.id == member.id

        try:
            deleted = await interaction.channel.purge(limit=amount, check=check)
            msg = f"Deleted **{len(deleted)}** message(s)."
            if member:
                msg += f" (Filtered to {member.mention})"
            await interaction.followup.send(embed=success_embed("Purge Complete", msg), ephemeral=True)
            if interaction.guild:
                channel_name = getattr(interaction.channel, "name", str(interaction.channel.id))
                await self._log_mod_action(interaction.guild, "Purge", interaction.user, interaction.user, f"Cleared {len(deleted)} messages in #{channel_name}")
        except Exception as e:
            await interaction.followup.send(embed=error_embed("Purge Failed", str(e)), ephemeral=True)

    @app_commands.command(name="slowmode", description="Set channel message slowmode delay")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(seconds="Slowmode in seconds (0 to 21600)")
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if not (0 <= seconds <= 21600):
            await interaction.response.send_message(embed=error_embed("Invalid Time", "Seconds must be between 0 and 21600 (6 hours)."), ephemeral=True)
            return

        await interaction.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await interaction.response.send_message(embed=success_embed("Slowmode Disabled", "Slowmode has been turned off."))
        else:
            await interaction.response.send_message(embed=success_embed("Slowmode Updated", f"Slowmode delay set to **{seconds}s**."))

    @app_commands.command(name="lock", description="Lock the current channel preventing @everyone from sending messages")
    @app_commands.default_permissions(manage_channels=True)
    @is_admin_or_owner()
    async def lock(self, interaction: discord.Interaction):
        channel = interaction.channel
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Channel locked by {interaction.user}")
        await interaction.response.send_message(embed=security_embed("Channel Locked", "Members can no longer send messages in this channel."))

    @app_commands.command(name="unlock", description="Unlock the current channel allowing @everyone to send messages")
    @app_commands.default_permissions(manage_channels=True)
    @is_admin_or_owner()
    async def unlock(self, interaction: discord.Interaction):
        channel = interaction.channel
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Channel unlocked by {interaction.user}")
        await interaction.response.send_message(embed=success_embed("Channel Unlocked", "Members can now send messages in this channel."))


async def setup(bot: SentinelBot):
    await bot.add_cog(ModerationCog(bot))
