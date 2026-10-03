import sqlite3
from pathlib import Path

for p in Path('.').rglob('*.db'):
    if '.venv' in str(p):
        continue
    try:
        conn = sqlite3.connect(p)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'workflow%'")
        tables = [r[0] for r in c.fetchall()]
        print(f"{p}: {tables}")
        conn.close()
    except Exception as e:
        print(f"{p}: error {e}")
