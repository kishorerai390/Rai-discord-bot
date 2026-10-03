import asyncio
import os
import aiohttp
import json
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
guild_id = '1457382179981099090'
target_user_id = '456226577798135808'

async def deep_scan():
    headers = {'Authorization': f'Bot {token}'}
    total_found = 0
    channels_with_msgs = {}
    all_msgs = []
    
    async with aiohttp.ClientSession() as s:
        async with s.get(f'https://discord.com/api/v10/guilds/{guild_id}/channels', headers=headers) as r:
            channels = await r.json()
            
        text_channels = [c for c in channels if c.get('type') in (0, 5)]
        print(f"Scanning {len(text_channels)} text channels...")
        
        for ch in text_channels:
            ch_id = ch['id']
            ch_name = ch.get('name', 'unknown')
            last_id = None
            ch_found = 0
            while True:
                url = f'https://discord.com/api/v10/channels/{ch_id}/messages?limit=100'
                if last_id:
                    url += f'&before={last_id}'
                async with s.get(url, headers=headers) as mr:
                    if mr.status != 200:
                        break
                    msgs = await mr.json()
                    if not msgs or not isinstance(msgs, list):
                        break
                    for m in msgs:
                        if m.get('author', {}).get('id') == target_user_id:
                            all_msgs.append({
                                'channel_id': ch_id,
                                'channel_name': ch_name,
                                'message_id': m['id'],
                                'timestamp': m.get('timestamp'),
                                'content': m.get('content', '')[:100]
                            })
                            ch_found += 1
                    last_id = msgs[-1]['id']
                    if len(msgs) < 100:
                        break
            if ch_found > 0:
                channels_with_msgs[ch_name] = ch_found
                total_found += ch_found
                
    print(f'Total messages found from user {target_user_id}: {total_found}')
    for c, cnt in channels_with_msgs.items():
        safe_c = c.encode('ascii', errors='replace').decode('ascii')
        print(f'  #{safe_c}: {cnt}')
        
    with open('data/all_target_user_messages.json', 'w', encoding='utf-8') as f:
        json.dump(all_msgs, f, indent=2)

if __name__ == '__main__':
    asyncio.run(deep_scan())
