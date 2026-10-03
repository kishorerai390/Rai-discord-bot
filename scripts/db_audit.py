import asyncio
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.database import Database

async def audit():
    db = Database()
    await db.connect()
    
    # 1. Integrity
    ok, errors = await db.check_integrity()
    print(f"Database Integrity: {'OK' if ok else 'FAILED'} (Errors: {errors})")

    # 2. Schema version
    async with db._db.execute("SELECT MAX(version) FROM schema_version") as c:
        v = (await c.fetchone())[0]
    print(f"Current Schema Version: {v}")

    # 3. Table and index counts
    async with db._db.execute("SELECT name FROM sqlite_master WHERE type='table'") as c:
        tables = [r[0] for r in await c.fetchall()]
    print(f"Total Tables: {len(tables)}")

    async with db._db.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index'") as c:
        indexes = await c.fetchall()
    print(f"Total Indexes: {len(indexes)}")

    # 4. PRAGMA checks
    for pragma in ["journal_mode", "synchronous", "foreign_keys", "busy_timeout"]:
        async with db._db.execute(f"PRAGMA {pragma};") as c:
            val = (await c.fetchone())[0]
            print(f"PRAGMA {pragma}: {val}")

    # 5. Measure query latency
    t0 = time.perf_counter()
    for _ in range(100):
        async with db._db.execute("SELECT 1") as c:
            await c.fetchone()
    avg_latency_ms = (time.perf_counter() - t0) * 10
    print(f"Average 'SELECT 1' latency: {avg_latency_ms:.3f} ms")

    # 6. Check critical table indexes
    critical_tables = ['workflow_executions', 'workflow_events', 'command_metrics', 'security_incidents', 'dynamic_room_events', 'music_analytics']
    for t in critical_tables:
        async with db._db.execute(f"PRAGMA index_list({t});") as c:
            idxs = await c.fetchall()
            print(f"Table {t}: {[r[1] for r in idxs]}")

    await db.close()

if __name__ == "__main__":
    asyncio.run(audit())
