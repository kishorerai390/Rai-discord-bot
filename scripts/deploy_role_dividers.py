import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"

DIVIDERS = [
    {"name": "─── ✦ MANAGEMENT ✦ ───", "anchor": "⚡ ┆ HEAD ADMIN"},
    {"name": "─── ✦ SPECIAL PERKS ✦ ───", "anchor": "🚀 ┆ SERVER BOOSTER"},
    {"name": "─── ✦ COMMUNITY ✦ ───", "anchor": "✨ ┆ VERIFIED MEMBER"},
    {"name": "─── ✦ SQUAD & GAMES ✦ ───", "anchor": "🎯 ┆ VALORANT / CS2"},
    {"name": "─── ✦ NOTIFICATIONS ✦ ───", "anchor": "📢 ┆ ANNOUNCEMENTS"},
    {"name": "─── ✦ THEMES & COLORS ✦ ───", "anchor": "🌸 ┆ ROSE GOLD"},
]

async def main():
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "X-Audit-Log-Reason": "Aesthetic Role Hierarchy Separation & Organization",
    }
    
    async with aiohttp.ClientSession(headers=headers) as s:
        # Fetch current roles
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles") as r:
            roles = await r.json()
            
        existing_names = {r["name"]: r for r in roles}
        created = []
        
        for div in DIVIDERS:
            name = div["name"]
            if name in existing_names:
                print(f"Divider already exists: {name}")
                continue
                
            payload = {
                "name": name,
                "permissions": "0",
                "color": 0x2B2D31,  # Discord Dark Theme Neutral
                "hoist": False,
                "mentionable": False,
            }
            
            async with s.post(f"https://discord.com/api/v10/guilds/{guild_id}/roles", json=payload) as r:
                if r.status in (200, 201):
                    role_data = await r.json()
                    print(f"Created divider: {name} (ID: {role_data['id']})")
                    created.append(role_data)
                else:
                    err = await r.text()
                    print(f"Failed to create divider {name}: {r.status} - {err}")
            await asyncio.sleep(0.5)
            
        print(f"\nCreated {len(created)} divider roles successfully!")

if __name__ == "__main__":
    asyncio.run(main())
