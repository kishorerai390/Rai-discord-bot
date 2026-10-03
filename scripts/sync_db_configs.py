"""
Synchronize SQLite database with the new server layout channel and category IDs.
Executes schema migrations and sets active configuration IDs.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from database.database import Database

GUILD_ID = 1457382179981099090

# Channel and Category IDs from live layout
HIDDEN_CATEGORY_ID = 1554891489564434677
CREATE_PRIVATE_ROOM_ID = 1554891386577485927

DYNAMIC_CATEGORY_ID = 1554891379174416474
CREATE_TEMP_ROOM_ID = 1554891383117193307

SECURITY_ALERT_CH_ID = 1554891447176667178
MODERATION_LOG_CH_ID = 1554891451140149352
SECURITY_LOG_CH_ID = 1554891455003107338
TICKET_LOG_CH_ID = 1554891458228519014
AUTOMATION_LOG_CH_ID = 1554891462846447631


async def main():
    print("Connecting to data/bot.db and applying migrations...")
    db = Database(Path("data/bot.db"))
    await db.connect()

    # 1. Update Hidden Voice Config
    print("Updating hidden_voice_config...")
    await db.update_hidden_voice_config(
        GUILD_ID,
        enabled=True,
        category_id=HIDDEN_CATEGORY_ID,
        entry_channel_id=CREATE_PRIVATE_ROOM_ID,
        max_rooms_per_user=1,
        max_users_per_room=99,
        empty_grace_period=60,
        allow_invited_members=True,
        allow_ownership_transfer=True,
        staff_can_view_hidden_rooms=False,  # CRITICAL: Default false
        automatic_cleanup=True,
        automatic_owner_transfer=False,
        room_name_format="🔒・{username}-private",
    )
    hv_cfg = await db.get_hidden_voice_config(GUILD_ID)
    print(f"Hidden Voice Config active: category={hv_cfg.category_id}, entry={hv_cfg.entry_channel_id}, staff_view={hv_cfg.staff_can_view_hidden_rooms}")

    # 2. Update Temp Voice Config (Public dynamic rooms)
    print("Updating temp_voice_config...")
    await db.update_temp_voice_config(
        GUILD_ID,
        enabled=True,
        hub_channel_id=CREATE_TEMP_ROOM_ID,
        category_id=DYNAMIC_CATEGORY_ID,
        default_user_limit=0,
    )
    tv_cfg = await db.get_temp_voice_config(GUILD_ID)
    print(f"Temp Voice Config active: hub={tv_cfg.hub_channel_id}, category={tv_cfg.category_id}")

    # 3. Update Logging Config with the new Staff & Security channels
    print("Updating logging_config...")
    await db.update_logging_config(
        GUILD_ID,
        enabled=True,
        security_channel_id=SECURITY_LOG_CH_ID,
        moderation_channel_id=MODERATION_LOG_CH_ID,
    )
    log_cfg = await db.get_logging_config(GUILD_ID)
    print(f"Logging Config active: security={log_cfg.security_channel_id}, moderation={log_cfg.moderation_channel_id}")

    await db.close()
    print("Database sync complete!")


if __name__ == "__main__":
    asyncio.run(main())
