import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

async def audit():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers) as r:
            roles = await r.json()
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/members?limit=1000", headers=headers) as r:
            members = await r.json()

    role_counts = {role["id"]: 0 for role in roles}
    for m in members:
        for rid in m.get("roles", []):
            if rid in role_counts:
                role_counts[rid] += 1

    roles.sort(key=lambda x: x.get("position", 0), reverse=True)
    for role in roles:
        rid = role["id"]
        pos = role.get("position", 0)
        cnt = role_counts.get(rid, 0)
        managed = role.get("managed", False)
        name = role.get("name", "")
        print(f"{pos:02d} | ID: {rid} | Members: {cnt:02d} | Managed: {managed} | {ascii(name)}")

if __name__ == "__main__":
    asyncio.run(audit())
