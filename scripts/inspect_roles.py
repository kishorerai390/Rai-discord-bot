import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

async def main():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers) as r:
            roles = await r.json()
            roles.sort(key=lambda x: x.get("position", 0), reverse=True)
            print(f"Total roles: {len(roles)}")
            for role in roles:
                print(f"Role: {ascii(role['name'])} (ID: {role['id']}, pos: {role['position']})")

if __name__ == "__main__":
    asyncio.run(main())
