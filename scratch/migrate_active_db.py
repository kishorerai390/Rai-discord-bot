import sys
import os
sys.path.insert(0, os.path.abspath("."))

import asyncio
import logging
from pathlib import Path
import aiosqlite
from database.migrations import run_migrations

logging.basicConfig(level=logging.INFO)

async def main():
    for db_name in ["data/bot.db", "data/sentinel.db"]:
        p = Path(db_name)
        if p.exists():
            print(f"--- Running migrations on {p} ---")
            async with aiosqlite.connect(p) as db:
                v = await run_migrations(db)
                print(f"{p} migrated to schema version {v}")

asyncio.run(main())
