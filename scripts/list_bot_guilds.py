import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
token = os.getenv("DISCORD_TOKEN")

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession(headers=headers) as s:
        async with s.get("https://discord.com/api/v10/users/@me/guilds") as r:
            guilds = await r.json()
            print(f"Bot is in {len(guilds)} guilds:")
            for g in guilds:
                print(f"  {g['id']} | {g['name']}")

if __name__ == "__main__":
    asyncio.run(main())
