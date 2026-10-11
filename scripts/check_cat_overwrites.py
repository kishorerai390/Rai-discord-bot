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

    print('=== CATEGORIES PERMISSIONS FOR @EVERYONE ===')
    for c in channels:
        if c.get('type') == 4: # category
            overwrites = c.get('permission_overwrites', [])
            ev = [o for o in overwrites if o['id'] == GUILD_ID]
            if ev:
                allow = int(ev[0]['allow'])
                deny = int(ev[0]['deny'])
                view_allowed = bool(allow & 1024)
                view_denied = bool(deny & 1024)
                print(f"📂 {c['name']} ({c['id']}) | view_allowed={view_allowed}, view_denied={view_denied}")
            else:
                print(f"📂 {c['name']} ({c['id']}) | NO @everyone overwrite (Default visible)")

if __name__ == '__main__':
    asyncio.run(main())
