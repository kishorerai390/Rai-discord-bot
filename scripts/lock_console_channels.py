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

# Target Read-Only / Interactive-Only Console Channels
CONSOLE_CHANNELS = {
    "welcome": 1545502705643167876,      # #🌸・WELCOME
    "rules": 1545502710101704714,        # #📜・RULES
    "support": 1555641079137706014,      # #🎟・SUPPORT-DESK
    "pods": 1555641081578782840,         # #💤・SLEEPING-PODS
    "room_ctrl": 1555459478155960421,    # #🛠️・ROOM-CONTROL
    "queue": 1555283393242206301,        # #📜・MUSIC-QUEUE
    "dj_ctrl": 1555283394274005092,      # #🔊・DJ-CONTROL
    "playlists": 1555283395330842714,    # #💿・PLAYLISTS
}

SEND_MESSAGES_FLAG = 2048        # 0x800
VIEW_CHANNEL_FLAG = 1024         # 0x400
READ_HISTORY_FLAG = 65536        # 0x10000

print("=" * 60)
print("✦ SECURING CONSOLE CHANNELS PERMISSIONS ✦")
print("=" * 60)

for name, ch_id in CONSOLE_CHANNELS.items():
    # Fetch existing overwrites
    r = requests.get(f"https://discord.com/api/v10/channels/{ch_id}", headers=headers)
    if r.status_code != 200:
        print(f"  ⚠️ Channel {name} ({ch_id}) not found")
        continue

    cdata = r.json()
    overwrites = cdata.get("permission_overwrites", [])
    everyone_ow = next((ow for ow in overwrites if ow["id"] == str(GUILD_ID)), None)

    current_deny = int(everyone_ow.get("deny", 0)) if everyone_ow else 0
    current_allow = int(everyone_ow.get("allow", 0)) if everyone_ow else 0

    new_deny = current_deny | SEND_MESSAGES_FLAG
    new_allow = (current_allow | VIEW_CHANNEL_FLAG | READ_HISTORY_FLAG) & ~SEND_MESSAGES_FLAG

    put_r = requests.put(
        f"https://discord.com/api/v10/channels/{ch_id}/permissions/{GUILD_ID}",
        headers=headers,
        json={
            "id": str(GUILD_ID),
            "type": 0,
            "allow": str(new_allow),
            "deny": str(new_deny),
        }
    )
    if put_r.status_code in (200, 204):
        print(f"  🔒 #{cdata['name']}: Send Messages DENIED for @everyone (Consoles Protected)")
    else:
        print(f"  ⚠️ Could not update #{cdata['name']}: {put_r.status_code}")

print("\n" + "=" * 60)
print("✦ CONSOLE PERMISSIONS HARDENED SUCCESSFULLY! ✦")
print("=" * 60)
