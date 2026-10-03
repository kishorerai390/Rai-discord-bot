import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "f:/Bot")

import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_GUILD_ID = 1457382179981099090

# Target legacy categories to remove
TARGET_CATEGORIES = [
    (1552374826423943188, "🎭 ┃ 𝙋𝙀𝙍𝙎𝙊𝙉𝘼𝙇 𝙎𝙐𝙄𝙏𝙀𝙎"),
    (1550186724137640006, "🔊 ┃ 𝙑𝙊𝙄𝘾𝙀 𝙇𝙊𝙐𝙉𝙂𝙀𝙎"),
    (1553071868234170428, "🎵 ┃ 𝙑𝙄𝘽𝙀 𝙎𝙏𝙐𝘿𝙄𝙊"),
    (1553071866040688841, "⚡ ┃ 𝙎𝙌𝙐𝘼𝘿 𝘼𝙍𝙀𝙉𝘼"),
    (1554170417634086922, "🔎 ┃ 𝙀𝙎𝙋𝙊𝙍𝙏𝙎 𝘾𝙃𝙀𝘾𝙆𝙄𝙉𝙂"),
    (1553069011045060759, "📡 ┃ 𝙇𝙄𝙑𝙀 𝙎𝙏𝘼𝙂𝙀"),
]

TARGET_CAT_IDS = {str(cat_id) for cat_id, _ in TARGET_CATEGORIES}

async def delete_legacy():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        # 1. Fetch current channels
        async with session.get(f"https://discord.com/api/v10/guilds/{TARGET_GUILD_ID}/channels", headers=headers) as resp:
            if resp.status != 200:
                print(f"Error fetching channels: {resp.status}")
                return
            channels = await resp.json()

        # Find child channels belonging to target categories
        child_channels = [c for c in channels if c.get("parent_id") in TARGET_CAT_IDS]
        categories_to_delete = [c for c in channels if c.get("id") in TARGET_CAT_IDS]

        print(f"Found {len(child_channels)} child channels and {len(categories_to_delete)} categories to clean up.")

        # 2. Delete child channels first
        deleted_children = 0
        for ch in child_channels:
            ch_id = ch.get("id")
            ch_name = ch.get("name")
            async with session.delete(f"https://discord.com/api/v10/channels/{ch_id}", headers=headers) as r:
                if r.status in (200, 204):
                    print(f"  🗑️ Deleted channel: '{ch_name}' (ID: {ch_id})")
                    deleted_children += 1
                else:
                    print(f"  ⚠️ Failed to delete '{ch_name}': HTTP {r.status}")
            await asyncio.sleep(0.4)

        # 3. Delete parent categories
        deleted_cats = 0
        for cat in categories_to_delete:
            cat_id = cat.get("id")
            cat_name = cat.get("name")
            async with session.delete(f"https://discord.com/api/v10/channels/{cat_id}", headers=headers) as r:
                if r.status in (200, 204):
                    print(f"  📁 Deleted category: '{cat_name}' (ID: {cat_id})")
                    deleted_cats += 1
                else:
                    print(f"  ⚠️ Failed to delete category '{cat_name}': HTTP {r.status}")
            await asyncio.sleep(0.4)

        print("\n" + "=" * 50)
        print(f"Cleanup Complete: Removed {deleted_children} channels and {deleted_cats} categories.")
        print("=" * 50)

if __name__ == "__main__":
    asyncio.run(delete_legacy())
