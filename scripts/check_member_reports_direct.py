import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
HEADERS = {"Authorization": f"Bot {TOKEN}"}

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get("https://discord.com/api/v10/channels/1558482223429058751", headers=HEADERS) as r:
            print("Status:", r.status)
            if r.status == 200:
                data = await r.json()
                print("Name:", ascii(data.get("name")))
                print("Parent:", data.get("parent_id"))
                print("Overwrites:", data.get("permission_overwrites"))
            else:
                text = await r.text()
                print("Error:", text)

if __name__ == "__main__":
    asyncio.run(main())
