"""
Inspect and remove auto-created stray report channels from foreign servers,
and reset their owner_reports_config in SQLite database.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import aiohttp
from dotenv import load_dotenv
from database.database import Database

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")

FOREIGN_GUILDS = [
    1428058914141900860,
    1494692962041467005,
    1516486851387588640,
    1545715275062575175,
    1552400206811631687,
]

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }
    db = Database()
    await db.connect()

    async with aiohttp.ClientSession() as s:
        for gid in FOREIGN_GUILDS:
            print(f"\n--- Checking Foreign Guild {gid} ---")
            async with s.get(f"https://discord.com/api/v10/guilds/{gid}/channels", headers=headers) as r:
                if r.status != 200:
                    print(f"Could not fetch channels for {gid}: {r.status}")
                    continue
                channels = await r.json()

            # Find categories and channels created by auto-repair
            target_channels = []
            target_categories = []
            for c in channels:
                name = c.get("name", "").lower()
                ctype = c.get("type")
                if ctype == 4 and "rai reports" in name:
                    target_categories.append(c)
                elif ctype == 0 and any(k in name for k in ["system-report", "security-report", "mod-report", "bot-report", "music-report", "room-report"]):
                    target_channels.append(c)

            print(f"Found {len(target_channels)} stray channels and {len(target_categories)} stray categories in guild {gid}")

            # Delete channels first
            for ch in target_channels:
                cid = ch.get("id")
                cname = ch.get("name")
                async with s.delete(f"https://discord.com/api/v10/channels/{cid}", headers=headers) as del_r:
                    print(f"  Deleted channel {cid} ({cname}): status {del_r.status}")
                await asyncio.sleep(0.5)

            # Delete categories
            for cat in target_categories:
                cid = cat.get("id")
                cname = cat.get("name")
                async with s.delete(f"https://discord.com/api/v10/channels/{cid}", headers=headers) as del_r:
                    print(f"  Deleted category {cid} ({cname}): status {del_r.status}")
                await asyncio.sleep(0.5)

            # Reset database config for this guild so it stays clean
            await db._db.execute(
                """
                UPDATE owner_reports_config
                SET category_id = NULL,
                    security_report_id = NULL,
                    mod_report_id = NULL,
                    music_report_id = NULL,
                    room_report_id = NULL,
                    bot_report_id = NULL,
                    system_report_id = NULL,
                    auto_repair = 0,
                    startup_reports_enabled = 0
                WHERE guild_id = ?
                """,
                (gid,),
            )
            await db._db.commit()
            print(f"Reset owner_reports_config for guild {gid} (auto_repair=0, startup_reports_enabled=0)")

    await db.close()
    print("\nCleanup of foreign servers complete!")

if __name__ == "__main__":
    asyncio.run(main())
