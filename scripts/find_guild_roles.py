import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
token = os.getenv("DISCORD_TOKEN")

guild_ids = [
    "1457382179981099090",
    "1494692962041467005",
    "1516486851387588640",
    "1545715275062575175",
    "1552400206811631687",
]

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession(headers=headers) as s:
        for gid in guild_ids:
            async with s.get(f"https://discord.com/api/v10/guilds/{gid}") as r:
                gdata = await r.json()
                gname = gdata.get("name", "Unknown")
            async with s.get(f"https://discord.com/api/v10/guilds/{gid}/roles") as r:
                roles = await r.json()
                matching = [r['name'] for r in roles if any(k in r['name'].lower() for k in ['male', 'pc.player', 'gamer', 'roblox'])]
                if matching:
                    print(f"Guild {gid} ({gname}) has matching roles: {matching}")

if __name__ == "__main__":
    asyncio.run(main())
