"""
Third-Party Bot Least-Privilege Shield for RAI.

Audits third-party external bots in the server, identifies over-privileged bots
(e.g., holding Administrator, Manage Roles, Ban, Kick), calculates risk scores,
and provides interactive one-click safe isolation into a dedicated least-privilege role.
"""

from __future__ import annotations

import datetime
import enum
import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from database.models import BotShieldAuditRecord
from utils.embeds import create_embed

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.BotPrivilegeShield")


class BotRiskTier(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    SAFE = "SAFE"


@dataclass
class BotPrivilegeAuditItem:
    bot_member: discord.Member
    risk_tier: BotRiskTier
    dangerous_permissions: List[str]
    roles_with_danger: List[discord.Role]
    is_isolated: bool = False


class BotShieldActionView(discord.ui.View):
    """Interactive action dashboard for managing third-party bot permissions."""

    def __init__(
        self,
        shield: "BotPrivilegeShield",
        bot: "SentinelBot",
        guild: discord.Guild,
        audit_items: List[BotPrivilegeAuditItem],
        requester: discord.Member,
    ):
        super().__init__(timeout=180.0)
        self.shield = shield
        self.bot = bot
        self.guild = guild
        self.audit_items = audit_items
        self.requester = requester

        # Populate select menu with high-risk bots if any exist
        high_risk_bots = [item for item in audit_items if item.risk_tier in (BotRiskTier.CRITICAL, BotRiskTier.HIGH) and not item.is_isolated]
        if high_risk_bots:
            options = [
                discord.SelectOption(
                    label=item.bot_member.display_name[:25],
                    description=f"{item.risk_tier.value}: {', '.join(item.dangerous_permissions[:3])}"[:50],
                    value=str(item.bot_member.id),
                    emoji="🤖",
                )
                for item in high_risk_bots[:25]
            ]
            self.select_bot.options = options
        else:
            self.remove_item(self.select_bot)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only the Founder or Server Administrators can execute bot isolation.", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="Select a high-risk bot to isolate...",
        custom_id="rai_bot_shield:select_bot",
        row=0,
    )
    async def select_bot(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        bot_id = int(select.values[0])
        bot_member = self.guild.get_member(bot_id)
        if not bot_member:
            await interaction.followup.send("❌ Bot member not found in server.", ephemeral=True)
            return

        success, msg = await self.shield.isolate_bot(self.guild, bot_member, interaction.user)
        if success:
            await interaction.followup.send(f"🛡️ **Success**: {msg}", ephemeral=True)
            # Re-audit and edit original embed
            new_audit = await self.shield.audit_guild_bots(self.guild)
            embed = self.shield.build_audit_embed(self.guild, new_audit)
            new_view = BotShieldActionView(self.shield, self.bot, self.guild, new_audit, self.requester)
            await interaction.message.edit(embed=embed, view=new_view)
        else:
            await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)

    @discord.ui.button(
        label="Auto-Isolate All High Risk Bots",
        style=discord.ButtonStyle.danger,
        emoji="🛡️",
        custom_id="rai_bot_shield:isolate_all",
        row=1,
    )
    async def isolate_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        high_risk_bots = [item for item in self.audit_items if item.risk_tier in (BotRiskTier.CRITICAL, BotRiskTier.HIGH) and not item.is_isolated]
        if not high_risk_bots:
            await interaction.followup.send("✅ No unisolated high-risk bots detected.", ephemeral=True)
            return

        results = []
        for item in high_risk_bots:
            ok, msg = await self.shield.isolate_bot(self.guild, item.bot_member, interaction.user)
            results.append(f"• **{item.bot_member.display_name}**: {'✅ Isolated' if ok else f'❌ {msg}'}")

        await interaction.followup.send("🛡️ **Batch Isolation Completed**:\n" + "\n".join(results), ephemeral=True)
        new_audit = await self.shield.audit_guild_bots(self.guild)
        embed = self.shield.build_audit_embed(self.guild, new_audit)
        new_view = BotShieldActionView(self.shield, self.bot, self.guild, new_audit, self.requester)
        await interaction.message.edit(embed=embed, view=new_view)

    @discord.ui.button(
        label="Re-Scan Bots",
        style=discord.ButtonStyle.secondary,
        emoji="🔄",
        custom_id="rai_bot_shield:rescan",
        row=1,
    )
    async def rescan_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        new_audit = await self.shield.audit_guild_bots(self.guild)
        embed = self.shield.build_audit_embed(self.guild, new_audit)
        new_view = BotShieldActionView(self.shield, self.bot, self.guild, new_audit, self.requester)
        await interaction.message.edit(embed=embed, view=new_view)
        await interaction.followup.send("✅ Bot privilege scan refreshed.", ephemeral=True)


