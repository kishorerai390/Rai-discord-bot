"""
Suggested Channel Improvements & Fixes for RAI FAM.
- Restores #bot-commands from ARCHIVE to COMMUNITY.
- Moves #late-night-talks from PODS & AFK to CHILL & HAVEN.
- Supports --dry-run (default) or --apply.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "F:/Bot")

import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# Target category IDs based on current live audit
COMMUNITY_CAT_ID = 1545803478490812578
CHILL_CAT_ID = 1554905799292231728

# Channel IDs
BOT_COMMANDS_CH_ID = 1549416359723532480  # Currently in Archive
LATE_NIGHT_TALKS_CH_ID = 1555641081578782840  # Currently in Pods & AFK


async def main():
    parser = argparse.ArgumentParser(description="Apply suggested server layout improvements.")
    parser.add_argument("--apply", action="store_true", help="Apply modifications to Discord API.")
    args = parser.parse_args()

    dry_run = not args.apply

    print("=" * 60)
    print("      SERVER CHANNEL IMPROVEMENTS & FIXES")
    print(f"      Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE APPLY'}")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        # 1. Move #bot-commands to Community category
        print("\n[1/2] Action: Restore #bot-commands to Community category")
        print(f"      Channel ID: {BOT_COMMANDS_CH_ID} -> Target Category: {COMMUNITY_CAT_ID}")
        if not dry_run:
            payload = {"parent_id": COMMUNITY_CAT_ID, "name": "🤖・bot-commands"}
            async with session.patch(
                f"https://discord.com/api/v10/channels/{BOT_COMMANDS_CH_ID}",
                headers=HEADERS,
                json=payload,
            ) as resp:
                if resp.status in (200, 204):
                    print("      [SUCCESS] Restored #bot-commands to Community!")
                else:
                    err = await resp.text()
                    print(f"      [ERROR] HTTP {resp.status}: {err}")
            await asyncio.sleep(1.0)
        else:
            print("      [DRY RUN] Would update parent_id to Community and rename to 🤖・bot-commands.")

        # 2. Move #late-night-talks to Chill & Haven category
        print("\n[2/2] Action: Move #late-night-talks to Chill & Haven category")
        print(f"      Channel ID: {LATE_NIGHT_TALKS_CH_ID} -> Target Category: {CHILL_CAT_ID}")
        if not dry_run:
            payload = {"parent_id": CHILL_CAT_ID, "name": "🌙・late-night-talks"}
            async with session.patch(
                f"https://discord.com/api/v10/channels/{LATE_NIGHT_TALKS_CH_ID}",
                headers=HEADERS,
                json=payload,
            ) as resp:
                if resp.status in (200, 204):
                    print("      [SUCCESS] Moved #late-night-talks to Chill & Haven!")
                else:
                    err = await resp.text()
                    print(f"      [ERROR] HTTP {resp.status}: {err}")
            await asyncio.sleep(1.0)
        else:
            print("      [DRY RUN] Would update parent_id to Chill & Haven and rename to 🌙・late-night-talks.")

    print("\n" + "=" * 60)
    if dry_run:
        print("Dry run completed. To execute live, run:")
        print("python scripts/apply_suggested_channel_improvements.py --apply")
    else:
        print("All actions completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
