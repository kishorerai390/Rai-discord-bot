import re

with open("cogs/music.py", "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

classes = re.findall(r'class\s+([a-zA-Z0-9_]+)(\(.*?\))?:', content)
print("Music classes:")
for c, b in classes:
    print(f"  - {c} {b}")

methods = re.findall(r'def\s+([a-zA-Z0-9_]+)\(self', content)
print("\nKey methods in cogs/music.py:")
print(", ".join(methods[:30]))

print("\nError handling and reconnects in music.py:")
error_mentions = re.findall(r'except\s+([a-zA-Z0-9_]+(\s+as\s+[a-zA-Z0-9_]+)?)', content)
print(f"Total try/except blocks: {len(error_mentions)}")
print(f"Unique exception types: {set(m[0].split()[0] for m in error_mentions)}")
