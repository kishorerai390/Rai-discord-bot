import os
import re

print("=== GATHERING DEEP AUDIT DATA ===")

# 1. Inspect requirements.txt
if os.path.exists("requirements.txt"):
    with open("requirements.txt", "r") as fp:
        reqs = fp.read().splitlines()
    print(f"Requirements ({len(reqs)} items):")
    for r in reqs:
        if r.strip() and not r.startswith("#"):
            print(f"  - {r.strip()}")

# 2. Inspect database tables in database/models.py and database/database.py
db_files = ["database/database.py", "database/models.py", "database/migrations.py"]
for db_f in db_files:
    if os.path.exists(db_f):
        with open(db_f, "r", encoding="utf-8") as fp:
            c = fp.read()
        classes = re.findall(r'class\s+([a-zA-Z0-9_]+)', c)
        tables = re.findall(r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z0-9_]+)', c, re.IGNORECASE)
        tables += re.findall(r'CREATE\s+TABLE\s+([a-zA-Z0-9_]+)', c, re.IGNORECASE)
        print(f"\n{db_f}:")
        print(f"  Classes: {classes}")
        print(f"  Tables: {list(set(tables))}")

# 3. Inspect Background Tasks
print("\n=== BACKGROUND TASKS (@tasks.loop) ===")
for root, dirs, files in os.walk("."):
    if ".venv" in root or "__pycache__" in root or ".git" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
            loops = re.findall(r'@tasks\.loop\((.*?)\)\s+async def ([a-zA-Z0-9_]+)', content, re.DOTALL)
            for args, name in loops:
                clean_args = " ".join(args.split())
                print(f"  [{f}] def {name}({clean_args})")

# 4. Inspect Tests
print("\n=== TESTS ===")
test_files = [f for f in os.listdir("tests") if f.endswith(".py") and not f.startswith("__")]
print(f"Found {len(test_files)} test files:")
for tf in sorted(test_files):
    print(f"  - {tf}")
