"""
Live Watcher: Automatically detects when 'THE Raivora' role is dragged above position 30,
and immediately applies the luxury font formatting to FOUNDER, HEAD ADMIN, and MODERATOR.
"""

import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
BOT_ID = "1554732669072445532"

TARGET_ROLES = {
    1545494610489643038: "👑 ╏ 𝓕ᴏᴜɴᴅᴇʀ 🍷",
    1545506927788687470: "⚡ ╏ 𝓗ᴇᴀᴅ 𝕬ᴅᴍɪɴ ⚡",
    1545494600347680918: "🛡️ ╏ 𝓜ᴏᴅᴇʀᴀᴛᴏʀ 🛡️",
}

async def watch_and_apply():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }
    
    print("⏳ Watching role hierarchy in Discord... Waiting for 'THE Raivora' role to be dragged to the top.")
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(60):  # Check for up to 3 minutes
            async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers) as r:
                if r.status != 200:
                    await asyncio.sleep(3)
                    continue
                roles = await r.json()
                role_dict = {role["id"]: role for role in roles}
                bot_role = next((role for role in roles if role.get("tags", {}).get("bot_id") == BOT_ID or "Raivora" in role.get("name", "")), None)
                
                if not bot_role:
                    await asyncio.sleep(3)
                    continue
                
                bot_pos = bot_role.get("position", 0)
                highest_target_pos = max(role_dict[str(rid)]["position"] for rid in TARGET_ROLES if str(rid) in role_dict)
                
                if bot_pos > highest_target_pos:
                    print(f"🎉 Detected 'THE Raivora' moved to position {bot_pos} (above highest target pos {highest_target_pos})!")
                    success_count = 0
                    for rid, new_name in TARGET_ROLES.items():
                        url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles/{rid}"
                        async with session.patch(url, headers=headers, json={"name": new_name}) as patch_resp:
                            if patch_resp.status == 200:
                                data = await patch_resp.json()
                                print(f"✅ Renamed role {rid} -> {data.get('name')}")
                                success_count += 1
                            else:
                                err_txt = await patch_resp.text()
                                print(f"❌ Failed to rename {rid}: {err_txt}")
                    
                    if success_count == len(TARGET_ROLES):
                        print("✨ ALL 3 ROLES SUCCESSFULLY UPDATED TO LUXURY FONT!")
                        return True
                    return False
            
            await asyncio.sleep(3)

    print("⚠️ Timeout waiting for role position move. Please ensure 'THE Raivora' is dragged above 'FOUNDER' in Server Settings > Roles.")
    return False

if __name__ == "__main__":
    asyncio.run(watch_and_apply())
