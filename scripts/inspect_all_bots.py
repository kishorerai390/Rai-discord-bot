import asyncio
import os
import aiohttp
import json
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"

async def check_bots():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        # Fetch members (up to 1000)
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/members?limit=1000", headers=headers) as r:
            members = await r.json()

        # Fetch roles
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers) as r:
            roles = {role["id"]: role["name"] for role in await r.json()}

        bots = [m for m in members if m.get("user", {}).get("bot")]
        print(f"Total bots in server: {len(bots)}\n")
        
        bot_list = []
        for b in bots:
            u = b["user"]
            u_id = u["id"]
            u_name = u["username"]
            role_ids = b.get("roles", [])
            role_names = [roles.get(rid, rid) for rid in role_ids]
            bot_list.append({
                "id": u_id,
                "name": u_name,
                "roles": role_names,
                "role_ids": role_ids
            })
        with open("data/server_bots.json", "w", encoding="utf-8") as f:
            json.dump(bot_list, f, indent=2)

        for b in bot_list:
            safe_roles = [r.encode('ascii', errors='replace').decode('ascii') for r in b['roles']]
            print(f"Bot: {b['name']} (ID: {b['id']})")
            print(f"  Roles: {', '.join(safe_roles) if safe_roles else 'None'}\n")


if __name__ == "__main__":
    asyncio.run(check_bots())
