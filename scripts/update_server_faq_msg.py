import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
CH_FAQ = 1557481215731306526
TARGET_MSG_ID = 1557481217580998739

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    embed = {
        "title": "❓ ✦ RAI FAM ┆ MASTER FAQ & KNOWLEDGE BASE ✦",
        "description": (
            "Welcome to the official **Knowledge Base & FAQ** for **✦ ʀᴀɪ ʀᴀᴍ ✦ (RAIVORA)**.\n"
            "Below are answers to the most common questions across the server.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "fields": [
            {
                "name": "✨ 1. How do I get verified?",
                "value": "Head to <#1545502700840427702> or click the button below to complete verification and unlock all channels immediately.",
                "inline": False,
            },
            {
                "name": "🎨 2. How do I pick notifications & squad roles?",
                "value": "Visit <#1545502722739150898> to toggle alerts for Giveaways, Tournaments, and games (Valorant, BGMI, Free Fire).",
                "inline": False,
            },
            {
                "name": "🔊 3. How do I create a private voice room?",
                "value": "Join **`➕・Join to Create`** in the `✧ ᴘʀɪᴠᴀᴛᴇ ᴠᴏɪᴄᴇ ✧` category. The bot instantly creates your room and auto-deletes it when empty.",
                "inline": False,
            },
            {
                "name": "🎧 4. How does 24/7 radio & music work?",
                "value": "Join `⚡ 24/7 Radio` or visit <#1555255695933186228> to control queues and stream lo-fi / gaming beats around the clock.",
                "inline": False,
            },
            {
                "name": "💎 5. How do I unlock VIP & level rewards?",
                "value": "Stay active in <#1545502730699808768>! Reach **Level 5** for `💖 ┆ RAI FAM`, **Level 10** for `💎 ┆ VIP MEMBER`, and **Level 25** for `💎 ┆ DIAMOND PATRON`.",
                "inline": False,
            },
            {
                "name": "🎫 6. How do I contact Staff or report an issue?",
                "value": "Visit <#1555641079137706014> and click **[Open Ticket]** to start an encrypted private support thread with our moderators.",
                "inline": False,
            },
        ],
        "color": 0x9333EA,  # Royal Purple
        "footer": {
            "text": "✦ RAI FAM ┆ Interactive Knowledge Base • Updated 24/7 ✦"
        },
    }

    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 3,  # Success
                    "label": "Verify Access",
                    "custom_id": "rt_wel:verify",
                    "emoji": {"name": "✨"},
                },
                {
                    "type": 2,
                    "style": 1,  # Primary
                    "label": "Role Picker",
                    "custom_id": "rt_wel:roles",
                    "emoji": {"name": "🌸"},
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary
                    "label": "Read Rules",
                    "custom_id": "rt_wel:rules",
                    "emoji": {"name": "📜"},
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary
                    "label": "Support Desk",
                    "custom_id": "ticket_open_general",
                    "emoji": {"name": "🎫"},
                },
            ],
        }
    ]

    async with aiohttp.ClientSession() as session:
        async with session.patch(
            f"https://discord.com/api/v10/channels/{CH_FAQ}/messages/{TARGET_MSG_ID}",
            headers=headers,
            json={"embeds": [embed], "components": components},
        ) as r:
            if r.status == 200:
                print("✅ Updated #server-faq with interactive buttons and luxury guide!")
            else:
                err = await r.text()
                print(f"⚠️ Error updating #server-faq: {r.status} - {err}")

if __name__ == "__main__":
    asyncio.run(main())
