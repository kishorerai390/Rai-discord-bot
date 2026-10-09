import asyncio
import aiosqlite
from pathlib import Path

GUILD_ID = 1457382179981099090
SECURITY_ALERTS_CH_ID = 1555283378612478072
DB_PATH = Path("data/bot.db")

async def main():
    if not DB_PATH.exists():
        print("Database does not exist at:", DB_PATH)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE autopilot_configs
            SET alert_channel_id = ?
            WHERE guild_id = ?
            """,
            (SECURITY_ALERTS_CH_ID, GUILD_ID)
        )
        await db.commit()
        print(f"Updated guild {GUILD_ID} autopilot alert_channel_id to {SECURITY_ALERTS_CH_ID}")

if __name__ == "__main__":
    asyncio.run(main())
