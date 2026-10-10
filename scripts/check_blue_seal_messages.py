import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
BLUE_SEAL_ID = "1477618724533043293"

HEADERS = {"Authorization": f"Bot {TOKEN}"}

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()

        for ch in channels:
            if ch.get("type") in (0, 5):
                cid = ch["id"]
                cname = ch.get("name")
                async with s.get(f"https://discord.com/api/v10/channels/{cid}/messages?limit=10", headers=HEADERS) as mr:
                    if mr.status == 200:
                        msgs = await mr.json()
                        for m in msgs:
                            if m.get("author", {}).get("id") == BLUE_SEAL_ID:
                                embeds = m.get("embeds", [])
                                title = embeds[0].get("title", "") if embeds else ""
                                desc = embeds[0].get("description", "") if embeds else ""
                                print(ascii(f"#{cname} | Title: {title} | Desc: {desc[:100]} | Content: {m.get('content', '')}"))

if __name__ == "__main__":
    asyncio.run(main())
