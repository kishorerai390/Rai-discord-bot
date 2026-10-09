import asyncio
import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
headers = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json"
}

CATEGORY_ID = 1554891379174416474
VOICE_HUB_ID = 1557461916144767046
ROOM_CTRL_ID = 1555459478155960421

VERIFIED_ROLE_ID = 1549504522953695269   # ✨ ╏ 𝓥ᴇʀɪғɪᴇᴅ 𝕸ᴇᴍʙᴇʀ
RAI_FAM_ROLE_ID = 1545494584203673740    # 💖 ╏ 𝓡ᴀɪ 𝕱ᴀᴍ
EVERYONE_ID = GUILD_ID

VIEW_CHANNEL = 1024
CONNECT = 1048576
SPEAK = 2097152
SEND_MESSAGES = 2048
READ_HISTORY = 65536

VOICE_ALLOW = VIEW_CHANNEL | CONNECT | SPEAK | READ_HISTORY
TEXT_ALLOW = VIEW_CHANNEL | READ_HISTORY

print("=" * 60)
print("✦ FIXING JOIN-TO-CREATE VC VISIBILITY & PERMISSIONS ✦")
print("=" * 60)

# 1. Update Category ✧ ᴘʀɪᴠᴀᴛᴇ ᴠᴏɪᴄᴇ ✧ Overwrites
print("\n[STEP 1] Configuring Category Overwrites...")
# @everyone: DENY VIEW_CHANNEL
requests.put(
    f"https://discord.com/api/v10/channels/{CATEGORY_ID}/permissions/{EVERYONE_ID}",
    headers=headers,
    json={"id": str(EVERYONE_ID), "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL)}
)
# Verified Member: ALLOW VIEW_CHANNEL, CONNECT, SPEAK
requests.put(
    f"https://discord.com/api/v10/channels/{CATEGORY_ID}/permissions/{VERIFIED_ROLE_ID}",
    headers=headers,
    json={"id": str(VERIFIED_ROLE_ID), "type": 0, "allow": str(VOICE_ALLOW), "deny": "0"}
)
# Rai Fam: ALLOW VIEW_CHANNEL, CONNECT, SPEAK
requests.put(
    f"https://discord.com/api/v10/channels/{CATEGORY_ID}/permissions/{RAI_FAM_ROLE_ID}",
    headers=headers,
    json={"id": str(RAI_FAM_ROLE_ID), "type": 0, "allow": str(VOICE_ALLOW), "deny": "0"}
)
print("  ✅ Category ✧ ᴘʀɪᴠᴀᴛᴇ ᴠᴏɪᴄᴇ ✧ permissions granted to Verified Member & Rai Fam.")

# 2. Update Channel ➕・Join to Create Overwrites
print("\n[STEP 2] Configuring ➕・Join to Create Voice Channel Overwrites...")
# @everyone: DENY VIEW_CHANNEL & CONNECT
requests.put(
    f"https://discord.com/api/v10/channels/{VOICE_HUB_ID}/permissions/{EVERYONE_ID}",
    headers=headers,
    json={"id": str(EVERYONE_ID), "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL | CONNECT)}
)
# Verified Member: ALLOW FULL VOICE ACCESS
requests.put(
    f"https://discord.com/api/v10/channels/{VOICE_HUB_ID}/permissions/{VERIFIED_ROLE_ID}",
    headers=headers,
    json={"id": str(VERIFIED_ROLE_ID), "type": 0, "allow": str(VOICE_ALLOW), "deny": "0"}
)
# Rai Fam: ALLOW FULL VOICE ACCESS
requests.put(
    f"https://discord.com/api/v10/channels/{VOICE_HUB_ID}/permissions/{RAI_FAM_ROLE_ID}",
    headers=headers,
    json={"id": str(RAI_FAM_ROLE_ID), "type": 0, "allow": str(VOICE_ALLOW), "deny": "0"}
)
print("  ✅ ➕・Join to Create explicitly visible and joinable for Verified & Rai Fam!")

# 3. Update Channel 🛠️・ʀᴏᴏᴍ-ᴄᴏɴᴛʀᴏʟ Overwrites
print("\n[STEP 3] Configuring 🛠️・ʀᴏᴏᴍ-ᴄᴏɴᴛʀᴏʟ Overwrites...")
# Verified Member: ALLOW VIEW, DENY SEND (Buttons only)
requests.put(
    f"https://discord.com/api/v10/channels/{ROOM_CTRL_ID}/permissions/{VERIFIED_ROLE_ID}",
    headers=headers,
    json={"id": str(VERIFIED_ROLE_ID), "type": 0, "allow": str(TEXT_ALLOW), "deny": str(SEND_MESSAGES)}
)
# Rai Fam: ALLOW VIEW, DENY SEND (Buttons only)
requests.put(
    f"https://discord.com/api/v10/channels/{ROOM_CTRL_ID}/permissions/{RAI_FAM_ROLE_ID}",
    headers=headers,
    json={"id": str(RAI_FAM_ROLE_ID), "type": 0, "allow": str(TEXT_ALLOW), "deny": str(SEND_MESSAGES)}
)
print("  ✅ 🛠️・ʀᴏᴏᴍ-ᴄᴏɴᴛʀᴏʟ visible for Verified Member & Rai Fam.")

# 4. Update Database Configuration for temp_voice_configs
print("\n[STEP 4] Updating Database temp_voice_configs...")
sys.path.insert(0, "F:/Bot")
from database.database import Database

async def update_db():
    db = Database("data/bot.db")
    await db.connect()
    await db.update_temp_voice_config(
        guild_id=GUILD_ID,
        enabled=True,
        hub_channel_id=VOICE_HUB_ID,
        category_id=CATEGORY_ID,
    )
    print("  ✅ Database updated with hub_channel_id = 1557461916144767046!")
    await db._db.close()

asyncio.run(update_db())

print("\n" + "=" * 60)
print("✦ JOIN-TO-CREATE VC VISIBILITY AND AUTO-TRIGGER REPAIRED! ✦")
print("=" * 60)
