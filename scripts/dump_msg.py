import asyncio
import os
import sys
import aiohttp
import json
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")

async def dump(cid, mid):
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/channels/{cid}/messages/{mid}", headers=headers) as r:
            m = await r.json()
            print(f"=== MSG {mid} in channel {cid} ===")
            if "embeds" in m and m["embeds"]:
                e = m["embeds"][0]
                print("Title:", e.get("title"))
                print("Desc:", e.get("description"))
                for f in e.get("fields", []):
                    print(f"  Field: {f.get('name')} -> {f.get('value')[:100]}")
            print("Components count:", len(m.get("components", [])))

async def main():
    await dump(1545502722739150898, 1557467800673591389)  # server-roles
    await dump(1557481215731306526, 1557481217580998739)  # server-faq
    await dump(1555641079137706014, 1558266440627519492)  # support-desk

if __name__ == "__main__":
    asyncio.run(main())
