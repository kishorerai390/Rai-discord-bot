import asyncio
import os
import aiohttp
import json
import sys
sys.path.insert(0, "F:/Bot")
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
VERIFY_CHANNEL_ID = 1545502700840427702
WELCOME_CHANNEL_ID = 1545502705643167876
RULES_CHANNEL_ID = 1545502710101704714
ROLES_CHANNEL_ID = 1545502722739150898
VERIFIED_ROLE_ID = 1549504522953695269
COMMUNITY_ROLE_ID = 1545494584203673740

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }
    
    # Update SQLite config first
    from database.database import Database
    db = Database("F:/Bot/sentinel.db")
    await db.connect()
    await db.update_verification_config(
        GUILD_ID,
        enabled=True,
        role_id=VERIFIED_ROLE_ID,
        channel_id=VERIFY_CHANNEL_ID,
        min_account_age_hours=0,
    )
    print("Verification config updated in SQLite sentinel.db!")
    await db.close()

    embed = {
        "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓥ᴇʀɪғɪᴄᴀᴛɪᴏɴ 𝕲ᴀᴛᴇ ✦",
        "description": (
            "Welcome to **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦** — the sanctuary for gaming, "
            "chill vibes, and automated community experiences.\n\n"
            "To safeguard our community against automated raid bots, spam, and malicious accounts, "
            "all incoming members must pass the **Rai Security Gate** before accessing channels."
        ),
        "color": 3066993,  # Emerald luxury green (0x2ECC71)
        "fields": [
            {
                "name": "📜 ╏ Server Guidelines",
                "value": (
                    "• Treat all members and staff with respect.\n"
                    "• Zero tolerance for hate speech, toxicity, or raids.\n"
                    "• No unsolicited DM advertising or phishing links.\n"
                    f"• Full guidelines detailed in <#{RULES_CHANNEL_ID}>."
                ),
                "inline": False,
            },
            {
                "name": "✨ ╏ Clearance Perks",
                "value": (
                    "Upon verification, you will automatically unlock:\n"
                    f"• <@&{VERIFIED_ROLE_ID}> — Verified clearance badge\n"
                    f"• <@&{COMMUNITY_ROLE_ID}> — Full access to community lounges\n"
                    f"• Voice lounges, game pings (<#{ROLES_CHANNEL_ID}>), & bot commands!"
                ),
                "inline": False,
            },
        ],
        "footer": {
            "text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Security Engine • Instant Verification ✦"
        },
    }

    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 3,  # Success (Green)
                    "label": "Verify & Enter Server",
                    "custom_id": "rai_verification_button",
                    "emoji": {"name": "✨"},
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary (Gray)
                    "label": "Server Rules",
                    "custom_id": "rai_verification_rules",
                    "emoji": {"name": "📜"},
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary (Gray)
                    "label": "Help & Support",
                    "custom_id": "rai_verification_help",
                    "emoji": {"name": "❓"},
                },
            ],
        }
    ]

    payload = {
        "content": "",
        "embeds": [embed],
        "components": components,
    }

    async with aiohttp.ClientSession() as session:
        # Check existing messages in channel
        async with session.get(f"https://discord.com/api/v10/channels/{VERIFY_CHANNEL_ID}/messages?limit=10", headers=headers) as r:
            messages = await r.json()
        
        target_msg_id = None
        if isinstance(messages, list):
            for m in messages:
                # If author is bot, we can edit
                if m.get("author", {}).get("bot"):
                    target_msg_id = m["id"]
                    break

        if target_msg_id:
            print(f"Editing existing message {target_msg_id} in #{VERIFY_CHANNEL_ID}...")
            async with session.patch(f"https://discord.com/api/v10/channels/{VERIFY_CHANNEL_ID}/messages/{target_msg_id}", headers=headers, json=payload) as r:
                res = await r.json()
                print("Edit result status:", r.status)
        else:
            print(f"Posting new message to #{VERIFY_CHANNEL_ID}...")
            async with session.post(f"https://discord.com/api/v10/channels/{VERIFY_CHANNEL_ID}/messages", headers=headers, json=payload) as r:
                res = await r.json()
                print("Post result status:", r.status)

if __name__ == "__main__":
    asyncio.run(main())
