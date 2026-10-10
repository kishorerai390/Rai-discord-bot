"""
Rai Expiring Temporary Roles & VIP Passes Cog.
Provides:
- /temprole add <member> <role> <duration>: Grants a role with automatic expiration (e.g., 30m, 2h, 24h, 7d).
- /temprole remove <member> <role>: Manually revokes an active temporary role early.
- /temprole list: Displays all active temporary passes with live <t:...:R> countdowns.
- Background task checking every 60s, automatically stripping roles upon expiration.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.owner_reporter import OwnerReporter
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.TempRolesCog")


def parse_duration_to_seconds(duration_str: str) -> Optional[int]:
    """Parses duration strings like '30m', '2h', '1d', '7d' into seconds."""
    match = re.match(r"^(\d+)\s*([mhd])$", duration_str.strip().lower())
    if not match:
        return None
    val, unit = match.groups()
    val = int(val)
    if unit == "m":
        return val * 60
    elif unit == "h":
        return val * 3600
    elif unit == "d":
        return val * 86400
    return None


class TempRolesCog(commands.Cog, name="TempRoles"):
    """Expiring Temporary Roles & Timed VIP Passes."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.expiry_check_loop.start()

    def cog_unload(self):
        self.expiry_check_loop.cancel()

    # ==========================================
    # BACKGROUND EXPIRY LOOP (Every 60 Seconds)
    # ==========================================

    @tasks.loop(seconds=60)
    async def expiry_check_loop(self):
        """Monitors and strips expired temporary roles."""
        await self.bot.wait_until_ready()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        try:
            async with self.bot.db._db.execute(
                "SELECT id, guild_id, user_id, role_id, expires_at FROM temporary_roles WHERE expires_at <= ?",
                (now_iso,),
            ) as cursor:
                expired = await cursor.fetchall()

            for item in expired:
                row_id = item["id"]
                guild_id = item["guild_id"]
                user_id = item["user_id"]
                role_id = item["role_id"]

                guild = self.bot.get_guild(guild_id)
                if guild:
                    member = guild.get_member(user_id)
                    role = guild.get_role(role_id)
                    if member and role and role in member.roles:
                        try:
                            await member.remove_roles(role, reason="Rai TempRoles: Pass expired automatically")
                            try:
                                await member.send(
                                    embed=info_embed(
                                        "Temporary Role Expired",
                                        f"Your temporary pass for the role **{role.name}** in **{guild.name}** has elapsed and been removed.",
                                    )
                                )
                            except Exception:
                                pass
                        except Exception as e:
                            logger.debug("Failed to remove expired role: %s", e)

                # Delete record from database
                await self.bot.db._db.execute("DELETE FROM temporary_roles WHERE id = ?", (row_id,))
                await self.bot.db._db.commit()

        except Exception as e:
            logger.error("[TEMP_ROLES_LOOP_ERR] Error checking expired roles: %s", e)

    # ==========================================
    # SLASH COMMAND GROUP: /temprole
    # ==========================================

    temprole_group = app_commands.Group(
        name="temprole",
        description="Expiring temporary role & VIP pass manager",
    )

    @temprole_group.command(name="add", description="Assign an expiring temporary role to a member")
    @app_commands.describe(
        member="Target member",
        role="Role to grant temporarily",
        duration="Duration before expiry (e.g. 30m, 2h, 24h, 7d)",
    )
    async def temprole_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        duration: str,
    ):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Administrator or Moderator permissions required.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Servers only.", ephemeral=True)
            return

        sec = parse_duration_to_seconds(duration)
        if not sec:
            await interaction.response.send_message(
                "❌ Invalid duration format! Use format like `30m`, `2h`, `24h`, or `7d`.",
                ephemeral=True,
            )
            return

        # Check hierarchy
        if role >= guild.me.top_role:
            await interaction.response.send_message("❌ I cannot assign this role because it is higher than or equal to my highest role.", ephemeral=True)
            return

        await interaction.response.defer()

        # Add role to member
        try:
            await member.add_roles(role, reason=f"Temporary role granted by {interaction.user} for {duration}")
        except discord.Forbidden:
            await interaction.followup.send("❌ Discord Forbidden: Insufficient permissions to manage this role.", ephemeral=True)
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        expires_dt = now + datetime.timedelta(seconds=sec)
        expires_iso = expires_dt.isoformat()
        expires_ts = int(expires_dt.timestamp())

        # Store in database
        await self.bot.db._db.execute(
            """
            INSERT INTO temporary_roles (guild_id, user_id, role_id, assigned_by, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild.id, member.id, role.id, interaction.user.id, expires_iso, now.isoformat()),
        )
        await self.bot.db._db.commit()

        embed = discord.Embed(
            title="⏳ 『RΛI』 • TEMPORARY ROLE ASSIGNED",
            description=(
                f"Successfully granted temporary role to {member.mention}!\n\n"
                f"• **Role:** {role.mention} (`{role.name}`)\n"
                f"• **Duration:** `{duration}`\n"
                f"• **Expires:** <t:{expires_ts}:R> (<t:{expires_ts}:f>)\n"
                f"• **Assigned By:** {interaction.user.mention}\n\n"
                f"The bot will automatically strip this role when the timer elapses."
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text="RAI Automated Role Lifecycle")
        embed.timestamp = now

        await interaction.followup.send(embed=embed)

    @temprole_group.command(name="remove", description="Revoke an active temporary role early")
    @app_commands.describe(
        member="Target member",
        role="Role to revoke",
    )
    async def temprole_remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
    ):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Administrator or Moderator permissions required.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Servers only.", ephemeral=True)
            return

        await interaction.response.defer()

        # Check DB
        async with self.bot.db._db.execute(
            "SELECT id FROM temporary_roles WHERE guild_id = ? AND user_id = ? AND role_id = ?",
            (guild.id, member.id, role.id),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await interaction.followup.send("❌ No active temporary role record found for this member and role.", ephemeral=True)
            return

        # Delete from DB
        await self.bot.db._db.execute("DELETE FROM temporary_roles WHERE id = ?", (row["id"],))
        await self.bot.db._db.commit()

        # Remove role
        if role in member.roles:
            try:
                await member.remove_roles(role, reason=f"Temporary role revoked early by {interaction.user}")
            except Exception:
                pass

        await interaction.followup.send(
            embed=success_embed(
                "Temporary Role Revoked",
                f"Successfully revoked temporary role {role.mention} from {member.mention}.",
            )
        )

    @temprole_group.command(name="list", description="List all active expiring roles and VIP passes")
    async def temprole_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Servers only.", ephemeral=True)
            return

        async with self.bot.db._db.execute(
            "SELECT user_id, role_id, expires_at FROM temporary_roles WHERE guild_id = ? ORDER BY expires_at ASC LIMIT 10",
            (guild.id,),
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message(
                embed=info_embed("No Active Temporary Roles", "There are currently no active temporary roles in this server."),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="⏳ 『RΛI』 • ACTIVE TEMPORARY PASSES",
            description="All active temporary roles currently managed by the lifecycle sentry:\n",
            color=0x3498DB,
        )

        for r in rows:
            user = guild.get_member(r["user_id"])
            role = guild.get_role(r["role_id"])
            u_text = user.mention if user else f"User `{r['user_id']}`"
            r_text = role.mention if role else f"Role `{r['role_id']}`"
            try:
                exp_dt = datetime.datetime.fromisoformat(r["expires_at"])
                ts = int(exp_dt.timestamp())
                exp_text = f"<t:{ts}:R> (<t:{ts}:t>)"
            except Exception:
                exp_text = r["expires_at"]

            embed.add_field(
                name=f"{u_text} ➔ {r_text}",
                value=f"Expires: {exp_text}",
                inline=False,
            )

        embed.set_footer(text="RAI Automated Role Lifecycle")
        await interaction.response.send_message(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(TempRolesCog(bot))
