import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
token = os.getenv("DISCORD_TOKEN")
guild_id = 1457382179981099090

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get("https://discord.com/api/v10/users/@me", headers=headers) as r:
            me_user = await r.json()
            bot_id = me_user["id"]
            print("Bot user:", me_user["username"], bot_id)
        
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/members/{bot_id}", headers=headers) as r:
            member = await r.json()
            bot_roles = member.get("roles", [])
            print("Bot role IDs:", bot_roles)
        
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers) as r:
            roles = await r.json()
            roles_by_id = {r["id"]: r for r in roles}
            
            print("\n--- Bot Roles and Positions ---")
            bot_roles_info = [roles_by_id[r_id] for r_id in bot_roles if r_id in roles_by_id]
            bot_roles_info.sort(key=lambda x: x.get("position", 0), reverse=True)
            for r in bot_roles_info:
                print(f"Role: {ascii(r['name'])}, Pos: {r['position']}, Perms: {r.get('permissions')}")
                
            top_pos = bot_roles_info[0]["position"] if bot_roles_info else 0
            print(f"\nBot Highest Role Position: {top_pos}")
            
            v_role = roles_by_id.get("1549504522953695269")
            rf_role = roles_by_id.get("1545494584203673740")
            print(f"Verified Member Role: {ascii(v_role['name'] if v_role else '')}, Pos: {v_role['position'] if v_role else 'Not Found'}")
            print(f"Rai Fam Role: {ascii(rf_role['name'] if rf_role else '')}, Pos: {rf_role['position'] if rf_role else 'Not Found'}")

if __name__ == "__main__":
    asyncio.run(main())
