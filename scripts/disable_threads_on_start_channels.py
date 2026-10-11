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
READ_MESSAGE_HISTORY = 65536

# Deny regular messages AND all thread creation
DENY_BITS = (
    2048               # SEND_MESSAGES
    | 32768            # ATTACH_FILES
    | 131072           # MENTION_EVERYONE
    | (1 << 35)        # CREATE_PUBLIC_THREADS
    | (1 << 36)        # CREATE_PRIVATE_THREADS
    | (1 << 38)        # SEND_MESSAGES_IN_THREADS
)

START_CHANNELS = [
    '1545502700840427702', # verify-here
    '1545502705643167876', # welcome
    '1545502710101704714', # rules
    '1545502718792175646', # announcements
    '1545502722739150898', # get-roles
]

async def main():
    headers = {
        'Authorization': f'Bot {TOKEN}',
        'Content-Type': 'application/json'
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        for cid in START_CHANNELS:
            async with session.get(f'https://discord.com/api/v10/channels/{cid}') as r:
                c = await r.json()
            
            ow = c.get('permission_overwrites', [])
            new_ow = []
            found_ev = False
            for o in ow:
                if o['id'] == GUILD_ID:
                    new_ow.append({
                        'id': o['id'],
                        'type': o['type'],
                        'allow': str(VIEW_CHANNEL | READ_MESSAGE_HISTORY),
                        'deny': str(DENY_BITS)
                    })
                    found_ev = True
                else:
                    new_ow.append(o)
            
            if not found_ev:
                new_ow.append({
                    'id': GUILD_ID,
                    'type': 0,
                    'allow': str(VIEW_CHANNEL | READ_MESSAGE_HISTORY),
                    'deny': str(DENY_BITS)
                })

            async with session.patch(f'https://discord.com/api/v10/channels/{cid}', json={'permission_overwrites': new_ow}) as pr:
                print(f"Disabled threads & locked input on #{c.get('name')}: status {pr.status}")
            await asyncio.sleep(1.0)

if __name__ == '__main__':
    asyncio.run(main())
