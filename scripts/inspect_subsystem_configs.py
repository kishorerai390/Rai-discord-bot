import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('f:/Bot/data/bot.db')
cursor = conn.cursor()

configs = ['welcome_config', 'ticket_config', 'automod_config', 'logging_config', 'voiceguard_config', 'raid_config']

for c in configs:
    cursor.execute(f"PRAGMA table_info({c})")
    cols = [col[1] for col in cursor.fetchall()]
    cursor.execute(f"SELECT * FROM {c} WHERE guild_id = 1457382179981099090")
    rows = cursor.fetchall()
    print(f"\n=== {c} ===")
    print('Cols:', cols)
    for r in rows:
        print('Row:', r)

conn.close()
