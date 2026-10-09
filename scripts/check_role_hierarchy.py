import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}
GUILD_ID = 1457382179981099090
BOT_ID = 1554732669072445532

r_roles = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers)
roles = r_roles.json()

r_bot = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{BOT_ID}", headers=headers)
bot_roles = set(r_bot.json().get("roles", []))

print("=" * 55)
print("✦ SERVER ROLE HIERARCHY AUDIT ✦")
print("=" * 55)

for r in sorted(roles, key=lambda x: x.get("position", 0), reverse=True)[:25]:
    marker = " ◄ [THE RAIVORA ROLE]" if r["id"] in bot_roles or r.get("managed") and "raivora" in r["name"].lower() else ""
    print(f"Pos {r['position']:2d} | {r['name']}{marker}")

print("\n--- NEW SECURITY ROLES POSITIONS ---")
for r in roles:
    if any(k in r["name"] for k in [". Secured .", ". UnBypassable .", ". Rai Sentinel .", ". Quarantined ."]):
        print(f"Pos {r['position']:2d} | {r['name']} (ID: {r['id']})")

