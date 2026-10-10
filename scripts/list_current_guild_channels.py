import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "F:/Bot")
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")

async def get_channels():
    async with aiohttp.ClientSession() as s:
        headers = {"Authorization": f"Bot {TOKEN}"}
        async with s.get("https://discord.com/api/v10/guilds/1457382179981099090/channels", headers=headers) as r:
            chs = await r.json()
            cats = {c["id"]: c["name"] for c in chs if c["type"] == 4}
            for c in sorted(chs, key=lambda x: (str(x.get("parent_id") or ""), x.get("position", 0))):
                if c["type"] in (0, 2):
                    cat_name = cats.get(c.get("parent_id"), "NO CATEGORY")
                    ctype = "VOICE" if c["type"] == 2 else "TEXT"
                    print(f"{cat_name} -> [{ctype}] #{c['name']} (ID: {c['id']})")

if __name__ == "__main__":
    asyncio.run(get_channels())
