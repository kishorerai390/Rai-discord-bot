import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers) as r:
            roles = await r.json()
            print(f"Total roles: {len(roles)}")
            for role in roles:
                print(f"  Role: {role.get('name')} (ID: {role.get('id')})")

if __name__ == "__main__":
    asyncio.run(main())
