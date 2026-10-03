import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
token = os.getenv("DISCORD_TOKEN")
guild_id = 1457382179981099090

key_channels = {
    "security_alerts": 1555283378612478072,
    "antinuke": 1555283380961026139,
    "lockdown_control": 1555283386656886825,
    "security_log": 1555283387340562574,
    "audit_monitor": 1555283390943469685,
    "admin_control": 1555283409465778218,
    "server_dashboard": 1555283414205075509,
    "bot_config": 1555283416071675954,
    "system_health": 1555283419355676787,
    "backup_control": 1555283418126876856,
}

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        for name, cid in key_channels.items():
            async with s.get(f"https://discord.com/api/v10/channels/{cid}/messages?limit=2", headers=headers) as r:
                msgs = await r.json()
                if isinstance(msgs, list):
                    for m in msgs:
                        titles = [ascii(e.get("title", "")) for e in m.get("embeds", [])]
                        comp_count = len(m.get("components", []))
                        print(f"{name} -> msg {m['id']}: titles={titles}, comps={comp_count}")

if __name__ == "__main__":
    asyncio.run(main())
