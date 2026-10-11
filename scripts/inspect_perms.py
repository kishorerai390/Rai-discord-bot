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
        # Check channels
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            channels = await resp.json()

        for c in channels:
            # Check status voice channels (1546099701496029194, 1546099703630798848)
            if c['id'] in ['1546099701496029194', '1546099703630798848']:
                print(f"Status Channel {c['name']} ({c['id']}) overwrites:")
                for o in c.get('permission_overwrites', []):
                    print(f"  ID: {o['id']} | type: {o['type']} | allow: {o['allow']} | deny: {o['deny']}")
            
            # Check staff channels
            if 'staff' in c['name'].lower() or 'mod-log' in c['name'].lower():
                print(f"Staff Channel {c['name']} ({c['id']}) overwrites:")
                for o in c.get('permission_overwrites', []):
                    print(f"  ID: {o['id']} | type: {o['type']} | allow: {o['allow']} | deny: {o['deny']}")

if __name__ == '__main__':
    asyncio.run(main())
