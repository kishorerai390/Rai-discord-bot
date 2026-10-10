"""
List all non-managed roles in the server with their position, color, and name.
"""
import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
HEADERS = {"Authorization": f"Bot {TOKEN}"}


async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as r:
            roles = await r.json()
            roles.sort(key=lambda x: x["position"], reverse=True)
            for r in roles:
                if not r.get("managed", False) and r["name"] != "@everyone":
                    hex_color = f"#{r['color']:06X}" if r["color"] else "None"
                    print(f"Pos {r['position']:02d} | ID: {r['id']} | Color: {hex_color} | {r['name']}")


if __name__ == "__main__":
    asyncio.run(main())
