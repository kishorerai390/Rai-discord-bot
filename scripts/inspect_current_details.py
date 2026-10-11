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
        # Check roles
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/roles') as resp:
            roles = await resp.json()
            print('=== GUILD ROLES ===')
            for r in roles:
                if any(x in r['name'].lower() for x in ['verify', 'member', 'admin', 'mod', 'owner']):
                    print(f"Role ID: {r['id']} | Name: {r['name']}")

        # Check channels
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            channels = await resp.json()
            print('\n=== TEXT CHANNELS ===')
            for c in sorted(channels, key=lambda x: (x.get('parent_id') or '', x.get('position', 0))):
                if c.get('type') == 0:
                    print(f"ID: {c['id']} | Cat: {c.get('parent_id')} | Name: {c['name']} | Slowmode: {c.get('rate_limit_per_user', 0)}s | Topic: {c.get('topic')}")

if __name__ == '__main__':
    asyncio.run(main())
