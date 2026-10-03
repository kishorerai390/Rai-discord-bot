"""
Deploy community feature consoles into target channels:
1. #🌸・WELCOME (1545502705643167876)
2. #📸・MEDIA-AND-CLIPS (1551184138932068373)
3. #🤖・BOT-COMMANDS (1549416359723532480)
4. #👑・ADMIN-CONTROL (1555283409465778218)
5. #🛠️・ROOM-CONTROL (1555459478155960421)
"""

import asyncio
import os
import sys

sys.path.insert(0, "F:/Bot")

import aiohttp
import discord
from dotenv import load_dotenv

from utils.community_features import (
    build_welcome_hub_embed,
    build_welcome_hub_view,
    build_media_showcase_embed,
    build_media_showcase_view,
    build_command_catalog_embed,
    build_command_catalog_view,
    build_staff_rapid_mod_embed,
    build_staff_rapid_mod_view,
    build_room_theme_embed,
    build_room_theme_view,
)

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

def view_to_action_rows(view: discord.ui.View):
    rows = []
    current_row = []
    for item in view.children:
        current_row.append(item.to_component_dict())
        if len(current_row) == 5:
            rows.append({"type": 1, "components": current_row})
            current_row = []
    if current_row:
        rows.append({"type": 1, "components": current_row})
    return rows

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}?with_counts=true", headers=headers) as r:
            guild_data = await r.json()

        class MockGuild:
            name = guild_data.get("name", "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦")
            id = GUILD_ID
            icon = type("MockIcon", (), {"url": f"https://cdn.discordapp.com/icons/{GUILD_ID}/{guild_data.get('icon')}.png" if guild_data.get("icon") else None})()

        mock_guild = MockGuild()

        deployments = [
            ("Welcome & Quick-Start Hub", 1545502705643167876, build_welcome_hub_embed(mock_guild), build_welcome_hub_view()),
            ("Media Showcase & Clip Spotlight", 1551184138932068373, build_media_showcase_embed(mock_guild), build_media_showcase_view()),
            ("Interactive Command Catalog", 1549416359723532480, build_command_catalog_embed(mock_guild), build_command_catalog_view()),
            ("Staff Rapid-Moderation Deck", 1555283409465778218, build_staff_rapid_mod_embed(mock_guild), build_staff_rapid_mod_view()),
            ("Room Theme & Mood Styler", 1555459478155960421, build_room_theme_embed(mock_guild), build_room_theme_view()),
        ]

        for title, channel_id, embed, view in deployments:
            payload = {
                "embeds": [embed.to_dict()],
                "components": view_to_action_rows(view),
            }
            async with s.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", headers=headers, json=payload) as r:
                res = await r.json()
                if r.status in (200, 201):
                    msg_id = res.get("id")
                    print(f"[SUCCESS] {title} deployed to channel {channel_id} (Msg ID: {msg_id})")
                    # Pin message
                    async with s.put(f"https://discord.com/api/v10/channels/{channel_id}/pins/{msg_id}", headers=headers) as pr:
                        print(f"  Pinned in channel {channel_id}: {pr.status}")
                else:
                    print(f"[ERROR] Failed {title}: {r.status} {res}")
            await asyncio.sleep(1.0)

        print("Community consoles deployment complete.")

if __name__ == "__main__":
    asyncio.run(main())
