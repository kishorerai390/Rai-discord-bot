import re
from collections import Counter

with open('music_bot/commands/music_cog.py', 'r', encoding='utf-8') as f:
    content = f.read()

app_cmds = re.findall(r'@app_commands\.command\s*\(\s*name\s*=\s*["\']([^"\']+)["\']', content)
print('App commands count:', len(app_cmds))
app_counts = Counter(app_cmds)
dup_app = {k: v for k, v in app_counts.items() if v > 1}
print('Duplicate app commands:', dup_app)

pfx_cmds = re.findall(r'@commands\.command\s*\(\s*name\s*=\s*["\']([^"\']+)["\']', content)
print('Prefix commands count:', len(pfx_cmds))
pfx_counts = Counter(pfx_cmds)
dup_pfx = {k: v for k, v in pfx_counts.items() if v > 1}
print('Duplicate prefix commands:', dup_pfx)
