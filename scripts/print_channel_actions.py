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
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/audit-logs?limit=30", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                users = {u["id"]: u["username"] for u in data.get("users", [])}
                entries = data.get("audit_log_entries", [])
                for e in entries:
                    at = e.get("action_type")
                    if at in (10, 11, 12): # channel create, update, delete
                        user_name = users.get(e.get("user_id"), e.get("user_id"))
                        c_name = next((c.get("new_value") or c.get("old_value") for c in e.get("changes", []) if c.get("key") == "name"), "unknown")
                        action_str = {10: "CREATE", 11: "UPDATE", 12: "DELETE"}.get(at, str(at))
                        print(ascii(f"{action_str} by {user_name} | Target: {e.get('target_id')} | Name: {c_name}"))
            else:
                print("Failed:", r.status)

if __name__ == "__main__":
    asyncio.run(main())
