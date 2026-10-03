"""
Deploy dedicated music consoles into target channels:
1. #🎼・MUSIC-REQUESTS (1555283396660428830)
2. #📜・QUEUE (1555283393242206301)
3. #🔊・DJ-CONTROL (1555283394274005092)
4. #💿・PLAYLISTS (1555283395330842714)
"""

import asyncio
import os
import sys

sys.path.insert(0, "F:/Bot")

import aiohttp
import discord
from dotenv import load_dotenv

from utils.music_consoles import (
    build_requests_console_embed,
    build_requests_console_view,
    build_queue_console_embed,
    build_queue_console_view,
    build_dj_console_embed,
    build_dj_console_view,
    build_playlists_console_embed,
    build_playlists_console_view,
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
            ("Music Request Hub", 1555283396660428830, build_requests_console_embed(mock_guild), build_requests_console_view()),
            ("Live Queue Board", 1555283393242206301, build_queue_console_embed(mock_guild, None), build_queue_console_view()),
            ("DJ Studio & Audio EQ", 1555283394274005092, build_dj_console_embed(mock_guild), build_dj_console_view()),
            ("Curated Playlists & Import Hub", 1555283395330842714, build_playlists_console_embed(mock_guild), build_playlists_console_view()),
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

        print("Music consoles deployment complete.")

if __name__ == "__main__":
    asyncio.run(main())
