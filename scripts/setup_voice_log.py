"""
Setup and initialize #🎙️・voice-log in RAI FAM:
1. Creates #🎙️・voice-log under '🛡️ ┃ STAFF & SECURITY' (1554891443343204494).
2. Sets permissions: Locked for @everyone, visible to Staff & Admins.
3. Updates logging_config in data/bot.db (voice_channel_id).
4. Deploys the official Voice Logging Matrix Header.
"""

import os
import aiohttp
import asyncio
import sqlite3
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
STAFF_CAT_ID = 1554891443343204494

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

async def create_voice_log_channel(session: aiohttp.ClientSession) -> int:
    # Check if channel already exists
    url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels"
    async with session.get(url, headers=HEADERS) as r:
        chs = await r.json()
        for c in chs:
            if "voice-log" in c.get("name", ""):
                print(f"Found existing voice-log channel: {c['id']}")
                return int(c["id"])

    # Create private text channel in staff category
    # @everyone deny VIEW_CHANNEL (1024)
    overwrites = [
        {
            "id": str(GUILD_ID),
            "type": 0,
            "allow": "0",
            "deny": "1049600",
        }
    ]
    payload = {
        "name": "🎙️・voice-log",
        "type": 0,
        "parent_id": str(STAFF_CAT_ID),
        "permission_overwrites": overwrites,
        "topic": "Real-time voice activity, session durations, streaming, video, and VC telemetry.",
    }
    async with session.post(url, headers=HEADERS, json=payload) as r:
        data = await r.json()
        cid = int(data["id"])
        print(f"Created voice-log channel with ID: {cid}")
        return cid

async def deploy_voice_log_header(session: aiohttp.ClientSession, channel_id: int):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    embed = {
        "title": "🎙️ RAI FAM — Real-Time Voice Activity & Telemetry Matrix",
        "description": (
            "Official audit stream tracking voice activity, room occupancy, streaming, and audio telemetry.\n\n"
            "**Tracked Voice Events:**\n"
            "• 📥 **Connections & Joins** — Tracks who joined which VC, room occupancy, and entry timestamp.\n"
            "• 📤 **Disconnections & Leaves** — Tracks departures with exact **session duration** (e.g. `45m 12s`).\n"
            "• 🔀 **Room Switches** — Real-time tracking from Room A ➔ Room B.\n"
            "• 📺 **Screen Sharing & Streams** — Alerts when a member begins streaming gameplay or video.\n"
            "• 📹 **Camera & Video** — Logs webcam activity and video sessions.\n"
            "• 🎙️ **Audio State** — Logs self-mute, self-deafen, and server moderation actions.\n"
            "• ⚠️ **Velocity Anomalies** — Flags rapid voice hopping (jumping between 3+ rooms in seconds).\n\n"
            "**Telemetry Status:** `🟢 ACTIVE & MONITORING ALL VOICE SUITES`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "color": 0x5865F2,
        "footer": {"text": "The Raivora Telemetry • Voice Activity Stream"},
    }
    async with session.post(url, headers=HEADERS, json={"embeds": [embed]}) as r:
        print(f"Deployed Voice Log Matrix Header: {r.status}")

def update_db_config(channel_id: int):
    conn = sqlite3.connect("data/bot.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE logging_config SET voice_channel_id = ? WHERE guild_id = ?",
        (channel_id, GUILD_ID),
    )
    conn.commit()
    conn.close()
    print(f"Updated logging_config with voice_channel_id: {channel_id}")

async def main():
    async with aiohttp.ClientSession() as session:
        cid = await create_voice_log_channel(session)
        update_db_config(cid)
        await deploy_voice_log_header(session, cid)
    print("Voice logging setup completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
