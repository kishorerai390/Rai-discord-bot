import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
GUILD_ID = 1457382179981099090
CAT_ID = "1554891379174416474"
VC_ID = "1557461916144767046"

r = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers).json()
print("Channels under category 1554891379174416474:")
for c in r:
    if str(c.get("parent_id")) == CAT_ID:
        print(f"  • {c['id']} | type={c['type']} | name={c['name']}")

# Check Voice Channel details
vc = next((c for c in r if str(c["id"]) == VC_ID), None)
if vc:
    print(f"\nVC details: {vc['name']}")
    print(f"  user_limit: {vc.get('user_limit')}")
    print(f"  bitrate: {vc.get('bitrate')}")
    print(f"  position: {vc.get('position')}")
    print(f"  parent_id: {vc.get('parent_id')}")
    print(f"  permission_overwrites: {vc.get('permission_overwrites')}")
