"""
Populate and initialize empty channels in RAI FAM:
1. 🎫・support (1554891431393370144) -> Support Desk & Interactive Ticket Panel
2. 📋・moderation-log (1554891451140149352) -> Live Moderation Audit Matrix
3. 🛡️・security-log (1554891455003107338) -> AI Security Sentinel & Defense Matrix
4. 🛡️｜ꜱᴛᴀꜰꜰ-ᴏᴘᴇʀᴀᴛɪᴏɴꜱ (1545502845208629328) -> Staff Operations Command Protocols
5. 📸｜ᴍᴇᴅɪᴀ-ᴀɴᴅ-ᴄʟɪᴘꜱ (1551184138932068373) -> Media & Gaming Clips Lounge
"""

import os
import aiohttp
import asyncio
import sqlite3
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

async def update_support_permissions(session: aiohttp.ClientSession):
    """Ensure @everyone can view 🎫・support and read history, but not send messages."""
    url = f"https://discord.com/api/v10/channels/1554891431393370144/permissions/{GUILD_ID}"
    # VIEW_CHANNEL = 1024, READ_MESSAGE_HISTORY = 65536
    # SEND_MESSAGES = 2048, CREATE_PUBLIC_THREADS = 0x800000000, CREATE_PRIVATE_THREADS = 0x1000000000
    allow = 1024 | 65536
    deny = 2048 | 0x800000000 | 0x1000000000
    payload = {
        "type": 0,  # role
        "allow": str(allow),
        "deny": str(deny),
    }
    async with session.put(url, headers=HEADERS, json=payload) as r:
        print(f"Updated @everyone permissions for #support: {r.status}")

async def deploy_support_panel(session: aiohttp.ClientSession):
    """Deploy official Ticket Creation Panel with select menu and button."""
    url = "https://discord.com/api/v10/channels/1554891431393370144/messages"
    embed = {
        "title": "🎫 RAI FAM — Official Support Desk & Help Center",
        "description": (
            "Welcome to the **RAI FAM** 24/7 Support Desk!\n"
            "If you have inquiries, need technical assistance, want to apply for staff, or need to report a rule violation, open a private encrypted ticket below.\n\n"
            "**Support Departments:**\n"
            "• ❓ **General Support** — Community questions, roles, economy, or server features.\n"
            "• 🐛 **Bug Reports** — Report bot errors, command glitches, or permission bugs.\n"
            "• 📋 **Staff Applications** — Inquire about moderator or event host positions.\n"
            "• 🤝 **Partnerships & Sponsorships** — Server cross-promotions, collaborations & creator links.\n"
            "• 🔒 **Private & Confidential** — Sensitive reports, security concerns, or founder escalations.\n\n"
            "⚡ **Instructions:**\n"
            "Select your department from the dropdown menu below, or click **[Create Ticket]** to open an immediate private room with our staff team.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "color": 0x5865F2,
        "footer": {"text": "RAI FAM💗 • 24/7 Priority Support System"},
    }

    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 3,
                    "custom_id": "sentinel_ticket_category_select",
                    "placeholder": "Select a support department...",
                    "options": [
                        {
                            "label": "General Support",
                            "description": "Questions about the community, roles, or bot features",
                            "emoji": {"name": "❓"},
                            "value": "general",
                        },
                        {
                            "label": "Bug Reports",
                            "description": "Report bugs, errors, or technical glitches",
                            "emoji": {"name": "🐛"},
                            "value": "bug",
                        },
                        {
                            "label": "Staff Applications",
                            "description": "Apply for moderator or event coordinator staff",
                            "emoji": {"name": "📋"},
                            "value": "staff",
                        },
                        {
                            "label": "Partnership Requests",
                            "description": "Server cross-promotions, affiliations, or collabs",
                            "emoji": {"name": "🤝"},
                            "value": "partnership",
                        },
                        {
                            "label": "Private Support",
                            "description": "Confidential matters or sensitive reports",
                            "emoji": {"name": "🔒"},
                            "value": "private",
                        },
                    ],
                }
            ],
        },
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,
                    "label": "Create Ticket",
                    "emoji": {"name": "🎫"},
                    "custom_id": "sentinel_ticket_create",
                }
            ],
        },
    ]

    async with session.post(url, headers=HEADERS, json={"embeds": [embed], "components": components}) as r:
        print(f"Deployed Support Panel: {r.status}")

