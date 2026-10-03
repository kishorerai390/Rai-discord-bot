import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"
music_category_id = "1555255661124784159"

voice_channels_to_move = [
    ("🔊・RΛI MUSIC", "1555255317170749472"),
    ("🎧・RΛI LOUNGE", "1555255319494402141"),
    ("🎵・MUSIC ROOM", "1555255321948327936"),
    ("🎶・LISTENING ROOM", "1555255323705475228"),
    ("⚡・RAI RADIO", "1555255325706424412"),
]

async def main():
    if not token:
        print("[ERROR] DISCORD_TOKEN is missing!")
        return

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        print(f"Moving 5 voice channels under category '🎵・RΛI MUSIC' ({music_category_id})...\n")
        
        for name, ch_id in voice_channels_to_move:
            url = f"https://discord.com/api/v10/channels/{ch_id}"
            payload = {
                "parent_id": music_category_id
            }
            async with session.patch(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    print(f"  [SUCCESS] Moved '{name}' ({ch_id}) -> '🎵・RΛI MUSIC'")
                else:
                    data = await resp.text()
                    print(f"  [FAILED] Could not move '{name}' ({ch_id}): HTTP {resp.status} - {data}")
            await asyncio.sleep(0.5)

        print("\nAll 5 voice channels processed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
