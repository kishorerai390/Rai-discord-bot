import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
guild_id = 1457382179981099090

async def main():
    headers = {'Authorization': f'Bot {token}'}
    async with aiohttp.ClientSession() as s:
        async with s.get(f'https://discord.com/api/v10/guilds/{guild_id}/channels', headers=headers) as r:
            channels = await r.json()
    cats = {c['id']: c for c in channels if c['type'] == 4}
    print(f'Total elements remaining: {len(channels)}')
    
    sorted_cats = sorted(cats.values(), key=lambda x: x.get('position', 0))
    for cat in sorted_cats:
        print(f"\n📁 {cat['name']} (ID: {cat['id']}, Pos: {cat.get('position')})")
        children = [c for c in channels if c.get('parent_id') == cat['id']]
        children.sort(key=lambda x: x.get('position', 0))
        for ch in children:
            t = '🔊' if ch['type'] == 2 else '💬'
            print(f"   {t} {ch['name']} (ID: {ch['id']}, Pos: {ch.get('position')})")
    
    uncat = [c for c in channels if c['type'] != 4 and not c.get('parent_id')]
    if uncat:
        print('\n⚠️ UNCATEGORIZED:')
        for ch in uncat:
            print(f"   {ch['name']} ({ch['id']})")

if __name__ == '__main__':
    asyncio.run(main())
