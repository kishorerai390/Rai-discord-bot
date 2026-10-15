with open('web/ui.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    l_lower = line.lower()
    if any(k in l_lower for k in ['rendermusic', 'path === "/music"', "path === '/music'", 'data-page="music"', 'id="music']):
        print(f"{i+1}: {line.strip()[:100]}")
