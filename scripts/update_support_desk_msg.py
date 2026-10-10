import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
CH_TICKETS = 1555641079137706014
TARGET_MSG_ID = 1558266440627519492

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    embed = {
        "title": "🎟️ ✦ RAI FAM ┆ VIP SUPPORT & CONCIERGE ✦",
        "description": (
            "Need private assistance with server permissions, role inquiries, partnerships, or reporting an incident?\n\n"
            "Click **[Open Ticket]** below to spawn an encrypted private support channel with our senior staff.\n"
            "When resolved, you receive a full dark-mode HTML transcript directly in your DMs!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "fields": [
            {
                "name": "⏱️ Average Staff Response",
                "value": "`< 5 Minutes • Real-Time Alert Dispatch`",
                "inline": True,
            },
            {
                "name": "🔒 Security & Confidentiality",
                "value": "`Strict Staff Isolation • Auto DM Transcript`",
                "inline": True,
            },
            {
                "name": "📋 Supported Categories",
                "value": "• General Help & Inquiries\n• Report Rule Breakers / Scams\n• Creator & Collab Partnerships\n• Billing / Nitro / Tier Inquiries",
                "inline": False,
            },
        ],
        "color": 0x9333EA,  # Royal Purple
        "footer": {
            "text": "✦ RAI FAM ┆ Automated Dispatch • Available 24/7 ✦"
        },
    }

    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,  # Primary
                    "label": "Open Ticket",
                    "custom_id": "ticket_open_general",
                    "emoji": {"name": "🎟️"},
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary
                    "label": "Rate Support (CSAT)",
                    "custom_id": "rt_tkt:csat",
                    "emoji": {"name": "⭐"},
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary
                    "label": "Support FAQ",
                    "custom_id": "rt_tkt:faq",
                    "emoji": {"name": "❓"},
                },
            ],
        }
    ]

    async with aiohttp.ClientSession() as session:
        async with session.patch(
            f"https://discord.com/api/v10/channels/{CH_TICKETS}/messages/{TARGET_MSG_ID}",
            headers=headers,
            json={"embeds": [embed], "components": components},
        ) as r:
            if r.status == 200:
                print("✅ Updated #support-desk with polished luxury console!")
            else:
                err = await r.text()
                print(f"⚠️ Error updating #support-desk: {r.status} - {err}")

if __name__ == "__main__":
    asyncio.run(main())
