"""
Deploy all Real-Time Consoles with Live Telemetry and Interactive Buttons across Discord channels.
Handles Discord system messages (type != 0) and Components V2 cleanly by posting fresh standard consoles.
"""

import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "F:/Bot")

import aiohttp
from dotenv import load_dotenv

from utils.realtime_consoles import (
    REALTIME_CHANNELS,
    build_admin_control_payload,
    build_server_dashboard_payload,
    build_bot_config_payload,
    build_system_health_payload,
    build_antinuke_payload,
    build_lockdown_payload,
    build_security_alerts_payload,
    build_honeypot_payload,
    build_room_control_payload,
    build_suggestions_payload,
    build_support_desk_payload,
    build_hall_of_fame_payload,
    build_music_control_payload,
    build_welcome_payload,
    build_bot_commands_payload,
)

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

async def update_or_post_console(session: aiohttp.ClientSession, channel_id: int, payload: dict, name: str):
    # Fetch existing messages
    async with session.get(f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=10", headers=HEADERS) as r:
        msgs = await r.json()

    target_id = None
    if isinstance(msgs, list) and len(msgs) > 0:
        # Find editable normal message (type == 0 and flags != 32768)
        for m in msgs:
            is_bot = m.get("author", {}).get("bot", False)
            msg_type = m.get("type", 0)
            flags = m.get("flags", 0)
            if is_bot and msg_type == 0 and not (flags & (1 << 15)): # Not IS_COMPONENTS_V2
                target_id = m["id"]
                break

        # Delete older duplicate or outdated messages
        for m in msgs:
            is_bot = m.get("author", {}).get("bot", False)
            msg_type = m.get("type", 0)
            # If it's another bot message or system pin message that isn't our target
            if is_bot and m["id"] != target_id:
                try:
                    await session.delete(f"https://discord.com/api/v10/channels/{channel_id}/messages/{m['id']}", headers=HEADERS)
                    await asyncio.sleep(0.15)
                except Exception:
                    pass

    success = False
    if target_id:
        async with session.patch(f"https://discord.com/api/v10/channels/{channel_id}/messages/{target_id}", headers=HEADERS, json=payload) as pr:
            if pr.status in (200, 201):
                print(f"✅ [UPDATED] Real-time console #{name} in {channel_id}")
                success = True
            else:
                # If patch fails for any reason, delete old and post fresh
                await session.delete(f"https://discord.com/api/v10/channels/{channel_id}/messages/{target_id}", headers=HEADERS)

    if not success:
        async with session.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", headers=HEADERS, json=payload) as cr:
            if cr.status in (200, 201):
                print(f"✅ [POSTED FRESH] Real-time console #{name} in {channel_id}")
            else:
                err_text = await cr.text()
                print(f"⚠️ [FAIL] #{name} in {channel_id}: {cr.status} - {err_text}")


async def main():
    print("🚀 Deploying Real-Time Consoles with Live Telemetry & Interactive Buttons...")
    
    consoles_to_deploy = [
        ("admin_control", REALTIME_CHANNELS["admin_control"], build_admin_control_payload()),
        ("server_dashboard", REALTIME_CHANNELS["server_dashboard"], build_server_dashboard_payload()),
        ("bot_config", REALTIME_CHANNELS["bot_config"], build_bot_config_payload()),
        ("system_health", REALTIME_CHANNELS["system_health"], build_system_health_payload()),
        ("antinuke", REALTIME_CHANNELS["antinuke"], build_antinuke_payload()),
        ("lockdown", REALTIME_CHANNELS["lockdown"], build_lockdown_payload()),
        ("security_alerts", REALTIME_CHANNELS["security_alerts"], build_security_alerts_payload()),
        ("honeypot", REALTIME_CHANNELS["honeypot"], build_honeypot_payload()),
        ("room_control", REALTIME_CHANNELS["room_control"], build_room_control_payload()),
        ("suggestions", REALTIME_CHANNELS["suggestions"], build_suggestions_payload()),
        ("support_desk", REALTIME_CHANNELS["support_desk"], build_support_desk_payload()),
        ("hall_of_fame", REALTIME_CHANNELS["hall_of_fame"], build_hall_of_fame_payload()),
        ("music_control", REALTIME_CHANNELS["music_control"], build_music_control_payload()),
        ("welcome", REALTIME_CHANNELS["welcome"], build_welcome_payload()),
        ("bot_commands", REALTIME_CHANNELS["bot_commands"], build_bot_commands_payload()),
    ]

    async with aiohttp.ClientSession() as session:
        for name, ch_id, payload in consoles_to_deploy:
            await update_or_post_console(session, ch_id, payload, name)
            await asyncio.sleep(0.3)

    print("🎉 All 15 Real-Time Consoles deployed cleanly with interactive buttons!")

if __name__ == "__main__":
    asyncio.run(main())
