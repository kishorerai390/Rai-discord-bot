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

print("=" * 60)
print("✦ EXECUTING & AUDITING SERVER OPTIMIZATION ACTIONS ✦")
print("=" * 60)

# 1. Check Suggestion 1 (Duplicate Category)
print("\n[ACTION 1] Checking duplicate category...")
r_cat = requests.get(f"https://discord.com/api/v10/channels/1557717563834765342", headers=headers)
if r_cat.status_code == 404:
    print("  ✅ Suggestion 1 Confirmed: Duplicate category '📋 | RAI REPORTS' is already deleted.")
else:
    print(f"  • Category exists (status {r_cat.status_code}), removing now...")
    del_r = requests.delete(f"https://discord.com/api/v10/channels/1557717563834765342", headers=headers)
    print(f"  ✅ Deleted duplicate category: {del_r.status_code}")

# 2. Execute Suggestion 2 (AFK Auto-Move Channel)
print("\n[ACTION 2] Configuring Guild AFK Auto-Move Channel...")
afk_payload = {
    "afk_channel_id": "1554891485818921042",  # 💤・AFK Sleep
    "afk_timeout": 900                       # 15 minutes = 900 seconds
}
r_afk = requests.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}", headers=headers, json=afk_payload)
if r_afk.status_code == 200:
    res = r_afk.json()
    print(f"  ✅ Successfully set AFK Channel: {res.get('afk_channel_id')} (Timeout: {res.get('afk_timeout')}s / 15m)")
else:
    print(f"  ⚠️ Could not update guild AFK channel directly via API ({r_afk.status_code}: {r_afk.text}).")
    print("     (Note: Bot requires 'Manage Server' permission on the Guild level if not permitted)")

# 3. Audit and Lock Down Staff Categories (Suggestion 3)
print("\n[ACTION 3] Auditing Staff Channel Category Permissions...")
staff_categories = {
    1555283372488658954: "🛡️ ═ ʀᴀɪ sᴇᴄᴜʀɪᴛʏ ═ 🛡️",
    1555283377249063083: "⚙️ ═ ʀᴀɪ ᴀᴅᴍɪɴ ═ ⚙️",
    1555428388280209422: "📋 ═ ʀᴀɪ ʀᴇᴘᴏʀᴛs ═ 📋",
    1554905886261121107: "✧ ᴇxᴇᴄᴜᴛɪᴠᴇ ʜǫ ✧",
}

# Fetch Guild Roles
r_roles = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers)
roles = r_roles.json()
role_map = {r["name"]: r["id"] for r in roles}
print(f"  • Total Guild Roles: {len(roles)}")

VIEW_CHANNEL_FLAG = 1024  # 0x400

for cat_id, cat_name in staff_categories.items():
    r_cat = requests.get(f"https://discord.com/api/v10/channels/{cat_id}", headers=headers)
    if r_cat.status_code != 200:
        print(f"  ⚠️ Could not fetch category {cat_name} ({cat_id})")
        continue
    cdata = r_cat.json()
    overwrites = cdata.get("permission_overwrites", [])
    
    # Check @everyone overwrite
    everyone_ow = next((ow for ow in overwrites if ow["id"] == str(GUILD_ID)), None)
    is_denied = False
    if everyone_ow:
        deny_int = int(everyone_ow.get("deny", 0))
        if (deny_int & VIEW_CHANNEL_FLAG) == VIEW_CHANNEL_FLAG:
            is_denied = True
    
    if is_denied:
        print(f"  🔒 {cat_name}: @everyone View Channel is already BLOCKED (Private).")
    else:
        print(f"  ⚠️ {cat_name}: @everyone View Channel is NOT blocked. Securing now...")
        # Put permission overwrite for @everyone
        # type 0 = role
        put_r = requests.put(
            f"https://discord.com/api/v10/channels/{cat_id}/permissions/{GUILD_ID}",
            headers=headers,
            json={
                "id": str(GUILD_ID),
                "type": 0,
                "allow": "0",
                "deny": str(VIEW_CHANNEL_FLAG)
            }
        )
        if put_r.status_code in (200, 204):
            print(f"     ✅ Secured {cat_name}: @everyone View Channel now BLOCKED.")
        else:
            print(f"     ❌ Failed to set permissions: {put_r.status_code} - {put_r.text}")

print("\n" + "=" * 60)
print("✦ OPTIMIZATIONS AUDIT & EXECUTION COMPLETE ✦")
print("=" * 60)
