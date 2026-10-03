"""
Migration CLI runner script.
Executes pending database migrations and verifies current schema version.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATABASE_PATH
from database.database import Database


async def main():
    print("=" * 45)
    print("      DATABASE MIGRATION RUNNER")
    print("=" * 45)
    print(f"Target Database: {DATABASE_PATH}")

    db = Database(DATABASE_PATH)
    try:
        await db.connect()
        async with db._db.execute("SELECT MAX(version) FROM schema_version") as cursor:
            row = await cursor.fetchone()
            version = row[0] if row and row[0] is not None else 0
        print(f"[OK] Database successfully updated to schema v{version}")

        # Run integrity check
        ok, errors = await db.check_integrity()
        if not ok:
            print(f"[ERROR] Database integrity checks failed: {errors}")
            sys.exit(3)
        print("[OK] Foreign keys and integrity verified.")
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(3)
    finally:
        await db.close()

    print("Migration finished cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
