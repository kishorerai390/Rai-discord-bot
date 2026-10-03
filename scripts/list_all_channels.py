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
            channels.sort(key=lambda x: (x.get("parent_id") or "0", x.get("position", 0)))
            for ch in channels:
                print(f"{ch['id']} | type={ch['type']} | parent={ch.get('parent_id')} | {ascii(ch['name'])}")

if __name__ == "__main__":
    asyncio.run(main())
