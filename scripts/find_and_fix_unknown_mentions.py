import os
import re
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
GUILD_ID = '1457382179981099090'

# Active music channels:
# 1555255325706424412: 🎧・Lost Tunes <3
# 1558483052550692884: 🎶・Vibe Check !
# 1558676274526814263: 🌌・Midnight Beats
# 1554905807240302652: ❄️・Vibin' ~!
# 1554905810574774286: 🌷・Just Us <3

async def main():
    headers = {
        'Authorization': f'Bot {TOKEN}',
        'Content-Type': 'application/json'
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        # 1. Get all current valid channel IDs
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            all_channels = await resp.json()
        
        valid_channel_ids = {str(c['id']) for c in all_channels}
        channel_names = {str(c['id']): c['name'] for c in all_channels}
        print(f"Total valid channels in server: {len(valid_channel_ids)}")

        # 2. Iterate through all text channels
        text_channels = [c for c in all_channels if c.get('type') in (0, 5)]
        print(f"Scanning {len(text_channels)} text channels for dead mentions (<#unknown>)...")

        for tc in text_channels:
            cid = tc['id']
            cname = tc['name']
            async with session.get(f'https://discord.com/api/v10/channels/{cid}/messages?limit=20') as m_resp:
                if m_resp.status != 200:
                    continue
                messages = await m_resp.json()

            for msg in messages:
                mid = msg['id']
                content = msg.get('content', '')
                embeds = msg.get('embeds', [])

                found_unknown = False
                new_embeds = []

                # Check content
                mentions = re.findall(r'<#(\d+)>', content)
                for ch_id in mentions:
                    if ch_id not in valid_channel_ids:
                        print(f"⚠️ In #{cname} (msg {mid}) content: found dead mention <#{ch_id}>")
                        found_unknown = True

                # Check embeds
                for emb in embeds:
                    emb_str = str(emb)
                    emb_mentions = re.findall(r'<#(\d+)>', emb_str)
                    dead_in_emb = [ch_id for ch_id in emb_mentions if ch_id not in valid_channel_ids]
                    if dead_in_emb:
                        print(f"⚠️ In #{cname} (msg {mid}) embed: found dead mentions: {dead_in_emb} (Title: {emb.get('title')})")
                        found_unknown = True

                        # Replace dead channel ID in embed fields / description
                        # 1554905803666751590 was the deleted 24/7 beats, replace with active 1555255325706424412 (Lost Tunes)
                        emb_copy = dict(emb)
                        if 'fields' in emb_copy:
                            new_fields = []
                            for f in emb_copy['fields']:
                                f_val = f.get('value', '')
                                # replace known deleted channel IDs
                                f_val = f_val.replace('<#1554905803666751590>', '<#1555255325706424412>')
                                f_val = f_val.replace('<#1545502735749480679>', '<#1545502730699808768>')
                                # remove any remaining dead mentions
                                for dead_id in dead_in_emb:
                                    f_val = f_val.replace(f'<#{dead_id}>', '•')
                                new_fields.append({**f, 'value': f_val})
                            emb_copy['fields'] = new_fields

                        if 'description' in emb_copy and emb_copy['description']:
                            desc = emb_copy['description']
                            desc = desc.replace('<#1554905803666751590>', '<#1555255325706424412>')
                            desc = desc.replace('<#1545502735749480679>', '<#1545502730699808768>')
                            for dead_id in dead_in_emb:
                                desc = desc.replace(f'<#{dead_id}>', '')
                            emb_copy['description'] = desc

                        new_embeds.append(emb_copy)
                    else:
                        new_embeds.append(emb)

                if found_unknown:
                    # Edit the bot's message to fix it!
                    patch_payload = {'embeds': new_embeds}
                    if content:
                        new_content = content.replace('<#1545502735749480679>', '<#1545502730699808768>')
                        for dead_id in mentions:
                            if dead_id not in valid_channel_ids:
                                new_content = new_content.replace(f'<#{dead_id}>', '')
                        patch_payload['content'] = new_content

                    async with session.patch(f'https://discord.com/api/v10/channels/{cid}/messages/{mid}', json=patch_payload) as patch_resp:
                        if patch_resp.status == 200:
                            print(f"✅ Repaired message {mid} in #{cname}!")
                        else:
                            text = await patch_resp.text()
                            print(f"❌ Failed to patch message {mid} in #{cname}: {patch_resp.status} - {text}")
                    await asyncio.sleep(1.0)

    print("\n🎉 SCAN & REPAIR COMPLETE!")

if __name__ == '__main__':
    asyncio.run(main())
