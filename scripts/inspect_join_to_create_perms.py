import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
GUILD_ID = 1457382179981099090
VC_ID = 1557461916144767046

# Fetch roles
r_roles = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers).json()
role_names = {r["id"]: r["name"] for r in r_roles}

# 1. Fetch channel 1557461916144767046
rc = requests.get(f"https://discord.com/api/v10/channels/{VC_ID}", headers=headers).json()
print("Channel Name:", rc.get("name"))
print("Parent Category ID:", rc.get("parent_id"))
print("Channel Overwrites:")
for ow in rc.get("permission_overwrites", []):
    name = role_names.get(ow["id"], f"User/Entity {ow['id']}")
    print(f"  • {name} (ID: {ow['id']}): allow={ow['allow']}, deny={ow['deny']}")

# 2. Fetch parent category
cat_id = rc.get("parent_id")
if cat_id:
    rp = requests.get(f"https://discord.com/api/v10/channels/{cat_id}", headers=headers).json()
    print(f"\nParent Category: {rp.get('name')} ({cat_id})")
    print("Category Overwrites:")
    for ow in rp.get("permission_overwrites", []):
        name = role_names.get(ow["id"], f"User/Entity {ow['id']}")
        print(f"  • {name} (ID: {ow['id']}): allow={ow['allow']}, deny={ow['deny']}")
