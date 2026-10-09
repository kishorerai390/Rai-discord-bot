"""
Assign RAI Bot to #🪤・honeypot-trap (ID: 1558168338386129004)
1. Configures strict stealth permission overwrites (Bot & Staff access, hidden from normal members).
2. Deploys the Cyberpunk Sentinel Honeypot Console to the channel.
"""

import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(r"f:\Bot\.env")

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
BOT_ID = 1554732669072445532
OWNER_ID = 1457380609641938981
STAFF_ROLE_ID = 1545494600347680918      # @👑 ╏ Council
VERIFIED_ROLE_ID = 1549504522953695269   # @✨ ╏ Verified Member
HONEYPOT_CHANNEL_ID = 1558168338386129004 # #🪤・honeypot-trap

headers = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json"
}

def assign_bot_to_honeypot():
    print(f"🔒 Assigning RAI Bot to Honeypot Channel: {HONEYPOT_CHANNEL_ID}...")

    # 1. Update Channel Overwrites
    # Permissions:
    # 1024 = VIEW_CHANNEL
    # 2048 = SEND_MESSAGES
    # 8192 = MANAGE_MESSAGES
    # 16384 = EMBED_LINKS
    # 32768 = ATTACH_FILES
    # 65536 = READ_MESSAGE_HISTORY
    overwrites = [
        {
            "id": str(GUILD_ID),  # @everyone
            "type": 0,            # Role
            "allow": "0",
            "deny": "1024"        # Deny VIEW_CHANNEL
        },
        {
            "id": str(VERIFIED_ROLE_ID), # Verified Member
            "type": 0,                   # Role
            "allow": "0",
            "deny": "1024"               # Deny VIEW_CHANNEL
        },
        {
            "id": str(BOT_ID),    # The Raivora Bot
            "type": 1,            # Member
            "allow": "268561424", # VIEW_CHANNEL, SEND_MESSAGES, EMBED_LINKS, ATTACH_FILES, READ_HISTORY, MANAGE_MESSAGES
            "deny": "0"
        },
        {
            "id": str(OWNER_ID),  # Server Owner
            "type": 1,            # Member
            "allow": "2147609600",
            "deny": "0"
        },
        {
            "id": str(STAFF_ROLE_ID), # Council Staff
            "type": 0,                # Role
            "allow": "68608",         # VIEW_CHANNEL, READ_HISTORY
            "deny": "2048"            # Deny SEND_MESSAGES for staff to prevent accidental triggers
        }
    ]

    patch_res = requests.patch(
        f"https://discord.com/api/v10/channels/{HONEYPOT_CHANNEL_ID}",
        headers=headers,
        json={
            "permission_overwrites": overwrites,
            "topic": "🔒 Autonomous Honeypot Trap | Guarded by RAI Sentinel. Unauthorized entities messaging here are banned instantly."
        }
    )

    if patch_res.status_code == 200:
        print("✅ Permissions successfully configured on #🪤・honeypot-trap.")
    else:
        print(f"⚠️ Failed to update permissions: {patch_res.status_code} - {patch_res.text}")

    # 2. Deploy Sentinel Console Panel
    console_embed = {
        "title": "🪤 『RΛI』 • STEALTH HONEYPOT DEFENSE MATRIX",
        "description": (
            "**Assigned Subsystem:** `Autonomous Honeypot Sentinel`\n\n"
            "• **Trap Classification:** Classified Perimeter Decoy\n"
            "• **Target Vector:** Rogue self-bots, unauthorized scrapers, token abusers, and raid crawlers.\n"
            "• **Autonomous Protocol:** Any unauthorized account sending any message or payload in this channel triggers an **instantaneous < 1ms ban**, 24-hour message purge, and automated critical incident alert.\n\n"
            "🛡️ **Status:** 🟢 **Assigned & Fully Operational**\n"
            "⚠️ **Warning:** Normal members should never have access to this channel. If you are reading this as staff, do not send messages here."
        ),
        "color": 0xED4245,
        "fields": [
            {
                "name": "⚡ Reaction Velocity",
                "value": "`Sub-Millisecond (< 1ms)`",
                "inline": True
            },
            {
                "name": "🔨 Enforcement",
                "value": "`Immediate Permanent Ban`",
                "inline": True
            },
            {
                "name": "📡 Telemetry Dispatch",
                "value": "`#🚨・threat-detection`",
                "inline": True
            }
        ],
        "footer": {
            "text": "RAI Autonomous Perimeter Defense • Stealth Honeypot System"
        }
    }

    # Check if a message already exists
    msgs = requests.get(f"https://discord.com/api/v10/channels/{HONEYPOT_CHANNEL_ID}/messages?limit=5", headers=headers).json()
    if isinstance(msgs, list) and len(msgs) > 0:
        msg_id = msgs[0]["id"]
        res = requests.patch(
            f"https://discord.com/api/v10/channels/{HONEYPOT_CHANNEL_ID}/messages/{msg_id}",
            headers=headers,
            json={"embeds": [console_embed]}
        )
        print(f"✅ Updated existing Honeypot Console message: {res.status_code}")
    else:
        res = requests.post(
            f"https://discord.com/api/v10/channels/{HONEYPOT_CHANNEL_ID}/messages",
            headers=headers,
            json={"embeds": [console_embed]}
        )
        print(f"✅ Deployed new Honeypot Sentinel Console: {res.status_code}")

if __name__ == "__main__":
    assign_bot_to_honeypot()
