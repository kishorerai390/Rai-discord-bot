import sqlite3

con = sqlite3.connect('data/bot.db')
cur = con.cursor()
tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for tname in tables:
    try:
        rows = cur.execute(f"SELECT * FROM {tname}").fetchall()
        for r in rows:
            if '1555428426607894570' in str(r):
                print(f"Match in {tname}: {r}")
    except Exception as e:
        pass
print("Done")
