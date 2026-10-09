import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
SECURITY_CAT_ID = 1555283372488658954
headers = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json"
}

# Fetch existing channels
r = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers).json()
hp = next((c for c in r if "honeypot" in c["name"].lower()), None)

if hp:
    print(f"✅ Honeypot Channel already exists: #{hp['name']} (ID: {hp['id']})")
else:
    # Create Honeypot Channel inside Security Category
    payload = {
        "name": "🪤・honeypot-trap",
        "type": 0, # Text
        "parent_id": str(SECURITY_CAT_ID),
        "topic": "🔒 Autonomous Honeypot Trap | Any automated bot or raider messaging here is banned instantly.",
        "permission_overwrites": [
            {
                "id": str(GUILD_ID), # @everyone
                "type": 0,
                "allow": "0",
                "deny": "1024" # VIEW_CHANNEL: False
            }
        ]
    }
    res = requests.post(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=payload)
    if res.status_code in (200, 201):
        ch = res.json()
        print(f"✅ Successfully created Stealth Honeypot: #{ch['name']} (ID: {ch['id']})")
    else:
        print(f"❌ Failed to create honeypot: {res.status_code} - {res.text}")
