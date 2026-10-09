import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
CH_ROLES = 1545502722739150898
TARGET_MSG_ID = "1557467800673591389"

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    embed = {
        "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓞ғғɪᴄɪᴀʟ 𝕾ᴇʀᴠᴇʀ 𝕽ᴏʟᴇs ✦",
        "description": (
            "Customize your server notifications, gaming squad pings, and vanity colors below.\n\n"
            "Click any button to **toggle** your roles on or off instantly!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔔 **NOTIFICATION PREFERENCES**\n"
            "• 📢 **Announcements** — Major community updates and bot announcements\n"
            "• 🎁 **Giveaways** — Discord Nitro, gift cards, and game pass alerts\n"
            "• 🏆 **Tournaments** — Competitive esports scrims and custom rooms\n\n"
            "🎮 **GAMING SQUAD PINGS**\n"
            "• 🎯 **Valorant / CS2** — Tactical FPS 5-stack and competitive lobbies\n"
            "• ⚡ **BGMI / PUBG** — Battle royale custom rooms and squad squads\n"
            "• 🔥 **Free Fire** — Clash squad and custom room pings\n\n"
            "🎨 **VANITY NAME COLORS** *(Select one)*\n"
            "• 🌸 **Rose Gold** — Soft luxury warm tone\n"
            "• 💠 **Cyber Cyan** — Electric neon cyan glow\n"
            "• 💜 **Neon Violet** — Royal amethyst purple aura\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "color": 3447003,  # 0x3498DB Neon Cyan / Blue
        "footer": {
            "text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Interactive Role Management • Instant Toggle ✦"
        },
    }

    components = [
        # Row 0: Notifications
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,  # Primary
                    "label": "Announcements",
                    "custom_id": "rai_role_opt:announcements",
                    "emoji": {"name": "📢"},
                },
                {
                    "type": 2,
                    "style": 3,  # Success
                    "label": "Giveaways",
                    "custom_id": "rai_role_opt:giveaways",
                    "emoji": {"name": "🎁"},
                },
                {
                    "type": 2,
                    "style": 4,  # Danger
                    "label": "Tournaments",
                    "custom_id": "rai_role_opt:tournaments",
                    "emoji": {"name": "🏆"},
                },
            ],
        },
        # Row 1: Gaming Squads
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 2,  # Secondary
                    "label": "Valorant / CS2",
                    "custom_id": "rai_role_opt:valorant",
                    "emoji": {"name": "🎯"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "BGMI / PUBG",
                    "custom_id": "rai_role_opt:bgmi",
                    "emoji": {"name": "⚡"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Free Fire",
                    "custom_id": "rai_role_opt:freefire",
                    "emoji": {"name": "🔥"},
                },
            ],
        },
        # Row 2: Vanity Colors
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 2,
                    "label": "Rose Gold",
                    "custom_id": "rai_role_opt:color_rose",
                    "emoji": {"name": "🌸"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Cyber Cyan",
                    "custom_id": "rai_role_opt:color_cyan",
                    "emoji": {"name": "💠"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Neon Violet",
                    "custom_id": "rai_role_opt:color_violet",
                    "emoji": {"name": "💜"},
                },
            ],
        },
    ]

    payload = {
        "content": "",
        "embeds": [embed],
        "components": components,
    }

    async with aiohttp.ClientSession() as s:
        print(f"Updating role message {TARGET_MSG_ID} in channel {CH_ROLES}...")
        async with s.patch(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages/{TARGET_MSG_ID}", headers=headers, json=payload) as pr:
            print("Update status:", pr.status)
            if pr.status != 200:
                print("Patch failed, posting fresh message...")
                async with s.post(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages", headers=headers, json=payload) as cr:
                    print("Create status:", cr.status)

if __name__ == "__main__":
    asyncio.run(main())
