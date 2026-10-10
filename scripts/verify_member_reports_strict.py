import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
OWNER_ID = 1457380609641938981
BOT_ID = 1554732669072445532
CH_ID = "1555428392181047366"

HEADERS = {"Authorization": f"Bot {TOKEN}"}
VIEW_CHANNEL = 1 << 10

async def fetch_json(s, url):
    for _ in range(5):
        try:
            async with s.get(url, headers=HEADERS) as r:
                return await r.json()
        except Exception:
            await asyncio.sleep(1)
    return {}

async def main():
    async with aiohttp.ClientSession() as s:
        ch = await fetch_json(s, f"https://discord.com/api/v10/channels/{CH_ID}")
        roles = await fetch_json(s, f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles")
        r_map = {r["id"]: r["name"] for r in roles}

    print("CHANNEL NAME:", ascii(ch["name"]))
    print("PARENT ID:", ch.get("parent_id"))
    overwrites = ch.get("permission_overwrites", [])
    print(f"Total Overwrites: {len(overwrites)}")

    passed = True
    # Everyone check
    ev_ow = next((ow for ow in overwrites if ow["id"] == str(GUILD_ID)), None)
    if ev_ow and (int(ev_ow["deny"]) & VIEW_CHANNEL):
        print("PASS: @everyone is DENIED view channel")
    else:
        print("FAIL: @everyone is NOT denied view channel")
        passed = False

    # Owner check
    ow_ow = next((ow for ow in overwrites if ow["id"] == str(OWNER_ID)), None)
    if ow_ow and (int(ow_ow["allow"]) & VIEW_CHANNEL):
        print("PASS: Owner is explicitly ALLOWED view channel")
    else:
        print("FAIL: Owner is NOT explicitly allowed")
        passed = False

    # Bot check
    bot_ow = next((ow for ow in overwrites if ow["id"] == str(BOT_ID)), None)
    if bot_ow and (int(bot_ow["allow"]) & VIEW_CHANNEL):
        print("PASS: Bot is explicitly ALLOWED view channel")
    else:
        print("FAIL: Bot is NOT explicitly allowed")
        passed = False

    # Check that NO other user or role has ALLOW
    for ow in overwrites:
        if ow["id"] not in (str(OWNER_ID), str(BOT_ID)):
            if int(ow.get("allow", 0)) & VIEW_CHANNEL:
                target_name = r_map.get(ow["id"], ow["id"])
                print(f"CRITICAL FAIL: {target_name} has ALLOW on VIEW_CHANNEL!")
                passed = False

    if passed:
        print("\n*** 100% VERIFIED: ⛨・member-reports is STRICTLY OWNER-ONLY! ***")

if __name__ == "__main__":
    asyncio.run(main())
