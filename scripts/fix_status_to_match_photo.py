"""
Fix Server Status and VC Status channels to match the photo reference exactly:
- 🔒 Server Status!
    🦋 {online} online 🦋 {members} members
- 🔒 Vc Status!
    🦋 {vc_users} vc user 🦋 {active_vc} Active vc
"""

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

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

SERVER_STATUS_CH_ID = "1546099701496029194"
VC_STATUS_CH_ID = "1546099703630798848"


async def main():
    print("=" * 60)
    print("   ALIGNING STATUS CHANNELS TO REFERENCE PHOTO")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        # Get live counts
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}?with_counts=true", headers=HEADERS) as r:
            guild_data = await r.json()

        members = guild_data.get("approximate_member_count", 46)
        online = guild_data.get("approximate_presence_count", 20)

        server_stat_name = f"🦋 {online} online 🦋 {members} members"
        vc_stat_name = "🦋 0 vc user 🦋 0 Active vc"

        # 1. Update Server Status
        print(f"\n[1/2] Updating Server Status Channel -> {server_stat_name}")
        async with session.patch(
            f"https://discord.com/api/v10/channels/{SERVER_STATUS_CH_ID}",
            headers=HEADERS,
            json={"name": server_stat_name},
        ) as resp:
            if resp.status in (200, 204):
                print(f"  [SUCCESS] Renamed to: {server_stat_name}")
            else:
                err = await resp.text()
                print(f"  [ERROR] HTTP {resp.status}: {err}")

        await asyncio.sleep(1.5)

        # 2. Update VC Status
        print(f"\n[2/2] Updating VC Status Channel -> {vc_stat_name}")
        async with session.patch(
            f"https://discord.com/api/v10/channels/{VC_STATUS_CH_ID}",
            headers=HEADERS,
            json={"name": vc_stat_name},
        ) as resp:
            if resp.status in (200, 204):
                print(f"  [SUCCESS] Renamed to: {vc_stat_name}")
            else:
                err = await resp.text()
                print(f"  [ERROR] HTTP {resp.status}: {err}")

    print("\n" + "=" * 60)
    print("   UPDATE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
