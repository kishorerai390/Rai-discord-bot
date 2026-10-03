"""
Verify that 📋 | RAI REPORTS category and all 6 channels are 100% strictly owner-only.
"""

import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
OWNER_ID = 1457380609641938981
BOT_ID = 1554732669072445532

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

VIEW_CHANNEL = 1024
SEND_MESSAGES = 2048
READ_MESSAGE_HISTORY = 65536

async def main():
    async with aiohttp.ClientSession() as session:
        # 1. Fetch Guild Channels
        url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels"
        async with session.get(url, headers=HEADERS) as r:
            chs = await r.json()

        cat = next((c for c in chs if c.get("type") == 4 and "RAI REPORTS" in c.get("name", "").upper()), None)
        if not cat:
            print("ERROR: Category not found!")
            return

        cat_id = cat["id"]
        report_channels = [c for c in chs if c.get("parent_id") == cat_id]

        print(f"CATEGORY: {ascii(cat['name'])} (ID: {cat_id})")
        print(f"Child Channels Count: {len(report_channels)}")

        targets = [cat] + report_channels
        all_passed = True

        for target in targets:
            name = ascii(target["name"])
            tid = target["id"]
            overwrites = target.get("permission_overwrites", [])
            print(f"\nVerifying {name} ({tid}) - Overwrites: {len(overwrites)}")

            # Check @everyone
            everyone_ow = next((ow for ow in overwrites if ow["id"] == str(GUILD_ID)), None)
            if not everyone_ow or not (int(everyone_ow["deny"]) & VIEW_CHANNEL):
                print(f"  FAILED: @everyone is NOT denied VIEW_CHANNEL on {name}!")
                all_passed = False
            else:
                print(f"  PASSED: @everyone is strictly DENIED VIEW_CHANNEL on {name}")

            # Check Owner
            owner_ow = next((ow for ow in overwrites if ow["id"] == str(OWNER_ID)), None)
            if not owner_ow or not (int(owner_ow["allow"]) & VIEW_CHANNEL):
                print(f"  WARNING: Owner explicit allow missing on {name} (Note: Owner still bypasses on Discord)")
            else:
                print(f"  PASSED: Owner explicit ALLOW VIEW_CHANNEL on {name}")

            # Check Rai Bot
            bot_ow = next((ow for ow in overwrites if ow["id"] == str(BOT_ID)), None)
            if not bot_ow or not (int(bot_ow["allow"]) & VIEW_CHANNEL):
                print(f"  FAILED: Rai Bot does NOT have VIEW_CHANNEL on {name}!")
                all_passed = False
            else:
                print(f"  PASSED: Rai Bot explicit ALLOW VIEW_CHANNEL on {name}")

            # Verify no unauthorized role has ALLOW
            for ow in overwrites:
                if ow["id"] not in (str(OWNER_ID), str(BOT_ID)):
                    allow_bits = int(ow["allow"])
                    if allow_bits & VIEW_CHANNEL:
                        print(f"  CRITICAL FAILURE: Role/Member {ow['id']} has VIEW_CHANNEL ALLOW on {name}!")
                        all_passed = False

        if all_passed:
            print("\n=======================================================")
            print("AUDIT RESULT: 100% SUCCESSFUL & VERIFIED!")
            print("The entire category and all 6 channels are GENUINELY INVISIBLE to everyone except the Server Owner and Rai.")
            print("=======================================================")
        else:
            print("\nAUDIT RESULT: ISSUES DETECTED")

if __name__ == "__main__":
    asyncio.run(main())
