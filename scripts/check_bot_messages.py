import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"
bot_id = "1554732669072445532"

async def check():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers) as r:
            channels = await r.json()

        text_channels = [c for c in channels if c.get("type") in (0, 5)]
        print(f"Checking {len(text_channels)} channels...")

        for ch in text_channels:
            cid = ch["id"]
            cname = ch.get("name", "unknown")
            async with s.get(f"https://discord.com/api/v10/channels/{cid}/messages?limit=10", headers=headers) as mr:
                if mr.status != 200:
                    continue
                msgs = await mr.json()
                for m in msgs:
                    author = m.get("author", {})
                    if author.get("id") == bot_id:
                        ts = m.get("timestamp")
                        content = m.get("content", "")
                        embeds = m.get("embeds", [])
                        embed_title = embeds[0].get("title", "") if embeds else ""
                        safe_name = cname.encode("ascii", errors="replace").decode("ascii")
                        safe_title = embed_title.encode("ascii", errors="replace").decode("ascii")
                        safe_content = content[:80].encode("ascii", errors="replace").decode("ascii")
                        print(f"[#{safe_name}] ({ts}) Title: {safe_title} | Content: {safe_content}")




if __name__ == "__main__":
    asyncio.run(check())
