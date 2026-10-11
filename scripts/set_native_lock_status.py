import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
GUILD_ID = '1457382179981099090'

# Categories:
# Server Status! (1546059369085534229)
# Vc Status! (1558678832326901780)
# Channels:
# 1546099701496029194 (Server Status VC)
# 1546099703630798848 (VC Status VC)

VIEW_CHANNEL = 1024
CONNECT = 1048576

async def main():
    headers = {
        'Authorization': f'Bot {TOKEN}',
        'Content-Type': 'application/json'
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        # 1. Update Category names: remove emoji lock so it matches screenshot 'Server Status!' & 'Vc Status!'
        for cat_id, name in [('1546059369085534229', 'Server Status!'), ('1558678832326901780', 'Vc Status!')]:
            # Set private category overwrites:
            # @everyone (GUILD_ID): deny VIEW_CHANNEL (1024)
            # VERIFIED MEMBER (1549504522953695269): allow VIEW_CHANNEL (1024), deny CONNECT (1048576)
            # MEMBER (1557491522025300018): allow VIEW_CHANNEL (1024), deny CONNECT (1048576)
            payload = {
                'name': name,
                'permission_overwrites': [
                    {
                        'id': GUILD_ID,
                        'type': 0, # role
                        'allow': '0',
                        'deny': str(VIEW_CHANNEL | CONNECT)
                    },
                    {
                        'id': '1549504522953695269', # VERIFIED MEMBER
                        'type': 0,
                        'allow': str(VIEW_CHANNEL),
                        'deny': str(CONNECT)
                    },
                    {
                        'id': '1557491522025300018', # MEMBER
                        'type': 0,
                        'allow': str(VIEW_CHANNEL),
                        'deny': str(CONNECT)
                    }
                ]
            }
            async with session.patch(f'https://discord.com/api/v10/channels/{cat_id}', json=payload) as resp:
                print(f"Patched Category {cat_id} ({name}): status {resp.status}")

        # 2. On the child channels: also ensure @everyone can view the channel count
        for ch_id in ['1546099701496029194', '1546099703630798848']:
            ch_payload = {
                'permission_overwrites': [
                    {
                        'id': GUILD_ID,
                        'type': 0,
                        'allow': str(VIEW_CHANNEL),
                        'deny': str(CONNECT)
                    },
                    {
                        'id': '1549504522953695269',
                        'type': 0,
                        'allow': str(VIEW_CHANNEL),
                        'deny': str(CONNECT)
                    }
                ]
            }
            async with session.patch(f'https://discord.com/api/v10/channels/{ch_id}', json=ch_payload) as resp:
                print(f"Patched Child Channel {ch_id}: status {resp.status}")

if __name__ == '__main__':
    asyncio.run(main())
