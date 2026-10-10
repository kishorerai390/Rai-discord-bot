import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
BOT_ID = "1554732669072445532"

HEADERS = {"Authorization": f"Bot {TOKEN}"}

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{BOT_ID}", headers=HEADERS) as r:
            if r.status == 200:
                m = await r.json()
                print("Bot Roles:", m.get("roles"))
            else:
                print("Failed to get bot member:", r.status, await r.text())

        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as r:
            roles = await r.json()
            r_map = {r["id"]: r["name"] for r in roles}

        for rid in m.get("roles", []):
            print(ascii(f"Role: {r_map.get(rid, rid)} ({rid})"))

if __name__ == "__main__":
    asyncio.run(main())
