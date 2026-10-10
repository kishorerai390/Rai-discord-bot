import json

with open("data/live_audit_dump.json", "r", encoding="utf-8") as f:
    data = json.load(f)

channels = data["channels"]
roles = {r["id"]: r["name"] for r in data["roles"]}
roles[str(data["guild"]["id"])] = "@everyone"

lines = []
report_cat = next((c for c in channels if c.get("type") == 4 and "ʀᴇᴘᴏʀᴛs" in c.get("name", "")), None)
if report_cat:
    lines.append(f"Report Category: {report_cat['name']} ({report_cat['id']})")
    for ow in report_cat.get("permission_overwrites", []):
        target = roles.get(ow["id"], f"User/Role {ow['id']}")
        allow_bits = int(ow["allow"])
        deny_bits = int(ow["deny"])
        lines.append(f"  Target: {target} (type={ow['type']}) | View Allow: {bool(allow_bits & 1024)} | View Deny: {bool(deny_bits & 1024)}")

    for ch in channels:
        if ch.get("parent_id") == report_cat["id"]:
            lines.append(f"\nChannel: {ch['name']} ({ch['id']})")
            for ow in ch.get("permission_overwrites", []):
                target = roles.get(ow["id"], f"User/Role {ow['id']}")
                allow_bits = int(ow["allow"])
                deny_bits = int(ow["deny"])
                lines.append(f"  Target: {target} (type={ow['type']}) | View Allow: {bool(allow_bits & 1024)} | View Deny: {bool(deny_bits & 1024)}")

with open("data/reports_perms.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Permissions written to data/reports_perms.txt")
