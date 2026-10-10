import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
HEADERS = {"Authorization": f"Bot {TOKEN}"}

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/audit-logs?limit=15", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                users = {u["id"]: u["username"] for u in data.get("users", [])}
                entries = data.get("audit_log_entries", [])
                for e in entries:
                    user_name = users.get(e.get("user_id"), e.get("user_id"))
                    action_type = e.get("action_type")
                    target_id = e.get("target_id")
                    changes = e.get("changes", [])
                    c_info = [(c.get("key"), c.get("old_value"), c.get("new_value")) for c in changes]
                    print(ascii(f"Action: {action_type} by {user_name} (target={target_id}) | changes: {c_info}"))
            else:
                print("Failed to fetch audit log:", r.status, await r.text())

if __name__ == "__main__":
    asyncio.run(main())
