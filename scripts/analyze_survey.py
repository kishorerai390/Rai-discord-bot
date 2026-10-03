import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open("data/server_survey_raw.json", "r", encoding="utf-8") as f:
    data = json.load(f)

g = data["guild"]
print("=== GUILD OVERVIEW ===")
print("Name:", g["name"])
print("ID:", g["id"])
print("Owner ID:", g["owner_id"])
print(f"Members: {data['members_total']} ({data['humans_count']} humans, {data['bots_count']} bots)")
print("Verification Level:", g["verification_level"])
print("Explicit Content Filter:", g["explicit_filter"])
print("MFA Level:", g["mfa_level"])
print("AFK Channel:", g["afk_channel_id"])
print("System Channel:", g["system_channel_id"])

print("\n=== CATEGORIES & CHANNELS ===")
print("Total Categories:", len(data["categories"]))
print("Total Channels:", data["channels_count"])
for cat in data["categories"]:
    texts = [c for c in cat["channels"] if c["type"] in (0, 5)]
    voices = [c for c in cat["channels"] if c["type"] == 2]
    print(f"  [{cat['position']:02d}] {cat['name']}: {len(cat['channels'])} channels ({len(texts)} text, {len(voices)} voice)")

print("\n=== ROLES & SECURITY ===")
roles = data["roles"]
roles.sort(key=lambda r: r["position"], reverse=True)
print("Total Roles:", len(roles))

admin_roles = []
for r in roles:
    perms = int(r.get("permissions", 0))
    if perms & 8:
        admin_roles.append(f"{r['name']} (pos: {r['position']}, id: {r['id']})")

print(f"Administrator Roles ({len(admin_roles)}):")
for ar in admin_roles:
    print("  *", ar)

# Ghost roles (position 1, 0 perms)
ghost_roles = [r["name"] for r in roles if r["position"] == 1 and int(r.get("permissions", 0)) == 0]
print(f"\nGhost/Placeholder Roles at Position 1 ({len(ghost_roles)}):")
for gr in ghost_roles:
    print("  *", gr)

print("\n=== DATABASE CONFIG ===")
print("guild_config:", data["db"]["guild_config"])
print("logging_config:", data["db"]["logging_config"])
print("owner_reports_config:", data["db"]["owner_reports_config"])
print("security_config:", data["db"]["security_config"])
