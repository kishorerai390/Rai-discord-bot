import re

with open("f:/Bot/utils/realtime_consoles.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find all custom_id defined
cids_defined = set(re.findall(r'["\']custom_id["\']:\s*["\']([^"\']+)["\']', content))
print("Custom IDs defined in payloads:")
for cid in sorted(cids_defined):
    print(" ", cid)

# Find all cid prefixes handled in handle_interaction
handled_prefixes = set(re.findall(r'cid\.startswith\(["\']([^"\']+)["\']\)', content))
print("\nPrefixes handled in RealtimeConsoleDispatcher:")
for p in sorted(handled_prefixes):
    print(" ", p)

print("\nMissing handlers:")
for cid in sorted(cids_defined):
    prefix = cid.split(":")[0] + ":"
    if prefix not in handled_prefixes and cid not in content[content.find("class RealtimeConsoleDispatcher"):]:
        print("  MISSING:", cid, f"(prefix: {prefix})")
