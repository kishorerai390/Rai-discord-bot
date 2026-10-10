import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")

channels = {
    "support-desk": 1555641079137706014,
    "server-faq": 1557481215731306526,
    "server-roles": 1545502722739150898,
}

async def test():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as s:
        for name, cid in channels.items():
            async with s.get(f"https://discord.com/api/v10/channels/{cid}/messages?limit=5", headers=headers) as r:
                msgs = await r.json()
                print(f"=== {name} ({cid}): {len(msgs)} messages ===")
                for m in msgs:
                    author = m["author"]["username"]
                    content = m.get("content", "")[:50]
                    embed_titles = [e.get("title", "No Title") for e in m.get("embeds", [])]
                    print(f"  [{m['id']}] {author}: {content} | Embeds: {embed_titles}")

if __name__ == "__main__":
    asyncio.run(test())
