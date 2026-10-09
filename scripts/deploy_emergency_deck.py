import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "F:/Bot")

import aiohttp
from dotenv import load_dotenv
from utils.community_features import build_staff_rapid_mod_embed, build_staff_rapid_mod_view

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
ADMIN_CHANNEL_ID = 1555283409465778218

def view_to_action_rows(view):
    rows = []
    current_buttons = []
    for item in view.children:
        comp_dict = item.to_component_dict()
        current_buttons.append(comp_dict)
        if len(current_buttons) == 5:
            rows.append({"type": 1, "components": current_buttons})
            current_buttons = []
    if current_buttons:
        rows.append({"type": 1, "components": current_buttons})
    return rows

async def main():
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        # Purge existing messages in #admin-control
        async with s.get(f"https://discord.com/api/v10/channels/{ADMIN_CHANNEL_ID}/messages?limit=50", headers=headers) as r:
            if r.status == 200:
                msgs = await r.json()
                for m in msgs:
                    await s.delete(f"https://discord.com/api/v10/channels/{ADMIN_CHANNEL_ID}/messages/{m['id']}", headers=headers)
                    await asyncio.sleep(0.3)

        mock_guild = type("MockGuild", (), {
            "name": "✦ Rai Fam ✦",
            "id": GUILD_ID,
            "icon": type("Icon", (), {"url": None})()
        })()

        embed = build_staff_rapid_mod_embed(mock_guild)
        view = build_staff_rapid_mod_view()

        payload = {
            "embeds": [embed.to_dict()],
            "components": view_to_action_rows(view)
        }

        async with s.post(f"https://discord.com/api/v10/channels/{ADMIN_CHANNEL_ID}/messages", headers=headers, json=payload) as pr:
            if pr.status in (200, 201):
                res = await pr.json()
                msg_id = res["id"]
                # Pin console
                await s.put(f"https://discord.com/api/v10/channels/{ADMIN_CHANNEL_ID}/pins/{msg_id}", headers=headers)
                print("✅ Successfully deployed and pinned updated Staff Rapid-Mod Deck with Emergency Lockdown buttons!")
            else:
                txt = await pr.text()
                print(f"❌ Failed to post: {pr.status} - {txt}")

if __name__ == "__main__":
    asyncio.run(main())
