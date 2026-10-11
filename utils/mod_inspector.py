"""
Interactive Mod View and Forensics Inspector for Rai.
Provides rich server-specific member telemetry, verification status,
and interactive staff action controls.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional, List
import discord
from discord import ui

from config import Colors
from utils.embeds import create_embed, success_embed, error_embed, warning_embed
from config.permissions import can_moderate, is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot


class WarnReasonModal(ui.Modal, title="Issue Member Warning"):
    reason_input = ui.TextInput(
        label="Warning Reason",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. Inappropriate language in voice lounge, spamming invites...",
        required=True,
        max_length=500,
    )

    def __init__(self, target: discord.Member, bot: SentinelBot):
        super().__init__()
        self.target = target
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value.strip()
        guild = interaction.guild
        moderator = interaction.user

        # Save to database
        if hasattr(self.bot, "db") and self.bot.db:
            await self.bot.db.create_moderation_warning(
                guild_id=guild.id,
                user_id=self.target.id,
                moderator_id=moderator.id,
                reason=reason,
            )

        # Notify target
        try:
            dm_emb = create_embed(
                title=f"⚠️ Warning Notice ╏ {guild.name}",
                description=f"You received a warning from staff in **{guild.name}**.\n\n**Reason:** {reason}",
                color=Colors.WARNING,
            )
            await self.target.send(embed=dm_emb)
        except Exception:
            pass

        # Log mod action
        try:
            from utils.owner_reporter import OwnerReporter
            OwnerReporter.send_mod_report(
                self.bot,
                guild.id,
                event="Member Warning Issued",
                user=self.target,
                moderator=moderator,
                reason=reason,
                action_taken="Warning logged to permanent moderation dossier",
            )
        except Exception:
            pass

        await interaction.response.send_message(
            embed=success_embed("Warning Recorded", f"⚠️ Successfully issued warning to {self.target.mention}.\n**Reason:** {reason}"),
            ephemeral=True,
        )


class ModInspectorView(ui.View):
    """Interactive Staff Quick-Action Controls for Member Inspection."""

    def __init__(self, target: discord.Member, bot: SentinelBot):
        super().__init__(timeout=300)
        self.target = target
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        can_mod, err = can_moderate(interaction.user, self.target, interaction.guild.me)
        if not can_mod and not is_admin_or_owner(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Permission Denied", err or "You do not have permission to moderate this member."),
                ephemeral=True,
            )
            return False
        return True

    @ui.button(label="Timeout 10m", style=discord.ButtonStyle.secondary, emoji="⏱️", row=0)
    async def timeout_10m(self, interaction: discord.Interaction, button: ui.Button):
        try:
            duration = datetime.timedelta(minutes=10)
            until = discord.utils.utcnow() + duration
            await self.target.timeout(until, reason=f"Staff Mod View quick-action by {interaction.user}")

            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_mod_report(
                    self.bot,
                    interaction.guild.id,
                    event="Member Timed Out (10m)",
                    user=self.target,
                    moderator=interaction.user,
                    reason="Mod View quick action",
                    action_taken="10 minute timeout engaged",
                )
            except Exception:
                pass

            await interaction.response.send_message(
                embed=success_embed("Timeout Applied", f"⏱️ Placed {self.target.mention} in timeout for **10 minutes**."),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(embed=error_embed("Action Failed", str(e)), ephemeral=True)

    @ui.button(label="Warn Member", style=discord.ButtonStyle.primary, emoji="⚠️", row=0)
    async def warn_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = WarnReasonModal(self.target, self.bot)
        await interaction.response.send_modal(modal)

    @ui.button(label="Infraction History", style=discord.ButtonStyle.secondary, emoji="📜", row=0)
    async def history_btn(self, interaction: discord.Interaction, button: ui.Button):
        if hasattr(self.bot, "db") and self.bot.db:
            warnings = await self.bot.db.get_warnings(interaction.guild.id, self.target.id)
            if not warnings:
                await interaction.response.send_message(
                    embed=create_embed(
                        title=f"📜 Infractions ╏ {self.target.name}",
                        description="✨ Clean record! No recorded warnings or infractions found.",
                        color=Colors.SUCCESS,
                    ),
                    ephemeral=True,
                )
                return

            desc = "\n\n".join(
                f"**#{w.id}** • <t:{int(datetime.datetime.fromisoformat(w.created_at).timestamp()) if 'T' in w.created_at else 0}:R>\n"
                f"👮 Moderator: <@{w.moderator_id}>\n"
                f"📝 Reason: `{w.reason}`"
                for w in warnings[:8]
            )
            embed = create_embed(
                title=f"📜 Infractions Dossier ╏ {self.target.name} ({len(warnings)} total)",
                description=desc,
                color=Colors.WARNING,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Database unavailable.", ephemeral=True)

    @ui.button(label="Disconnect Voice", style=discord.ButtonStyle.secondary, emoji="🔊", row=1)
    async def disconnect_vc(self, interaction: discord.Interaction, button: ui.Button):
        if not self.target.voice or not self.target.voice.channel:
            await interaction.response.send_message(
                embed=warning_embed("Not in Voice", f"{self.target.mention} is not currently connected to any voice channel."),
                ephemeral=True,
            )
            return

        try:
            ch_name = self.target.voice.channel.name
            await self.target.move_to(None, reason=f"Disconnected by staff {interaction.user}")
            await interaction.response.send_message(
                embed=success_embed("Voice Disconnected", f"🔊 Disconnected {self.target.mention} from **#{ch_name}**."),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(embed=error_embed("Disconnect Failed", str(e)), ephemeral=True)

    @ui.button(label="Kick Member", style=discord.ButtonStyle.danger, emoji="🚫", row=1)
    async def kick_btn(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await self.target.kick(reason=f"Kicked via Mod View by {interaction.user}")
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_mod_report(
                    self.bot,
                    interaction.guild.id,
                    event="Member Kicked",
                    user=self.target,
                    moderator=interaction.user,
                    reason="Mod View quick kick action",
                    action_taken="Member removed from server",
                    severity="HIGH",
                )
            except Exception:
                pass

            await interaction.response.send_message(
                embed=success_embed("Member Kicked", f"🚫 Successfully kicked {self.target.mention} from the server."),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(embed=error_embed("Kick Failed", str(e)), ephemeral=True)


async def build_mod_view_embed(bot: SentinelBot, member: discord.Member, requester: discord.Member) -> discord.Embed:
    """Constructs the rich Mod View & Telemetry embed."""
    guild = member.guild
    embed = create_embed(
        title=f"👤 Mod View ╏ {member.display_name}",
        color=member.accent_color.value if hasattr(member, "accent_color") and member.accent_color else 0x9B59B6,
        thumbnail_url=member.display_avatar.url,
    )

    # 1. Server Activity & Standing
    is_pending = getattr(member, "pending", False)
    screening_str = "⏳ Pending (Unacknowledged)" if is_pending else "✅ Agreed to Rules"
    is_timed_out = member.is_timed_out()
    timeout_str = f"⚠️ Timed out until <t:{int(member.timed_out_until.timestamp())}:R>" if is_timed_out else "✅ None (Clear)"

    embed.add_field(
        name="📊 Account & Verification",
        value=(
            f"• **Username:** `{member.name}`\n"
            f"• **User ID:** `{member.id}`\n"
            f"• **Created:** {discord.utils.format_dt(member.created_at, 'R')}\n"
            f"• **Joined:** {discord.utils.format_dt(member.joined_at, 'R') if member.joined_at else 'Unknown'}\n"
            f"• **Rules Status:** {screening_str}"
        ),
        inline=False,
    )

    # 2. Forensics & Moderation Standing
    warning_count = 0
    if hasattr(bot, "db") and bot.db:
        try:
            warnings = await bot.db.get_warnings(guild.id, member.id)
            warning_count = len(warnings)
        except Exception:
            warning_count = 0

    embed.add_field(
        name="🛡️ Moderation & Standing",
        value=(
            f"• **Active Warnings:** `{warning_count}`\n"
            f"• **Timeout Standing:** {timeout_str}\n"
            f"• **Bot Account:** `{'Yes' if member.bot else 'No'}`\n"
            f"• **Top Role:** {member.top_role.mention}"
        ),
        inline=True,
    )

    # 3. Voice & Dynamic VC
    vc_status = "Not in voice"
    if member.voice and member.voice.channel:
        mute_badge = " [Muted]" if member.voice.self_mute or member.voice.mute else ""
        deaf_badge = " [Deaf]" if member.voice.self_deaf or member.voice.deaf else ""
        vc_status = f"{member.voice.channel.mention}{mute_badge}{deaf_badge}"

    owned_vc = "None"
    if hasattr(bot, "db") and bot.db:
        try:
            dyn_room = await bot.db.get_dynamic_room_by_owner(guild.id, member.id)
            if dyn_room and dyn_room.status == "active":
                owned_vc = f"<#{dyn_room.voice_channel_id}>"
        except Exception:
            pass

    embed.add_field(
        name="🎙️ Voice Status",
        value=(
            f"• **Connected VC:** {vc_status}\n"
            f"• **Owned Dynamic Room:** {owned_vc}"
        ),
        inline=True,
    )

    # 4. Roles Breakdown (Filter out divider labels for compact aesthetic)
    meaningful_roles = [
        r.mention for r in member.roles
        if not r.is_default() and "───" not in r.name
    ]
    if meaningful_roles:
        role_chunks = " ".join(meaningful_roles[:16])
        if len(meaningful_roles) > 16:
            role_chunks += f" *(+{len(meaningful_roles) - 16} more)*"
        embed.add_field(name=f"🏷️ Assigned Roles ({len(meaningful_roles)})", value=role_chunks, inline=False)

    embed.set_footer(
        text=f"RλI://CORE • Mod View • Requested by {requester.display_name}",
        icon_url=guild.icon.url if guild.icon else None,
    )
    return embed
