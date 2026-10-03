import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "f:/Bot")

import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_GUILD_ID = 1457382179981099090

# Critical channel IDs that MUST be preserved
PRESERVE_CHANNEL_IDS = {
    # Stats Counters
    "1546099701496029194",  # All Members
    "1546099703630798848",  # Members
    "1546059375574130769",  # Bots

    # Information Channels
    "1545502700840427702",  # ✨｜ᴠᴇʀɪꜰʏ-ʜᴇʀᴇ
    "1545502705643167876",  # 🌸｜ᴡᴇʟᴄᴏᴍᴇ
    "1545502710101704714",  # 📜｜ʀᴜʟᴇꜱ-ᴀɴᴅ-ɪɴꜰᴏ
    "1545502718792175646",  # 📢｜ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛꜱ
    "1545502722739150898",  # 🏷️｜ʀᴏʟᴇꜱ

    # Community Lounge
    "1545502730699808768",  # 💬｜ɢᴇɴᴇʀᴀʟ-ᴄʜᴀᴛ
    "1551184138932068373",  # 📸｜ᴍᴇᴅɪᴀ-ᴀɴᴅ-ᴄʟɪᴘꜱ
    "1549416359723532480",  # 🤖｜ʙᴏᴛ-ᴄᴏᴍᴍᴀɴᴅꜱ

    # Dynamic Voice Rooms
    "1554891383117193307",  # ➕・CREATE YOUR ROOM
    "1554891386577485927",  # 🔐・CREATE PRIVATE ROOM

    # Staff & System
    "1554891455003107338",  # 🛡️・security-log
    "1554891451140149352",  # 📋・moderation-log
    "1554891431393370144",  # 🎫・support
    "1554891485818921042",  # 💤・AFK
}

# Categories to preserve
PRESERVE_CATEGORY_IDS = {
    "1546059369085534229",  # 📊 SERVER STATS 📊
    "1545803464712650844",  # ✦ ┃ 𝙄𝙉𝙁𝙊𝙍𝙈𝘼𝙏𝙄𝙊𝙉
    "1545803478490812578",  # 💬 ┃ 𝘾𝙊𝙈𝙈𝙐𝙉𝙄𝙏𝙔
    "1554891379174416474",  # 👤 ┃ DYNAMIC VOICE ROOMS
    "1554891489564434677",  # 🔐 ┃ HIDDEN ROOMS
    "1554891443343204494",  # 🛡️ ┃ STAFF & SECURITY
    "1554891470325031013",  # 💤 ┃ SYSTEM
}

async def deploy():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        # 1. Fetch current channels
        async with session.get(f"https://discord.com/api/v10/guilds/{TARGET_GUILD_ID}/channels", headers=headers) as resp:
            channels = await resp.json()

        print(f"Total starting channels & categories: {len(channels)}")

        # Identify channels to delete
        channels_to_delete = []
        categories_to_delete = []

        for c in channels:
            c_id = str(c.get("id"))
            c_type = c.get("type")
            if c_type == 4:
                # Category
                if c_id not in PRESERVE_CATEGORY_IDS:
                    categories_to_delete.append(c)
            else:
                # Text or Voice
                if c_id not in PRESERVE_CHANNEL_IDS:
                    channels_to_delete.append(c)

        print(f"Targeting {len(channels_to_delete)} extra channels and {len(categories_to_delete)} categories for removal.")

        # 2. Delete non-preserved channels first
        deleted_ch = 0
        for c in channels_to_delete:
            c_id = c.get("id")
            c_name = c.get("name")
            async with session.delete(f"https://discord.com/api/v10/channels/{c_id}", headers=headers) as r:
                if r.status in (200, 204):
                    print(f"  🗑️ Deleted: {c_name} ({c_id})")
                    deleted_ch += 1
                elif r.status == 429:
                    retry_data = await r.json()
                    wait_sec = retry_data.get("retry_after", 1.0)
                    print(f"  ⏳ Rate limited, waiting {wait_sec}s...")
                    await asyncio.sleep(wait_sec)
                    async with session.delete(f"https://discord.com/api/v10/channels/{c_id}", headers=headers) as r2:
                        if r2.status in (200, 204):
                            deleted_ch += 1
                else:
                    print(f"  ⚠️ Error deleting {c_name}: {r.status}")
            await asyncio.sleep(0.35)

        # 3. Delete non-preserved categories
        deleted_cat = 0
        for c in categories_to_delete:
            c_id = c.get("id")
            c_name = c.get("name")
            async with session.delete(f"https://discord.com/api/v10/channels/{c_id}", headers=headers) as r:
                if r.status in (200, 204):
                    print(f"  📁 Deleted Category: {c_name} ({c_id})")
                    deleted_cat += 1
                elif r.status == 429:
                    retry_data = await r.json()
                    wait_sec = retry_data.get("retry_after", 1.0)
                    await asyncio.sleep(wait_sec)
                    async with session.delete(f"https://discord.com/api/v10/channels/{c_id}", headers=headers) as r2:
                        if r2.status in (200, 204):
                            deleted_cat += 1
                else:
                    print(f"  ⚠️ Error deleting category {c_name}: {r.status}")
            await asyncio.sleep(0.35)

        # 4. Polish Category Names with Midnight Luxe theme
        theme_names = {
            "1546059369085534229": "📊 ┃ SERVER STATS",
            "1545803464712650844": "✦ ┃ INFORMATION",
            "1545803478490812578": "💬 ┃ COMMUNITY LOUNGE",
            "1554891379174416474": "👤 ┃ DYNAMIC VOICE ROOMS",
            "1554891489564434677": "🔐 ┃ HIDDEN ROOMS",
            "1554891443343204494": "🛡️ ┃ STAFF & SECURITY",
            "1554891470325031013": "💤 ┃ SYSTEM",
        }

        print("\nApplying Midnight Luxe Category Titles...")
        for cat_id, new_name in theme_names.items():
            async with session.patch(
                f"https://discord.com/api/v10/channels/{cat_id}",
                headers=headers,
                json={"name": new_name}
            ) as r:
                if r.status in (200, 204):
                    print(f"  ✨ Renamed category: {new_name}")
            await asyncio.sleep(0.35)

        # Move support channel to staff category if needed
        async with session.patch(
            f"https://discord.com/api/v10/channels/1554891431393370144",
            headers=headers,
            json={"parent_id": "1554891443343204494"}
        ) as r:
            if r.status in (200, 204):
                print("  📌 Attached #ticket-support to Staff & Security category")

        print("\n" + "=" * 50)
        print(f"Midnight Luxe Deployment Complete!")
        print(f"Deleted {deleted_ch} extra channels and {deleted_cat} bloated categories.")
        print(f"The server is now streamlined to ~15 core high-traffic channels.")
        print("=" * 50)

if __name__ == "__main__":
    asyncio.run(deploy())
