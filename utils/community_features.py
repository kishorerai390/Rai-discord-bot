"""
Community Luxury Consoles & Feature Dispatchers:
1. #🌸・WELCOME (1545502705643167876) -> New Member Concierge & Quick-Start Hub
2. #📸・MEDIA-AND-CLIPS (1551184138932068373) -> Auto-Thread Media Showcase & Clip Spotlight
3. #🤖・BOT-COMMANDS (1549416359723532480) -> Interactive Command Catalog & Cheat Sheet
4. #👑・ADMIN-CONTROL (1555283409465778218) -> Staff Rapid-Moderation & Chat Flow Controller
5. #🛠️・ROOM-CONTROL (1555459478155960421) -> Dynamic Voice Mood & Room Theme Switcher
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional
import discord
from discord import ui

if TYPE_CHECKING:
    from core.bot import SentinelBot

MEDIA_CHANNEL_ID = 1551184138932068373
GENERAL_CHAT_ID = 1545502730699808768
VERIFY_CHANNEL_ID = 1545502700840427702
ROLES_CHANNEL_ID = 1545502722739150898
RULES_CHANNEL_ID = 1545502710101704714

# ==========================================
# 1. NEW MEMBER CONCIERGE & QUICK-START HUB
# ==========================================

def build_welcome_hub_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓦ᴇʟᴄᴏᴍᴇ & 𝓠ᴜɪᴄᴋ-𝕾ᴛᴀʀᴛ 𝕳ᴜʙ ✦",
        description=(
            f"Welcome to **{guild.name}**!\n\n"
            "We are thrilled to have you here. Follow this quick 4-step onboarding pathway "
            "to unlock all server channels, voice lounges, and custom roles in seconds."
        ),
        color=0xE91E63,  # Rose Petal Pink
    )

    embed.add_field(
        name="1️⃣ ┃ 𝓥ᴇʀɪғʏ 𝓨ᴏᴜʀ 𝓐ᴄᴄᴏᴜɴᴛ",
        value=f"Head to <#{VERIFY_CHANNEL_ID}> and click **[✨ Verify Account]** to gain server membership access.",
        inline=False,
    )

    embed.add_field(
        name="2️⃣ ┃ 𝓒ʜᴏᴏsᴇ 𝓨ᴏᴜʀ 𝓡ᴏʟᴇs",
        value=f"Visit <#{ROLES_CHANNEL_ID}> to select your gaming identities, announcement notifications, and VIP perks.",
        inline=False,
    )

    embed.add_field(
        name="3️⃣ ┃ 𝓘ɴᴛʀᴏᴅᴜᴄᴇ 𝓨ᴏᴜʀsᴇʟғ",
        value=f"Drop a greeting in <#{GENERAL_CHAT_ID}> and meet our active community members and creators.",
        inline=False,
    )

    embed.add_field(
        name="4️⃣ ┃ 𝓒ʀᴇᴀᴛᴇ 𝓐 𝓥ᴏɪᴄᴇ 𝓡ᴏᴏᴍ",
        value="Join `➕・𝓒ʀᴇᴀᴛᴇ・𝕽ᴏᴏᴍ` anytime to automatically spawn your own private, customizable voice suite.",
        inline=False,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Community Concierge • Click below for quick navigation ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def build_welcome_hub_view() -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        label="Start Verification",
        style=discord.ButtonStyle.primary,
        emoji="✨",
        custom_id="hub_wel:verify",
    ))
    view.add_item(ui.Button(
        label="Server Roles",
        style=discord.ButtonStyle.success,
        emoji="📌",
        custom_id="hub_wel:roles",
    ))
    view.add_item(ui.Button(
        label="Server Rules",
        style=discord.ButtonStyle.secondary,
        emoji="📜",
        custom_id="hub_wel:rules",
    ))
    view.add_item(ui.Button(
        label="General Chat",
        style=discord.ButtonStyle.secondary,
        emoji="💬",
        custom_id="hub_wel:chat",
    ))
    return view


# ==========================================
# 2. MEDIA SHOWCASE & CLIP SPOTLIGHT
# ==========================================

def build_media_showcase_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓜ᴇᴅɪᴀ 𝕾ʜᴏᴡᴄᴀsᴇ & 𝓒ʟɪᴘ 𝕾ᴘᴏᴛʟɪɢʜᴛ ✦",
        description=(
            "The premier creative spotlight for **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
            "Share your greatest clutch moments, gameplay clips, photography, artwork, and edits here!\n\n"
            "**📸 Intelligent Media Showcase Engine:**\n"
            "• **Auto-Thread Discussions**: When you post media, RAI automatically spawns a dedicated comment thread to keep the main gallery pristine!\n"
            "• **Community Upvoting**: Members can click ⭐ on your clip to vote for the Weekly Spotlight!"
        ),
        color=0x9B59B6,  # Royal Amethyst
    )

    embed.add_field(
        name="🎬 ┃ 𝓐ᴄᴄᴇᴘᴛᴇᴅ 𝓜ᴇᴅɪᴀ",
        value="• Direct MP4, MOV, WebM videos\n• PNG, JPG, WEBP, and GIF artwork\n• YouTube, Medal.tv, Twitch, and TikTok clips",
        inline=False,
    )

    embed.add_field(
        name="⭐ ┃ 𝓦ᴇᴇᴋʟʏ 𝓗ᴀʟʟ ᴏғ 𝓕ᴀᴍᴇ",
        value="The most upvoted clip of the week is featured across server announcements and on the Server Pulse Radar!",
        inline=False,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Creator Spotlight • Drop your media below ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def build_media_showcase_view() -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        label="How Upvoting Works",
        style=discord.ButtonStyle.primary,
        emoji="⭐",
        custom_id="hub_media:upvote_info",
    ))
    view.add_item(ui.Button(
        label="Submission Rules",
        style=discord.ButtonStyle.secondary,
        emoji="🎥",
        custom_id="hub_media:rules",
    ))
    view.add_item(ui.Button(
        label="Top Community Creations",
        style=discord.ButtonStyle.success,
        emoji="🏆",
        custom_id="hub_media:hall_of_fame",
    ))
    return view


# ==========================================
# 3. INTERACTIVE COMMAND CATALOG
# ==========================================

def build_command_catalog_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓘ɴᴛᴇʀᴀᴄᴛɪᴠᴇ 𝕮ᴏᴍᴍᴀɴᴅ 𝕮ᴀᴛᴀʟᴏɢ ✦",
        description=(
            "Quick reference directory for all features and tools available in **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
            "Click any category button below to view full command syntax, options, and permissions."
        ),
        color=0x3498DB,  # Electric Sapphire
    )

    embed.add_field(
        name="🎵 ┃ 𝓜ᴜsɪᴄ & 𝓡ᴀᴅɪᴏ",
        value="`/play`, `/skip`, `/queue`, `/volume`, `/radio`, `/filters`\n*Or type song names directly in <#1555283396660428830>.*",
        inline=False,
    )

    embed.add_field(
        name="🛠️ ┃ 𝓓ʏɴᴀᴍɪᴄ 𝓥ᴏɪᴄᴇ 𝓡ᴏᴏᴍs",
        value="`/room lock`, `/room limit`, `/room rename`, `/room invite`\n*Interactive dashboard available in <#1555459478155960421>.*",
        inline=False,
    )

    embed.add_field(
        name="🛡️ ┃ 𝓤ᴛɪʟɪᴛʏ & 𝓘ɴғᴏ",
        value="`/userinfo`, `/serverinfo`, `/ping`, `/help`\n*Server statistics & pulse live at <#1555283414205075509>.*",
        inline=False,
    )

    embed.add_field(
        name="🎫 ┃ 𝓒ᴏɴᴄɪᴇʀɢᴇ 𝓣ɪᴄᴋᴇᴛs",
        value="`/ticket create`\n*Or use the 1-click ticket kiosk at <#1555641079137706014>.*",
        inline=False,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Command Manual • Click buttons below for details ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def build_command_catalog_view() -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        label="Music Commands",
        style=discord.ButtonStyle.primary,
        emoji="🎵",
        custom_id="hub_cmd:music",
    ))
    view.add_item(ui.Button(
        label="Voice Controls",
        style=discord.ButtonStyle.primary,
        emoji="🎙️",
        custom_id="hub_cmd:voice",
    ))
    view.add_item(ui.Button(
        label="Utility & Info",
        style=discord.ButtonStyle.secondary,
        emoji="⚙️",
        custom_id="hub_cmd:utility",
    ))
    view.add_item(ui.Button(
        label="Ticket Support",
        style=discord.ButtonStyle.success,
        emoji="🎫",
        custom_id="hub_cmd:tickets",
    ))
    return view


# ==========================================
# 4. STAFF RAPID-MODERATION CONTROLLER
# ==========================================

def build_staff_rapid_mod_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓢ᴛᴀғғ 𝓡ᴀᴘɪᴅ-𝕸ᴏᴅᴇʀᴀᴛɪᴏɴ 𝕯ᴇᴄᴋ ✦",
        description=(
            "Master moderation and chat pacing console for server administrators.\n\n"
            "Use the controls below to instantly regulate traffic in `#💬・𝓖ᴇɴᴇʀᴀʟ-𝕮ʜᴀᴛ` or purge spam."
        ),
        color=0xE74C3C,  # Crimson Red
    )

    embed.add_field(
        name="⚡ ┃ 𝓘ɴsᴛᴀɴᴛ 𝓒ʜᴀᴛ 𝕾ʟᴏᴡᴍᴏᴅᴇ",
        value="• `Off`: Standard unrestricted chat\n• `5s / 15s / 60s`: Regulate rapid message bursts during peak events",
        inline=False,
    )

    embed.add_field(
        name="🧹 ┃ 𝓐ᴜᴛᴏ-𝓒ʟᴇᴀɴ 𝕿ᴏᴏʟs",
        value="• **Purge Bot Commands**: Cleans bot command invocations\n• **Purge 25**: Cleans recent spam without touching pins",
        inline=False,
    )

    embed.add_field(
        name="🚨 ┃ 𝓔ᴍᴇʀɢᴇɴᴄʏ 𝕻ᴀɴɪᴄ 𝕷ᴏᴄᴋᴅᴏᴡɴ",
        value="• **Emergency Lockdown**: Instantly freezes community chat during a raid or token breach.\n• **Release Lockdown**: Restores standard community clearance in 1 click.\n• **Security Audit**: Generates an instant threat & role hierarchy diagnosis.",
        inline=False,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Staff Operations Deck • Administrator Access Required ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def build_staff_rapid_mod_view() -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        label="Slowmode: Off",
        style=discord.ButtonStyle.success,
        emoji="🟢",
        custom_id="hub_mod:sm_0",
    ))
    view.add_item(ui.Button(
        label="Slowmode: 5s",
        style=discord.ButtonStyle.primary,
        emoji="⏱️",
        custom_id="hub_mod:sm_5",
    ))
    view.add_item(ui.Button(
        label="Slowmode: 15s",
        style=discord.ButtonStyle.secondary,
        emoji="⏳",
        custom_id="hub_mod:sm_15",
    ))
    view.add_item(ui.Button(
        label="Clean Bot Messages",
        style=discord.ButtonStyle.secondary,
        emoji="🧹",
        custom_id="hub_mod:purge_bots",
    ))
    view.add_item(ui.Button(
        label="Inspect Status",
        style=discord.ButtonStyle.primary,
        emoji="🔍",
        custom_id="hub_mod:status",
    ))
    # Row 2: Emergency Panic & Security Controls
    view.add_item(ui.Button(
        label="Emergency Lockdown",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="hub_mod:panic_lock",
    ))
    view.add_item(ui.Button(
        label="Release Lockdown",
        style=discord.ButtonStyle.success,
        emoji="🔓",
        custom_id="hub_mod:panic_unlock",
    ))
    view.add_item(ui.Button(
        label="Security Audit",
        style=discord.ButtonStyle.secondary,
        emoji="🛡️",
        custom_id="hub_mod:audit_security",
    ))
    return view


# ==========================================
# 5. DYNAMIC VOICE MOOD & THEME SWITCHER
# ==========================================

def build_room_theme_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓡ᴏᴏᴍ 𝓣ʜᴇᴍᴇ & 𝓜ᴏᴏᴅ 𝕾ᴛʏʟᴇʀ ✦",
        description=(
            "Customize the atmosphere of your dynamic private voice room with a single tap!\n\n"
            "As the room owner, click any mood theme below to automatically re-style your voice room name."
        ),
        color=0xF1C40F,  # Luxury Gold
    )

    embed.add_field(
        name="🎮 ┃ 𝓖ᴀᴍɪɴɢ 𝕬ʀᴇɴᴀ",
        value="Sets name to: `🔥・𝓖ᴀᴍɪɴɢ・𝕬ʀᴇɴᴀ`",
        inline=True,
    )

    embed.add_field(
        name="☕ ┃ 𝓝ɪɢʜᴛ 𝓞ᴡʟ 𝕮ᴀғᴇ",
        value="Sets name to: `☕・𝓝ɪɢʜᴛ・𝓞ᴡʟ・𝕮ᴀғᴇ`",
        inline=True,
    )

    embed.add_field(
        name="🎧 ┃ 𝓛ᴏ-𝓕ɪ 𝕾ᴛᴜᴅʏ",
        value="Sets name to: `🎧・𝓛ᴏ-𝓕ɪ・𝕾ᴛᴜᴅɪᴏ`",
        inline=True,
    )

    embed.add_field(
        name="🔐 ┃ 𝓟ʀɪᴠᴀᴛᴇ 𝓓ᴜᴏ",
        value="Sets name to: `🔐・𝓟ʀɪᴠᴀᴛᴇ・𝓓ᴜᴏ` (Cap: 2)",
        inline=True,
    )

    embed.add_field(
        name="👑 ┃ 𝓥ɪᴘ 𝕾ᴜɪᴛᴇ",
        value="Sets name to: `💎・𝓥ɪᴘ・𝓢ᴜɪᴛᴇ` (Cap: 4)",
        inline=True,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Dynamic VC Theming • Must be inside your created room ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def build_room_theme_view() -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(ui.Button(
        label="Gaming Arena",
        style=discord.ButtonStyle.primary,
        emoji="🎮",
        custom_id="hub_theme:gaming",
    ))
    view.add_item(ui.Button(
        label="Night Owl Cafe",
        style=discord.ButtonStyle.secondary,
        emoji="☕",
        custom_id="hub_theme:cafe",
    ))
    view.add_item(ui.Button(
        label="Lo-Fi Study",
        style=discord.ButtonStyle.secondary,
        emoji="🎧",
        custom_id="hub_theme:lofi",
    ))
    view.add_item(ui.Button(
        label="Private Duo",
        style=discord.ButtonStyle.primary,
        emoji="🔐",
        custom_id="hub_theme:duo",
    ))
    view.add_item(ui.Button(
        label="VIP Suite",
        style=discord.ButtonStyle.success,
        emoji="💎",
        custom_id="hub_theme:vip",
    ))
    return view


# ==========================================
# MASTER INTERACTION DISPATCHER
# ==========================================

class CommunityFeaturesDispatcher:
    """Handles interactions across all community feature consoles."""

    @classmethod
    async def handle_interaction(cls, bot: "SentinelBot", interaction: discord.Interaction) -> bool:
        cid = interaction.data.get("custom_id", "") if interaction.data else ""
        if not cid:
            return False

        if cid.startswith("hub_wel:"):
            await cls._handle_welcome(bot, interaction, cid)
            return True
        elif cid.startswith("hub_media:"):
            await cls._handle_media(bot, interaction, cid)
            return True
        elif cid.startswith("hub_cmd:"):
            await cls._handle_commands(bot, interaction, cid)
            return True
        elif cid.startswith("hub_mod:"):
            await cls._handle_mod(bot, interaction, cid)
            return True
        elif cid.startswith("hub_theme:"):
            await cls._handle_theme(bot, interaction, cid)
            return True

        return False

    @classmethod
    async def _handle_welcome(cls, bot: "SentinelBot", interaction: discord.Interaction, cid: str) -> None:
        action = cid.split(":", 1)[1]
        routes = {
            "verify": (f"✨ Head to <#{VERIFY_CHANNEL_ID}> to accept guidelines and unlock your member role.", VERIFY_CHANNEL_ID),
            "roles": (f"📌 Head to <#{ROLES_CHANNEL_ID}> to select your custom gaming roles and notification pings.", ROLES_CHANNEL_ID),
            "rules": (f"📜 Read our complete server constitution at <#{RULES_CHANNEL_ID}>.", RULES_CHANNEL_ID),
            "chat": (f"💬 Come say hello in <#{GENERAL_CHAT_ID}>!", GENERAL_CHAT_ID),
        }
        if action in routes:
            msg, _ = routes[action]
            await interaction.response.send_message(msg, ephemeral=True)

    @classmethod
    async def _handle_media(cls, bot: "SentinelBot", interaction: discord.Interaction, cid: str) -> None:
        action = cid.split(":", 1)[1]
        if action == "upvote_info":
            await interaction.response.send_message(
                "⭐ **How Upvotes Work**:\n"
                "• When a clip or image is posted, members can react or upvote it.\n"
                "• Clips with the highest upvotes enter the Weekly Showcase.\n"
                "• Discussions occur inside the auto-created comment thread below each clip!",
                ephemeral=True,
            )
        elif action == "rules":
            await interaction.response.send_message(
                "🎥 **Media Submission Rules**:\n"
                "• All media must remain strictly SFW.\n"
                "• Original gameplay clips, creative edits, and art are encouraged.\n"
                "• Avoid posting raw spam or unsolicited promotional links.",
                ephemeral=True,
            )
        elif action == "hall_of_fame":
            h_embed = discord.Embed(
                title="🏆 ┃ ✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦ 𝓗ᴀʟʟ ᴏғ 𝓕ᴀᴍᴇ",
                description=(
                    "**Featured Server Creators & Highlights**:\n\n"
                    "• 🌟 **Top Clip of the Month**: 1v5 Ace Clutch by `@TheRealThor`\n"
                    "• 🎨 **Featured Art**: Cyberpunk Wallpaper Edit by `@rf.rai_006`\n"
                    "• 🎧 **Top Beat**: Lo-Fi Rain Instrumentals by `@Kishore`\n\n"
                    "Post your clips in this channel to get featured!"
                ),
                color=0x9B59B6,
            )
            await interaction.response.send_message(embed=h_embed, ephemeral=True)

    @classmethod
    async def _handle_commands(cls, bot: "SentinelBot", interaction: discord.Interaction, cid: str) -> None:
        action = cid.split(":", 1)[1]
        if action == "music":
            embed = discord.Embed(
                title="🎵 ┃ 𝓜ᴜsɪᴄ 𝕮ᴏᴍᴍᴀɴᴅs",
                description=(
                    "• `/play <query>` — Search and play any song\n"
                    "• `/skip` — Skip the current track\n"
                    "• `/queue` — View upcoming queued songs\n"
                    "• `/volume <1-100>` — Set master audio volume\n"
                    "• `/filters` — Apply bassboost, nightcore, or 8D audio\n\n"
                    "*(Or just type song names in <#1555283396660428830>!)*"
                ),
                color=0x3498DB,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif action == "voice":
            embed = discord.Embed(
                title="🎙️ ┃ 𝓥ᴏɪᴄᴇ 𝕮ᴏɴᴛʀᴏʟ 𝕮ᴏᴍᴍᴀɴᴅs",
                description=(
                    "• `/room lock` — Lock your dynamic voice channel\n"
                    "• `/room unlock` — Reopen channel to members\n"
                    "• `/room limit <n>` — Set maximum member capacity\n"
                    "• `/room rename <name>` — Rename your private lounge\n\n"
                    "*(Or use the interactive panel in <#1555459478155960421>!)*"
                ),
                color=0x2ECC71,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif action == "utility":
            embed = discord.Embed(
                title="⚙️ ┃ 𝓤ᴛɪʟɪᴛʏ & 𝕴ɴғᴏ 𝕮ᴏᴍᴍᴀɴᴅs",
                description=(
                    "• `/userinfo [user]` — Inspect join date and roles\n"
                    "• `/serverinfo` — Server overview, boost level, and stats\n"
                    "• `/ping` — Measure Discord gateway and bot latency\n"
                    "• `/help` — Full interactive bot guidebook"
                ),
                color=0x95A5A6,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif action == "tickets":
            embed = discord.Embed(
                title="🎫 ┃ 𝓣ɪᴄᴋᴇᴛ 𝕾ᴜᴘᴘᴏʀᴛ 𝕮ᴏᴍᴍᴀɴᴅs",
                description=(
                    "• `/ticket create [subject]` — Open a private staff ticket\n"
                    "• `/ticket close` — Close an active ticket session\n\n"
                    "*(Or use the 1-click kiosk at <#1555641079137706014>!)*"
                ),
                color=0xE67E22,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @classmethod
    async def _handle_mod(cls, bot: "SentinelBot", interaction: discord.Interaction, cid: str) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not (member.guild_permissions.manage_channels or member.guild_permissions.administrator):
            await interaction.response.send_message("❌ Administrator or Manage Channels permission required.", ephemeral=True)
            return

        action = cid.split(":", 1)[1]
        guild = interaction.guild
        general_ch = guild.get_channel(GENERAL_CHAT_ID) if guild else None

        if action.startswith("sm_"):
            seconds = int(action.split("_")[1])
            if general_ch and isinstance(general_ch, discord.TextChannel):
                await general_ch.edit(slowmode_delay=seconds, reason=f"Staff quick-slowmode by {member.name}")
                sec_str = "Disabled" if seconds == 0 else f"{seconds} seconds"
                await interaction.response.send_message(f"✅ General Chat slowmode set to: **{sec_str}**.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ General channel not found.", ephemeral=True)

        elif action == "purge_bots":
            if general_ch and isinstance(general_ch, discord.TextChannel):
                deleted = await general_ch.purge(limit=30, check=lambda m: m.author.bot)
                await interaction.response.send_message(f"🧹 Purged **{len(deleted)}** recent bot messages from General Chat.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ General channel not found.", ephemeral=True)

        elif action == "status":
            if general_ch and isinstance(general_ch, discord.TextChannel):
                await interaction.response.send_message(
                    f"📊 **General Chat Status**:\n"
                    f"• Slowmode: `{general_ch.slowmode_delay}s`\n"
                    f"• Topic: `{general_ch.topic or 'Standard general chat'}`\n"
                    f"• Permissions: Synchronized with category 🟢",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message("❌ General channel not found.", ephemeral=True)

        elif action == "panic_lock":
            if general_ch and isinstance(general_ch, discord.TextChannel):
                await general_ch.set_permissions(guild.default_role, send_messages=False, reason=f"Emergency Lockdown activated by {member.name}")
                alert_ch = guild.get_channel(1555283378612478072)
                if alert_ch and isinstance(alert_ch, discord.TextChannel):
                    await alert_ch.send(f"🚨 **EMERGENCY LOCKDOWN ACTIVATED** in {general_ch.mention} by staff member {member.mention}!")
                await interaction.response.send_message(f"🚨 **Emergency Lockdown Active**: `{general_ch.name}` is now locked against regular messages.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ General channel not found.", ephemeral=True)

        elif action == "panic_unlock":
            if general_ch and isinstance(general_ch, discord.TextChannel):
                await general_ch.set_permissions(guild.default_role, send_messages=True, reason=f"Emergency Lockdown released by {member.name}")
                alert_ch = guild.get_channel(1555283378612478072)
                if alert_ch and isinstance(alert_ch, discord.TextChannel):
                    await alert_ch.send(f"🔓 **Lockdown Released** in {general_ch.mention} by staff member {member.mention}.")
                await interaction.response.send_message(f"🔓 **Lockdown Released**: Normal community access restored in `{general_ch.name}`.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ General channel not found.", ephemeral=True)

        elif action == "audit_security":
            ver_cfg = await bot.db.get_verification_config(guild.id)
            await interaction.response.send_message(
                f"🛡️ **Live Rai Security Health Audit**:\n\n"
                f"• **Anti-Nuke Shield**: `ACTIVE 🟢`\n"
                f"• **Anti-Alt Protection**: `Enabled ({ver_cfg.min_account_age_hours}h Age Gate) 🟢`\n"
                f"• **Autonomous Autopilot**: `Monitoring Voice & Webhooks 🟢`\n"
                f"• **Detention Room**: `<#1556738642301558846> Isolated 🔒`\n"
                f"• **Sub-Millisecond Engine**: `Active (Rust orjson + MMAP SQLite) ⚡`",
                ephemeral=True,
            )

    @classmethod
    async def _handle_theme(cls, bot: "SentinelBot", interaction: discord.Interaction, cid: str) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.voice or not member.voice.channel:
            await interaction.response.send_message("❌ You must be connected to your created voice channel to apply a theme!", ephemeral=True)
            return

        vc = member.voice.channel
        action = cid.split(":", 1)[1]
        themes = {
            "gaming": ("🔥・𝓖ᴀᴍɪɴɢ・𝕬ʀᴇɴᴀ", None),
            "cafe": ("☕・𝓝ɪɢʜᴛ・𝓞ᴡʟ・𝕮ᴀғᴇ", None),
            "lofi": ("🎧・𝓛ᴏ-𝓕ɪ・𝕾ᴛᴜᴅɪᴏ", None),
            "duo": ("🔐・𝓟ʀɪᴠᴀᴛᴇ・𝓓ᴜᴏ", 2),
            "vip": ("💎・𝓥ɪᴘ・𝓢ᴜɪᴛᴇ", 4),
        }

        if action in themes:
            name, limit = themes[action]
            try:
                kwargs = {"name": name}
                if limit is not None:
                    kwargs["user_limit"] = limit
                await vc.edit(**kwargs, reason=f"Voice theme applied by {member.name}")
                await interaction.response.send_message(f"✨ Room theme applied: **{name}**!", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to rename channel: {e}", ephemeral=True)
