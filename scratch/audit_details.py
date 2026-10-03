import asyncio
import os
import sys
from pathlib import Path
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_GUILD_ID = 1457382179981099090

async def check():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{TARGET_GUILD_ID}/channels", headers=headers) as r:
            channels = await r.json()
        async with s.get(f"https://discord.com/api/v10/guilds/{TARGET_GUILD_ID}/roles", headers=headers) as r:
            roles = await r.json()

    verify_ch = next((c for c in channels if "ᴠᴇʀɪꜰʏ" in c.get("name", "") or "verify" in c.get("name", "").lower()), None)
    print("Verification Channel:")
    if verify_ch:
        print(f"Name: {verify_ch.get('name')}, ID: {verify_ch.get('id')}, Category ID: {verify_ch.get('parent_id')}")
        print("Overwrites:", verify_ch.get("permission_overwrites"))
    
    print("\nBot & Third-party roles analysis:")
    for role in roles:
        name = role.get("name")
        p = int(role.get("permissions", 0))
        is_admin = bool(p & 0x8)
        can_mention = bool(p & 0x20000)
        can_ban = bool(p & 0x4)
        can_kick = bool(p & 0x2)
        if is_admin or can_mention or can_ban or can_kick:
            print(f"- {name}: Admin={is_admin}, MentionEveryone={can_mention}, BanMembers={can_ban}, KickMembers={can_kick}")

if __name__ == "__main__":
    asyncio.run(check())
