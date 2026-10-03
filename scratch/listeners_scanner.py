import os
import re

cogs_dir = "cogs"
listeners_map = {}

for f in sorted(os.listdir(cogs_dir)):
    if f.endswith(".py") and not f.startswith("__"):
        path = os.path.join(cogs_dir, f)
        with open(path, "r", encoding="utf-8", errors="ignore") as fp:
            content = fp.read()
        
        matches = re.findall(r'@commands\.Cog\.listener\(\)\s+async def ([a-zA-Z0-9_]+)\(self,?\s*([^)]*)\)', content)
        if matches:
            listeners_map[f] = matches

for cog, list_matches in listeners_map.items():
    print(f"[{cog}]")
    for name, params in list_matches:
        print(f"  - {name}({params})")
