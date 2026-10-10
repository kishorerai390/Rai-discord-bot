"""
Script to:
1. Delete the Blue Seal anti-nuke log message (1558534909369385051) from #welcome.
2. Deny Send Messages to Blue Seal in #welcome to prevent any future rogue bot logs there.
3. Repost the full, pristine Welcome message with interactive role buttons at the bottom of #welcome.
"""

import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
WELCOME_ID = 1545502705643167876
BLUE_SEAL_BOT_ID = 1477618724533043293
BLUE_SEAL_ROLE_ID = 1550547059009130588

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

BLUE_LOG_MSG_ID = 1558534909369385051


async def main():
    print("🚀 Cleaning #welcome channel and protecting it...")

    async with aiohttp.ClientSession() as session:
        # 1. Delete the Blue Seal Anti-Nuke message
        print(f"🗑️ Deleting Blue Logs message ({BLUE_LOG_MSG_ID}) from #welcome...")
        async with session.delete(
            f"https://discord.com/api/v10/channels/{WELCOME_ID}/messages/{BLUE_LOG_MSG_ID}",
            headers=HEADERS,
        ) as dr:
            if dr.status in (200, 204):
                print("  ✅ Successfully deleted Blue Logs message from #welcome!")
            else:
                err = await dr.text()
                print(f"  ⚠️ Note on deleting message: {dr.status} - {err}")

        await asyncio.sleep(0.5)

        # 2. Block Blue Seal from sending messages in #welcome
        print("🛡️ Restricting Blue Seal from posting in #welcome...")
        # Overwrite on channel for Blue Seal role or member: deny SEND_MESSAGES (1 << 11)
        async with session.put(
            f"https://discord.com/api/v10/channels/{WELCOME_ID}/permissions/{BLUE_SEAL_BOT_ID}",
            headers=HEADERS,
            json={
                "type": 1,  # Member
                "deny": str(1 << 11),  # Deny SEND_MESSAGES
                "allow": "0",
            },
        ) as pr:
            if pr.status in (200, 204):
                print("  ✅ Blue Seal successfully blocked from sending messages in #welcome!")
            else:
                err = await pr.text()
                print(f"  ⚠️ Permission update note: {pr.status} - {err}")

        await asyncio.sleep(0.5)

        # 3. Repost the clean luxury Welcome Embed with role buttons
        print("🌸 Reposting pristine Welcome Card with interactive role buttons...")
        welcome_embed = {
            "title": "✦ 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐓𝐎 𝐑𝐀𝐈 𝐅𝐀𝐌 ✦",
            "description": (
                "```asciidoc\n"
                "=== THE OFFICIAL RAI COMMUNITY REALM ===\n"
                "```\n"
                "👑 **Welcome to the home of RAI FAM!**\n"
                "A premium black-and-purple community for gaming squads, music lovers, and creative editors.\n\n"
                "**✦ QUICK ONBOARDING GUIDE:**\n"
                "• **1.** Read server guidelines in <#1545502710101704714>\n"
                "• **2.** Click the buttons below to claim your interest roles\n"
                "• **3.** Say hello and introduce yourself in <#1545502730699808768>\n"
                "• **4.** Chill to 24/7 lo-fi and high-fidelity music in <#1555255325706424412>\n\n"
                "🔗 **Official Invite Link:** `https://discord.gg/uW4vTv2H`"
            ),
            "color": 0x7C3AED,  # Royal Purple
            "thumbnail": {
                "url": "https://cdn.discordapp.com/icons/1457382179981099090/a_icon.gif"
            },
            "footer": {
                "text": "RAI FAM Ecosystem • Founded by rf.rai_006",
            },
        }

        buttons_payload = {
            "embeds": [welcome_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {"type": 2, "style": 1, "label": "Gamer", "emoji": {"name": "🎮"}, "custom_id": "role_toggle:gamer"},
                        {"type": 2, "style": 1, "label": "Music Lover", "emoji": {"name": "🎧"}, "custom_id": "role_toggle:music_lover"},
                        {"type": 2, "style": 1, "label": "Editor", "emoji": {"name": "🎨"}, "custom_id": "role_toggle:editor"},
                    ]
                }
            ]
        }

        async with session.post(
            f"https://discord.com/api/v10/channels/{WELCOME_ID}/messages",
            headers=HEADERS,
            json=buttons_payload,
        ) as wr:
            if wr.status in (200, 201):
                print("  ✅ Pristine Welcome Card reposted at bottom of #welcome successfully!")
            else:
                err = await wr.text()
                print(f"  ⚠️ Repost note: {wr.status} - {err}")

    print("\n🎉 #welcome is now completely pristine, beautiful, and protected!")


if __name__ == "__main__":
    asyncio.run(main())
