"""
Server Layout Arrangement & Polish:
1. Deletes 3 empty legacy categories (0 channels):
   - ⚙️ ═ RAI ADMIN ═ ⚙️
   - ✦ PRIVATE REPORTING ✦
   - ✦ CREATOR STUDIO ✦
2. Moves staff voice channel (Staff Operations HQ) into ✦ STAFF ✦ category.
3. Sets the logical category order:
   - 🔒 Server Status! (Pos 0)
   - 🔒 Vc Status! (Pos 1)
   - ✦ START HERE ✦ (Pos 2)
   - ✦ COMMUNITY ✦ (Pos 3)
   - ✦ SUPPORT ✦ (Pos 4)
   - ✦ BOT ✦ (Pos 5)
   - 🍒・Personal Area ! (Pos 6)
   - 🍒・Fun Voice Channels ! (Pos 7)
   - 🍒・Gaming Zone ! (Pos 8)
   - 🍒・Editing Zone ! (Pos 9)
   - 🍒・Music Zone ! (Pos 10)
   - 🍒・Theater ! (Pos 11)
   - 🍒・Private Zone ! (Pos 12)
   - 🍒・AFK Zone ! (Pos 13)
   - ✦ STAFF ✦ (Pos 14)
   - ✧ DETENTION ROOM ✧ (Pos 15)
   - 📦・ARCHIVE (Pos 16)
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

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

EMPTY_CATEGORIES_TO_DELETE = [
    "1555283377249063083",  # ⚙️ ═ RAI ADMIN ═ ⚙️ (0 ch)
    "1555428388280209422",  # ✦ PRIVATE REPORTING ✦ (0 ch)
    "1558483212873769090",  # ✦ CREATOR STUDIO ✦ (0 ch)
]

TARGET_CATEGORY_ORDER = [
    ("1546059369085534229", "🔒 Server Status!"),
    ("1558678832326901780", "🔒 Vc Status!"),
    ("1545803464712650844", "✦ START HERE ✦"),
    ("1545803478490812578", "✦ COMMUNITY ✦"),
    ("1558679085293510746", "✦ SUPPORT ✦"),
    ("1558679157603311697", "✦ BOT ✦"),
    ("1554891379174416474", "🍒・Personal Area !"),
    ("1554905799292231728", "🍒・Fun Voice Channels !"),
    ("1554905821467648051", "🍒・Gaming Zone !"),
    ("1554905886261121107", "🍒・Editing Zone !"),
    ("1555255661124784159", "🍒・Music Zone !"),
    ("1558676285733994516", "🍒・Theater !"),
    ("1554905776030613535", "🍒・Private Zone !"),
    ("1554891470325031013", "🍒・AFK Zone !"),
    ("1555283372488658954", "✦ STAFF ✦"),
    ("1556740753336565881", "✧ DETENTION ROOM ✧"),
    ("1558532566544551947", "📦・ARCHIVE"),
]


async def main():
    print("=" * 65)
    print("      ARRANGING SERVER LAYOUT & CATEGORY ORDER")
    print("=" * 65)

    async with aiohttp.ClientSession() as session:
        # 1. Delete the 3 completely empty categories
        print("\n[1/3] Deleting 3 empty legacy categories (0 channels)...")
        for cat_id in EMPTY_CATEGORIES_TO_DELETE:
            async with session.delete(f"https://discord.com/api/v10/channels/{cat_id}", headers=HEADERS) as resp:
                if resp.status in (200, 204):
                    print(f"  [DELETED] Category {cat_id}")
                else:
                    print(f"  [NOTE] Category {cat_id} -> HTTP {resp.status}")
            await asyncio.sleep(1.0)

        # 2. Move Staff Operations HQ voice channel into ✦ STAFF ✦
        print("\n[2/3] Moving Staff Operations HQ into ✦ STAFF ✦ category...")
        staff_vc_id = "1554905903508095066"
        staff_cat_id = "1555283372488658954"
        async with session.patch(
            f"https://discord.com/api/v10/channels/{staff_vc_id}",
            headers=HEADERS,
            json={"parent_id": staff_cat_id},
        ) as resp:
            if resp.status in (200, 204):
                print("  [SUCCESS] Staff Operations HQ moved to ✦ STAFF ✦")
            else:
                print(f"  [NOTE] Move Staff HQ -> HTTP {resp.status}")
        await asyncio.sleep(1.0)

        # 3. Apply Category Order
        print("\n[3/3] Setting logical category order...")
        reorder_payload = []
        for pos, (cid, name) in enumerate(TARGET_CATEGORY_ORDER):
            reorder_payload.append({"id": cid, "position": pos})
            print(f"  Pos {pos:2d} -> {name}")

        async with session.patch(
            f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels",
            headers=HEADERS,
            json=reorder_payload,
        ) as resp:
            if resp.status in (200, 204):
                print("\n  [SUCCESS] Category positions updated successfully!")
            else:
                err = await resp.text()
                print(f"\n  [ERROR] Updating category positions -> HTTP {resp.status}: {err}")

    print("\n" + "=" * 65)
    print("   ARRANGEMENT COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
