import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv("F:/Bot/.env")
token = os.getenv("DISCORD_TOKEN")
guild_id = 1457382179981099090

import unicodedata

def norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get("https://discord.com/api/v10/guilds/1457382179981099090/channels", headers=headers) as r:
            channels = await r.json()
            cat_channels = [ch for ch in channels if ch.get("parent_id") == "1554891379174416474"]
            print("--- CHANNELS IN '╭━━━ 𝓟ʀɪᴠᴀᴛᴇ・𝕍ᴏɪᴄᴇ ━━━╮' ---")
            for c in cat_channels:
                print(f"{c['id']} | type={c['type']} | {repr(c['name'])}")

if __name__ == "__main__":
    asyncio.run(main())
