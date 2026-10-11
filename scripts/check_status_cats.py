import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')

cats = ['1546059369085534229', '1558678832326901780']

async def main():
    headers = {'Authorization': f'Bot {TOKEN}'}
    async with aiohttp.ClientSession(headers=headers) as session:
        for cid in cats:
            async with session.get(f'https://discord.com/api/v10/channels/{cid}') as resp:
                data = await resp.json()
                print(f"Category {data['name']} ({cid}):")
                for o in data.get('permission_overwrites', []):
                    print(f"  id: {o['id']} | type: {o['type']} | allow: {o['allow']} | deny: {o['deny']}")

if __name__ == '__main__':
    asyncio.run(main())
