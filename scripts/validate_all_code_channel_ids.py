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

async def main():
    headers = {'Authorization': f'Bot {TOKEN}'}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f'https://discord.com/api/v10/guilds/{GUILD_ID}/channels') as resp:
            channels = await resp.json()
    valid_ids = {str(c['id']) for c in channels}

    # Scan python files in utils/ and cogs/
    paths_to_check = ['f:/Bot/utils', 'f:/Bot/cogs']
    dead_found = False

    for p in paths_to_check:
        for root, dirs, files in os.walk(p):
            for file in files:
                if file.endswith('.py'):
                    fpath = os.path.join(root, file)
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    mentions = re.findall(r'<#(\d+)>', content)
                    for m in set(mentions):
                        if m not in valid_ids:
                            print(f"Dead mention <#{m}> found in {file}!")
                            dead_found = True

    if not dead_found:
        print("✅ ALL channel mentions across utils/ and cogs/ are 100% VALID!")

if __name__ == '__main__':
    asyncio.run(main())
