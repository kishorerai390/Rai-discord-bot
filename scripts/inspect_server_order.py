import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
token = os.getenv("DISCORD_TOKEN")
guild_id = 1457382179981099090

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers) as r:
            channels = await r.json()

        categories = [c for c in channels if c["type"] == 4]
        categories.sort(key=lambda x: x.get("position", 0))

        uncategorized = [c for c in channels if c["type"] != 4 and not c.get("parent_id")]
        uncategorized.sort(key=lambda x: x.get("position", 0))

        print("=== UNCATEGORIZED CHANNELS ===")
        for c in uncategorized:
            print(f"  Pos {c.get('position', 0)}: {c['id']} | type {c['type']} | {ascii(c['name'])}")

        print("=== ALL CATEGORIES ORDER ===")
        for cat in categories:
            children = [c for c in channels if c.get("parent_id") == cat["id"]]
            print(f"Cat Pos {cat.get('position', 0)}: [{cat['id']}] {ascii(cat['name'])} ({len(children)} channels)")

if __name__ == "__main__":
    asyncio.run(main())
