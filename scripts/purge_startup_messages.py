"""
Purge unsolicited startup messages from #system-report channels across guilds.
"""

import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")

SYSTEM_REPORT_CHANNELS = [
    1555673101235388476,
    1555673103567298605,
    1555673102237565056,
    1555673102732632091,
    1555673102073987185,
    1555428426607894570,
]

async def purge_startup_messages():
    headers = {"Authorization": f"Bot {TOKEN}"}
    deleted_total = 0
    async with aiohttp.ClientSession() as s:
        for cid in SYSTEM_REPORT_CHANNELS:
            try:
                async with s.get(f"https://discord.com/api/v10/channels/{cid}/messages?limit=20", headers=headers) as r:
                    if r.status != 200:
                        continue
                    msgs = await r.json()
                    for m in msgs:
                        embeds = m.get("embeds", [])
                        is_startup_msg = False
                        for emb in embeds:
                            title = emb.get("title", "")
                            desc = emb.get("description", "")
                            fields_str = str(emb.get("fields", []))
                            if "Bot Core Online & Synchronized" in title or "Bot Core Online & Synchronized" in desc or "Bot Core Online & Synchronized" in fields_str:
                                is_startup_msg = True
                                break
                        if is_startup_msg:
                            mid = m.get("id")
                            async with s.delete(f"https://discord.com/api/v10/channels/{cid}/messages/{mid}", headers=headers) as del_resp:
                                if del_resp.status in (200, 204):
                                    print(f"Deleted startup msg {mid} from channel {cid}")
                                    deleted_total += 1
                                else:
                                    print(f"Failed deleting msg {mid} from {cid}: {del_resp.status}")
                            await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Error checking channel {cid}: {e}")
    print(f"Total startup messages purged: {deleted_total}")

if __name__ == "__main__":
    asyncio.run(purge_startup_messages())
