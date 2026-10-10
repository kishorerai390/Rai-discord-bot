import json

with open("data/live_audit_dump.json", "r", encoding="utf-8") as f:
    data = json.load(f)

guild = data["guild"]
roles = data["roles"]
bots = data["bots"]
channels = data["channels"]
activity = data["activity"]

out_lines = []
def p(s=""):
    out_lines.append(str(s))

p(f"=== GUILD: {guild['name']} ({guild['id']}) ===")
p(f"Owner ID: {guild['owner_id']} | Humans: {guild['human_count']} | Bots: {guild['bot_count']}")

p("\n=== ROLES WITH ADMIN ===")
for r in roles:
    if r["is_admin"]:
        p(f"Pos {r['position']:02d} | {r['name']} (ID: {r['id']}) | members: {r['member_count']} | managed: {r['managed']}")

p("\n=== ROLES WITH MODERATION (KICK/BAN/MANAGE_MESSAGES) ===")
for r in roles:
    if r["is_mod"] and not r["is_admin"]:
        p(f"Pos {r['position']:02d} | {r['name']} (ID: {r['id']}) | members: {r['member_count']}")

p("\n=== ALL ROLES IN HIERARCHY ===")
for r in roles:
    p(f"Pos {r['position']:02d} | {r['name']} (ID: {r['id']}) | members: {r['member_count']} | admin: {r['is_admin']}")

p("\n=== BOTS & ROLES ===")
for b in bots:
    p(f"Bot: {b['name']} ({b['id']}) | Admin: {b['has_admin']} | Roles: {b['roles']}")

categories = [c for c in channels if c.get("type") == 4]
categories.sort(key=lambda x: x.get("position", 0))

p(f"\n=== CHANNELS SUMMARY (Total: {len(channels)}) ===")
cat_ids = {c["id"]: c["name"] for c in categories}
cat_channels = {}
orphan_channels = []
for c in channels:
    pid = c.get("parent_id")
    if pid in cat_ids:
        cat_channels.setdefault(pid, []).append(c)
    elif c.get("type") != 4:
        orphan_channels.append(c)

for cat in categories:
    cid = cat["id"]
    cname = cat["name"]
    children = cat_channels.get(cid, [])
    children.sort(key=lambda x: x.get("position", 0))
    p(f"\n[Category: {cname}] (ID: {cid}, pos: {cat.get('position')}, channels: {len(children)})")
    for ch in children:
        t = "VC" if ch["type"] == 2 else ("Text" if ch["type"] in (0, 5) else f"Type {ch['type']}")
        act = activity.get(ch["id"], {})
        rec = act.get("count_recent", "-")
        last_time = act.get("last_msg_time", "")
        last_author = act.get("last_msg_author", "")
        msg_info = f"msgs={rec} (last: {last_author} @ {last_time[:10] if last_time else 'none'})" if t == "Text" else ""
        p(f"  {t:4s} | {ch['name']} ({ch['id']}) {msg_info}")

if orphan_channels:
    p("\n[Orphan Channels]:")
    for ch in orphan_channels:
        p(f"  {ch['name']} ({ch['id']})")

with open("data/audit_summary.txt", "w", encoding="utf-8") as out:
    out.write("\n".join(out_lines))

print("Analysis successfully written to data/audit_summary.txt")
