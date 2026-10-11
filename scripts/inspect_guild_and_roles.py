import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
GUILD_ID = '1457382179981099090'

async def main():
    headers = {'Authorization': f'Bot {TOKEN}'}
    async with aiohttp.ClientSession(headers=headers) as session:
        # Guild info
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}') as resp:
            guild = await resp.json()
            tier = guild.get('premium_tier', 0)
            boosts = guild.get('premium_subscription_count', 0)
            # Tier 0/1: 96kbps max (96000), Tier 1: 128kbps (128000), Tier 2: 256kbps, Tier 3: 384kbps
            max_bitrate = 96000
            if tier == 1: max_bitrate = 128000
            elif tier == 2: max_bitrate = 256000
            elif tier == 3: max_bitrate = 384000
            print(f"GUILD: {guild.get('name')} | Tier: {tier} | Boosts: {boosts} | Max Bitrate: {max_bitrate//1000}kbps")

        # Roles
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/roles') as resp:
            roles = await resp.json()
            print('\nALL ROLES (ordered by hierarchy position):')
            for r in sorted(roles, key=lambda x: x.get('position', 0), reverse=True):
                print(f"Pos {r.get('position', 0):2d} | ID: {r['id']} | Name: {r['name']} | Color: #{r.get('color', 0):06x}")

if __name__ == '__main__':
    asyncio.run(main())
