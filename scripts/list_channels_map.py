import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
HEADERS = {"Authorization": f"Bot {TOKEN}"}

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()

    cats = {c["id"]: c["name"] for c in channels if c.get("type") == 4}
    for c in channels:
        t = "Cat" if c["type"] == 4 else ("VC" if c["type"] == 2 else "Text")
        pname = cats.get(c.get("parent_id"), "Root")
        print(ascii(f"{c['id']} | {t:4s} | {pname:25s} | {c.get('name')}"))

if __name__ == "__main__":
    asyncio.run(main())
