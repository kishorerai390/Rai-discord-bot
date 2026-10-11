import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
token = os.getenv("DISCORD_TOKEN")

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession(headers=headers) as s:
        async with s.get("https://discord.com/api/v10/channels/1558715927653126185/messages?limit=10") as r:
            msgs = await r.json()
            print(f"Messages count: {len(msgs)}")
            for m in msgs:
                print(f"[{m.get('timestamp')}] {m.get('author', {}).get('username')}: {m.get('content')}")
                if m.get("embeds"):
                    for emb in m["embeds"]:
                        print(f"  EMBED: {emb.get('title')} - {emb.get('description')}")

if __name__ == "__main__":
    asyncio.run(main())
