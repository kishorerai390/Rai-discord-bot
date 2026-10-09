import json

with open("scripts/server_roles_data.json", "r", encoding="utf-8") as f:
    guilds = json.load(f)

with open("scripts/roles_summary.txt", "w", encoding="utf-8") as out:
    for g in guilds:
        out.write(f"=== GUILD: {g['guild_name']} (ID: {g['guild_id']}) - Members: {g['approximate_member_count']} ===\n")
        for r in g["roles"]:
            pos = r["position"]
            rid = r["id"]
            name = r["name"]
            color = r["color"]
            perms = ", ".join(r["permissions"])
            managed = " [Managed/Bot]" if r["managed"] else ""
            hoist = " [Hoisted]" if r["hoist"] else ""
            out.write(f"  [{pos:2d}] {name}{managed}{hoist} (ID: {rid}) | Color: {color} | Perms: {perms}\n")
        out.write("\n")

print("Written summary to scripts/roles_summary.txt")
