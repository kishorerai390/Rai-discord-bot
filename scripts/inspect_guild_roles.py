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
        async with s.get("https://discord.com/api/v10/guilds/1457382179981099090/roles") as r:
            roles = await r.json()
            roles.sort(key=lambda x: x.get("position", 0), reverse=True)
            for role in roles:
                print(f"{role['position']:2d} | {role['id']} | {role['name']}")

if __name__ == "__main__":
    asyncio.run(main())
