import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
GUILD_ID = 1457382179981099090

# Fetch members (up to 100)
r_members = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/members?limit=100", headers=headers).json()
r_roles = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers).json()
role_names = {r["id"]: r["name"] for r in r_roles}

print(f"Total Members Fetched: {len(r_members)}")
for m in r_members:
    user = m.get("user", {})
    if user.get("bot"):
        continue
    user_roles = [role_names.get(rid, rid) for rid in m.get("roles", [])]
    print(f"User: {user.get('username')}#{user.get('discriminator')} ({user.get('id')})")
    print(f"  Roles ({len(user_roles)}): {', '.join(user_roles) if user_roles else 'NONE'}")
