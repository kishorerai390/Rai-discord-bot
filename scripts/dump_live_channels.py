import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {"Authorization": f"Bot {TOKEN}"}

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()

    lines = []
    categories = {c["id"]: c["name"] for c in channels if c.get("type") == 4}
    for c in channels:
        pid = c.get("parent_id")
        pname = categories.get(pid, "None")
        lines.append(f"{c['id']} | type={c.get('type')} | parent={pname} ({pid}) | {c.get('name')}")

    with open("data/current_live_channels.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Total live channels: {len(channels)}")

if __name__ == "__main__":
    asyncio.run(main())
