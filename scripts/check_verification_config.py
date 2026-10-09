import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "F:/Bot")
from database.database import Database

async def run():
    db = Database("data/bot.db")
    await db.connect()
    cfg = await db.get_verification_config(1457382179981099090)
    print(f"Verification Config for 1457382179981099090:")
    print(f"  • Enabled: {cfg.enabled}")
    print(f"  • Role ID: {cfg.role_id}")
    print(f"  • Min Account Age (Hours): {cfg.min_account_age_hours}")

    if cfg.min_account_age_hours < 24:
        print("  • Updating min_account_age_hours to 24 hours (1-day anti-alt shield)...")
        await db.update_verification_config(
            guild_id=1457382179981099090,
            enabled=True,
            min_account_age_hours=24,
        )
        print("  ✅ Updated: Minimum account age set to 24 hours!")

    await db._db.close()

if __name__ == "__main__":
    asyncio.run(run())
