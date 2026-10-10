"""
Script to inspect messages in #welcome channel.
"""
import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
WELCOME_ID = 1545502705643167876
HEADERS = {"Authorization": f"Bot {TOKEN}"}


async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/channels/{WELCOME_ID}/messages?limit=10", headers=HEADERS) as r:
            msgs = await r.json()
            for m in msgs:
                author = m.get("author", {}).get("username")
                embed_titles = [e.get("title") for e in m.get("embeds", [])]
                print(f"ID: {m['id']} | Author: {author} | Embeds: {embed_titles} | Content: {m.get('content', '')[:60]}")


if __name__ == "__main__":
    asyncio.run(main())
