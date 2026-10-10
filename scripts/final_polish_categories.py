import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
HEADERS = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

GAMING_CAT_ID = "1554905821467648051"
CREATOR_CAT_ID = "1558483212873769090"
CHILL_CAT_ID = "1554905799292231728"

async def main():
    async with aiohttp.ClientSession() as s:
        # 1. Move gaming-hub to GAMING ARENA
        print("Moving gaming-hub to Gaming Arena...")
        await s.patch("https://discord.com/api/v10/channels/1557475853175234660", headers=HEADERS, json={
            "parent_id": GAMING_CAT_ID,
            "name": "⌖・gaming-hub"
        })
        await asyncio.sleep(0.5)

        # 2. Rename Stream Showcase to 🎬 Creator Lounge in Creator Studio
        print("Renaming Cinema / Stream VC in Creator Studio...")
        await s.patch("https://discord.com/api/v10/channels/1554905870817689600", headers=HEADERS, json={
            "name": "🎬 Creator Lounge",
            "parent_id": CREATOR_CAT_ID
        })
        await asyncio.sleep(0.5)

    print("Polish complete!")

if __name__ == "__main__":
    asyncio.run(main())
