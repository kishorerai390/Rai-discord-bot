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
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            channels = await resp.json()
            for c in sorted(channels, key=lambda x: (x.get('parent_id') or '', x.get('position', 0))):
                if c.get('type') == 2:
                    print(f"ID: {c['id']} | {c['name']} | Bitrate: {c.get('bitrate', 0)//1000}kbps | Limit: {c.get('user_limit', 0)}")

if __name__ == '__main__':
    asyncio.run(main())
