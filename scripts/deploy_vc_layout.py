"""
Deploy Voice Channel Layout based on user screenshots:
- 🎭 | PERSONAL AREA (SOLO limit 1, DUO limit 2, DUO limit 2, TRIO limit 3)
- 😹 | FUN VOICE CHANNELS (FUN TIME, VOICE-1, VOICE-2, VOICE-3, OPEN VOICE)
- 🎚 | EDITING ZONE (DRAG ME)
- 🔱 | RAI-ESP ! (RAI FAM, INTHU ENGA AREA)
- ⚜️ | Checking Zone (CHECKING-AREA, PC-CHECKING, PHONE-CHECKING, PVT-CHECKING [Locked])
- 🍃 | SONG ZONE (RAI 24/7, SONG LOUNGE)
- 🎥 | THEATER (MOVIE¹, MOVIE²)
- 🔏 | PRIVATE-ZONE (PVT-CHANNEL, PVT-CHANNEL, PVT-WORK, PVT-LIVE STREAM, ONLY ADMINS [Locked])
- ✌🏻 | AESTHETICS (boyz-dp, girlz-dp, banners)
- 🚫 | HIDE CHANNELS (DRAG ME [Hidden])
"""

import asyncio
import os
import sys
from pathlib import Path
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(r"f:\Bot\.env")

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

# Permission Bitwise Flags
VIEW_CHANNEL = 1 << 10
CONNECT = 1 << 20
SPEAK = 1 << 21

CATEGORIES_AND_CHANNELS = [
    {
        "name": "🎭 ┃ PERSONAL AREA",
        "channels": [
            {"name": "🥂｜・SOLO", "type": 2, "user_limit": 1},
            {"name": "🥂｜・DUO", "type": 2, "user_limit": 2},
            {"name": "🥂｜・DUO", "type": 2, "user_limit": 2},
            {"name": "🥂｜・TRIO", "type": 2, "user_limit": 3},
        ],
    },
    {
        "name": "😹 ┃ FUN VOICE CHANNELS",
        "channels": [
            {"name": "🐣｜FUN TIME", "type": 2, "user_limit": 0},
            {"name": "🔮｜VOICE-1", "type": 2, "user_limit": 0},
            {"name": "🔮｜VOICE-2", "type": 2, "user_limit": 0},
            {"name": "🔮｜VOICE-3", "type": 2, "user_limit": 0},
            {"name": "🔮｜OPEN VOICE", "type": 2, "user_limit": 0},
        ],
    },
    {
        "name": "🔱 ┃ RAI-ESP !",
        "channels": [
            {"name": "☘️｜RAI FAM", "type": 2, "user_limit": 0},
            {"name": "☘️｜INTHU ENGA AREA", "type": 2, "user_limit": 0},
        ],
    },
    {
        "name": "⚜️ ┃ Checking Zone",
        "channels": [
            {"name": "🔎｜CHECKING-AREA", "type": 2, "user_limit": 0},
            {"name": "🔎｜PC-CHECKING", "type": 2, "user_limit": 0},
            {"name": "🔎｜PHONE-CHECKING", "type": 2, "user_limit": 0},
            {"name": "🔒｜PVT-CHECKING", "type": 2, "user_limit": 0, "locked": True},
        ],
    },
    {
        "name": "🍃 ┃ SONG ZONE",
        "channels": [
            {"name": "🎧｜RAI 24/7", "type": 2, "user_limit": 0},
            {"name": "🎧｜SONG LOUNGE", "type": 2, "user_limit": 0},
        ],
    },
    {
        "name": "🎥 ┃ THEATER",
        "channels": [
            {"name": "📼｜MOVIE¹", "type": 2, "user_limit": 0},
            {"name": "📼｜MOVIE²", "type": 2, "user_limit": 0},
        ],
    },
    {
        "name": "🎚 ┃ EDITING ZONE",
        "channels": [
            {"name": "🌕｜DRAG ME", "type": 2, "user_limit": 0},
        ],
    },
    {
        "name": "🔏 ┃ PRIVATE-ZONE",
        "channels": [
            {"name": "🔮｜PVT-CHANNEL", "type": 2, "user_limit": 0, "locked": True},
            {"name": "🔮｜PVT-CHANNEL", "type": 2, "user_limit": 0, "locked": True},
            {"name": "🔮｜PVT-WORK", "type": 2, "user_limit": 0, "locked": True},
            {"name": "🔮｜PVT-LIVE STREAM", "type": 2, "user_limit": 0, "locked": True},
            {"name": "🔇｜ONLY ADMINS", "type": 2, "user_limit": 0, "admin_only": True},
        ],
    },
    {
        "name": "✌🏻 ┃ AESTHETICS",
        "channels": [
            {"name": "📸・boyz-dp", "type": 0},
            {"name": "🌸・girlz-dp", "type": 0},
            {"name": "🖼️・banners", "type": 0},
        ],
    },
    {
        "name": "🚫 ┃ HIDE CHANNELS",
        "hidden": True,
        "channels": [
            {"name": "🔮｜DRAG ME", "type": 2, "user_limit": 0},
        ],
    },
]


