import asyncio
import os
import aiohttp
import unicodedata
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
            for role in roles:
                name = role['name']
                if "\u254f" in name or "\u2506" in name:
                    print("ROLE:", repr(name))
                    sep = "\u254f" if "\u254f" in name else "\u2506"
                    parts = name.split(sep)
                    if len(parts) == 2:
                        content = parts[1].strip()
                        print("  CONTENT:", repr(content))
                        for idx, char in enumerate(content):
                            print(f"    [{idx}] {repr(char)}: {hex(ord(char))} ({unicodedata.name(char, 'UNKNOWN')})")

if __name__ == "__main__":
    asyncio.run(main())
