import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
GUILD_ID = '1457382179981099090'

VERIFIED_ROLE_ID = '1549504522953695269'  # ✨ ┆ VERIFIED MEMBER
MEMBER_ROLE_ID = '1557491522025300018'    # 👤 ┆ MEMBER
MOD_ROLE_ID = '1545494600347680918'       # 🛡️ ┆ MODERATOR
ADMIN_ROLE_ID = '1545506927788687470'     # ⚡ ┆ HEAD ADMIN

# Permissions bitmasks
VIEW_CHANNEL = 1024
CONNECT = 1048576
SEND_MESSAGES = 2048

# Categories to hide until verified
GATED_CATEGORIES = [
    '1545803478490812578',  # ✦ COMMUNITY ✦
    '1558679085293510746',  # ✦ SUPPORT ✦
    '1558679157603311697',  # ✦ BOT ✦
    '1554891379174416474',  # 🍒・Personal Area !
    '1554905799292231728',  # 🍒・Fun Voice Channels !
    '1554905821467648051',  # 🍒・Gaming Zone !
    '1554905886261121107',  # 🍒・Editing Zone !
    '1555255661124784159',  # 🍒・Music Zone !
    '1558676285733994516',  # 🍒・Theater !
    '1554905776030613535',  # 🍒・Private Zone !
    '1554891470325031013',  # 🍒・AFK Zone !
]

STATUS_CATEGORIES = [
    '1546059369085534229',  # Server Status!
    '1558678832326901780',  # Vc Status!
]

START_HERE_CAT = '1545803464712650844'

async def main():
    headers = {
        'Authorization': f'Bot {TOKEN}',
        'Content-Type': 'application/json'
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        # Fetch current channels
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            channels = await resp.json()

        print("=== 1. FIXING STATUS CATEGORIES FOR MOBILE ===")
        # On status categories: @everyone view_channel: allow, connect: deny
        # This makes the category header 'Server Status!' and 'Vc Status!' render properly on mobile!
        for cat_id in STATUS_CATEGORIES:
            overwrites = [
                {
                    'id': GUILD_ID, # @everyone
                    'type': 0,
                    'allow': str(VIEW_CHANNEL),
                    'deny': str(CONNECT | SEND_MESSAGES)
                }
            ]
            async with session.patch(f'https://discord.com/api/v10/channels/{cat_id}', json={'permission_overwrites': overwrites}) as patch_resp:
                print(f"Status Cat {cat_id}: status {patch_resp.status}")
            await asyncio.sleep(1.0)

        # On status child channels: sync overwrites
        for ch_id in ['1546099701496029194', '1546099703630798848']:
            ch_overwrites = [
                {
                    'id': GUILD_ID,
                    'type': 0,
                    'allow': str(VIEW_CHANNEL),
                    'deny': str(CONNECT)
                }
            ]
            async with session.patch(f'https://discord.com/api/v10/channels/{ch_id}', json={'permission_overwrites': ch_overwrites}) as patch_resp:
                print(f"Status Channel {ch_id}: status {patch_resp.status}")
            await asyncio.sleep(1.0)

        print("\n=== 2. CONFIGURING ✦ START HERE ✦ PERMISSIONS ===")
        # Visible to @everyone
        start_overwrites = [
            {
                'id': GUILD_ID,
                'type': 0,
                'allow': str(VIEW_CHANNEL),
                'deny': str(SEND_MESSAGES)
            }
        ]
        async with session.patch(f'https://discord.com/api/v10/channels/{START_HERE_CAT}', json={'permission_overwrites': start_overwrites}) as patch_resp:
            print(f"Start Here Cat: status {patch_resp.status}")
        await asyncio.sleep(1.0)

        print("\n=== 3. LOCKING GATED CATEGORIES (HIDDEN UNTIL VERIFIED) ===")
        for cat_id in GATED_CATEGORIES:
            cat_obj = next((c for c in channels if c['id'] == cat_id), None)
            cat_name = cat_obj['name'] if cat_obj else cat_id

            # @everyone: deny VIEW_CHANNEL
            # VERIFIED MEMBER & MEMBER: allow VIEW_CHANNEL
            # MOD & ADMIN: allow VIEW_CHANNEL
            new_overwrites = [
                {
                    'id': GUILD_ID, # @everyone
                    'type': 0,
                    'allow': '0',
                    'deny': str(VIEW_CHANNEL)
                },
                {
                    'id': VERIFIED_ROLE_ID,
                    'type': 0,
                    'allow': str(VIEW_CHANNEL),
                    'deny': '0'
                },
                {
                    'id': MEMBER_ROLE_ID,
                    'type': 0,
                    'allow': str(VIEW_CHANNEL),
                    'deny': '0'
                },
                {
                    'id': MOD_ROLE_ID,
                    'type': 0,
                    'allow': str(VIEW_CHANNEL),
                    'deny': '0'
                },
                {
                    'id': ADMIN_ROLE_ID,
                    'type': 0,
                    'allow': str(VIEW_CHANNEL),
                    'deny': '0'
                }
            ]
            async with session.patch(f'https://discord.com/api/v10/channels/{cat_id}', json={'permission_overwrites': new_overwrites}) as patch_resp:
                print(f"🔒 Gated Category: {cat_name} -> status {patch_resp.status}")
            await asyncio.sleep(1.2)

        print("\n=== 4. CLEARING OVERRIDING CHILD OVERWRITES SO THEY INHERIT CATEGORY GATE ===")
        # Check child channels inside gated categories
        for ch in channels:
            parent_id = ch.get('parent_id')
            if parent_id in GATED_CATEGORIES and ch.get('type') != 4:
                cid = ch['id']
                cname = ch['name']
                # Check if channel has an explicit @everyone overwrite that allows VIEW_CHANNEL
                ch_overwrites = ch.get('permission_overwrites', [])
                ev_overwrite = next((o for o in ch_overwrites if o['id'] == GUILD_ID), None)
                
                if ev_overwrite and (int(ev_overwrite['allow']) & VIEW_CHANNEL):
                    print(f"Cleaning child channel {cname} ({cid}) - removing @everyone view allow...")
                    # Update overwrite so view_channel is not allowed for @everyone
                    filtered_ow = []
                    for o in ch_overwrites:
                        if o['id'] == GUILD_ID:
                            # remove VIEW_CHANNEL from allow, add to deny or remove
                            allow_val = int(o['allow']) & ~VIEW_CHANNEL
                            deny_val = int(o['deny']) | VIEW_CHANNEL
                            filtered_ow.append({
                                'id': o['id'],
                                'type': o['type'],
                                'allow': str(allow_val),
                                'deny': str(deny_val)
                            })
                        else:
                            filtered_ow.append(o)
                    async with session.patch(f'https://discord.com/api/v10/channels/{cid}', json={'permission_overwrites': filtered_ow}) as clean_resp:
                        print(f"  Cleaned {cname}: status {clean_resp.status}")
                    await asyncio.sleep(1.0)

    print("\n🎉 CLEAN VERIFICATION GATE APPLIED SUCCESSFULLY!")

if __name__ == '__main__':
    asyncio.run(main())
