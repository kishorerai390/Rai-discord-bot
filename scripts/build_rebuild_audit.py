import json
import os
import shutil
import sys
from datetime import datetime

def generate_audit_and_backup():
    sys.stdout.reconfigure(encoding='utf-8')
    with open('data/live_audit_dump.json', 'r', encoding='utf-8') as f:
        dump = json.load(f)

    # 1. Create timestamped backup
    os.makedirs('data/backups/server_rebuild', exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'data/backups/server_rebuild/backup_guild_1457382179981099090_{ts}.json'
    with open(backup_path, 'w', encoding='utf-8') as f_out:
        json.dump(dump, f_out, indent=2, ensure_ascii=False)
    print(f"Timestamped backup created at: {backup_path}")

    guild = dump.get('guild', {})
    roles = sorted(dump.get('roles', []), key=lambda x: x.get('position', 0), reverse=True)
    channels = dump.get('channels', [])

    print(f"\nGuild ID: {guild.get('id')}")
    print(f"Guild Name: {guild.get('name')}")
    print(f"Total Roles: {len(roles)}")
    print(f"Total Channels: {len(channels)}")

    # Summary of roles
    print("\n--- ROLES INVENTORY ---")
    admin_roles = []
    mod_roles = []
    bot_roles = []
    member_roles = []
    for r in roles:
        rid = r.get('id')
        name = r.get('name')
        pos = r.get('position', 0)
        perms = int(r.get('permissions', 0)) if str(r.get('permissions', 0)).isdigit() else 0
        is_admin = bool(perms & 8)
        is_mod = bool(perms & (1 << 13) or perms & (1 << 1) or perms & (1 << 2)) # Manage Server, Kick, Ban
        is_managed = r.get('managed', False)

        entry = {"id": rid, "name": name, "pos": pos, "is_admin": is_admin, "is_managed": is_managed}
        if is_admin:
            admin_roles.append(entry)
        elif is_mod:
            mod_roles.append(entry)
        elif is_managed or "bot" in name.lower():
            bot_roles.append(entry)
        else:
            member_roles.append(entry)

    print(f"Admin Roles ({len(admin_roles)}): {[r['name'] for r in admin_roles]}")
    print(f"Mod Roles ({len(mod_roles)}): {[r['name'] for r in mod_roles]}")
    print(f"Bot/Managed Roles ({len(bot_roles)}): {[r['name'] for r in bot_roles]}")
    print(f"Member/Other Roles ({len(member_roles)}): {len(member_roles)} roles")

if __name__ == '__main__':
    generate_audit_and_backup()
