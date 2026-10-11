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
VIP_ROLE_ID = '1551184081067450451'
MOD_ROLE_ID = '1545494600347680918'

VIEW_CHANNEL = 1024
CONNECT = 1048576

async def main():
    headers = {'Authorization': f'Bot {TOKEN}'}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            channels = await resp.json()

    print("=== VOICE CHANNELS ACCESSIBILITY FOR VERIFIED MEMBER ===")
    for c in channels:
        if c.get('type') != 2:
            continue
        cname = c['name']
        cid = c['id']

        # Skip status counter channels
        if cid in ('1546099701496029194', '1546099703630798848'):
            continue

        ow = c.get('permission_overwrites', [])
        # Find verified role overwrite
        v_ow = next((o for o in ow if o['id'] == VERIFIED_ROLE_ID), None)
        ev_ow = next((o for o in ow if o['id'] == GUILD_ID), None)

        can_view = True
        can_connect = True

        if v_ow:
            v_allow = int(v_ow['allow'])
            v_deny = int(v_ow['deny'])
            if v_deny & VIEW_CHANNEL: can_view = False
            if v_deny & CONNECT: can_connect = False
        elif ev_ow:
            ev_allow = int(ev_ow['allow'])
            ev_deny = int(ev_ow['deny'])
            if ev_deny & VIEW_CHANNEL: can_view = False
            if ev_deny & CONNECT: can_connect = False

        if can_view and not can_connect:
            print(f"⚠️ LOCKED FOR VERIFIED: {cname} ({cid}) - Can View, but CANNOT Connect (Shows Padlock!)")
        elif not can_view:
            print(f"🙈 HIDDEN FOR VERIFIED: {cname} ({cid})")
        else:
            print(f"✅ OPEN FOR VERIFIED: {cname} ({cid})")

if __name__ == '__main__':
    asyncio.run(main())
