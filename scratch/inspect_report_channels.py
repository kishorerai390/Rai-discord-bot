import asyncio
import os
import aiohttp
import sys
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
sys.stdout.reconfigure(encoding='utf-8')

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get("https://discord.com/api/v10/guilds/1457382179981099090/channels") as resp:
            channels = await resp.json()
            for c in channels:
                if c.get("parent_id") == "1558682539491598438":
                    print(f"{c['id']} | {c['name']}")

if __name__ == "__main__":
    asyncio.run(main())
