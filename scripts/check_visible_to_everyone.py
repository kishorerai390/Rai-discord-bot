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

async def main():
    headers = {'Authorization': f'Bot {TOKEN}'}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            channels = await resp.json()

    categories = {c['id']: c for c in channels if c.get('type') == 4}

    print("=== CHANNELS VISIBLE TO @everyone (UNVERIFIED USERS) ===")
    for c in channels:
        if c.get('type') == 4:
            continue
        
        cid = c['id']
        name = c['name']
        parent_id = c.get('parent_id')
        cat = categories.get(parent_id, {})
        cat_name = cat.get('name', 'None')

        # Check category overwrite
        cat_allow = 0
        cat_deny = 0
        for o in cat.get('permission_overwrites', []):
            if o['id'] == GUILD_ID:
                cat_allow = int(o['allow'])
                cat_deny = int(o['deny'])

        # Check channel overwrite
        ch_allow = 0
        ch_deny = 0
        has_ch_ev = False
        for o in c.get('permission_overwrites', []):
            if o['id'] == GUILD_ID:
                ch_allow = int(o['allow'])
                ch_deny = int(o['deny'])
                has_ch_ev = True

        visible = True
        if has_ch_ev:
            if ch_deny & VIEW_CHANNEL:
                visible = False
            elif ch_allow & VIEW_CHANNEL:
                visible = True
        else:
            # inherits from category
            if cat_deny & VIEW_CHANNEL:
                visible = False
            elif cat_allow & VIEW_CHANNEL:
                visible = True

        if visible:
            print(f"👁️ VISIBLE: [{cat_name}] {name} (type: {c.get('type')})")

if __name__ == '__main__':
    asyncio.run(main())
