import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

async def main():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers) as r:
            chs = await r.json()
            cats = {c["id"]: c["name"] for c in chs if c.get("type") == 4}
            text_chs = [c for c in chs if c.get("type") == 0]
            for c in sorted(text_chs, key=lambda x: (x.get("parent_id") or "", x.get("position", 0))):
                cid = c["id"]
                parent_name = cats.get(c.get("parent_id"), "None")
                async with s.get(f"https://discord.com/api/v10/channels/{cid}/messages?limit=1", headers=headers) as mr:
                    msgs = await mr.json()
                    count = len(msgs) if isinstance(msgs, list) else 0
                    print(f"[{count} msgs] {ascii(parent_name)} -> {ascii(c['name'])} ({cid})")

asyncio.run(main())
