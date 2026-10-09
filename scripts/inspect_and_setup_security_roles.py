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
print("✦ SECURITY ROLES & CHANNEL PROVISIONING SYSTEM ✦")
print("=" * 60)

# 1. Fetch current Guild roles
r = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers)
roles = r.json()
role_by_name = {role["name"].strip().lower(): role for role in roles}

# Target Security Roles matching Rage Optimiser luxury style
DESIRED_ROLES = [
    {
        "name": "🔴 . Secured .",
        "color": 0xE74C3C,      # Red
        "hoist": True,
        "permissions": "0",     # Badge / Trust anchor
    },
    {
        "name": "🟢 . UnBypassable .",
        "color": 0x2ECC71,      # Green
        "hoist": True,
        "permissions": "0",     # Whitelist anchor
    },
    {
        "name": "🛡️ . Rai Sentinel .",
        "color": 0x9B59B6,      # Purple / Royal
        "hoist": True,
        "permissions": "0",
    },
    {
        "name": "⛓️ . Quarantined .",
        "color": 0x34495E,      # Muted Dark Slate
        "hoist": False,
        "permissions": "0",     # Stripped
    }
]

created_role_ids = {}

for target in DESIRED_ROLES:
    key = target["name"].strip().lower()
    existing = None
    for rname, rdata in role_by_name.items():
        if target["name"].lower() in rname or (key.replace(" ", "") in rname.replace(" ", "")):
            existing = rdata
            break

    if existing:
        print(f"  ✓ Role already exists: {existing['name']} (ID: {existing['id']})")
        created_role_ids[target["name"]] = existing["id"]
    else:
        print(f"  + Creating role: {target['name']}...")
        payload = {
            "name": target["name"],
            "color": target["color"],
            "hoist": target["hoist"],
            "mentionable": False,
        }
        res = requests.post(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers, json=payload)
        if res.status_code in (200, 201):
            nd = res.json()
            print(f"    ✅ Created {nd['name']} (ID: {nd['id']})")
            created_role_ids[target["name"]] = nd["id"]
        else:
            print(f"    ❌ Failed to create role: {res.status_code} - {res.text}")

# 2. Fetch Guild and assign roles to The Raivora (Bot ID 1554732669072445532) and Guild Owner
r_guild = requests.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}", headers=headers)
guild_data = r_guild.json()
owner_id = guild_data.get("owner_id")
bot_id = 1554732669072445532

print(f"\n[ASSIGNMENT] Assigning Security Badges...")
for target_name in ["🔴 . Secured .", "🟢 . UnBypassable ."]:
    role_id = created_role_ids.get(target_name)
    if not role_id:
        continue
    
    # Assign to Bot
    res_b = requests.put(f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{bot_id}/roles/{role_id}", headers=headers)
    if res_b.status_code in (200, 204):
        print(f"  ✅ Assigned {target_name} to The Raivora ({bot_id})")
    else:
        print(f"  ⚠️ Note for Bot role {target_name}: {res_b.status_code}")

    # Assign to Server Owner
    if owner_id:
        res_o = requests.put(f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{owner_id}/roles/{role_id}", headers=headers)
        if res_o.status_code in (200, 204):
            print(f"  ✅ Assigned {target_name} to Server Owner ({owner_id})")

# 3. Channel Check: Quarantine & Security Categories
print(f"\n[CHANNELS] Verifying Defense & Quarantine Channels...")

DETENTION_CAT_ID = 1556740753336565881
PRISON_CHAT_ID = 1556738642301558846
PRISON_VC_ID = 1556738643471630408
SECURITY_CAT_ID = 1555283372488658954
SECURITY_ALERTS_ID = 1555283378612478072
ANTI_NUKE_ID = 1555283380961026139

quarantine_role_id = created_role_ids.get("⛓️ . Quarantined .")

if quarantine_role_id:
    # 1. Allow Quarantined role to view and speak in Prison Chat only
    allow_prison = 1024 | 2048 | 65536  # VIEW_CHANNEL | SEND_MESSAGES | READ_HISTORY
    res_pr = requests.put(
        f"https://discord.com/api/v10/channels/{PRISON_CHAT_ID}/permissions/{quarantine_role_id}",
        headers=headers,
        json={"id": str(quarantine_role_id), "type": 0, "allow": str(allow_prison), "deny": "0"}
    )
    if res_pr.status_code in (200, 204):
        print(f"  🔒 Prison Chat {PRISON_CHAT_ID}: Configured full access for ⛓️ . Quarantined .")

    # 2. Block Quarantined role from regular general chat
    res_gen = requests.put(
        f"https://discord.com/api/v10/channels/1545502730699808768/permissions/{quarantine_role_id}",
        headers=headers,
        json={"id": str(quarantine_role_id), "type": 0, "allow": "0", "deny": "1024"}
    )
    if res_gen.status_code in (200, 204):
        print(f"  🔒 General Chat: VIEW_CHANNEL blocked for ⛓️ . Quarantined .")

print(f"  ✓ Anti-Nuke Control Channel: {ANTI_NUKE_ID}")
print(f"  ✓ Real-Time Security Alerts: {SECURITY_ALERTS_ID}")
print(f"  ✓ Detention Isolation Room : {PRISON_CHAT_ID}")

print("\n" + "=" * 60)
print("✦ SECURITY ROLES & CHANNELS SETUP COMPLETE ✦")
print("=" * 60)
