import json
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    with open('data/live_audit_dump.json', 'r', encoding='utf-8') as f:
        d = json.load(f)

    print('=== GUILD INFO ===')
    g = d.get('guild', {})
    print(f"ID: {g.get('id')}")
    print(f"Name: {g.get('name')}")
    print(f"Owner ID: {g.get('owner_id')}")
    print(f"AFK Channel ID: {g.get('afk_channel_id')} (Timeout: {g.get('afk_timeout')}s)")
    print(f"System Channel ID: {g.get('system_channel_id')}")
    print(f"Rules Channel ID: {g.get('rules_channel_id')}")
    print(f"Public Updates Channel ID: {g.get('public_updates_channel_id')}")

    print('\n=== ROLES (Top to Bottom by position) ===')
    roles = sorted(d.get('roles', []), key=lambda x: x.get('position', 0), reverse=True)
    for r in roles:
        is_admin = bool(int(r.get('permissions', 0)) & 8)
        print(f"pos={r.get('position', 0):2d} | ID={r.get('id')} | color=0x{r.get('color', 0):06X} | admin={is_admin} | {r.get('name')}")

    print('\n=== BOTS & INTEGRATIONS ===')
    for b in d.get('bots', []):
        u = b.get('user', {})
        print(f"Bot: {u.get('username')}#{u.get('discriminator')} (ID: {u.get('id')}) | Roles: {b.get('roles')}")

    print('\n=== CATEGORIES & CHANNELS ===')
    channels = d.get('channels', [])
    cats = [c for c in channels if c.get('type') == 4]
    cats.sort(key=lambda x: x.get('position', 0))
    for cat in cats:
        print(f"\n[CATEGORY] {cat.get('name')} (ID: {cat.get('id')}, pos: {cat.get('position')})")
        children = [c for c in channels if c.get('parent_id') == cat.get('id')]
        children.sort(key=lambda x: x.get('position', 0))
        for ch in children:
            t_str = 'VC' if ch.get('type') == 2 else ('STAGE' if ch.get('type') == 13 else 'TEXT')
            print(f"   {t_str:5s} pos={ch.get('position', 0):2d} | #{ch.get('name')} | ID={ch.get('id')}")

    orphans = [c for c in channels if not c.get('parent_id') and c.get('type') != 4]
    if orphans:
        print('\n[NO CATEGORY / ORPHANS]')
        for ch in orphans:
            t_str = 'VC' if ch.get('type') == 2 else 'TEXT'
            print(f"   {t_str:5s} pos={ch.get('position', 0):2d} | #{ch.get('name')} | ID={ch.get('id')}")

if __name__ == '__main__':
    main()
