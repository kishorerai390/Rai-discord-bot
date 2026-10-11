"""
Permanently Delete 📦・ARCHIVE Category and its child channels.
Rate-limited with 1.2s backoff to stay clear of Discord API limits.
"""

from __future__ import annotations

import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "F:/Bot")

import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
ARCHIVE_CAT_ID = "1558532566544551947"

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}


async def main():
    print("=" * 60)
    print("   PERMANENTLY DELETING 📦・ARCHIVE CATEGORY & CHANNELS")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        # Fetch current channels
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()

        # Find all children of ARCHIVE
        archive_children = [c for c in channels if c.get("parent_id") == ARCHIVE_CAT_ID]
        print(f"\nFound {len(archive_children)} channels inside 📦・ARCHIVE:")

        for ch in archive_children:
            ch_id = ch["id"]
            ch_name = ch["name"]
            print(f"  Deleting channel: #{ch_name} ({ch_id})...")
            async with session.delete(f"https://discord.com/api/v10/channels/{ch_id}", headers=HEADERS) as resp:
                if resp.status in (200, 204):
                    print(f"    [DELETED] #{ch_name}")
                else:
                    err = await resp.text()
                    print(f"    [ERROR] #{ch_name} -> HTTP {resp.status}: {err}")
            await asyncio.sleep(1.2)

        # Now delete the category itself
        print(f"\nDeleting 📦・ARCHIVE Category ({ARCHIVE_CAT_ID})...")
        async with session.delete(f"https://discord.com/api/v10/channels/{ARCHIVE_CAT_ID}", headers=HEADERS) as resp:
            if resp.status in (200, 204):
                print("  [DELETED] 📦・ARCHIVE category removed successfully!")
            else:
                err = await resp.text()
                print(f"  [ERROR] ARCHIVE Category -> HTTP {resp.status}: {err}")

    print("\n" + "=" * 60)
    print("   ARCHIVE CLEANUP COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
