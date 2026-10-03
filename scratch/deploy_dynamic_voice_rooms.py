import os
import sys
import requests
import json
import sqlite3
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv("f:/Bot/.env")
token = os.getenv("DISCORD_TOKEN")
guild_id = 1457382179981099090
headers = {
    "Authorization": f"Bot {token}",
    "Content-Type": "application/json"
}

print(f"=== DEPLOYING DYNAMIC VOICE ROOMS & ROOM-CONTROL IN GUILD {guild_id} ===")

# 1. Fetch current channels
res = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers)
channels = res.json()

dynamic_cat = None
for c in channels:
    if c.get("type") == 4 and "DYNAMIC VOICE ROOMS" in c.get("name", "").upper():
        dynamic_cat = c
        break

if not dynamic_cat:
    # Create category
    payload = {
        "name": "🔊 | DYNAMIC VOICE ROOMS",
        "type": 4
    }
    r = requests.post(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, json=payload)
    dynamic_cat = r.json()
    print(f"Created category: {dynamic_cat.get('name')} ({dynamic_cat.get('id')})")
else:
    print(f"Found existing dynamic category: {dynamic_cat.get('name')} ({dynamic_cat.get('id')})")
    # Update category name if needed to '🔊 | DYNAMIC VOICE ROOMS'
    if dynamic_cat.get("name") != "🔊 | DYNAMIC VOICE ROOMS":
        requests.patch(f"https://discord.com/api/v10/channels/{dynamic_cat['id']}", headers=headers, json={"name": "🔊 | DYNAMIC VOICE ROOMS"})
        print("Updated category name to: 🔊 | DYNAMIC VOICE ROOMS")

cat_id = dynamic_cat["id"]

# 2. Check trigger voice channels & room-control
public_hub = None
private_hub = None
room_control = None

for c in channels:
    if c.get("parent_id") == cat_id:
        name = c.get("name", "")
        ctype = c.get("type")
        if ctype == 2:  # Voice
            if "CREATE YOUR ROOM" in name.upper():
                public_hub = c
            elif "CREATE PRIVATE ROOM" in name.upper():
                private_hub = c
        elif ctype == 0:  # Text
            if "ROOM-CONTROL" in name.upper():
                room_control = c

# Rename or create public hub
if not public_hub:
    payload = {
        "name": "🔊・CREATE YOUR ROOM",
        "type": 2,
        "parent_id": cat_id,
        "user_limit": 1
    }
    r = requests.post(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, json=payload)
    public_hub = r.json()
    print(f"Created public hub: {public_hub.get('name')} ({public_hub.get('id')})")
else:
    print(f"Found public hub: {public_hub.get('name')} ({public_hub.get('id')})")
    if public_hub.get("name") != "🔊・CREATE YOUR ROOM":
        requests.patch(f"https://discord.com/api/v10/channels/{public_hub['id']}", headers=headers, json={"name": "🔊・CREATE YOUR ROOM"})
        print("Renamed public hub to: 🔊・CREATE YOUR ROOM")

# Check private hub
if not private_hub:
    payload = {
        "name": "🔐・CREATE PRIVATE ROOM",
        "type": 2,
        "parent_id": cat_id,
        "user_limit": 1
    }
    r = requests.post(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, json=payload)
    private_hub = r.json()
    print(f"Created private hub: {private_hub.get('name')} ({private_hub.get('id')})")
else:
    print(f"Found private hub: {private_hub.get('name')} ({private_hub.get('id')})")

# 3. Create or verify 🛠️・ROOM-CONTROL text channel
if not room_control:
    payload = {
        "name": "🛠️・room-control",
        "type": 0,
        "parent_id": cat_id,
        "topic": "Central Control Panel for Temporary Dynamic Voice Rooms",
        "permission_overwrites": [
            {
                "id": str(guild_id),  # @everyone
                "type": 0,
                "allow": "66560",  # View Channel (1024) + Read Message History (65536)
                "deny": "2048"     # Send Messages
            }
        ]
    }
    r = requests.post(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, json=payload)
    room_control = r.json()
    print(f"Created central control channel: {room_control.get('name')} ({room_control.get('id')})")
else:
    print(f"Found central control channel: {room_control.get('name')} ({room_control.get('id')})")

# 4. Update SQLite database configuration
conn = sqlite3.connect("f:/Bot/data/bot.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Update temp_voice_config
cur.execute("""
    INSERT INTO temp_voice_config (guild_id, enabled, hub_channel_id, category_id, default_user_limit, updated_at)
    VALUES (?, 1, ?, ?, 0, datetime('now'))
    ON CONFLICT(guild_id) DO UPDATE SET
        enabled = 1,
        hub_channel_id = excluded.hub_channel_id,
        category_id = excluded.category_id,
        updated_at = excluded.updated_at
""", (guild_id, int(public_hub["id"]), int(cat_id)))
conn.commit()
print("Updated SQLite temp_voice_config successfully.")

# 5. Post Welcome / Instructions Embed in 🛠️・room-control
embed_payload = {
    "embeds": [
        {
            "title": "🛠️ DYNAMIC VOICE ROOM CONTROL CENTER",
            "description": (
                "Welcome to the central control panel for **Dynamic Voice Rooms**.\n\n"
                "**How It Works:**\n"
                "• Join **🔊・CREATE YOUR ROOM** to spawn a public room.\n"
                "• Join **🔐・CREATE PRIVATE ROOM** to spawn an owner-only private room.\n"
                "• Rai will immediately move you into your new room and post an interactive control panel right here.\n\n"
                "**Available Room Controls:**\n"
                "✏️ **Rename** — Give your room a custom name\n"
                "🔐 **Privacy** — Switch between Public, Locked, Invite-Only, and Owner-Only\n"
                "👥 **Members** — Invite friends, remove members, or moderate voice\n"
                "🔢 **User Limit** — Set occupant limit (0 for Unlimited)\n"
                "🎨 **Customize** — Apply instant templates (Gaming, Chill, Music, Creator, etc.)\n"
                "👑 **Transfer Owner** — Hand room ownership to another occupant\n"
                "🔇 **Mute / Disconnect** — Server mute or disconnect occupants\n"
                "🧹 **Clear Room** — Disconnect all other members\n"
                "🗑️ **Delete Room** — Close and delete the temporary voice room\n\n"
                "*All room controls strictly target your own room with zero cross-room interference. "
                "Responses are ephemeral and visible only to you.*"
            ),
            "color": 0x5865F2,
            "footer": {
                "text": "Rai Dynamic Voice Sentinel • Interactive Operations"
            }
        }
    ]
}

requests.post(f"https://discord.com/api/v10/channels/{room_control['id']}/messages", headers=headers, json=embed_payload)
print(f"Posted control center guide in {room_control.get('name')} ({room_control['id']})")
print("=== DEPLOYMENT COMPLETE ===")
