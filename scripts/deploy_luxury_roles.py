import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
CH_ROLES = 1545502722739150898

GAME_OPTIONS = [
    {
        "label": "Valorant / CS2",
        "value": "1551184094313062470",
        "description": "Squad pings & competitive matchmaking",
        "emoji": {"name": "🎯"},
    },
    {
        "label": "BGMI / PUBG",
        "value": "1551184098834251786",
        "description": "Battle royale squads & scrim alerts",
        "emoji": {"name": "⚡"},
    },
    {
        "label": "Free Fire",
        "value": "1551184102957523048",
        "description": "Clash squad & guild war pings",
        "emoji": {"name": "🔥"},
    },
]

NOTIF_OPTIONS = [
    {
        "label": "Announcements",
        "value": "1550199913093144649",
        "description": "Important server updates & patch notes",
        "emoji": {"name": "📢"},
    },
    {
        "label": "Giveaways",
        "value": "1550199917262143560",
        "description": "Discord Nitro, game passes & VIP perks",
        "emoji": {"name": "🎁"},
    },
    {
        "label": "Tournaments",
        "value": "1550199921007792188",
        "description": "Community esports tournaments & prize events",
        "emoji": {"name": "🏆"},
    },
]

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        # 1. Fetch existing messages in channel
        async with s.get(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages?limit=20", headers=headers) as r:
            msgs = await r.json()

        game_msg_id = None
        notif_msg_id = None

        if isinstance(msgs, list):
            for m in msgs:
                embeds = m.get("embeds", [])
                if not embeds:
                    # Delete stray empty or plain messages
                    await s.delete(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages/{m['id']}", headers=headers)
                    continue
                title = embeds[0].get("title", "")
                if "GAME" in title.upper() or "𝓖ᴀᴍɪɴɢ" in title:
                    game_msg_id = m["id"]
                elif "NOTIF" in title.upper() or "𝓝ᴏᴛɪғɪᴄᴀᴛɪᴏɴ" in title:
                    notif_msg_id = m["id"]
                elif "FOUNDER" in title.upper() or "Role: @" in title:
                    # Clean up test message
                    print(f"Deleting test message {m['id']}...")
                    await s.delete(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages/{m['id']}", headers=headers)

        game_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓖ᴀᴍɪɴɢ 𝕽ᴏʟᴇs ✦",
            "description": (
                "Select your favorite gaming titles from the dropdown below to receive squad pings, "
                "find teammates, and unlock dedicated voice arenas!\n\n"
                "• Selecting a role **adds** it to your profile.\n"
                "• Deselecting a role **removes** it automatically."
            ),
            "color": 0x3498DB,  # Vibrant Cyan / Blue
            "fields": [
                {
                    "name": "🎮 ╏ Available Squad Roles",
                    "value": (
                        "• <@&1551184094313062470>\n"
                        "• <@&1551184098834251786>\n"
                        "• <@&1551184102957523048>"
                    ),
                    "inline": False,
                }
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Self-Assignable Roles • Instant Sync ✦"},
        }

        game_payload = {
            "embeds": [game_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 3,
                            "custom_id": "rai_role_select_games",
                            "placeholder": "🎯 Choose your game titles...",
                            "min_values": 0,
                            "max_values": len(GAME_OPTIONS),
                            "options": GAME_OPTIONS,
                        }
                    ],
                }
            ],
        }

        notif_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓝ᴏᴛɪғɪᴄᴀᴛɪᴏɴ 𝕻ɪɴɢs ✦",
            "description": (
                "Never miss out on official server updates, community giveaways, or prize tournaments!\n\n"
                "• Selecting a role **adds** it to your profile.\n"
                "• Deselecting a role **removes** it automatically."
            ),
            "color": 0xE67E22,  # Vivid Warm Amber
            "fields": [
                {
                    "name": "🔔 ╏ Available Alerts",
                    "value": (
                        "• <@&1550199913093144649>\n"
                        "• <@&1550199917262143560>\n"
                        "• <@&1550199921007792188>"
                    ),
                    "inline": False,
                }
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Community Alerts • Toggle Anytime ✦"},
        }

        notif_payload = {
            "embeds": [notif_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 3,
                            "custom_id": "rai_role_select_notifs",
                            "placeholder": "📢 Choose notification alerts...",
                            "min_values": 0,
                            "max_values": len(NOTIF_OPTIONS),
                            "options": NOTIF_OPTIONS,
                        }
                    ],
                }
            ],
        }

        if game_msg_id:
            print(f"Updating Game Roles Panel {game_msg_id}...")
            async with s.patch(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages/{game_msg_id}", headers=headers, json=game_payload) as r:
                print("Game panel update status:", r.status)
        else:
            print("Posting new Game Roles Panel...")
            async with s.post(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages", headers=headers, json=game_payload) as r:
                print("Game panel post status:", r.status)

        await asyncio.sleep(1)

        if notif_msg_id:
            print(f"Updating Notif Roles Panel {notif_msg_id}...")
            async with s.patch(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages/{notif_msg_id}", headers=headers, json=notif_payload) as r:
                print("Notif panel update status:", r.status)
        else:
            print("Posting new Notif Roles Panel...")
            async with s.post(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages", headers=headers, json=notif_payload) as r:
                print("Notif panel post status:", r.status)

if __name__ == "__main__":
    asyncio.run(main())
