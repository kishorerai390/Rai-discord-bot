import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
GUILD_ID = '1457382179981099090'

MAX_BITRATE = 96000 # Tier 0 Discord max bitrate (96 kbps)

# Specific user limit refinements for aesthetic feel
USER_LIMITS = {
    '1558676123456372867': 2,  # 🪽・Only Us <3
    '1558676161553367091': 2,  # 💌・Our Little World <3
    '1558676148211159082': 4,  # 🗝️・Secret Spot
}

async def main():
    headers = {
        'Authorization': f'Bot {TOKEN}',
        'Content-Type': 'application/json'
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        # Get all channels
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            channels = await resp.json()

        print("=== BOOSTING VOICE CHANNELS TO 96KBPS MAXIMUM FIDELITY ===")
        for c in channels:
            if c.get('type') == 2: # Voice channel
                cid = c['id']
                current_bitrate = c.get('bitrate', 64000)
                current_limit = c.get('user_limit', 0)
                target_limit = USER_LIMITS.get(cid, current_limit)

                needs_patch = (current_bitrate < MAX_BITRATE) or (cid in USER_LIMITS and current_limit != target_limit)

                if needs_patch:
                    payload = {
                        'bitrate': MAX_BITRATE,
                        'user_limit': target_limit
                    }
                    async with session.patch(f'https://discord.com/api/v10/channels/{cid}', json=payload) as patch_resp:
                        if patch_resp.status == 200:
                            data = await patch_resp.json()
                            print(f"🚀 Boosted: {data['name']} -> {data.get('bitrate')//1000}kbps (Limit: {data.get('user_limit')})")
                        else:
                            text = await patch_resp.text()
                            print(f"❌ Failed to boost {c['name']} ({cid}): {patch_resp.status} - {text}")
                    await asyncio.sleep(1.2) # Avoid rate limits
                else:
                    print(f"⚡ Already optimal: {c['name']} ({current_bitrate//1000}kbps, Limit: {current_limit})")

        # Reposition music-control to top of Music Zone (position 0 in parent)
        music_control_id = '1555255695933186228'
        music_cat_id = '1555255661124784159'
        async with session.patch(f'https://discord.com/api/v10/channels/{music_control_id}', json={'position': 0}) as m_resp:
            if m_resp.status == 200:
                print("✅ Placed #♫・music-control neatly at top of Music Zone")
            else:
                print(f"Note on music-control position: {m_resp.status}")

    print("\n🎉 ALL VOICE CHANNELS FULLY BOOSTED & REFINED!")

if __name__ == '__main__':
    asyncio.run(main())
