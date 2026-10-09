import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
GUILD_ID = 1457382179981099090

r_roles = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers).json()
role_names = {r["id"]: r["name"] for r in r_roles}

targets = [
    ("Category: ✧ ᴘʀɪᴠᴀᴛᴇ ᴠᴏɪᴄᴇ ✧", "1554891379174416474"),
    ("Channel: 🛠️・ʀᴏᴏᴍ-ᴄᴏɴᴛʀᴏʟ", "1555459478155960421"),
    ("Channel: ➕・Join to Create", "1557461916144767046")
]

VIEW_CHANNEL = 1024
CONNECT = 1048576
SPEAK = 2097152

for title, cid in targets:
    rc = requests.get(f"https://discord.com/api/v10/channels/{cid}", headers=headers).json()
    print("=" * 60)
    print(f"{title} (ID: {cid})")
    print("=" * 60)
    for ow in rc.get("permission_overwrites", []):
        rname = role_names.get(ow["id"], f"Entity {ow['id']}")
        allow = int(ow.get("allow", 0))
        deny = int(ow.get("deny", 0))
        
        view_state = "ALLOW" if (allow & VIEW_CHANNEL) else ("DENY" if (deny & VIEW_CHANNEL) else "INHERIT")
        conn_state = "ALLOW" if (allow & CONNECT) else ("DENY" if (deny & CONNECT) else "INHERIT")
        
        print(f"  • {rname} ({ow['id']}):")
        print(f"      VIEW_CHANNEL: {view_state}")
        print(f"      CONNECT     : {conn_state}")
