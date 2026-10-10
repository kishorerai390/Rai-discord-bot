import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
OWNER_ID = 1457380609641938981
BOT_ID = 1554732669072445532

TARGET_CH_ID = "1555428392181047366"  # Existing channel under Private Reporting

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
MANAGE_CHANNELS = 1 << 4
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_MESSAGE_HISTORY = 1 << 16
MANAGE_MESSAGES = 1 << 13

DENY_ALL = VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY
OWNER_ALLOW = VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY | MANAGE_CHANNELS | EMBED_LINKS | ATTACH_FILES | MANAGE_MESSAGES
BOT_ALLOW = VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY | EMBED_LINKS | ATTACH_FILES

async def main():
    async with aiohttp.ClientSession() as s:
        # Get roles to deny all server roles
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as r:
            roles = await r.json()

        overwrites = [
            # 1. @everyone Deny View, Send, History
            {
                "id": str(GUILD_ID),
                "type": 0,
                "deny": str(DENY_ALL),
                "allow": "0"
            },
            # 2. Server Owner Explicit Full Allow
            {
                "id": str(OWNER_ID),
                "type": 1,
                "allow": str(OWNER_ALLOW),
                "deny": "0"
            },
            # 3. Rai Sentinel Bot Allow
            {
                "id": str(BOT_ID),
                "type": 1,
                "allow": str(BOT_ALLOW),
                "deny": "0"
            }
        ]

        # Explicitly deny every role in server
        for r in roles:
            if r["id"] != str(GUILD_ID) and not r.get("managed"):
                overwrites.append({
                    "id": str(r["id"]),
                    "type": 0,
                    "deny": str(VIEW_CHANNEL),
                    "allow": "0"
                })

        payload = {
            "name": "⛨・member-reports",
            "topic": "Confidential member reports, evidence logs, and direct owner inquiries. Strictly private.",
            "permission_overwrites": overwrites
        }

        print("Configuring ⛨・member-reports...")
        async with s.patch(f"https://discord.com/api/v10/channels/{TARGET_CH_ID}", headers=HEADERS, json=payload) as pr:
            print("Status:", pr.status)
            if pr.status in (200, 204):
                res = await pr.json()
                print("Successfully reconfigured channel:", ascii(res.get("name")), res.get("id"))
            else:
                print("Failed:", await pr.text())

if __name__ == "__main__":
    asyncio.run(main())
