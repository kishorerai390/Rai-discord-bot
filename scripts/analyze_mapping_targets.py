import json
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    with open('data/live_audit_dump.json', 'r', encoding='utf-8') as f:
        dump = json.load(f)

    channels = dump.get('channels', [])
    cats = {c['id']: c for c in channels if c.get('type') == 4}
    
    # Analyze text channels and voice channels
    text_chans = [c for c in channels if c.get('type') in (0, 5)]
    vc_chans = [c for c in channels if c.get('type') in (2, 13)]

    print(f"Total Categories: {len(cats)}")
    print(f"Total Text/Announcement Channels: {len(text_chans)}")
    print(f"Total Voice/Stage Channels: {len(vc_chans)}")

    # Let's see all text channels and their current names and IDs
    print("\n--- EXISTING TEXT CHANNELS ---")
    for ch in text_chans:
        parent = cats.get(ch.get('parent_id'), {}).get('name', 'NO_CAT')
        print(f"ID: {ch['id']} | Parent: {parent[:20]:20s} | Name: #{ch['name']}")

    print("\n--- EXISTING VOICE CHANNELS ---")
    for vc in vc_chans:
        parent = cats.get(vc.get('parent_id'), {}).get('name', 'NO_CAT')
        print(f"ID: {vc['id']} | Parent: {parent[:20]:20s} | Name: {vc['name']} (limit: {vc.get('user_limit', 0)})")

if __name__ == '__main__':
    main()
