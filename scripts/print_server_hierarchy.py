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

    cats = [c for c in channels if c.get('type') == 4]
    cats.sort(key=lambda x: x.get('position', 0))

    non_cats = [c for c in channels if c.get('type') != 4]

    print('================ LIVE SERVER LAYOUT ================')
    for cat in cats:
        children = [c for c in non_cats if c.get('parent_id') == cat['id']]
        children.sort(key=lambda x: x.get('position', 0))
        print(f"\n📂 {cat['name']}")
        for ch in children:
            t = '#' if ch['type'] in (0, 5) else '🔊'
            print(f"   {t} {ch['name']}")

if __name__ == '__main__':
    asyncio.run(main())
