import sqlite3
conn = sqlite3.connect("data/bot.db")
c = conn.cursor()
c.execute("PRAGMA table_info(guild_config)")
print([r[1] for r in c.fetchall()])
c.execute("SELECT guild_id FROM guild_config LIMIT 5")
print("Guild IDs:", c.fetchall())
conn.close()
