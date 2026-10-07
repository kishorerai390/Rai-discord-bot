"""
Interactive Rules and Server Guide Console for Rai.
Provides a persistent multi-tab interactive guidebook in #rules-and-guide.
"""

from __future__ import annotations

import datetime
from typing import Optional
import discord
from discord import ui

RULES_CHANNEL_ID = 1545502710101704714
ROLES_CHANNEL_ID = 1545502722739150898
VERIFY_CHANNEL_ID = 1545502700840427702
GENERAL_CHAT_ID = 1545502735749480679


def build_rules_master_embed(guild: discord.Guild) -> discord.Embed:
    """Builds the main luxury overview embed for #rules-and-guide."""
    embed = discord.Embed(
        title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓞ғғɪᴄɪᴀʟ 𝕾ᴇʀᴠᴇʀ 𝕲ᴜɪᴅᴇ & 𝕽ᴜʟᴇs ✦",
        description=(
            "Welcome to the official constitution and server handbook of **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
            "Our community is dedicated to providing an elite, welcoming environment for gaming, "
            "music, and genuine friendships. To protect this atmosphere, all members must uphold "
            "the standards set below.\n\n"
            "👇 **Explore Our Guidelines:** Click any category button below to view detailed guidelines, "
            "voice lounge etiquette, safety policies, and member perks."
        ),
        color=0x9B59B6,  # Royal Amethyst
    )

    embed.add_field(
        name="📜 ╏ Category 1: General Conduct",
        value="Mutual respect, zero harassment, no toxic behavior, and strict SFW policy.",
        inline=False,
    )
    embed.add_field(
        name="🎙️ ╏ Category 2: Voice & Music Lounges",
        value="Clean audio etiquette, respect for dynamic room owners, and fair DJ queue rotation.",
        inline=False,
    )
    embed.add_field(
        name="🛡️ ╏ Category 3: Security & Anti-Raid",
        value="Autonomous anti-raid active 24/7. Strict ban on phishing links, unsolicited DMs, and bot alts.",
        inline=False,
    )
    embed.add_field(
        name="💎 ╏ Category 4: VIP & Server Perks",
        value=f"Unlock custom roles in <#{ROLES_CHANNEL_ID}>, private room creation, and booster privileges.",
        inline=False,
    )

    embed.set_footer(
        text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Governance • Click a tab below ✦",
        icon_url=guild.icon.url if guild.icon else None,
    )
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def get_rules_tab_embed(tab_key: str, guild: discord.Guild) -> discord.Embed:
    """Returns the dedicated category embed for the selected tab."""
    if tab_key == "general":
        embed = discord.Embed(
            title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓖ᴇɴᴇʀᴀʟ 𝕮ᴏɴᴅᴜᴄᴛ ✦",
            description=(
                "**1. Mutual Dignity & Decency**\n"
                "Treat every member, creator, and staff member with courtesy. Hate speech, racism, sexism, "
                "or targeted harassment of any form results in an immediate removal.\n\n"
                "**2. Strictly Safe For Work (SFW)**\n"
                "All text channels, avatars, statuses, and voice streams must remain strictly SFW. "
                "Any explicit, suggestive, or gore content results in a permanent server ban.\n\n"
                "**3. Anti-Spam & Flooding**\n"
                "Avoid spamming capital letters, repeated emojis, mass pings, or wall-of-text messages. "
                "Keep discussions clean and readable for everyone.\n\n"
                f"💬 Head over to <#{GENERAL_CHAT_ID}> to meet the community!"
            ),
            color=0x3498DB,
        )
    elif tab_key == "voice":
        embed = discord.Embed(
            title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓥ᴏɪᴄᴇ & 𝓛ᴏᴜɴɢᴇ 𝕰ᴛɪǫᴜᴇᴛᴛᴇ ✦",
            description=(
                "**1. Microphone & Audio Quality**\n"
                "Use push-to-talk or adjust voice sensitivity to prevent background echo. "
                "Do not scream, blast loud soundboards, or interrupt active conversations.\n\n"
                "**2. Dynamic Voice Rooms**\n"
                "Joining `➕・𝓒ʀᴇᴀᴛᴇ・𝕽ᴏᴏᴍ` generates your own temporary channel. As the owner, "
                "you can lock, rename, and set limits using the room control panel.\n\n"
                "**3. The Knock System**\n"
                "If a dynamic room is locked, click **[🔔 Knock to Join]** on the control panel to request permission. "
                "Do not spam the owner's direct messages.\n\n"
                "**4. Music Lounges**\n"
                "In dedicated music channels, respect the song queue. Do not spam skip other members' tracks."
            ),
            color=0x2ECC71,
        )
    elif tab_key == "security":
        embed = discord.Embed(
            title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓢ᴇᴄᴜʀɪᴛʏ & 𝓐ɴᴛɪ-𝕽ᴀɪᴅ 𝕻ᴏʟɪᴄʏ ✦",
            description=(
                "**1. Autonomous Security Engine**\n"
                "Rai operates a real-time autonomous security watchdog protecting the server against "
                "malicious bot raids, token grabbers, and mass mentions.\n\n"
                "**2. Zero Unsolicited DM Advertising**\n"
                "Sending unsolicited direct messages to members promoting servers, services, or sales is strictly forbidden. "
                "Members caught doing so will be banned.\n\n"
                "**3. Link Verification**\n"
                "Do not post suspicious links, fake Discord Nitro gifts, or untrusted file downloads. "
                "Rai will automatically quarantine malicious links and take punitive action."
            ),
            color=0xE74C3C,
        )
    elif tab_key == "perks":
        embed = discord.Embed(
            title="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓥ɪᴘ & 𝓢ᴇʀᴠᴇʀ 𝕻ᴇʀᴋs ✦",
            description=(
                "**1. Self-Assignable Roles**\n"
                f"Pick up your squad roles (Valorant, BGMI, Free Fire) and event pings in <#{ROLES_CHANNEL_ID}>.\n\n"
                "**2. Server Booster Benefits**\n"
                "Server Boosters receive the exclusive `@🚀 ╏ Server Booster` badge, highest voice bitrate in rooms, "
                "and private lounge privileges.\n\n"
                "**3. Community Loyalty**\n"
                "Active chatters and voice room hosts gain recognition, special role promotions, and priority giveaway access!"
            ),
            color=0xF1C40F,
        )
    else:
        embed = build_rules_master_embed(guild)

    embed.set_footer(text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Community Guidelines Handbook ✦")
    return embed


class RulesConsoleView(ui.View):
    """Persistent interactive view for the Server Rules Console."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="General Conduct", style=discord.ButtonStyle.secondary, emoji="📜", custom_id="rai_rules_tab:general", row=0)
    async def general_tab(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild or interaction.client.get_guild(1457382179981099090)  # type: ignore
        embed = get_rules_tab_embed("general", guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Voice & Lounges", style=discord.ButtonStyle.secondary, emoji="🎙️", custom_id="rai_rules_tab:voice", row=0)
    async def voice_tab(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild or interaction.client.get_guild(1457382179981099090)  # type: ignore
        embed = get_rules_tab_embed("voice", guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Security Policy", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="rai_rules_tab:security", row=0)
    async def security_tab(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild or interaction.client.get_guild(1457382179981099090)  # type: ignore
        embed = get_rules_tab_embed("security", guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Server Perks", style=discord.ButtonStyle.secondary, emoji="💎", custom_id="rai_rules_tab:perks", row=0)
    async def perks_tab(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild or interaction.client.get_guild(1457382179981099090)  # type: ignore
        embed = get_rules_tab_embed("perks", guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="I Acknowledge the Guidelines", style=discord.ButtonStyle.success, emoji="✅", custom_id="rai_rules_acknowledge", row=1)
    async def acknowledge_btn(self, interaction: discord.Interaction, button: ui.Button):
        member = interaction.user
        ack_embed = discord.Embed(
            title="✦ 𝕲ᴜɪᴅᴇʟɪɴᴇs 𝓐ᴄᴋɴᴏᴡʟᴇᴅɢᴇᴅ ✦",
            description=(
                f"Thank you, {member.mention}! ✨\n\n"
                "Your acceptance of the **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦** Community Guidelines has been recorded.\n"
                f"• Verified Role: <@&1549504522953695269>\n"
                f"• Community Access: Granted\n\n"
                f"Enjoy your stay and have fun!"
            ),
            color=0x2ECC71,
        )
        ack_embed.set_footer(text="✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Community Integrity Confirmed ✦")
        if not interaction.response.is_done():
            try:
                await interaction.response.send_message(embed=ack_embed, ephemeral=True)
            except discord.HTTPException as he:
                if he.code == 40060:
                    await interaction.followup.send(embed=ack_embed, ephemeral=True)
                else:
                    raise
        else:
            await interaction.followup.send(embed=ack_embed, ephemeral=True)
