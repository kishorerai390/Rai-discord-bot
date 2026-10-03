"""
Prune newly created duplicate categories and channels:
- 12 channels in 🛡️・RΛI SECURITY (1555281200057290895)
- 7 channels in ⚙️・RΛI SYSTEM (1555281201751793757)
- 7 channels in 👑・RΛI ADMIN (1555281202892636230)
- 4 redundant text channels in 🎵・RΛI MUSIC (queue, dj-control, playlists, music-requests)
- The 3 duplicate categories themselves
"""

import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(r"f:\Bot\.env")

TOKEN = os.getenv("DISCORD_TOKEN")
HEADERS = {"Authorization": f"Bot {TOKEN}"}

CHANNELS_TO_DELETE = [
    # Music extra text channels
    "1555281218600312973",  # queue
    "1555281220365983804",  # dj-control
    "1555281222077386752",  # playlists
    "1555281223180357775",  # music-requests

    # 🛡️・RΛI SECURITY duplicate channels
    "1555281204645990420",  # threat-detection
    "1555281207015641288",  # anti-nuke
    "1555281209876029523",  # anti-raid
    "1555281210966679605",  # anti-spam
    "1555281212396806295",  # automod
    "1555281213625733153",  # lockdown
    "1555281214904991994",  # security-events
    "1555281216377327696",  # audit-logs
    "1555281251068412017",  # raid-alert
    "1555281252691742770",  # critical-alert
    "1555281254243508385",  # nuke-detection
    "1555281256587993160",  # emergency-lock

    # ⚙️・RΛI SYSTEM duplicate channels
    "1555281224887574548",  # bot-status
    "1555281226024353824",  # system-stats
    "1555281227010023474",  # ai-status
    "1555281227907469375",  # database
    "1555281233079046217",  # health-status
    "1555281236707123314",  # maintenance
    "1555281239341142088",  # system-events

    # 👑・RΛI ADMIN duplicate channels
    "1555281241480237179",  # admin-control
    "1555281243111694406",  # configuration
    "1555281243967328326",  # permissions
    "1555281244973965465",  # tools
    "1555281246601486434",  # backup
    "1555281248367288443",  # restore
    "1555281249612865536",  # emergency-control
]

CATEGORIES_TO_DELETE = [
    "1555281200057290895",  # 🛡️・RΛI SECURITY
    "1555281201751793757",  # ⚙️・RΛI SYSTEM
    "1555281202892636230",  # 👑・RΛI ADMIN
]

async def api_delete(session: aiohttp.ClientSession, url: str) -> bool:
    while True:
        async with session.delete(url, headers=HEADERS) as r:
            if r.status == 429:
                data = await r.json()
                retry_after = data.get("retry_after", 1.0)
                await asyncio.sleep(retry_after)
                continue
            if r.status in (200, 204, 404):
                await asyncio.sleep(0.3)
                return True
            err = await r.text()
            print(f"  [DELETE ERROR {r.status}] {url} -> {err}")
            return False

async def main():
    print("Pruning 30 duplicate channels...")
    async with aiohttp.ClientSession() as s:
        for cid in CHANNELS_TO_DELETE:
            ok = await api_delete(s, f"https://discord.com/api/v10/channels/{cid}")
            if ok:
                print(f"  Deleted channel {cid}")

        print("\nPruning 3 duplicate categories...")
        for cat_id in CATEGORIES_TO_DELETE:
            ok = await api_delete(s, f"https://discord.com/api/v10/channels/{cat_id}")
            if ok:
                print(f"  Deleted category {cat_id}")

    print("\nAll duplicate extra channels and categories pruned successfully!")

if __name__ == "__main__":
    asyncio.run(main())
