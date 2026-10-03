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

    print(f"Total current channels: {len(channels)}")
    for cat in categories:
        cat_id = cat.get("id")
        cat_channels = [c for c in channels if c.get("parent_id") == cat_id]
        print(f"\n📁 Category '{cat.get('name')}' (ID: {cat_id}) - {len(cat_channels)} channels")
        for ch in cat_channels:
            print(f"   • [{ch.get('type')}] '{ch.get('name')}' (ID: {ch.get('id')})")

if __name__ == "__main__":
    asyncio.run(inspect())
