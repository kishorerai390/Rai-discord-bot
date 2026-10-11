import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
GUILD_ID = '1457382179981099090'

VIEW_CHANNEL = 1024

target_channels = [
    '1554905903508095066', # Staff Operations HQ
    '1557481242054758482', # 🖤・No Entry <3
    '1558676123456372867', # 🪽・Only Us <3
    '1558676148211159082', # 🗝️・Secret Spot
    '1558676161553367091', # 💌・Our Little World <3
]

async def main():
    headers = {'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'}
    async with aiohttp.ClientSession(headers=headers) as session:
        for cid in target_channels:
            async with session.get(f'https://discord.com/api/v10/channels/{cid}') as r:
                c = await r.json()
            
            ow = c.get('permission_overwrites', [])
            new_ow = []
            for o in ow:
                if o['id'] == GUILD_ID:
                    allow_val = int(o['allow']) & ~VIEW_CHANNEL
                    deny_val = int(o['deny']) | VIEW_CHANNEL
                    new_ow.append({'id': o['id'], 'type': o['type'], 'allow': str(allow_val), 'deny': str(deny_val)})
                else:
                    new_ow.append(o)
            
            async with session.patch(f'https://discord.com/api/v10/channels/{cid}', json={'permission_overwrites': new_ow}) as pr:
                print(f"Hidden {c.get('name')}: status {pr.status}")
            await asyncio.sleep(1.0)

if __name__ == '__main__':
    asyncio.run(main())
