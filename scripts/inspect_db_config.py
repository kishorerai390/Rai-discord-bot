import sqlite3

conn = sqlite3.connect('f:/Bot/data/bot.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [t[0] for t in cursor.fetchall()]
print('Tables in bot.db:', tables)

for target in ['verification_config', 'verification_settings', 'server_stats_config', 'temp_voice_config', 'guild_settings']:
    if target in tables:
        cursor.execute(f"PRAGMA table_info({target})")
        cols = [c[1] for c in cursor.fetchall()]
        cursor.execute(f"SELECT * FROM {target}")
        rows = cursor.fetchall()
        print(f"\n--- {target} ({cols}) ---")
        for r in rows:
            print(r)

conn.close()
