import asyncio
import aiosqlite
from database.migrations import run_migrations

async def main():
    async with aiosqlite.connect(":memory:") as db:
        v = await run_migrations(db)
        print("Final version:", v)
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
            tables = [row[0] for row in await cursor.fetchall()]
            print("Tables count:", len(tables))
            print("community_gaming_profiles in tables:", "community_gaming_profiles" in tables)

asyncio.run(main())
