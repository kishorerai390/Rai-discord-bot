import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
GUILD_ID = '1457382179981099090'

VERIFIED_ROLE_ID = '1549504522953695269'

VIEW_CHANNEL = 1024
CONNECT = 1048576
SEND_MESSAGES = 2048

async def main():
    headers = {'Authorization': f'Bot {TOKEN}'}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            channels = await resp.json()

    print("=== CHANNELS WITH RESTRICTIONS FOR VERIFIED MEMBERS ===")
    for c in channels:
        if c.get('type') == 4:
            continue
        cname = c['name']
        cid = c['id']
        ow = c.get('permission_overwrites', [])

        for o in ow:
            if o['id'] in (GUILD_ID, VERIFIED_ROLE_ID):
                allow = int(o['allow'])
                deny = int(o['deny'])
                # Voice channel: view allowed but connect denied
                if c.get('type') == 2:
                    if (allow & VIEW_CHANNEL) and (deny & CONNECT):
                        print(f"🔒 Voice Channel with Connect Denied: {cname} ({cid}) [Role: {o['id']}]")
                # Text channel: view allowed but send denied
                if c.get('type') in (0, 5):
                    if (allow & VIEW_CHANNEL) and (deny & SEND_MESSAGES):
                        print(f"🔒 Text Channel with Send Denied: {cname} ({cid}) [Role: {o['id']}]")

if __name__ == '__main__':
    asyncio.run(main())
