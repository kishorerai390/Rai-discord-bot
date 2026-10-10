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
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/audit-logs?limit=50", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                users = {u["id"]: u["username"] for u in data.get("users", [])}
                entries = data.get("audit_log_entries", [])
                for e in entries:
                    if str(e.get("target_id")) == "1558482223429058751" or "member-reports" in str(e):
                        user_name = users.get(e.get("user_id"), e.get("user_id"))
                        print(ascii(f"MATCH: Action {e.get('action_type')} by {user_name} on {e.get('target_id')}"))
            else:
                print("Failed:", r.status)

if __name__ == "__main__":
    asyncio.run(main())