async def deploy_moderation_log_header(session: aiohttp.ClientSession):
    """Deploy official Moderation Log Matrix header."""
    url = "https://discord.com/api/v10/channels/1554891451140149352/messages"
    embed = {
        "title": "📋 RAI FAM — Live Moderation Audit Matrix",
        "description": (
            "Official real-time audit stream for server disciplinary actions, automated enforcement, and security sanctions.\n\n"
            "**Enforcement Routing:**\n"
            "• 🚫 **AutoMod Sanctions** — Instant Kicks on Word Filter Violations & Emoji Floods.\n"
            "• 🔨 **Disciplinary Actions** — Captures all `/ban`, `/kick`, `/timeout`, `/warn`, and unbans.\n"
            "• 🧹 **Channel Sanitization** — Message purge logs & bulk deletions.\n"
            "• ⚠️ **Warning Ledger** — Member penalty points & warning milestones.\n\n"
            "**Active Server Policy:**\n"
            "• **AutoMod Mode:** `KICK FROM SERVER` 🚫\n"
            "• **Emoji Limit:** `Max 8 Emojis (Exceeding triggers immediate kick)`\n"
            "• **Phishing / Malicious Links:** `100% Intercepted + 24h Quarantine`\n"
            "• **Anti-Spam Threshold:** `5 msgs / 5 seconds`\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "color": 0x5865F2,
        "footer": {"text": "The Raivora AutoMod • Disciplinary Audit Stream"},
    }
    async with session.post(url, headers=HEADERS, json={"embeds": [embed]}) as r:
        print(f"Deployed Moderation Log Header: {r.status}")

async def deploy_security_log_header(session: aiohttp.ClientSession):
    """Deploy official Security Sentinel Matrix header."""
    url = "https://discord.com/api/v10/channels/1554891455003107338/messages"
    embed = {
        "title": "🛡️ RAI FAM — AI Security Sentinel & Defense Matrix",
        "description": (
            "Autonomous server integrity supervisor and zero-day threat interception terminal.\n\n"
            "**Active Protective Matrices:**\n"
            "• 🧠 **Dual-Core AI Engine** — Google Gemini 1.5 Flash Cloud Neural + Rai Embedded Sentinel.\n"
            "• ⏱️ **24/7 Autonomous Watchdog** — Continuous 60s role, channel overwrite, and admin permission audits.\n"
            "• 🛑 **Anti-Nuke Velocity Shield** — Velocity tracking against unauthorized mass channel/role drops.\n"
            "• 🎣 **Token Logger / Phishing Shield** — Deep regex & neural heuristic blocking malicious domains.\n"
            "• 👑 **Founder Incident Escalation** — 1-Click Interactive Countermeasure alerts sent to Owner DM `rc.rai_007`.\n\n"
            "**Current Shield Metrics:**\n"
            "• **Server Security Score:** `100/100` (OPTIMAL 🟢)\n"
            "• **Watchdog Interval:** `60 Seconds` (Continuous)\n"
            "• **Status:** Active & Vigilant\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "color": 0xEB459E,
        "footer": {"text": "Rai Premium AI Security Sentinel • Threat Intelligence"},
    }
    async with session.post(url, headers=HEADERS, json={"embeds": [embed]}) as r:
        print(f"Deployed Security Log Header: {r.status}")

async def deploy_staff_operations_manual(session: aiohttp.ClientSession):
    """Deploy Staff Operations Protocols & Directives."""
    url = "https://discord.com/api/v10/channels/1545502845208629328/messages"
    embed = {
        "title": "🛡️ RAI FAM — Staff Operations Center & Protocols",
        "description": (
            "Welcome to the private staff operations hub. All server administrators and moderators coordinate operations here.\n\n"
            "**Staff Duties & Standard Operating Procedures:**\n"
            "1. 💬 **Community Care** — Maintain a friendly, luxurious midnight atmosphere in `#💬｜ɢᴇɴᴇʀᴀʟ-ᴄʜᴀᴛ`.\n"
            "2. 🎫 **Ticket Resolution** — Check `#🎫・support` tickets promptly. Close resolved tickets with `/ticket close`.\n"
            "3. 📋 **Audit Review** — Monitor `#📋・moderation-log` for AutoMod kicks and member warnings.\n"
            "4. 🛡️ **Security Vigilance** — If an incident arises, notify founder `rc.rai_007` immediately.\n\n"
            "**Core Moderator Commands:**\n"
            "• `/warn <user> <reason>` — Issue formal warning\n"
            "• `/timeout <user> <duration> <reason>` — Mute disruptive member\n"
            "• `/kick <user> <reason>` — Expel member from server\n"
            "• `/ban <user> [delete_days] <reason>` — Ban member\n"
            "• `/purge <count>` — Bulk delete spam in channel\n"
            "• `/slowmode <seconds>` — Slow chat rate during peak hours\n"
            "• `/ticket close` — Close support ticket and generate transcript\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "color": 0x2B2D31,
        "footer": {"text": "RAI FAM💗 • Staff Operations Directive"},
    }
    async with session.post(url, headers=HEADERS, json={"embeds": [embed]}) as r:
        print(f"Deployed Staff Operations Manual: {r.status}")

async def deploy_media_hub_guide(session: aiohttp.ClientSession):
    """Deploy Media & Clips Lounge guide."""
    url = "https://discord.com/api/v10/channels/1551184138932068373/messages"
    embed = {
        "title": "📸 RAI FAM — Media, Artwork & Gaming Clips Lounge",
        "description": (
            "Share your best moments with the family!\n\n"
            "**What to Post Here:**\n"
            "• 🎮 **Gaming Highlights & Clutch Clips** (BGMI, Free Fire, Valorant, Apex)\n"
            "• 🎨 **Art, Graphic Designs & Banners**\n"
            "• 🖥️ **Desk & Gaming Setups**\n"
            "• 📷 **Photography & Travel Highlights**\n"
            "• 🎭 **Memes & Funny Moments**\n\n"
            "**Guidelines:**\n"
            "• Keep all media respectful and adhering to `#📜｜ʀᴜʟᴇꜱ-ᴀɴᴅ-ɪɴꜰᴏ`.\n"
            "• No NSFW, gore, or malicious files.\n"
            "• React with 🔥 and ❤️ to support creators in the community!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "color": 0x3498DB,
        "footer": {"text": "RAI FAM💗 • Media & Creator Lounge"},
    }
    async with session.post(url, headers=HEADERS, json={"embeds": [embed]}) as r:
        print(f"Deployed Media Hub Guide: {r.status}")

def sync_database_configs():
    """Sync logging_config and ticket_config in data/bot.db."""
    conn = sqlite3.connect("data/bot.db")
    cur = conn.cursor()
    # logging_config
    cur.execute(
        """
        UPDATE logging_config SET
            moderation_channel_id = 1554891451140149352,
            automod_channel_id = 1554891451140149352,
            security_channel_id = 1554891455003107338
        WHERE guild_id = ?
        """,
        (GUILD_ID,)
    )
    # ticket_config
    cur.execute(
        """
        UPDATE ticket_config SET
            category_id = 1554891443343204494,
            log_channel_id = 1554891451140149352,
            transcript_enabled = 1
        WHERE guild_id = ?
        """,
        (GUILD_ID,)
    )
    conn.commit()
    conn.close()
    print("Database configs synchronized for logging and tickets.")

async def main():
    sync_database_configs()
    async with aiohttp.ClientSession() as session:
        await update_support_permissions(session)
        await deploy_support_panel(session)
        await deploy_moderation_log_header(session)
        await deploy_security_log_header(session)
        await deploy_staff_operations_manual(session)
        await deploy_media_hub_guide(session)
    print("All empty channels successfully populated and initialized!")

if __name__ == "__main__":
    asyncio.run(main())
