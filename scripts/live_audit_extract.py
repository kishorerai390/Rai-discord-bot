import asyncio
import os
import json
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

VIEW_CHANNEL = 1 << 10
ADMINISTRATOR = 1 << 3
MANAGE_CHANNELS = 1 << 4
MANAGE_GUILD = 1 << 5
VIEW_AUDIT_LOG = 1 << 7
MANAGE_MESSAGES = 1 << 13
KICK_MEMBERS = 1 << 1
BAN_MEMBERS = 1 << 2

async def main():
    async with aiohttp.ClientSession() as s:
        # 1. Guild Info
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}", headers=HEADERS) as r:
            guild = await r.json()
        
        # 2. Roles
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as r:
            roles = await r.json()
        
        # 3. Channels
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()
            
        # 4. Members (limit 1000)
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/members?limit=1000", headers=HEADERS) as r:
            members = await r.json()

        # Build analysis
        roles_by_id = {r["id"]: r for r in roles}
        roles.sort(key=lambda x: x.get("position", 0), reverse=True)

        # Bot analysis
        bots = [m for m in members if m.get("user", {}).get("bot")]
        humans = [m for m in members if not m.get("user", {}).get("bot")]

        # Count members per role
        role_counts = {r["id"]: 0 for r in roles}
        for m in members:
            for r_id in m.get("roles", []):
                if r_id in role_counts:
                    role_counts[r_id] += 1

        # Check channel messages / activity
        channel_activity = {}
        for ch in channels:
            ch_id = ch["id"]
            ch_type = ch.get("type")
            if ch_type in (0, 5): # text / announcement
                try:
                    async with s.get(f"https://discord.com/api/v10/channels/{ch_id}/messages?limit=5", headers=HEADERS) as mr:
                        if mr.status == 200:
                            msgs = await mr.json()
                            channel_activity[ch_id] = {
                                "count_recent": len(msgs),
                                "last_msg_time": msgs[0]["timestamp"] if msgs else None,
                                "last_msg_author": msgs[0]["author"]["username"] if msgs else None,
                                "pinned_count": 0
                            }
                        else:
                            channel_activity[ch_id] = {"error": mr.status}
                except Exception as e:
                    channel_activity[ch_id] = {"error": str(e)}

        audit_data = {
            "guild": {
                "id": guild.get("id"),
                "name": guild.get("name"),
                "owner_id": guild.get("owner_id"),
                "member_count": len(members),
                "human_count": len(humans),
                "bot_count": len(bots),
                "verification_level": guild.get("verification_level"),
                "afk_channel_id": guild.get("afk_channel_id"),
                "system_channel_id": guild.get("system_channel_id"),
            },
            "roles": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "position": r["position"],
                    "color": hex(r["color"]),
                    "permissions": r["permissions"],
                    "is_admin": bool(int(r["permissions"]) & ADMINISTRATOR),
                    "is_manage_guild": bool(int(r["permissions"]) & MANAGE_GUILD),
                    "is_manage_channels": bool(int(r["permissions"]) & MANAGE_CHANNELS),
                    "is_mod": bool(int(r["permissions"]) & (KICK_MEMBERS | BAN_MEMBERS | MANAGE_MESSAGES)),
                    "member_count": role_counts.get(r["id"], 0),
                    "managed": r.get("managed", False),
                }
                for r in roles
            ],
            "bots": [
                {
                    "id": b["user"]["id"],
                    "name": b["user"]["username"],
                    "roles": [roles_by_id[rid]["name"] for rid in b.get("roles", []) if rid in roles_by_id],
                    "has_admin": any(bool(int(roles_by_id[rid]["permissions"]) & ADMINISTRATOR) for rid in b.get("roles", []) if rid in roles_by_id)
                }
                for b in bots
            ],
            "channels": channels,
            "activity": channel_activity
        }

        with open("data/live_audit_dump.json", "w", encoding="utf-8") as f:
            json.dump(audit_data, f, indent=2, ensure_ascii=False)

        print("Live audit dump written to data/live_audit_dump.json")

if __name__ == "__main__":
    asyncio.run(main())
