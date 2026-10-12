"""
THOR APEX — Advanced Invite Tracker Cog (APEX INVITE).
Provides slash commands for invite inspection, leaderboards, history,
auditing, resetting, synchronizing, and reward role management.
"""

from __future__ import annotations

import datetime
import math
from typing import Optional, TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from database.models import InviteTrackerConfig
from services.invite_tracker_service import InviteTrackerService
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot


class ConfirmResetView(discord.ui.View):
    """Interactive confirmation view for resetting invite statistics."""

    def __init__(self, author_id: int, target_name: str):
        super().__init__(timeout=60.0)
        self.author_id = author_id
        self.target_name = target_name
        self.confirmed: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the administrator who initiated this reset can confirm it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"⏳ Resetting invite statistics for **{self.target_name}**...",
            view=self,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="❌ Invite reset operation cancelled.",
            view=self,
        )


class LeaderboardPaginationView(discord.ui.View):
    """Paginated view for server invite leaderboard rankings."""

    def __init__(self, bot: SentinelBot, guild: discord.Guild, total_count: int, per_page: int = 10):
        super().__init__(timeout=120.0)
        self.bot = bot
        self.guild = guild
        self.per_page = per_page
        self.page = 0
        self.max_page = max(0, math.ceil(total_count / per_page) - 1)
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = (self.page <= 0)
        self.next_button.disabled = (self.page >= self.max_page)

    async def get_page_embed(self) -> discord.Embed:
        offset = self.page * self.per_page
        entries = await self.bot.db.get_invite_leaderboard(self.guild.id, limit=self.per_page, offset=offset)

        embed = discord.Embed(
            title=f"🏆 {self.guild.name} — Top Inviters Leaderboard",
            color=Colors.GOLD,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        if self.guild.icon:
            embed.set_thumbnail(url=self.guild.icon.url)

        if not entries:
            embed.description = "*No tracked invitations recorded yet for this server.*"
            embed.set_footer(text=f"THOR APEX • Page {self.page + 1}/{max(1, self.max_page + 1)}")
            return embed

        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        lines = []
        for idx, stat in enumerate(entries):
            rank = offset + idx + 1
            medal = medals.get(rank - 1, f"`#{rank}`")
            user = self.bot.get_user(stat.user_id)
            user_str = f"<@{stat.user_id}>" if user else f"User `{stat.user_id}`"
            net = stat.effective_invites
            lines.append(
                f"{medal} **{user_str}** — **{net}** Net "
                f"*(✅ {stat.regular_invites} reg | ❌ {stat.left_invites} left | ⚠️ {stat.fake_invites} fake | 🎁 {stat.bonus_invites} bns)*"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"THOR APEX • Page {self.page + 1}/{max(1, self.max_page + 1)}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self._update_buttons()
            embed = await self.get_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
            self._update_buttons()
            embed = await self.get_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()


class InviteTrackerCog(commands.Cog, name="InviteTracker"):
    """THOR APEX Advanced Invite Tracking, Analytics, and Reward Roles."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.tracker = InviteTrackerService.get_instance(bot)

    async def cog_load(self) -> None:
        logger = self.tracker.bot.logger if hasattr(self.tracker.bot, "logger") else None
        # Prime invite caches for all connected guilds on cog load
        for guild in self.bot.guilds:
            try:
                await self.tracker.sync_guild(guild)
            except Exception as e:
                pass

    # ==========================================
    # LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        self.tracker.on_invite_create(invite)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        self.tracker.on_invite_delete(invite)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.tracker.process_member_join(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.tracker.process_member_remove(member)

    # ==========================================
    # USER SLASH COMMANDS
    # ==========================================

    @app_commands.command(name="invites", description="Display a member's total, successful, fake, and left invites.")
    @app_commands.describe(member="The member whose invite counts to inspect (defaults to you).")
    async def cmd_invites(
        self, interaction: discord.Interaction, member: Optional[discord.Member] = None
    ) -> None:
        target = member or interaction.user
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        stats = await self.bot.db.get_inviter_stats(guild.id, target.id)
        config = await self.bot.db.get_invite_tracker_config(guild.id)

        embed = discord.Embed(
            title=f"✉️ Invite Statistics — {target.display_name}",
            color=Colors.PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(
            name="⚡ Net / Valid Invites",
            value=f"**{stats.effective_invites}**",
            inline=True,
        )
        embed.add_field(
            name="📊 Total Recorded",
            value=f"**{stats.total_invites}**",
            inline=True,
        )
        embed.add_field(
            name="🎁 Bonus Invites",
            value=f"**{stats.bonus_invites}**",
            inline=True,
        )
        embed.add_field(
            name="✅ Regular Joins",
            value=f"`{stats.regular_invites}`",
            inline=True,
        )
        embed.add_field(
            name="❌ Left Server",
            value=f"`{stats.left_invites}`",
            inline=True,
        )
        embed.add_field(
            name="⚠️ Fake / Young",
            value=f"`{stats.fake_invites}`",
            inline=True,
        )

        embed.set_footer(text="THOR APEX • Apex Invite Architecture")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="invite-leaderboard", description="Show the top inviters in the server.")
    async def cmd_invite_leaderboard(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        config = await self.bot.db.get_invite_tracker_config(guild.id)
        if not config.leaderboard_visible and not (
            interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id
        ):
            await interaction.response.send_message("❌ The invite leaderboard is currently hidden by server staff.", ephemeral=True)
            return

        # Fetch top 100 count for pagination
        all_leaders = await self.bot.db.get_invite_leaderboard(guild.id, limit=100, offset=0)
        view = LeaderboardPaginationView(self.bot, guild, total_count=len(all_leaders), per_page=10)
        embed = await view.get_page_embed()
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="invite-info", description="Display detailed invite metrics and conversion statistics.")
    @app_commands.describe(member="The member to inspect (defaults to you).")
    async def cmd_invite_info(
        self, interaction: discord.Interaction, member: Optional[discord.Member] = None
    ) -> None:
        target = member or interaction.user
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        stats = await self.bot.db.get_inviter_stats(guild.id, target.id)
        join_record = await self.bot.db.get_member_invite(guild.id, target.id)

        embed = discord.Embed(
            title=f"🔍 Detailed Invite Intelligence ╏ {target.name}",
            color=Colors.INFO,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)

        # Performance Ratios
        total = stats.total_invites
        reg = stats.regular_invites
        left = stats.left_invites
        conversion = round((reg / total * 100), 1) if total > 0 else 0.0
        retention = round(((reg - left) / reg * 100), 1) if reg > 0 else 0.0

        embed.add_field(name="⚡ Net Invites", value=f"**{stats.effective_invites}**", inline=True)
        embed.add_field(name="🎯 Conversion Rate", value=f"**{conversion}%**", inline=True)
        embed.add_field(name="🛡️ Member Retention", value=f"**{retention}%**", inline=True)

        embed.add_field(
            name="📋 Detailed Breakdown",
            value=(
                f"• Regular Joins: **{stats.regular_invites}**\n"
                f"• Departed Members: **{stats.left_invites}**\n"
                f"• Flagged/Fake Accounts: **{stats.fake_invites}**\n"
                f"• Administrator Bonus: **{stats.bonus_invites}**"
            ),
            inline=False,
        )

        # Who invited this target member
        if join_record and join_record.inviter_id:
            inviter = self.bot.get_user(join_record.inviter_id)
            inviter_str = f"<@{join_record.inviter_id}> ({inviter.name if inviter else join_record.inviter_id})"
            code_str = f"`{join_record.invite_code}`" if join_record.invite_code else "Direct / Unknown"
            embed.add_field(
                name="👤 Joining Lineage",
                value=f"Invited by: {inviter_str}\nCode: {code_str}\nStatus: `{join_record.classification.upper()}`",
                inline=False,
            )
        else:
            embed.add_field(
                name="👤 Joining Lineage",
                value="*Joined via vanity URL, server discovery, or direct bot invite.*",
                inline=False,
            )

        embed.set_footer(text="THOR APEX • Apex Invite Architecture")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="invite-history", description="Show recent invite activity for a member.")
    @app_commands.describe(member="The member whose recent invite activity to view.")
    async def cmd_invite_history(
        self, interaction: discord.Interaction, member: Optional[discord.Member] = None
    ) -> None:
        target = member or interaction.user
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        records = await self.bot.db.get_recent_invite_history(guild.id, user_id=target.id, limit=10)

        embed = discord.Embed(
            title=f"📜 Recent Invite History — {target.name}",
            color=Colors.PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)

        if not records:
            embed.description = f"*No recent invite history found for {target.mention}.*"
            await interaction.response.send_message(embed=embed)
            return

        lines = []
        for r in records:
            member_obj = self.bot.get_user(r.member_id)
            m_str = f"<@{r.member_id}>" if member_obj else f"User `{r.member_id}`"
            joined_dt = r.joined_at[:19].replace("T", " ")
            status_emoji = "✅"
            if r.classification == "fake":
                status_emoji = "⚠️"
            elif r.classification == "rejoin":
                status_emoji = "🔄"
            if r.left_at:
                status_emoji = "❌"

            lines.append(
                f"{status_emoji} {m_str} • `{r.classification.upper()}`\n"
                f"   Code: `{r.invite_code or 'N/A'}` | Date: `{joined_dt}`"
                f"{' | *(Left Server)*' if r.left_at else ''}"
            )

        embed.description = "\n\n".join(lines)
        embed.set_footer(text="THOR APEX • Apex Invite Architecture")
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # ADMINISTRATIVE COMMANDS
    # ==========================================

    @app_commands.command(name="invites-reset", description="Reset invite statistics with administrator confirmation.")
    @app_commands.describe(member="The member to reset (leave blank to reset ALL server invite statistics).")
    @app_commands.default_permissions(administrator=True)
    async def cmd_invites_reset(
        self, interaction: discord.Interaction, member: Optional[discord.Member] = None
    ) -> None:
        guild = interaction.guild
        if not guild or not (interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id):
            await interaction.response.send_message("❌ Only server administrators can reset invite statistics.", ephemeral=True)
            return

        target_name = member.name if member else f"ALL MEMBERS IN {guild.name}"
        view = ConfirmResetView(interaction.user.id, target_name)

        embed = discord.Embed(
            title="⚠️ Warning: Reset Invite Statistics",
            description=(
                f"Are you sure you want to permanently reset invite statistics for **{target_name}**?\n\n"
                "• Regular, fake, left, and bonus invite counts will be set to **0**.\n"
                "• Historical join records will be marked as cleared.\n"
                "• This action cannot be undone."
            ),
            color=Colors.ALERT,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if view.confirmed:
            target_id = member.id if member else None
            await self.bot.db.reset_inviter_stats(guild.id, target_id)
            success_embed = discord.Embed(
                title="✅ Invite Statistics Reset Complete",
                description=f"Successfully reset invite metrics for **{target_name}**.",
                color=Colors.SUCCESS,
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)

    @app_commands.command(name="invites-sync", description="Synchronize invite caches with live Discord server data.")
    @app_commands.default_permissions(administrator=True)
    async def cmd_invites_sync(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild or not (interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id):
            await interaction.response.send_message("❌ Only server administrators can synchronize invite caches.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        t_start = datetime.datetime.now(datetime.timezone.utc)
        success = await self.tracker.sync_guild(guild)
        elapsed_ms = round((datetime.datetime.now(datetime.timezone.utc) - t_start).total_seconds() * 1000, 1)

        if not success:
            err_embed = discord.Embed(
                title="❌ Invite Synchronization Failed",
                description=(
                    "Could not synchronize invites with Discord.\n\n"
                    "**Troubleshooting:**\n"
                    "• Ensure the bot has the **Manage Server / Manage Guild** permission.\n"
                    "• Check Discord API status."
                ),
                color=Colors.ERROR,
            )
            await interaction.followup.send(embed=err_embed, ephemeral=True)
            return

        cached_count = len(self.tracker._invite_cache.get(guild.id, {}))
        vanity_uses = self.tracker._vanity_cache.get(guild.id, 0)

        embed = discord.Embed(
            title="⚡ Invite Cache Synchronized",
            description=f"Successfully refreshed invite tracking cache for **{guild.name}** in `{elapsed_ms}ms`.",
            color=Colors.SUCCESS,
        )
        embed.add_field(name="🔗 Active Invites Cached", value=f"**{cached_count}** links", inline=True)
        embed.add_field(name="🌐 Vanity Uses Tracked", value=f"**{vanity_uses}** uses", inline=True)
        embed.set_footer(text="THOR APEX • Apex Invite Architecture")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="invites-config", description="View or configure invite-tracking settings.")
    @app_commands.describe(
        log_channel="Channel where invite joins and departures are logged.",
        welcome_channel="Channel for welcome messages containing inviter placeholders.",
        welcome_message="Custom template ({user}, {username}, {inviter}, {inviter_tag}, {invite_code}, {inviter_invites}).",
        send_welcome="Enable or disable welcome messages sent by invite tracker.",
        min_account_age="Minimum account age in days to avoid fake invite classification.",
        deduct_on_leave="Deduct an invite when an invited member leaves.",
        rewards_enabled="Enable or disable automated invite milestone roles.",
        enabled="Enable or disable invite tracking entirely.",
    )
    @app_commands.default_permissions(administrator=True)
    async def cmd_invites_config(
        self,
        interaction: discord.Interaction,
        log_channel: Optional[discord.TextChannel] = None,
        welcome_channel: Optional[discord.TextChannel] = None,
        welcome_message: Optional[str] = None,
        send_welcome: Optional[bool] = None,
        min_account_age: Optional[int] = None,
        deduct_on_leave: Optional[bool] = None,
        rewards_enabled: Optional[bool] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        guild = interaction.guild
        if not guild or not (interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id):
            await interaction.response.send_message("❌ Only server administrators can configure invite tracking.", ephemeral=True)
            return

        config = await self.bot.db.get_invite_tracker_config(guild.id)

        # Apply updates if arguments provided
        updated = False
        if log_channel is not None:
            config.log_channel_id = log_channel.id
            updated = True
        if welcome_channel is not None:
            config.welcome_channel_id = welcome_channel.id
            updated = True
        if welcome_message is not None:
            config.welcome_message = welcome_message
            updated = True
        if send_welcome is not None:
            config.send_welcome = send_welcome
            updated = True
        if min_account_age is not None:
            config.min_account_age_days = max(0, min_account_age)
            updated = True
        if deduct_on_leave is not None:
            config.deduct_on_leave = deduct_on_leave
            updated = True
        if rewards_enabled is not None:
            config.rewards_enabled = rewards_enabled
            updated = True
        if enabled is not None:
            config.enabled = enabled
            updated = True

        if updated:
            await self.bot.db.upsert_invite_tracker_config(config)

        # Display status embed
        embed = discord.Embed(
            title=f"⚙️ Invite Tracking Configuration ╏ {guild.name}",
            color=Colors.SUCCESS if config.enabled else Colors.SECONDARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="🛡️ System Status", value="🟢 **Enabled**" if config.enabled else "🔴 **Disabled**", inline=True)
        embed.add_field(name="📋 Log Channel", value=f"<#{config.log_channel_id}>" if config.log_channel_id else "*Disabled*", inline=True)
        embed.add_field(name="💬 Welcome Channel", value=f"<#{config.welcome_channel_id}>" if config.welcome_channel_id else "*Disabled*", inline=True)

        embed.add_field(name="🎉 Send Welcome", value="✅ **Yes**" if config.send_welcome else "❌ **No**", inline=True)
        embed.add_field(name="⏳ Fake Age Threshold", value=f"**{config.min_account_age_days} days**", inline=True)
        embed.add_field(name="📤 Deduct on Leave", value="✅ **Yes**" if config.deduct_on_leave else "❌ **No**", inline=True)

        embed.add_field(name="🎁 Reward Milestones", value="🟢 **Enabled**" if config.rewards_enabled else "🔴 **Disabled**", inline=True)
        embed.add_field(name="🌐 Track Vanity URLs", value="✅ **Yes**" if config.track_vanity else "❌ **No**", inline=True)
        embed.add_field(name="🏆 Leaderboard Visible", value="✅ **Yes**" if config.leaderboard_visible else "❌ **No**", inline=True)

        embed.add_field(
            name="📝 Welcome Message Template",
            value=f"```{config.welcome_message}```",
            inline=False,
        )
        embed.set_footer(text="THOR APEX • Apex Invite Architecture")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # REWARD MILESTONE COMMANDS
    # ==========================================

    reward_group = app_commands.Group(
        name="invite-reward",
        description="Manage automated invite milestone role rewards.",
        default_permissions=discord.Permissions(administrator=True),
    )

    @reward_group.command(name="add", description="Add an automated role reward milestone.")
    @app_commands.describe(invites="Number of verified invites required.", role="Role to award.")
    async def cmd_reward_add(
        self, interaction: discord.Interaction, invites: int, role: discord.Role
    ) -> None:
        guild = interaction.guild
        if not guild or not (interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id):
            await interaction.response.send_message("❌ Only server administrators can manage invite rewards.", ephemeral=True)
            return

        if role >= guild.me.top_role:
            await interaction.response.send_message(
                f"❌ The role {role.mention} is higher than or equal to my highest role. Move my role above it first.",
                ephemeral=True,
            )
            return

        if invites <= 0:
            await interaction.response.send_message("❌ Required invites must be at least 1.", ephemeral=True)
            return

        await self.bot.db.add_invite_reward(guild.id, required_invites=invites, role_id=role.id)
        embed = discord.Embed(
            title="🎁 Invite Reward Milestone Configured",
            description=f"Members reaching **{invites} verified invites** will automatically receive {role.mention}.",
            color=Colors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reward_group.command(name="remove", description="Remove an invite reward milestone.")
    @app_commands.describe(invites="Number of invites for the milestone to remove.")
    async def cmd_reward_remove(self, interaction: discord.Interaction, invites: int) -> None:
        guild = interaction.guild
        if not guild or not (interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id):
            await interaction.response.send_message("❌ Only server administrators can manage invite rewards.", ephemeral=True)
            return

        removed = await self.bot.db.remove_invite_reward(guild.id, required_invites=invites)
        if removed:
            await interaction.response.send_message(f"✅ Removed invite reward milestone for **{invites} invites**.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ No milestone found for **{invites} invites**.", ephemeral=True)

    @reward_group.command(name="list", description="List all configured invite reward milestones.")
    async def cmd_reward_list(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        rewards = await self.bot.db.get_invite_rewards(guild.id)
        embed = discord.Embed(
            title=f"🎁 Invite Reward Milestones ╏ {guild.name}",
            color=Colors.PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        if not rewards:
            embed.description = "*No invite milestone rewards configured yet. Use `/invite-reward add` to create one.*"
            await interaction.response.send_message(embed=embed)
            return

        lines = []
        for r in rewards:
            role = guild.get_role(r.role_id)
            r_str = role.mention if role else f"Deleted Role (`{r.role_id}`)"
            lines.append(f"• **{r.required_invites} Invites** ➔ {r_str}")

        embed.description = "\n".join(lines)
        embed.set_footer(text="THOR APEX • Apex Invite Architecture")
        await interaction.response.send_message(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(InviteTrackerCog(bot))
