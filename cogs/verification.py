"""
Smart Verification System Cog for Rai.
Provides interactive luxury button verification, new-account protection,
automatic verified & community role assignment, welcome channel broadcasts,
and persistent verification audit logs.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from database.models import VerificationConfig
from utils.embeds import (
    create_embed,
    error_embed,
    info_embed,
    security_embed,
    success_embed,
    warning_embed,
)
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

# Core Server Constants for ✦ Rai Fam ✦
DEFAULT_VERIFIED_ROLE_ID = 1549504522953695269   # ✨ ╏ 𝓥ᴇʀɪғɪᴇᴅ 𝕸ᴇᴍʙᴇʀ
COMMUNITY_MEMBER_ROLE_ID = 1545494584203673740   # 💖 ╏ 𝓡ᴀɪ 𝕱ᴀᴍ
VERIFY_CHANNEL_ID = 1545502700840427702         # #✨・𝓥ᴇʀɪғʏ-𝕳ᴇʀᴇ
WELCOME_CHANNEL_ID = 1545502705643167876        # #🌸・𝓦ᴇʟᴄᴏᴍᴇ
RULES_CHANNEL_ID = 1545502710101704714          # #📜・𝓡ᴜʟᴇs-ᴀɴᴅ-𝕲ᴜɪᴅᴇ
ROLES_CHANNEL_ID = 1545502722739150898          # #📌・𝓢ᴇʀᴠᴇʀ-𝕽ᴏʟᴇs
GENERAL_CHAT_ID = 1545502735749480679           # #💬・𝓖ᴇɴᴇʀᴀʟ-𝓒ʜᴀᴛ


def build_luxury_verification_embed(guild: discord.Guild, min_age_hours: int = 0) -> discord.Embed:
    """Builds the signature Fusion B luxury verification gateway embed."""
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓥ᴇʀɪғɪᴄᴀᴛɪᴏɴ 𝕲ᴀᴛᴇ ✦",
        description=(
            "Welcome to **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦** — the official sanctuary for gaming, "
            "chill vibes, and automated community experiences.\n\n"
            "To safeguard our community against automated raid bots, spam, and malicious actors, "
            "all incoming members must pass the **Rai Security Gate** before accessing channels."
        ),
        color=0x2ECC71,  # Emerald luxury green
    )
    
    embed.add_field(
        name="📜 ╏ Server Guidelines",
        value=(
            "• Treat all members and staff with respect.\n"
            "• Zero tolerance for hate speech, toxicity, or raids.\n"
            "• No unsolicited DM advertising or phishing links.\n"
            f"• Full guidelines detailed in <#{RULES_CHANNEL_ID}>."
        ),
        inline=False,
    )
    
    embed.add_field(
        name="✨ ╏ Clearance Perks",
        value=(
            "Upon verification, you will automatically unlock:\n"
            f"• <@&{DEFAULT_VERIFIED_ROLE_ID}> — Verified clearance badge\n"
            f"• <@&{COMMUNITY_MEMBER_ROLE_ID}> — Full access to community lounges\n"
            f"• Voice loungers, game pings (<#{ROLES_CHANNEL_ID}>), & bot commands!"
        ),
        inline=False,
    )

    if min_age_hours > 0:
        embed.add_field(
            name="🛡️ ╏ Anti-Alt Protection",
            value=f"Accounts must be at least **{min_age_hours} hours** old to verify.",
            inline=True,
        )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Security Engine • Instant Verification ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


class VerificationButtonView(discord.ui.View):
    """Persistent button view for interactive member verification."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify & Enter Server",
        style=discord.ButtonStyle.success,
        emoji="✨",
        custom_id="rai_verification_button",
    )
    async def verify_button(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            return

        bot: SentinelBot = interaction.client  # type: ignore
        cfg = await bot.db.get_verification_config(guild.id)
        
        target_role_id = cfg.role_id or DEFAULT_VERIFIED_ROLE_ID
        primary_role = guild.get_role(target_role_id)
        community_role = guild.get_role(COMMUNITY_MEMBER_ROLE_ID)

        if not primary_role:
            await interaction.response.send_message(
                embed=error_embed("Configuration Error", "The primary verification role could not be found."),
                ephemeral=True,
            )
            return

        # Check if already verified
        if primary_role in member.roles:
            await interaction.response.send_message(
                embed=info_embed(
                    "Already Verified",
                    f"✦ You are already a verified member of **{guild.name}**!\n"
                    f"Head over to <#{GENERAL_CHAT_ID}> to chat with everyone.",
                ),
                ephemeral=True,
            )
            return

        # Account age protection check
        age_hours = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).total_seconds() / 3600.0
        min_age = cfg.min_account_age_hours if cfg.enabled else 0
        if min_age > 0 and age_hours < min_age:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Account Too New",
                    f"Your Discord account must be at least **{min_age} hours** old to verify.\n"
                    f"Current account age: `{age_hours:.1f} hours`.\n"
                    f"Please try again once your account meets this requirement.",
                ),
                ephemeral=True,
            )
            return

        # Assign roles
        roles_to_add = [primary_role]
        if community_role and community_role not in member.roles:
            roles_to_add.append(community_role)

        try:
            await member.add_roles(*roles_to_add, reason="✦ Rai Luxury Verification Gate Passed ✦")
            await bot.db.record_verification(guild.id, member.id, age_hours)
            
            if hasattr(bot, "role_manager") and bot.role_manager:
                try:
                    await bot.role_manager.on_verification_completed(member)
                except Exception as r_err:
                    logger.warning(f"RoleManager verification hook error: {r_err}")

            # 1. Ephemeral Success Card
            success_card = discord.Embed(
                title="✦ 𝓥ᴇʀɪғɪᴄᴀᴛɪᴏɴ 𝕾ᴜᴄᴄᴇssғᴜʟ ✦",
                description=(
                    f"Welcome to **{guild.name}**, {member.mention}! 🎉\n\n"
                    f"Your access has been unlocked:\n"
                    f"• **Clearance Badge**: {primary_role.mention}\n"
                    f"{'• **Community Role**: ' + community_role.mention if community_role else ''}\n\n"
                    f"🌟 **Next Steps:**\n"
                    f"1. Check our full rules in <#{RULES_CHANNEL_ID}>\n"
                    f"2. Customize your game & notification roles in <#{ROLES_CHANNEL_ID}>\n"
                    f"3. Jump in and introduce yourself in <#{GENERAL_CHAT_ID}>!"
                ),
                color=0x2ECC71,
            )
            success_card.set_thumbnail(url=member.display_avatar.url)
            success_card.set_footer(text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ You're all set! Enjoy your stay ✦")
            await interaction.response.send_message(embed=success_card, ephemeral=True)
            logger.info(f"Member {member} ({member.id}) successfully verified in {guild.name}")

            # 2. Public Welcome Announcement in #🌸・𝓦ᴇʟᴄᴏᴍᴇ
            welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
            if welcome_channel and isinstance(welcome_channel, discord.TextChannel):
                welcome_embed = discord.Embed(
                    title="🌸 𝓦ᴇʟᴄᴏᴍᴇ ᴛᴏ ✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦",
                    description=(
                        f"A new star has arrived! Please give a warm welcome to {member.mention}!\n\n"
                        f"We are thrilled to have you here in our family. Make yourself at home, "
                        f"grab your self-roles in <#{ROLES_CHANNEL_ID}>, and hop into voice or text chat!"
                    ),
                    color=0xFF77A9,  # Soft luxury sakura pink
                )
                welcome_embed.set_thumbnail(url=member.display_avatar.url)
                welcome_embed.add_field(name="👤 Member", value=f"{member.mention} (`{member.name}`)", inline=True)
                welcome_embed.add_field(name="💎 Member #", value=f"#{guild.member_count}", inline=True)
                welcome_embed.add_field(name="🛡️ Clearance", value="`Verified Member` ✨", inline=True)
                welcome_embed.set_footer(
                    text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Welcoming System ✦",
                    icon_url=guild.icon.url if guild.icon else None,
                )
                welcome_embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
                try:
                    await welcome_channel.send(content=f"Welcome {member.mention}! 🌸", embed=welcome_embed)
                except Exception as w_err:
                    logger.warning(f"Failed to post welcome announcement: {w_err}")

        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Permission Error", "I lack the required permissions to assign the verified roles (check role hierarchy)."),
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error during verification for {member}: {e}")
            await interaction.response.send_message(
                embed=error_embed("Verification Error", "An unexpected error occurred while assigning your role."),
                ephemeral=True,
            )

    @discord.ui.button(
        label="Server Rules",
        style=discord.ButtonStyle.secondary,
        emoji="📜",
        custom_id="rai_verification_rules",
    )
    async def rules_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        rules_embed = discord.Embed(
            title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓒ᴏᴍᴍᴜɴɪᴛʏ 𝕲ᴜɪᴅᴇʟɪɴᴇs ✦",
            description=(
                "To ensure a safe and enjoyable atmosphere for everyone, all members are required to follow these core standards:\n\n"
                "**1. Respect & Courtesy**\n"
                "Treat all members and moderators with decency. Discrimination, hate speech, and harassment are strictly prohibited.\n\n"
                "**2. Anti-Spam & Promotion**\n"
                "Do not flood channels, spam emojis/mentions, or send unsolicited server invites / self-promotional DMs.\n\n"
                "**3. Safe Content Only**\n"
                "Keep all content safe for work (SFW). Any malicious files, token grabbers, or NSFW material result in an instant ban.\n\n"
                "**4. Voice & Lounge Etiquette**\n"
                "Use appropriate microphone volume. Do not play earrape audio or scream down mics.\n\n"
                f"📖 For full details and server bylaws, visit <#{RULES_CHANNEL_ID}>."
            ),
            color=0x3498DB,
        )
        rules_embed.set_footer(text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Governance ✦")
        await interaction.response.send_message(embed=rules_embed, ephemeral=True)

    @discord.ui.button(
        label="Help & Support",
        style=discord.ButtonStyle.secondary,
        emoji="❓",
        custom_id="rai_verification_help",
    )
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        help_embed = discord.Embed(
            title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓥ᴇʀɪғɪᴄᴀᴛɪᴏɴ 𝕬ssɪsᴛᴀɴᴄᴇ ✦",
            description=(
                "**Trouble verifying?** Here are quick troubleshooting steps:\n\n"
                "• **Account Age Requirement**: Brand-new Discord accounts created minutes ago may be held until meeting the minimum age requirement.\n"
                "• **Lag or Discord Issues**: If the verification button is unresponsive, try restarting your Discord client.\n"
                "• **Need Staff Help?**: If you are still unable to verify, contact a Moderator or Administrator directly.\n\n"
                "Our autonomous security engine is active 24/7 to ensure your account is safe."
            ),
            color=0xE67E22,
        )
        help_embed.set_footer(text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Member Support Desk ✦")
        await interaction.response.send_message(embed=help_embed, ephemeral=True)


class VerificationCog(commands.Cog, name="Verification"):
    """Smart Verification and New-Member Protection."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    verification_group = app_commands.Group(
        name="verification",
        description="Configure and manage new-member verification",
        default_permissions=discord.Permissions(administrator=True),
    )

    @verification_group.command(name="setup", description="Deploy or update the luxury verification gate")
    @is_admin_or_owner()
    @app_commands.describe(
        channel="Channel where the verification panel will be posted (defaults to #verify-here)",
        role="Primary role to grant (defaults to Verified Member)",
        min_account_age_hours="Minimum account age in hours to qualify (0 = no check)",
    )
    async def verification_setup(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        role: Optional[discord.Role] = None,
        min_account_age_hours: Optional[int] = 0,
    ):
        guild = interaction.guild
        if not guild:
            return

        target_channel = channel or guild.get_channel(VERIFY_CHANNEL_ID)
        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Channel Error", "Target verification channel could not be found."),
                ephemeral=True,
            )
            return

        target_role = role or guild.get_role(DEFAULT_VERIFIED_ROLE_ID)
        if not target_role:
            await interaction.response.send_message(
                embed=error_embed("Role Error", "Primary verified role could not be found."),
                ephemeral=True,
            )
            return

        if target_role >= guild.me.top_role:
            await interaction.response.send_message(
                embed=error_embed("Role Hierarchy Error", f"The role {target_role.mention} is higher than or equal to Rai's highest role."),
                ephemeral=True,
            )
            return

        min_age = max(0, min_account_age_hours or 0)
        await self.bot.db.update_verification_config(
            guild.id,
            enabled=True,
            role_id=target_role.id,
            channel_id=target_channel.id,
            min_account_age_hours=min_age,
        )

        embed = build_luxury_verification_embed(guild, min_age)
        view = VerificationButtonView()

        try:
            # Check if there is an existing bot message in the channel to edit cleanly
            found_existing = False
            async for msg in target_channel.history(limit=20):
                if msg.author.id == self.bot.user.id and (
                    "VERIFICATION" in (msg.embeds[0].title or "") if msg.embeds else False
                    or "𝓥ᴇʀɪғɪᴄᴀᴛɪᴏɴ" in (msg.embeds[0].title or "") if msg.embeds else False
                ):
                    await msg.edit(embed=embed, view=view)
                    found_existing = True
                    break

            if not found_existing:
                await target_channel.send(embed=embed, view=view)

            await interaction.response.send_message(
                embed=success_embed(
                    "Luxury Verification Gate Deployed",
                    f"Gate active in {target_channel.mention} granting {target_role.mention} + <@&{COMMUNITY_MEMBER_ROLE_ID}>.",
                ),
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Failed to deploy verification panel: {e}")
            await interaction.response.send_message(
                embed=error_embed("Failed to Deploy Panel", f"Could not post/edit verification message: {e}"),
                ephemeral=True,
            )

    @verification_group.command(name="status", description="Check current verification settings and stats")
    @is_admin_or_owner()
    async def verification_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return
        cfg = await self.bot.db.get_verification_config(guild.id)
        role_mention = f"<@&{cfg.role_id}>" if cfg.role_id else f"<@&{DEFAULT_VERIFIED_ROLE_ID}>"
        channel_mention = f"<#{cfg.channel_id}>" if cfg.channel_id else f"<#{VERIFY_CHANNEL_ID}>"

        embed = create_embed(
            title=f"✦ 𝓥ᴇʀɪғɪᴄᴀᴛɪᴏɴ 𝕾ᴛᴀᴛᴜs ╏ {guild.name} ✦",
            color=Colors.SUCCESS if cfg.enabled else Colors.DEFAULT,
        )
        embed.add_field(name="Status", value="🟢 Active" if cfg.enabled else "⚪ Inactive", inline=True)
        embed.add_field(name="Primary Role", value=role_mention, inline=True)
        embed.add_field(name="Community Role", value=f"<@&{COMMUNITY_MEMBER_ROLE_ID}>", inline=True)
        embed.add_field(name="Gate Channel", value=channel_mention, inline=True)
        embed.add_field(name="Welcome Channel", value=f"<#{WELCOME_CHANNEL_ID}>", inline=True)
        embed.add_field(name="Min Account Age", value=f"`{cfg.min_account_age_hours} hours`", inline=True)
        embed.set_footer(text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Security & Welcoming ✦")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @verification_group.command(name="disable", description="Disable member verification")
    @is_admin_or_owner()
    async def verification_disable(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return
        await self.bot.db.update_verification_config(guild.id, enabled=False)
        await interaction.response.send_message(
            embed=warning_embed("Verification Gate Disabled", "New-member verification has been deactivated."),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Fallback listener for legacy or button custom_ids."""
        if interaction.type != discord.InteractionType.component:
            return
        if interaction.response.is_done():
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if custom_id in ("btn_verify_member", "rai_verification_button"):
            view = VerificationButtonView()
            await view.verify_button(interaction, None)  # type: ignore
        elif custom_id == "rai_verification_rules":
            view = VerificationButtonView()
            await view.rules_button(interaction, None)  # type: ignore
        elif custom_id == "rai_verification_help":
            view = VerificationButtonView()
            await view.help_button(interaction, None)  # type: ignore
        elif custom_id.startswith("rai_rules_tab:"):
            from utils.rules_view import get_rules_tab_embed
            tab = custom_id.split(":", 1)[1]
            embed = get_rules_tab_embed(tab, interaction.guild)  # type: ignore
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        elif custom_id == "rai_rules_acknowledge":
            from utils.rules_view import RulesConsoleView
            view = RulesConsoleView()
            await view.acknowledge_btn(interaction, None)  # type: ignore
        elif custom_id.startswith("rai_role_opt:"):
            role_key = custom_id.split(":", 1)[1]
            role_map = {
                "announcements": (1550199913093144649, "Announcements"),
                "giveaways": (1550199917262143560, "Giveaways"),
                "tournaments": (1550199921007792188, "Tournaments"),
                "valorant": (1551184094313062470, "Valorant / Gaming"),
            }
            if role_key in role_map and interaction.guild and isinstance(interaction.user, discord.Member):
                r_id, r_name = role_map[role_key]
                role = interaction.guild.get_role(r_id)
                if role:
                    if role in interaction.user.roles:
                        try:
                            await interaction.user.remove_roles(role, reason="Self-assigned role toggle")
                            await interaction.response.send_message(f"➖ Removed **{role.name}** from your profile.", ephemeral=True)
                        except Exception as e:
                            await interaction.response.send_message(f"❌ Could not remove role: {e}", ephemeral=True)
                    else:
                        try:
                            await interaction.user.add_roles(role, reason="Self-assigned role toggle")
                            await interaction.response.send_message(f"➕ Added **{role.name}** to your profile!", ephemeral=True)
                        except Exception as e:
                            await interaction.response.send_message(f"❌ Could not add role: {e}", ephemeral=True)


async def setup(bot: SentinelBot):
    from utils.rules_view import RulesConsoleView
    bot.add_view(VerificationButtonView())
    bot.add_view(RulesConsoleView())
    await bot.add_cog(VerificationCog(bot))
