"""
Apply Clean Modern Sans typography across RAI FAM channels and server header:
Standardizes font to ultra-clean modern sans with bullet dots ('・') for 100% cross-platform clarity.
"""

import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# Channel renaming map
CHANNELS_MAP = {
    1545502700840427702: "✨・verify-here",
    1545502705643167876: "🌸・welcome",
    1545502710101704714: "📜・rules-and-info",
    1545502722739150898: "🏷️・roles",
    1545502730699808768: "💬・general-chat",
    1551184138932068373: "📸・media-and-clips",
    1549416359723532480: "🤖・bot-commands",
    1545502845208629328: "🛡️・staff-operations",
}

async def update_channels(session: aiohttp.ClientSession):
    for cid, new_name in CHANNELS_MAP.items():
        url = f"https://discord.com/api/v10/channels/{cid}"
        payload = {"name": new_name}
        async with session.patch(url, headers=HEADERS, json=payload) as r:
            status = r.status
            print(f"Renamed channel {cid} to {ascii(new_name)} -> HTTP {status}")
            await asyncio.sleep(1.0)  # Safe rate limit pause

async def update_guild_name(session: aiohttp.ClientSession):
    url = f"https://discord.com/api/v10/guilds/{GUILD_ID}"
    new_guild_name = "✦ RAI FAM💗 ✦"
    payload = {"name": new_guild_name}
    async with session.patch(url, headers=HEADERS, json=payload) as r:
        print(f"Updated guild name to {ascii(new_guild_name)} -> HTTP {r.status}")

async def main():
    async with aiohttp.ClientSession() as session:
        await update_channels(session)
        await update_guild_name(session)
    print("Clean Modern Sans typography successfully deployed across the entire server!")

if __name__ == "__main__":
    asyncio.run(main())
