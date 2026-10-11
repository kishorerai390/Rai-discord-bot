import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"

ANCHOR_MAP = {
    "─── ✦ MANAGEMENT ✦ ───": "⚡ ┆ HEAD ADMIN",
    "─── ✦ SPECIAL PERKS ✦ ───": "🚀 ┆ SERVER BOOSTER",
    "─── ✦ COMMUNITY ✦ ───": "✨ ┆ VERIFIED MEMBER",
    "─── ✦ SQUAD & GAMES ✦ ───": "🎯 ┆ VALORANT / CS2",
    "─── ✦ NOTIFICATIONS ✦ ───": "📢 ┆ ANNOUNCEMENTS",
    "─── ✦ THEMES & COLORS ✦ ───": "🌸 ┆ ROSE GOLD",
}

async def main():
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "X-Audit-Log-Reason": "Aesthetic Role Hierarchy Positioning",
    }
    
    async with aiohttp.ClientSession(headers=headers) as s:
        # Fetch current roles
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles") as r:
            roles = await r.json()
            
        role_by_name = {r["name"]: r for r in roles}
        
        # We need to position dividers right above their anchor
        # Build ordered list of roles from highest to lowest excluding the 6 dividers first
        dividers = set(ANCHOR_MAP.keys())
        non_divider_roles = [r for r in roles if r["name"] not in dividers]
        non_divider_roles.sort(key=lambda x: x["position"], reverse=True)
        
        # Now construct target order from highest (top) to lowest (bottom)
        final_ordered_roles = []
        for r in non_divider_roles:
            # Check if any divider should be placed before this anchor
            for div_name, anchor_name in ANCHOR_MAP.items():
                if r["name"] == anchor_name and div_name in role_by_name:
                    final_ordered_roles.append(role_by_name[div_name])
            final_ordered_roles.append(r)
            
        # Reverse because position 1 is near bottom, highest number is top
        # Note: Bot role position limit applies, so only reorder roles below the bot's highest role
        bot_member_url = f"https://discord.com/api/v10/guilds/{guild_id}/members/@me"
        async with s.get(bot_member_url) as r:
            me = await r.json()
            me_role_ids = set(me.get("roles", []))
            
        bot_roles = [r for r in roles if r["id"] in me_role_ids]
        max_bot_pos = max([r["position"] for r in bot_roles]) if bot_roles else 999
        print(f"Bot highest role position: {max_bot_pos}")
        
        # Calculate new positions (lowest is position 1, 0 is @everyone)
        # We assign positions from 1 upwards for modifiable roles
        final_ordered_roles.reverse() # now index 0 is @everyone (pos 0)
        
        payload = []
        for new_pos, r in enumerate(final_ordered_roles):
            if r["name"] == "@everyone":
                continue
            if r["position"] < max_bot_pos and r["name"] in dividers:
                # We can move divider
                # Find its new position
                payload.append({"id": r["id"], "position": new_pos})
                
        if payload:
            print(f"Updating positions for {len(payload)} roles...")
            async with s.patch(f"https://discord.com/api/v10/guilds/{guild_id}/roles", json=payload) as r:
                if r.status == 200:
                    print("✅ Role dividers positioned successfully!")
                else:
                    err = await r.text()
                    print(f"Error positioning roles: {r.status} - {err}")
        else:
            print("No role position updates needed.")

if __name__ == "__main__":
    asyncio.run(main())
