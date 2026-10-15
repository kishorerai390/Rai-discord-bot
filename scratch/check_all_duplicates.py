import os
import re
from collections import defaultdict

app_cmds = defaultdict(list)
pfx_cmds = defaultdict(list)

for root, _, files in os.walk('music_bot'):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8') as fh:
                txt = fh.read()
            for m in re.finditer(r'@app_commands\.command\s*\(\s*name\s*=\s*["\']([^"\']+)["\']', txt):
                app_cmds[m.group(1)].append(p)
            for m in re.finditer(r'@commands\.command\s*\(\s*name\s*=\s*["\']([^"\']+)["\']', txt):
                pfx_cmds[m.group(1)].append(p)

print('Duplicate App Commands across music_bot:')
dup_app = {k: v for k, v in app_cmds.items() if len(v) > 1}
if not dup_app:
    print('  None!')
else:
    for k, v in dup_app.items():
        print(f'  /{k}: {len(v)} occurrences -> {v}')

print('\nDuplicate Prefix Commands across music_bot:')
dup_pfx = {k: v for k, v in pfx_cmds.items() if len(v) > 1}
if not dup_pfx:
    print('  None!')
else:
    for k, v in dup_pfx.items():
        print(f'  !{k}: {len(v)} occurrences -> {v}')
