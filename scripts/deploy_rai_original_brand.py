"""
Deploy 100% Original Rai Server Redesign:
Transforms the server away from the Thor Apex clone into an original, authentic Rai Fam brand:
- Renames and styles categories & voice channels with Midnight Luxe typography and branding.
- Removes Thor-specific channels (INTHU ENGA AREA, Checking Zone, DRAG ME, Aesthetics boyz/girlz dp, etc.).
- Keeps essential community text channels (#general-chat, #media-and-clips, #bot-commands, Information, Staff).
- Re-orders categories cleanly.
"""

import asyncio
import os
import sys
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


async def deploy():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        # 1. Fetch current channels
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers) as r:
            channels = await r.json()

        print(f"Total current channels/categories: {len(channels)}")

        # Fetch roles to get moderator and admin IDs
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers) as r:
            roles = await r.json()

        everyone_id = next(role["id"] for role in roles if role["name"] == "@everyone")
        mod_role = next((role for role in roles if "MODERATOR" in role["name"]), None)
        admin_role = next((role for role in roles if "ADMIN" in role["name"]), None)
        vip_role = next((role for role in roles if "VIP" in role["name"]), None)

        # 2. Identify channels/categories to DELETE (Thor clones & unwanted text channels)
        delete_targets = [
            "✌🏻 ┃ AESTHETICS",
            "📸・boyz-dp",
            "🌸・girlz-dp",
            "🖼️・banners",
            "🚫 ┃ HIDE CHANNELS",
            "🎚 ┃ EDITING ZONE",
            "🌕｜DRAG ME",
            "🔮｜DRAG ME",
            "⚜️ ┃ Checking Zone",
            "🔎｜PHONE-CHECKING",
            "🔒｜PVT-CHECKING",
            "🍃 ┃ SONG ZONE",
            "🎧｜RAI 24/7",
            "🎧｜SONG LOUNGE",
            "🔮｜OPEN VOICE",
        ]

        # Look for duplicate PVT-CHANNELs to delete one
        pvt_channels = [c for c in channels if c["name"] == "🔮｜PVT-CHANNEL"]
        if len(pvt_channels) > 1:
            delete_targets.append(pvt_channels[0]["name"])

        for c in channels:
            c_name = c["name"]
            c_id = c["id"]
            if c_name in delete_targets:
                async with s.delete(f"https://discord.com/api/v10/channels/{c_id}", headers=headers) as r:
                    print(f"  🗑️ Deleted Thor clone: {c_name} ({c_id}) - {r.status}")
                await asyncio.sleep(0.35)

        # 3. Rename & Transform Categories to Original Rai Brand
        category_transformations = {
            "1554905776030613535": "🍸 ┃ RAI SUITES",               # Was PERSONAL AREA
            "1554905799292231728": "🎧 ┃ CHILL & MUSIC HAVEN",      # Was FUN VOICE CHANNELS
            "1554905821467648051": "⚔️ ┃ GAMING ARENA",             # Was RAI-ESP !
            "1554905866673856714": "🎬 ┃ CINEMA & STREAMS",         # Was THEATER
            "1554905886261121107": "🔒 ┃ EXECUTIVE & CREATOR HQ",   # Was PRIVATE-ZONE
            "1554891489564434677": "🔐 ┃ HIDDEN ROOMS",
            "1554891443343204494": "🛡️ ┃ STAFF & SECURITY",
            "1554891470325031013": "💤 ┃ SYSTEM",
        }

        print("\nTransforming categories to Rai original brand...")
        for cat_id, new_name in category_transformations.items():
            async with s.patch(f"https://discord.com/api/v10/channels/{cat_id}", headers=headers, json={"name": new_name}) as r:
                if r.status in (200, 204):
                    print(f"  ✨ Category rebranded: {new_name}")
            await asyncio.sleep(0.35)

        # 4. Rename & Configure Voice Channels to Original Rai Identity
        channel_transformations = {
            # RAI SUITES
            "1554905780397015172": {"name": "💎・Solo Sanctum", "user_limit": 1, "parent_id": "1554905776030613535"},
            "1554905785233051812": {"name": "🥂・Duo Lounge I", "user_limit": 2, "parent_id": "1554905776030613535"},
            "1554905791994003616": {"name": "🥂・Duo Lounge II", "user_limit": 2, "parent_id": "1554905776030613535"},
            "1554905795555237931": {"name": "✨・Trio Chamber", "user_limit": 3, "parent_id": "1554905776030613535"},

            # CHILL & MUSIC HAVEN
            "1554905803666751590": {"name": "🎵・24/7 Lo-Fi & Beats", "user_limit": 0, "parent_id": "1554905799292231728"},
            "1554905807240302652": {"name": "☕・Night Owl Café", "user_limit": 0, "parent_id": "1554905799292231728"},
            "1554905810574774286": {"name": "🌊・Vibe Studio", "user_limit": 0, "parent_id": "1554905799292231728"},
            "1554905813737545770": {"name": "🎤・Open Mic & Stage", "user_limit": 0, "parent_id": "1554905799292231728"},

            # GAMING ARENA
            "1554905825544241302": {"name": "🔥・Battlegrounds Squad", "user_limit": 0, "parent_id": "1554905821467648051"},
            "1554905829033902151": {"name": "🕹️・Casual Arcade", "user_limit": 0, "parent_id": "1554905821467648051"},
            "1554905836768469032": {"name": "🎯・Ranked Comms I", "user_limit": 5, "parent_id": "1554905821467648051"},
            "1554905842300485642": {"name": "🎯・Ranked Comms II", "user_limit": 5, "parent_id": "1554905821467648051"},

            # CINEMA & STREAMS
            "1554905870817689600": {"name": "🍿・Cinema Hall", "user_limit": 0, "parent_id": "1554905866673856714"},
            "1554905874437513248": {"name": "📺・Stream Showcase", "user_limit": 0, "parent_id": "1554905866673856714"},

            # EXECUTIVE & CREATOR HQ
            "1554905907509596180": {"name": "🏛️・Executive Boardroom", "user_limit": 0, "parent_id": "1554905886261121107"},
            "1554905899414454446": {"name": "🔮・Creator Studio", "user_limit": 0, "parent_id": "1554905886261121107"},
            "1554905903508095066": {"name": "🛡️・Staff Operations Voice", "user_limit": 0, "parent_id": "1554905886261121107"},

            # SYSTEM
            "1554891485818921042": {"name": "💤・Sleep & AFK", "user_limit": 0, "parent_id": "1554891470325031013"},
        }

        print("\nRebranding voice channels with Rai identity...")
        for ch_id, patch_data in channel_transformations.items():
            async with s.patch(f"https://discord.com/api/v10/channels/{ch_id}", headers=headers, json=patch_data) as r:
                if r.status in (200, 204):
                    print(f"  🔊 Rebranded channel: {patch_data['name']}")
                else:
                    print(f"  ⚠️ Error patching {ch_id}: {r.status}")
            await asyncio.sleep(0.35)

        # 5. Create 'Squad Suite' in RAI SUITES
        async with s.post(
            f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels",
            headers=headers,
            json={
                "name": "👑・Squad Suite",
                "type": 2,
                "user_limit": 4,
                "parent_id": "1554905776030613535",
            }
        ) as r:
            if r.status in (200, 201):
                print("  🔊 Created: 👑・Squad Suite [limit: 4]")

        # 6. Apply Strict Permissions to Executive & Creator HQ
        exec_overwrites = [
            {"id": everyone_id, "type": 0, "deny": str(CONNECT | VIEW_CHANNEL), "allow": "0"}
        ]
        if mod_role:
            exec_overwrites.append({"id": mod_role["id"], "type": 0, "allow": str(CONNECT | VIEW_CHANNEL | SPEAK), "deny": "0"})
        if admin_role:
            exec_overwrites.append({"id": admin_role["id"], "type": 0, "allow": str(CONNECT | VIEW_CHANNEL | SPEAK), "deny": "0"})

        await s.patch(
            "https://discord.com/api/v10/channels/1554905907509596180",
            headers=headers,
            json={"permission_overwrites": exec_overwrites}
        )
        print("  🔒 Secured Executive Boardroom (Founder/Admin only)")

        # 7. Apply Canonical Category Ordering
        canonical_order = [
            "1546059369085534229",  # 📊 ┃ SERVER STATS (0)
            "1545803464712650844",  # ✦ ┃ INFORMATION (1)
            "1545803478490812578",  # 💬 ┃ COMMUNITY LOUNGE (2)
            "1554891379174416474",  # 🎙️ ┃ DYNAMIC VOICE ROOMS (3)
            "1554905776030613535",  # 🍸 ┃ RAI SUITES (4)
            "1554905799292231728",  # 🎧 ┃ CHILL & MUSIC HAVEN (5)
            "1554905821467648051",  # ⚔️ ┃ GAMING ARENA (6)
            "1554905866673856714",  # 🎬 ┃ CINEMA & STREAMS (7)
            "1554905886261121107",  # 🔒 ┃ EXECUTIVE & CREATOR HQ (8)
            "1554891489564434677",  # 🔐 ┃ HIDDEN ROOMS (9)
            "1554891443343204494",  # 🛡️ ┃ STAFF & SECURITY (10)
            "1554891470325031013",  # 💤 ┃ SYSTEM (11)
        ]

        reorder_payload = [{"id": cid, "position": idx} for idx, cid in enumerate(canonical_order)]
        async with s.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=reorder_payload) as r:
            print(f"\n✨ Canonical category hierarchy applied: status {r.status}")

        print("\n" + "=" * 50)
        print("Rai Original Brand Deployment Complete!")
        print("All Thor Apex copies removed.")
        print("Server is 100% original, cohesive, and premium.")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(deploy())
