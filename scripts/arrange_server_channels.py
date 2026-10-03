"""
Arrange and Clean Server Channel Hierarchy:
1. Sequentially normalizes every category position (0 to 11).
2. Sequentially normalizes every child channel position inside each category (0, 1, 2...).
3. Configures official Guild Settings:
   - afk_channel_id -> 💤・Sleep & AFK
   - system_channel_id -> 🌸｜ᴡᴇʟᴄᴏᴍᴇ
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

# Target Arrangement Order
CATEGORY_ORDER = [
    "1546059369085534229",  # 0: 📊 ┃ SERVER STATS
    "1545803464712650844",  # 1: ✦ ┃ INFORMATION
    "1545803478490812578",  # 2: 💬 ┃ COMMUNITY LOUNGE
    "1554891379174416474",  # 3: 🎙️ ┃ DYNAMIC VOICE ROOMS
    "1554905776030613535",  # 4: 🍸 ┃ RAI SUITES
    "1554905799292231728",  # 5: 🎧 ┃ CHILL & MUSIC HAVEN
    "1554905821467648051",  # 6: ⚔️ ┃ GAMING ARENA
    "1554905866673856714",  # 7: 🎬 ┃ CINEMA & STREAMS
    "1554905886261121107",  # 8: 🔒 ┃ EXECUTIVE & CREATOR HQ
    "1554891489564434677",  # 9: 🔐 ┃ HIDDEN ROOMS
    "1554891443343204494",  # 10: 🛡️ ┃ STAFF & SECURITY
    "1554891470325031013",  # 11: 💤 ┃ SYSTEM
]

# Specific Channel Ordering per Category
CHANNEL_ORDER_PER_CATEGORY = {
    # 0: SERVER STATS
    "1546059369085534229": [
        "1546099701496029194",  # All Members
        "1546099703630798848",  # Members
        "1546059375574130769",  # Bots
    ],
    # 1: INFORMATION
    "1545803464712650844": [
        "1545502700840427702",  # ✨｜ᴠᴇʀɪꜰʏ-ʜᴇʀᴇ (Pos 0)
        "1545502705643167876",  # 🌸｜ᴡᴇʟᴄᴏᴍᴇ
        "1545502710101704714",  # 📜｜ʀᴜʟᴇꜱ-ᴀɴᴅ-ɪɴꜰᴏ
        "1545502718792175646",  # 📢｜ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛꜱ
        "1545502722739150898",  # 🏷️｜ʀᴏʟᴇꜱ
    ],
    # 2: COMMUNITY LOUNGE
    "1545803478490812578": [
        "1545502730699808768",  # 💬｜ɢᴇɴᴇʀᴀʟ-ᴄʜᴀᴛ
        "1551184138932068373",  # 📸｜ᴍᴇᴅɪᴀ-ᴀɴᴅ-ᴄʟɪᴘꜱ
        "1549416359723532480",  # 🤖｜ʙᴏᴛ-ᴄᴏᴍᴍᴀɴᴅꜱ
    ],
    # 3: DYNAMIC VOICE ROOMS
    "1554891379174416474": [
        "1554891383117193307",  # ➕・CREATE YOUR ROOM
        "1554891386577485927",  # 🔐・CREATE PRIVATE ROOM
    ],
    # 4: RAI SUITES
    "1554905776030613535": [
        "1554905780397015172",  # 💎・Solo Sanctum
        "1554905785233051812",  # 🥂・Duo Lounge I
        "1554905791994003616",  # 🥂・Duo Lounge II
        "1554905795555237931",  # ✨・Trio Chamber
        "1554909104760422430",  # 👑・Squad Suite
    ],
    # 5: CHILL & MUSIC HAVEN
    "1554905799292231728": [
        "1554905803666751590",  # 🎵・24/7 Lo-Fi & Beats
        "1554905807240302652",  # ☕・Night Owl Café
        "1554905810574774286",  # 🌊・Vibe Studio
        "1554905813737545770",  # 🎤・Open Mic & Stage
    ],
    # 6: GAMING ARENA
    "1554905821467648051": [
        "1554905825544241302",  # 🔥・Battlegrounds Squad
        "1554905836768469032",  # 🎯・Ranked Comms I
        "1554905842300485642",  # 🎯・Ranked Comms II
        "1554905829033902151",  # 🕹️・Casual Arcade
    ],
    # 7: CINEMA & STREAMS
    "1554905866673856714": [
        "1554905870817689600",  # 🍿・Cinema Hall
        "1554905874437513248",  # 📺・Stream Showcase
    ],
    # 8: EXECUTIVE & CREATOR HQ
    "1554905886261121107": [
        "1554905907509596180",  # 🏛️・Executive Boardroom
        "1554905899414454446",  # 🔮・Creator Studio
        "1554905903508095066",  # 🛡️・Staff Operations Voice
    ],
    # 10: STAFF & SECURITY
    "1554891443343204494": [
        "1545502845208629328",  # 🛡️｜ꜱᴛᴀꜰꜰ-ᴏᴘᴇʀᴀᴛɪᴏɴꜱ
        "1554891431393370144",  # 🎫・support
        "1554891451140149352",  # 📋・moderation-log
        "1554891455003107338",  # 🛡️・security-log
    ],
    # 11: SYSTEM
    "1554891470325031013": [
        "1554891485818921042",  # 💤・Sleep & AFK
    ],
}


async def arrange():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        # 1. Arrange Categories
        print("Arranging category positions...")
        cat_payload = [{"id": cat_id, "position": idx} for idx, cat_id in enumerate(CATEGORY_ORDER)]
        async with s.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=cat_payload) as r:
            print(f"Categories arranged: status {r.status}")
        await asyncio.sleep(0.5)

        # 2. Arrange Channels inside each Category
        print("Arranging channels inside categories...")
        channel_payload = []
        for cat_id, ch_ids in CHANNEL_ORDER_PER_CATEGORY.items():
            for idx, ch_id in enumerate(ch_ids):
                channel_payload.append({"id": ch_id, "position": idx, "parent_id": cat_id})

        # Send in chunks of 20 to avoid payload limits
        chunk_size = 20
        for i in range(0, len(channel_payload), chunk_size):
            chunk = channel_payload[i : i + chunk_size]
            async with s.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=chunk) as r:
                print(f"  Batch {i // chunk_size + 1} applied: status {r.status}")
            await asyncio.sleep(0.4)

        # 3. Configure Guild Settings (AFK channel & System Welcome channel)
        print("Configuring official guild settings...")
        guild_settings = {
            "afk_channel_id": "1554891485818921042",  # 💤・Sleep & AFK
            "afk_timeout": 300,                       # 5 minutes
            "system_channel_id": "1545502705643167876",  # 🌸｜ᴡᴇʟᴄᴏᴍᴇ
        }
        async with s.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}", headers=headers, json=guild_settings) as r:
            print(f"Guild AFK & Welcome channels updated: status {r.status}")

        print("\n" + "=" * 50)
        print("Server channels and categories arranged flawlessly!")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(arrange())
