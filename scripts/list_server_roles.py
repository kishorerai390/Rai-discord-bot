import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import discord
from config import DISCORD_TOKEN

async def main():
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    async with discord.Client(intents=intents) as client:
        await client.login(DISCORD_TOKEN)
        guilds_data = []
        async for g_entry in client.fetch_guilds():
            g = await client.fetch_guild(g_entry.id, with_counts=True)
            roles = await g.fetch_roles()
            roles.sort(key=lambda r: r.position, reverse=True)
            
            output = {
                "guild_name": g.name,
                "guild_id": str(g.id),
                "approximate_member_count": g.approximate_member_count,
                "roles": []
            }
            
            for r in roles:
                perms = []
                if r.permissions.administrator: perms.append("ADMIN")
                if r.permissions.manage_guild: perms.append("MANAGE_GUILD")
                if r.permissions.manage_channels: perms.append("MANAGE_CHANNELS")
                if r.permissions.ban_members: perms.append("BAN")
                if r.permissions.kick_members: perms.append("KICK")
                if r.permissions.mention_everyone: perms.append("MENTION_EVERYONE")
                if r.permissions.moderate_members: perms.append("TIMEOUT")
                
                output["roles"].append({
                    "position": r.position,
                    "id": str(r.id),
                    "name": r.name,
                    "color": f"#{r.color.value:06x}" if r.color.value else "Default",
                    "hoist": r.hoist,
                    "managed": r.managed,
                    "mentionable": r.mentionable,
                    "permissions": perms or ["STANDARD"]
                })
            guilds_data.append(output)
            
        with open("scripts/server_roles_data.json", "w", encoding="utf-8") as f:
            json.dump(guilds_data, f, indent=2, ensure_ascii=False)
            
        print(f"Exported {len(guilds_data)} guilds to scripts/server_roles_data.json")

if __name__ == "__main__":
    asyncio.run(main())
