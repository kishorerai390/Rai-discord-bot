import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
CH_ROLES = 1545502722739150898
TARGET_MSG_ID = 1557467800673591389

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    embed = {
        "title": "✦ RAI FAM ┆ OFFICIAL ROLE SELECTION ✦",
        "description": (
            "Customize your server notifications, gaming squad pings, and vanity colors below.\n\n"
            "Click any button to **toggle** your roles on or off instantly!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔔 **NOTIFICATION PREFERENCES**\n"
            "• 📢 **Announcements** — Major community updates & event pings\n"
            "• 🎁 **Giveaways** — Discord Nitro, gift cards & game pass alerts\n"
            "• 🏆 **Tournaments** — Competitive esports scrims & custom lobbies\n\n"
            "🎮 **GAMING SQUAD PINGS**\n"
            "• 🎯 **Valorant / CS2** — Tactical FPS 5-stack & ranked comms\n"
            "• ⚡ **BGMI / PUBG** — Battle royale custom rooms & squad squads\n"
            "• 🔥 **Free Fire** — Clash squad & custom room pings\n\n"
            "🎨 **VANITY NAME COLORS** *(Mutually exclusive)*\n"
            "• 🌸 **Rose Gold** — Soft luxury rose tone\n"
            "• 💠 **Cyber Cyan** — Electric neon cyan glow\n"
            "• 💜 **Neon Violet** — Royal amethyst purple aura\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "color": 0x9333EA,  # Royal Purple
        "footer": {
            "text": "✦ RAI FAM ┆ Instant Role Dispatch • Non-Destructive ✦"
        },
    }

    components = [
        # Row 0: Notifications
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,
                    "label": "Announcements",
                    "custom_id": "rai_role_opt:announcements",
                    "emoji": {"name": "📢"},
                },
                {
                    "type": 2,
                    "style": 3,
                    "label": "Giveaways",
                    "custom_id": "rai_role_opt:giveaways",
                    "emoji": {"name": "🎁"},
                },
                {
                    "type": 2,
                    "style": 4,
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
                    "style": 2,
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

    async with aiohttp.ClientSession() as session:
        async with session.patch(
            f"https://discord.com/api/v10/channels/{CH_ROLES}/messages/{TARGET_MSG_ID}",
            headers=headers,
            json={"embeds": [embed], "components": components},
        ) as r:
            if r.status == 200:
                print("✅ Updated #server-roles embed and buttons to luxury aesthetic!")
            else:
                err = await r.text()
                print(f"⚠️ Error updating #server-roles: {r.status} - {err}")

if __name__ == "__main__":
    asyncio.run(main())
