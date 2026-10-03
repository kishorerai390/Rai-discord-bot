with open("cogs/security.py", "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

import re
classes = re.findall(r'class\s+([a-zA-Z0-9_]+)(\(.*?\))?:', content)
print("Security classes:")
for c, b in classes:
    print(f"  - {c} {b}")

methods = re.findall(r'async def\s+([a-zA-Z0-9_]+)\(self', content)
print(f"\nTotal async methods in cogs/security.py: {len(methods)}")
print(", ".join(methods[:25]))

# check for rate limiting and lock mechanisms
locks = re.findall(r'asyncio\.Lock', content)
print(f"\nAsyncio locks in security.py: {len(locks)}")
