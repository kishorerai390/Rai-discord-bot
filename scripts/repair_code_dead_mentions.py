import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Dead channel ID to active channel ID map
MAPPING = {
    '1555283414205075509': '1545502730699808768', # old dashboard -> general-chat
    '1555283396660428830': '1555283393242206301', # old song-requests -> music-queue
    '1555283378612478072': '1555283387340562574', # old security alerts -> mod-logs
    '1555255317170749472': '1555255325706424412', # old lounge 1 -> Lost Tunes
    '1555255321948327936': '1558483052550692884', # old lounge 2 -> Vibe Check
    '1555255319494402141': '1558676274526814263', # old lounge 3 -> Midnight Beats
    '1558483087283720352': '1555255325706424412', # old beats -> Lost Tunes
    '1554905803666751590': '1555255325706424412', # old 24/7 beats -> Lost Tunes
    '1558482965175078994': '1545502730699808768', # old clip chat -> general-chat
    '1558168338386129004': '1555283387340562574', # old containment -> mod-logs
    '1555428426607894570': '1545502730699808768', # old lounge -> general-chat
}

files_to_fix = [
    'f:/Bot/utils/community_features.py',
    'f:/Bot/utils/luxury_consoles.py',
    'f:/Bot/utils/music_consoles.py',
    'f:/Bot/utils/realtime_consoles.py',
]

for fpath in files_to_fix:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    modified = False
    for dead_id, active_id in MAPPING.items():
        if dead_id in content:
            content = content.replace(f'<#{dead_id}>', f'<#{active_id}>')
            content = content.replace(dead_id, active_id)
            modified = True
            print(f"Replaced {dead_id} -> {active_id} in {fpath}")

    if modified:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Updated {fpath}")

print("Done updating code references!")
