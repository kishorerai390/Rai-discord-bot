import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
headers = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json"
}

r = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers)
roles = r.json()

bot_role = next((r for r in roles if "raivora" in r["name"].lower() or "sentinel" in r["name"].lower() and r.get("managed")), None)
if not bot_role:
    bot_role = next((r for r in roles if "1554732669072445532" in str(r.get("tags", {}).get("bot_id", ""))), None)

bot_pos = bot_role["position"] if bot_role else 46
print(f"Bot Highest Managed Role Position: {bot_pos}")

secured_role = next((r for r in roles if "🔴 . Secured ." in r["name"]), None)
unbypassable_role = next((r for r in roles if "🟢 . UnBypassable ." in r["name"]), None)
sentinel_role = next((r for r in roles if "🛡️ . Rai Sentinel ." in r["name"]), None)

reorder_payload = []
# Move unbypassable, secured, and sentinel as high as possible under bot role
if unbypassable_role:
    reorder_payload.append({"id": unbypassable_role["id"], "position": bot_pos - 1})
if secured_role:
    reorder_payload.append({"id": secured_role["id"], "position": bot_pos - 2})
if sentinel_role:
    reorder_payload.append({"id": sentinel_role["id"], "position": bot_pos - 3})

print(f"Attempting to reorder roles to positions {bot_pos-1}, {bot_pos-2}, {bot_pos-3}...")
res = requests.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers, json=reorder_payload)
if res.status_code == 200:
    print("✅ Successfully elevated security badges to the top of member hierarchy!")
else:
    print(f"⚠️ Reorder response: {res.status_code} - {res.text}")
