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

        with open("F:/Bot/scripts/server_hierarchy.txt", "w", encoding="utf-8") as f:
            for cat in categories:
                f.write(f"\n==========================================\n")
                f.write(f"CATEGORY Pos {cat.get('position', 0)}: [{cat['id']}] {cat['name']}\n")
                f.write(f"==========================================\n")
                children = [c for c in channels if c.get("parent_id") == cat["id"]]
                children.sort(key=lambda x: x.get("position", 0))
                for ch in children:
                    type_name = "Text" if ch["type"] == 0 else ("Voice" if ch["type"] == 2 else ("Announcement" if ch["type"] == 5 else f"Type {ch['type']}"))
                    f.write(f"  Pos {ch.get('position', 0):2d} | [{ch['id']}] ({type_name:12s}) {ch['name']}\n")
        print("Hierarchy written to scripts/server_hierarchy.txt successfully.")

if __name__ == "__main__":
    asyncio.run(main())
