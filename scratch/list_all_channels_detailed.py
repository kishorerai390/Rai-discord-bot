import asyncio
import os
import sys
from pathlib import Path
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_GUILD_ID = 1457382179981099090

async def inspect():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://discord.com/api/v10/guilds/{TARGET_GUILD_ID}/channels", headers=headers) as resp:
            channels = await resp.json()

    categories = [c for c in channels if c.get("type") == 4]
    categories.sort(key=lambda c: c.get("position", 0))

    no_parent = [c for c in channels if c.get("type") != 4 and not c.get("parent_id")]

    print(f"Total Channels: {len(channels)}")
    print(f"Total Categories: {len(categories)}")
    if no_parent:
        print(f"\nChannels without category ({len(no_parent)}):")
        for c in no_parent:
            print(f"  - [{c.get('type')}] {c.get('name')} (ID: {c.get('id')})")

    for cat in categories:
        cat_id = cat.get("id")
        cat_channels = [c for c in channels if c.get("parent_id") == cat_id]
        cat_channels.sort(key=lambda c: c.get("position", 0))
        print(f"\n📁 Category: '{cat.get('name')}' (ID: {cat_id}, Position: {cat.get('position')}) - {len(cat_channels)} channels")
        for c in cat_channels:
            type_str = "Text" if c.get("type") in (0, 5) else ("Voice" if c.get("type") == 2 else f"Type {c.get('type')}")
            print(f"    • [{type_str}] '{c.get('name')}' (ID: {c.get('id')})")

if __name__ == "__main__":
    asyncio.run(inspect())