class BotPrivilegeShield:
    """Core engine for third-party bot privilege auditing and safe isolation."""

    SAFE_BOT_ROLE_NAME = "🤖 ╏ Safe Bot"

    DANGEROUS_PERMS = {
        "administrator": ("Administrator", BotRiskTier.CRITICAL),
        "manage_roles": ("Manage Roles", BotRiskTier.CRITICAL),
        "manage_guild": ("Manage Server", BotRiskTier.HIGH),
        "manage_channels": ("Manage Channels", BotRiskTier.HIGH),
        "ban_members": ("Ban Members", BotRiskTier.HIGH),
        "kick_members": ("Kick Members", BotRiskTier.HIGH),
        "mention_everyone": ("Mention Everyone", BotRiskTier.MODERATE),
        "manage_webhooks": ("Manage Webhooks", BotRiskTier.MODERATE),
    }

    def __init__(self, bot: "SentinelBot"):
        self.bot = bot

    async def audit_guild_bots(self, guild: discord.Guild) -> List[BotPrivilegeAuditItem]:
        """Audits all external bots on the server and returns structured risk items."""
        db_records = await self.bot.db.get_bot_shield_audits(guild.id)
        isolated_ids = {r.bot_id for r in db_records if r.is_isolated}

        items: List[BotPrivilegeAuditItem] = []
        for member in guild.members:
            # Exclude human members and Rai itself
            if not member.bot or member.id == self.bot.user.id:
                continue

            dangerous_found: List[str] = []
            highest_tier = BotRiskTier.SAFE
            roles_with_danger: List[discord.Role] = []

            for role in member.roles:
                if role.is_default():
                    continue
                perms = role.permissions
                role_has_danger = False
                for perm_attr, (perm_title, tier) in self.DANGEROUS_PERMS.items():
                    if getattr(perms, perm_attr, False):
                        role_has_danger = True
                        if perm_title not in dangerous_found:
                            dangerous_found.append(perm_title)
                        if tier == BotRiskTier.CRITICAL:
                            highest_tier = BotRiskTier.CRITICAL
                        elif tier == BotRiskTier.HIGH and highest_tier != BotRiskTier.CRITICAL:
                            highest_tier = BotRiskTier.HIGH
                        elif tier == BotRiskTier.MODERATE and highest_tier not in (BotRiskTier.CRITICAL, BotRiskTier.HIGH):
                            highest_tier = BotRiskTier.MODERATE

                if role_has_danger and role not in roles_with_danger:
                    roles_with_danger.append(role)

            if not dangerous_found:
                highest_tier = BotRiskTier.LOW

            is_isolated = member.id in isolated_ids

            items.append(
                BotPrivilegeAuditItem(
                    bot_member=member,
                    risk_tier=highest_tier,
                    dangerous_permissions=dangerous_found,
                    roles_with_danger=roles_with_danger,
                    is_isolated=is_isolated,
                )
            )

        # Sort: CRITICAL -> HIGH -> MODERATE -> LOW
        order = {BotRiskTier.CRITICAL: 0, BotRiskTier.HIGH: 1, BotRiskTier.MODERATE: 2, BotRiskTier.LOW: 3, BotRiskTier.SAFE: 4}
        items.sort(key=lambda x: (order[x.risk_tier], x.bot_member.display_name.lower()))
        return items

    def build_audit_embed(self, guild: discord.Guild, items: List[BotPrivilegeAuditItem]) -> discord.Embed:
        """Renders an executive security report embed summarizing third-party bot privileges."""
        critical_count = sum(1 for i in items if i.risk_tier == BotRiskTier.CRITICAL and not i.is_isolated)
        high_count = sum(1 for i in items if i.risk_tier == BotRiskTier.HIGH and not i.is_isolated)
        isolated_count = sum(1 for i in items if i.is_isolated)

        color = discord.Color.red() if (critical_count + high_count) > 0 else discord.Color.green()

        embed = discord.Embed(
            title="🛡️ ┃ 𝓡ᴀɪ ╏ 𝓣ʜɪʀᴅ-𝕻ᴀʀᴛʏ 𝕭ᴏᴛ 𝕾ʜɪᴇʟᴅ",
            description=(
                f"Comprehensive least-privilege audit of external bots on **{guild.name}**.\n"
                f"Third-party bots with destructive permissions pose critical supply-chain risks.\n\n"
                f"🔴 **Critical**: `{critical_count}` ╏ 🟠 **High Risk**: `{high_count}` ╏ "
                f"🛡️ **Isolated**: `{isolated_count}` ╏ 🤖 **Total External Bots**: `{len(items)}`"
            ),
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        # List top bots
        for item in items[:10]:
            icon = "🔴" if item.risk_tier == BotRiskTier.CRITICAL else "🟠" if item.risk_tier == BotRiskTier.HIGH else "🟡" if item.risk_tier == BotRiskTier.MODERATE else "🟢"
            status_text = " *(ISOLATED)*" if item.is_isolated else ""
            perms_text = ", ".join(item.dangerous_permissions) if item.dangerous_permissions else "Standard Read/Write/Connect"
            roles_text = ", ".join(f"`{r.name}`" for r in item.roles_with_danger) if item.roles_with_danger else "None"

            field_name = f"{icon} {item.bot_member.display_name}{status_text}"
            field_value = (
                f"**Risk Level**: `{item.risk_tier.value}`\n"
                f"**Dangerous Permissions**: `{perms_text}`\n"
                f"**Flagged Roles**: {roles_text}"
            )
            embed.add_field(name=field_name, value=field_value, inline=False)

        embed.set_footer(
            text="Use the action controls below to enforce least-privilege mode.",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None,
        )
        return embed

    async def isolate_bot(
        self, guild: discord.Guild, bot_member: discord.Member, requester: discord.Member
    ) -> Tuple[bool, str]:
        """
        Isolates a bot to least-privilege status:
        1. Ensures a dedicated '🤖 ╏ Safe Bot' role exists with safe permissions.
        2. Assigns '🤖 ╏ Safe Bot' to the bot member.
        3. Removes high-risk roles that grant Administrator or destructive permissions.
        4. Logs immutable audit record.
        """
        if not guild.me.guild_permissions.manage_roles:
            return False, "Rai lacks 'Manage Roles' permission to modify bot roles."

        bot_top_pos = getattr(bot_member.top_role, "position", 0)
        me_top_pos = getattr(guild.me.top_role, "position", 0)
        if bot_top_pos >= me_top_pos:
            return False, f"Role hierarchy blocked: {bot_member.display_name} has a role higher than or equal to Rai."

        # 1. Find or create Safe Bot Role
        safe_role = discord.utils.get(guild.roles, name=self.SAFE_BOT_ROLE_NAME)
        if not safe_role:
            try:
                safe_perms = discord.Permissions(
                    view_channel=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True,
                    use_external_emojis=True,
                    add_reactions=True,
                    connect=True,
                    speak=True,
                    use_voice_activation=True,
                )
                safe_role = await guild.create_role(
                    name=self.SAFE_BOT_ROLE_NAME,
                    permissions=safe_perms,
                    color=discord.Color.from_rgb(88, 101, 242),
                    reason="Created by Rai Bot Least-Privilege Shield for safe external bots.",
                )
            except Exception as e:
                logger.error(f"Failed to create Safe Bot Role in {guild.id}: {e}")
                return False, f"Failed to create safe role: {e}"

        # 2. Identify roles to remove
        roles_to_remove = []
        for role in bot_member.roles:
            if role.is_default() or getattr(role, "managed", False):
                continue
            if getattr(role, "position", 0) >= me_top_pos:
                continue
            # Check if role grants dangerous permissions
            perms = role.permissions
            if any(getattr(perms, p, False) for p in self.DANGEROUS_PERMS):
                roles_to_remove.append(role)

        # 3. Apply role changes
        try:
            if safe_role not in bot_member.roles:
                await bot_member.add_roles(safe_role, reason=f"Isolated by {requester} via Rai Bot Shield")

            for role in roles_to_remove:
                await bot_member.remove_roles(role, reason=f"High-risk permission stripped by {requester} via Rai Bot Shield")

            # 4. Record to SQLite
            audit_id = f"BS-{uuid.uuid4().hex[:8].upper()}"
            record = BotShieldAuditRecord(
                audit_id=audit_id,
                guild_id=guild.id,
                bot_id=bot_member.id,
                bot_name=bot_member.name,
                risk_level="ISOLATED",
                dangerous_permissions="STRIPPED",
                is_isolated=True,
                isolated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            await self.bot.db.record_bot_shield_audit(record)

            removed_names = ", ".join(r.name for r in roles_to_remove) if roles_to_remove else "None"
            return True, f"Successfully isolated **{bot_member.display_name}** into `{self.SAFE_BOT_ROLE_NAME}`. Stripped roles: `{removed_names}`."
        except Exception as e:
            logger.error(f"Error during bot isolation of {bot_member.id}: {e}")
            return False, f"Discord API error: {e}"
