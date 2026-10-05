import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
r = requests.get('https://discord.com/api/v10/guilds/1525030316845301781/widget.json')
data = r.json()
print('Server Name:', data.get('name'))
print('Total channels in widget:', len(data.get('channels', [])))
for c in data.get('channels', []):
    print(f"{c.get('id')}: {c.get('name')}")
