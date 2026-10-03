import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
CH_RULES = 1545502710101704714
ROLES_CHANNEL_ID = 1545502722739150898
OLD_MSG_TO_DELETE = "1554820859087028236"
TARGET_MSG_TO_UPDATE = "1554837570461106297"

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    embed = {
        "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓞ғғɪᴄɪᴀʟ 𝕾ᴇʀᴠᴇʀ 𝕲ᴜɪᴅᴇ & 𝕽ᴜʟᴇs ✦",
        "description": (
            "Welcome to the official constitution and server handbook of **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
            "Our community is dedicated to providing an elite, welcoming environment for gaming, "
            "music, and genuine friendships. To protect this atmosphere, all members must uphold "
            "the standards set below.\n\n"
            "👇 **Explore Our Guidelines:** Click any category button below to view detailed guidelines, "
            "voice lounge etiquette, safety policies, and member perks."
        ),
        "color": 10181046,  # 0x9B59B6 Royal Amethyst
        "fields": [
            {
                "name": "📜 ╏ Category 1: General Conduct",
                "value": "Mutual respect, zero harassment, no toxic behavior, and strict SFW policy.",
                "inline": False,
            },
            {
                "name": "🎙️ ╏ Category 2: Voice & Music Lounges",
                "value": "Clean audio etiquette, respect for dynamic room owners, and fair DJ queue rotation.",
                "inline": False,
            },
            {
                "name": "🛡️ ╏ Category 3: Security & Anti-Raid",
                "value": "Autonomous anti-raid active 24/7. Strict ban on phishing links, unsolicited DMs, and bot alts.",
                "inline": False,
            },
            {
                "name": "💎 ╏ Category 4: VIP & Server Perks",
                "value": f"Unlock custom roles in <#{ROLES_CHANNEL_ID}>, private room creation, and booster privileges.",
                "inline": False,
            },
        ],
        "footer": {
            "text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Governance • Click a tab below ✦"
        },
    }

    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 2,  # Secondary
                    "label": "General Conduct",
                    "custom_id": "rai_rules_tab:general",
                    "emoji": {"name": "📜"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Voice & Lounges",
                    "custom_id": "rai_rules_tab:voice",
                    "emoji": {"name": "🎙️"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Security Policy",
                    "custom_id": "rai_rules_tab:security",
                    "emoji": {"name": "🛡️"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Server Perks",
                    "custom_id": "rai_rules_tab:perks",
                    "emoji": {"name": "💎"},
                },
            ],
        },
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 3,  # Success
                    "label": "I Acknowledge the Guidelines",
                    "custom_id": "rai_rules_acknowledge",
                    "emoji": {"name": "✅"},
                }
            ],
        },
    ]

    payload = {
        "content": "",
        "embeds": [embed],
        "components": components,
    }

    async with aiohttp.ClientSession() as s:
        # Delete old duplicate message
        try:
            print(f"Deleting older duplicate message {OLD_MSG_TO_DELETE}...")
            async with s.delete(f"https://discord.com/api/v10/channels/{CH_RULES}/messages/{OLD_MSG_TO_DELETE}", headers=headers) as dr:
                print("Delete status:", dr.status)
        except Exception as e:
            print("Delete error:", e)

        await asyncio.sleep(1)

        # Update target message
        print(f"Updating message {TARGET_MSG_TO_UPDATE} with interactive console...")
        async with s.patch(f"https://discord.com/api/v10/channels/{CH_RULES}/messages/{TARGET_MSG_TO_UPDATE}", headers=headers, json=payload) as pr:
            print("Update status:", pr.status)
            if pr.status != 200:
                # If editing failed, post fresh message
                print("Posting new interactive message...")
                async with s.post(f"https://discord.com/api/v10/channels/{CH_RULES}/messages", headers=headers, json=payload) as cr:
                    print("Create status:", cr.status)

if __name__ == "__main__":
    asyncio.run(main())
