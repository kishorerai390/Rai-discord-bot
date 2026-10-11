import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('f:/Bot/data/bot.db')
cursor = conn.cursor()

# 1. Update ticket_config category_id to SUPPORT category (1558679085293510746)
cursor.execute('''
    UPDATE ticket_config 
    SET category_id = 1558679085293510746 
    WHERE guild_id = 1457382179981099090
''')
print("✅ Updated ticket_config category_id to ✦ SUPPORT ✦ (1558679085293510746)")

# 2. Update logging_config to route dead 404 channels to mod-logs and bot-report
cursor.execute('''
    UPDATE logging_config 
    SET security_channel_id = 1555283387340562574,
        voice_channel_id = 1555283387340562574
    WHERE guild_id = 1457382179981099090
''')
print("✅ Repaired logging_config dead channels to active #🛡️・mod-logs (1555283387340562574)")

conn.commit()
conn.close()
