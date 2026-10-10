import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

CREATOR_STUDIO_CAT_ID = 1558483212873769090
ARCHIVE_CAT_ID = 1558532566544551947

# Channels to move into Creator Studio
CREATOR_CHANNELS = [
    (1558483065578197002, "✧・pfp-and-banners"),
    (1558483087283720352, "𖦹・editing-tips"),
    (1558483098553819228, "♧・collab-requests"),
    (1558483178862288987, "🏅・edit-of-the-week"),
]

# Duplicate voice to archive
DUPLICATE_VOICE_CHANNELS = [
    (1558483052550692884, "🎶・24/7 Radio & Beats"),
]

async def main():
    print("🚀 Reorganizing channels into appropriate categories...")
    async with aiohttp.ClientSession() as session:
        # Move creator channels
        for ch_id, ch_name in CREATOR_CHANNELS:
            payload = {"parent_id": str(CREATOR_STUDIO_CAT_ID)}
            async with session.patch(
                f"https://discord.com/api/v10/channels/{ch_id}",
                headers=HEADERS,
                json=payload
            ) as r:
                if r.status == 200:
                    print(f"✅ Moved '{ch_name}' to Creator Studio.")
                else:
                    err = await r.text()
                    print(f"⚠️ Failed to move '{ch_name}': {r.status} - {err}")
            await asyncio.sleep(0.5)

        # Archive duplicate music channel
        for ch_id, ch_name in DUPLICATE_VOICE_CHANNELS:
            payload = {"parent_id": str(ARCHIVE_CAT_ID)}
            async with session.patch(
                f"https://discord.com/api/v10/channels/{ch_id}",
                headers=HEADERS,
                json=payload
            ) as r:
                if r.status == 200:
                    print(f"✅ Moved '{ch_name}' to Archive (keeping primary 24/7 Radio in Music Lounge).")
                else:
                    err = await r.text()
                    print(f"⚠️ Failed to archive '{ch_name}': {r.status} - {err}")
            await asyncio.sleep(0.5)

        print("✨ Channel reorganization complete!")

if __name__ == "__main__":
    asyncio.run(main())