async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        # 1. Fetch current roles to get @everyone and admin/staff IDs
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers) as r:
            roles = await r.json()

        everyone_role = next(role for role in roles if role["name"] == "@everyone")
        everyone_id = everyone_role["id"]
        mod_role = next((role for role in roles if "MODERATOR" in role["name"]), None)
        admin_role = next((role for role in roles if "ADMIN" in role["name"]), None)
        vip_role = next((role for role in roles if "VIP" in role["name"]), None)

        print(f"Role IDs found: @everyone={everyone_id}, Mod={getattr(mod_role, 'get', lambda x: None)('id')}")

        # 2. Fetch existing channels so we don't recreate duplicates
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers) as r:
            existing = await r.json()

        existing_names = {c["name"]: c for c in existing}

        for cat_data in CATEGORIES_AND_CHANNELS:
            cat_name = cat_data["name"]
            cat_id = None

            # Check if category already exists
            if cat_name in existing_names and existing_names[cat_name]["type"] == 4:
                cat_id = existing_names[cat_name]["id"]
                print(f"Category already exists: {cat_name} ({cat_id})")
            else:
                cat_payload = {
                    "name": cat_name,
                    "type": 4,
                }
                # If hidden category
                if cat_data.get("hidden"):
                    cat_payload["permission_overwrites"] = [
                        {
                            "id": everyone_id,
                            "type": 0,
                            "deny": str(VIEW_CHANNEL),
                            "allow": "0",
                        }
                    ]

                async with s.post(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=cat_payload) as r:
                    if r.status in (200, 201):
                        new_cat = await r.json()
                        cat_id = new_cat["id"]
                        print(f"📁 Created Category: {cat_name} ({cat_id})")
                    else:
                        print(f"❌ Failed to create category {cat_name}: {r.status} - {await r.text()}")
                        continue
                await asyncio.sleep(0.4)

            # Create channels inside this category
            for ch_data in cat_data["channels"]:
                ch_name = ch_data["name"]
                ch_type = ch_data.get("type", 2)
                user_limit = ch_data.get("user_limit", 0)

                # Check if channel exists under this category
                match = next((c for c in existing if c["name"] == ch_name and c.get("parent_id") == cat_id), None)
                if match:
                    print(f"  Channel already exists: {ch_name} ({match['id']})")
                    continue

                ch_payload = {
                    "name": ch_name,
                    "type": ch_type,
                    "parent_id": cat_id,
                }
                if ch_type == 2:
                    ch_payload["user_limit"] = user_limit

                overwrites = []
                if ch_data.get("admin_only"):
                    overwrites.append({
                        "id": everyone_id,
                        "type": 0,
                        "deny": str(CONNECT | VIEW_CHANNEL),
                        "allow": "0",
                    })
                    if mod_role:
                        overwrites.append({
                            "id": mod_role["id"],
                            "type": 0,
                            "allow": str(CONNECT | VIEW_CHANNEL | SPEAK),
                            "deny": "0",
                        })
                    if admin_role:
                        overwrites.append({
                            "id": admin_role["id"],
                            "type": 0,
                            "allow": str(CONNECT | VIEW_CHANNEL | SPEAK),
                            "deny": "0",
                        })
                elif ch_data.get("locked"):
                    overwrites.append({
                        "id": everyone_id,
                        "type": 0,
                        "deny": str(CONNECT),
                        "allow": str(VIEW_CHANNEL),
                    })
                    if vip_role:
                        overwrites.append({
                            "id": vip_role["id"],
                            "type": 0,
                            "allow": str(CONNECT | SPEAK),
                            "deny": "0",
                        })
                    if mod_role:
                        overwrites.append({
                            "id": mod_role["id"],
                            "type": 0,
                            "allow": str(CONNECT | SPEAK),
                            "deny": "0",
                        })

                if overwrites:
                    ch_payload["permission_overwrites"] = overwrites

                async with s.post(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=ch_payload) as r:
                    if r.status in (200, 201):
                        new_ch = await r.json()
                        print(f"  🔊 Created: {ch_name} (ID: {new_ch['id']}) [limit: {user_limit}]")
                    elif r.status == 429:
                        data = await r.json()
                        wait = data.get("retry_after", 1.0)
                        print(f"  ⏳ Rate limited, waiting {wait}s...")
                        await asyncio.sleep(wait)
                        async with s.post(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=ch_payload) as r2:
                            if r2.status in (200, 201):
                                new_ch = await r2.json()
                                print(f"  🔊 Created: {ch_name} (ID: {new_ch['id']}) [limit: {user_limit}]")
                    else:
                        print(f"  ⚠️ Error creating {ch_name}: {r.status} - {await r.text()}")
                await asyncio.sleep(0.35)

        # 3. Clean up category ordering
        ordered_categories = [
            "1546059369085534229",  # SERVER STATS (0)
            "1545803464712650844",  # INFORMATION (1)
            "1545803478490812578",  # COMMUNITY LOUNGE (2)
            "1554891379174416474",  # DYNAMIC VOICE ROOMS (3)
        ]

        # Fetch all channels again to include the newly created categories
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers) as r:
            all_channels = await r.json()

        cat_lookup = {c["name"]: c["id"] for c in all_channels if c["type"] == 4}

        new_cat_order = [
            "🎭 ┃ PERSONAL AREA",
            "😹 ┃ FUN VOICE CHANNELS",
            "🔱 ┃ RAI-ESP !",
            "⚜️ ┃ Checking Zone",
            "🍃 ┃ SONG ZONE",
            "🎥 ┃ THEATER",
            "🎚 ┃ EDITING ZONE",
            "🔏 ┃ PRIVATE-ZONE",
            "✌🏻 ┃ AESTHETICS",
            "🚫 ┃ HIDE CHANNELS",
        ]

        for name in new_cat_order:
            if name in cat_lookup:
                ordered_categories.append(cat_lookup[name])

        ordered_categories.extend([
            "1554891489564434677",  # HIDDEN ROOMS
            "1554891443343204494",  # STAFF & SECURITY
            "1554891470325031013",  # SYSTEM
        ])

        reorder_payload = [{"id": cid, "position": idx} for idx, cid in enumerate(ordered_categories)]
        async with s.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=reorder_payload) as r:
            print(f"\n✨ Category reordering applied: status {r.status}")

        print("\n" + "=" * 50)
        print("Voice Channel Layout deployed successfully!")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
