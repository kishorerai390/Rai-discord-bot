"""
Update the top 3 roles (Founder, Head Admin, Moderator) to match the server's luxury font aesthetic.
"""

import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

ROLES_TO_UPDATE = {
    1545494610489643038: "👑 ╏ 𝓕ᴏᴜɴᴅᴇʀ 🍷",
    1545506927788687470: "⚡ ╏ 𝓗ᴇᴀᴅ 𝕬ᴅᴍɪɴ ⚡",
    1545494600347680918: "🛡️ ╏ 𝓜ᴏᴅᴇʀᴀᴛᴏʀ 🛡️",
}

async def update_roles():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }
    
    async with aiohttp.ClientSession() as session:
        for role_id, new_name in ROLES_TO_UPDATE.items():
            url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles/{role_id}"
            async with session.patch(url, headers=headers, json={"name": new_name}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Successfully updated role {role_id} -> {data.get('name')}")
                elif resp.status == 403:
                    print(f"⚠️ Discord Hierarchy 403 on role {role_id}: The bot's role must be dragged higher than this role in Server Settings > Roles.")
                else:
                    body = await resp.text()
                    print(f"❌ Failed to update role {role_id} ({resp.status}): {body}")

if __name__ == "__main__":
    asyncio.run(update_roles())
