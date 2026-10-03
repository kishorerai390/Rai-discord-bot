import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"

# IDs of exact duplicate roles to remove
DUPLICATE_ROLE_IDS = [
    "1553097622745522218",  # ⚡・Free Fire (Duplicate of 🔥・Free Fire)
    "1553097624872030230",  # ⚡・BGMI (Duplicate of ⚡・BGMI / PUBG)
    "1553097627531346103",  # 🎯・Valorant (Duplicate of 🎯・Valorant / CS2)
    "1553097632228839609",  # 🎬・Watch Party (Duplicate of 🍿・Movie Nights)
    "1553097634187710525",  # 🎙️・Stage Events (Duplicate/redundant)
]

async def optimize_roles():
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "X-Audit-Log-Reason": "Autonomous Server Role Optimization & De-duplication"
    }
    
    async with aiohttp.ClientSession() as s:
        # 1. Delete redundant duplicate roles
        deleted_count = 0
        for rid in DUPLICATE_ROLE_IDS:
            url = f"https://discord.com/api/v10/guilds/{guild_id}/roles/{rid}"
            async with s.delete(url, headers=headers) as r:
                if r.status in (204, 404):
                    deleted_count += 1
                    print(f"Deleted duplicate role ID: {rid}")
                else:
                    print(f"Could not delete role {rid}: status {r.status}")
            await asyncio.sleep(0.5)

        # 2. Re-fetch all roles to get fresh list
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers) as r:
            roles = await r.json()

        print(f"\nRemaining roles count: {len(roles)}")
        
        # Sort roles descending by position
        roles.sort(key=lambda x: x.get("position", 0), reverse=True)
        
        # Categorize
        managed_roles = [r for r in roles if r.get("managed")]
        staff_roles = [r for r in roles if any(x in r["name"] for x in ["FOUNDER", "HEAD ADMIN", "MODERATOR", "TRIAL MOD"])]
        dividers = [r for r in roles if "───" in r["name"]]
        
        print(f"Managed Bot Roles: {len(managed_roles)}")
        print(f"Staff Roles: {len(staff_roles)}")
        print(f"Category Dividers: {len(dividers)}")

if __name__ == "__main__":
    asyncio.run(optimize_roles())
