"""
Deploy luxury consoles via direct Discord REST API.
"""

import asyncio
import os
import sys

sys.path.insert(0, "F:/Bot")

import aiohttp
import discord
from dotenv import load_dotenv

from utils.luxury_consoles import (
    build_server_pulse_embed,
    build_server_pulse_view,
    build_world_clock_embed,
    build_world_clock_view,
    build_vip_concierge_embed,
    build_vip_concierge_view,
    build_quarantine_vault_embed,
    build_quarantine_vault_view,
    build_soundscape_embed,
    build_soundscape_view,
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
        # Fetch guild data
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}?with_counts=true", headers=headers) as r:
            guild_data = await r.json()

        # Mock a minimal guild object for embed building
        class MockGuild:
            name = guild_data.get("name", "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦")
            id = GUILD_ID
            member_count = guild_data.get("approximate_member_count", 39)
            members = []
            icon = type("MockIcon", (), {"url": f"https://cdn.discordapp.com/icons/{GUILD_ID}/{guild_data.get('icon')}.png" if guild_data.get("icon") else None})()

        mock_guild = MockGuild()

        deployments = [
            ("Server Pulse & Live Radar", 1555283414205075509, build_server_pulse_embed(mock_guild), build_server_pulse_view()),
            ("World Clock & Event Schedule", 1545502718792175646, build_world_clock_embed(mock_guild), build_world_clock_view()),
            ("VIP & Booster Concierge", 1545502722739150898, build_vip_concierge_embed(mock_guild), build_vip_concierge_view()),
            ("Zero-Trust Quarantine Vault", 1555283378612478072, build_quarantine_vault_embed(mock_guild), build_quarantine_vault_view()),
            ("Soundscape Studio & Focus Pods", 1555641081578782840, build_soundscape_embed(mock_guild), build_soundscape_view()),
        ]

        for title, channel_id, embed, view in deployments:
            payload = {
                "embeds": [embed.to_dict()],
                "components": view_to_action_rows(view),
            }
            async with s.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", headers=headers, json=payload) as r:
                res = await r.json()
                if r.status in (200, 201):
                    print(f"[SUCCESS] {title} deployed to channel {channel_id} (Msg ID: {res.get('id')})")
                else:
                    print(f"[ERROR] Failed {title}: {r.status} {res}")
            await asyncio.sleep(1.0)

        print("REST deployment process finished.")

if __name__ == "__main__":
    asyncio.run(main())
