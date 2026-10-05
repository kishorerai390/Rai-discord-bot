import os, requests, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('DISCORD_TOKEN')
headers = {'Authorization': f'Bot {token}'}
r = requests.get('https://discord.com/api/v10/guilds/1457382179981099090/channels', headers=headers)
if r.status_code == 200:
    for c in r.json():
        print(f"{c.get('type')}: {c.get('name')}")
else:
    print('Status:', r.status_code, r.text)
