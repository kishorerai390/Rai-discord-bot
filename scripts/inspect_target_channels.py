import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
token = os.getenv("DISCORD_TOKEN")
headers = {"Authorization": f"Bot {token}"}

channels = {
    "Server Dashboard": 1555283414205075509,
    "Announcements": 1545502718792175646,
    "Sleeping Pods": 1555641081578782840,
    "Security Alerts": 1555283378612478072,
    "Server Roles": 1545502722739150898,
}

async def main():
    async with aiohttp.ClientSession() as s:
        for name, cid in channels.items():
            async with s.get(f"https://discord.com/api/v10/channels/{cid}/messages?limit=5", headers=headers) as r:
                msgs = await r.json()
                print(f"=== {name} ({cid}): {len(msgs)} messages ===")
                for m in msgs:
                    embed_titles = [e.get("title", "") for e in m.get("embeds", [])]
                    print(f"  ID {m['id']} | Author: {m['author']['username']} | Embeds: {[ascii(t) for t in embed_titles]}")

if __name__ == "__main__":
    asyncio.run(main())
