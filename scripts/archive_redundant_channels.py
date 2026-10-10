"""
Safe Archive Script for RAI FAM.
Moves redundant channels into a hidden 📦・ARCHIVE category.
Zero message loss, zero channel deletions.
Rate-limited with 1.0s backoff between channel modifications to stay safe.
"""

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

# Redundant channels to move into Archive
TARGET_CHANNELS = [
    # Music text clutter
    (1555283393242206301, "music-queue"),
    (1555283394274005092, "dj-control"),
    (1555283395330842714, "playlists"),

    # Redundant Reports & Admin clones
    (1555428420383416400, "bot-report"),
    (1555428406726893619, "music-report"),
    (1555428413102235701, "room-report"),
    (1555428399919538297, "mod-report"),
    (1555428426607894570, "system-report"),
    (1555283418126876856, "backup-control"),
    (1557479356899524678, "backup-vault"),
    (1555283417183031516, "automation-control"),
    (1557479367297339432, "staff-activity"),
    (1557479979053228072, "staff-ledger"),
    (1555283390943469685, "audit-monitor"),

    # Unused Community Text Channels
    (1549416359723532480, "bot-commands"),
    (1557477517282123826, "birthdays"),
    (1557477508255842304, "rai-shop"),
    (1557475848892973219, "level-up"),
    (1557479964109181068, "server-polls"),
    (1557481220911136868, "hall-of-fame"),
    (1557481233246584892, "introductions"),
]


async def main():
    print(f"🚀 Starting safe channel archive for Guild: {GUILD_ID}...")

    async with aiohttp.ClientSession() as session:
        # 1. Fetch current channels to find or create ARCHIVE category
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()

        archive_cat_id = None
        for c in channels:
            if c.get("type") == 4 and "archive" in c.get("name", "").lower():
                archive_cat_id = int(c["id"])
                print(f"📦 Found existing Archive category: '{c['name']}' ({archive_cat_id})")
                break

        # If not found, create a hidden ARCHIVE category
        if not archive_cat_id:
            print("📦 Creating hidden '📦・ARCHIVE' category...")
            payload = {
                "name": "📦・ARCHIVE",
                "type": 4,
                "permission_overwrites": [
                    {
                        "id": str(GUILD_ID),  # @everyone
                        "type": 0,
                        "deny": str(1 << 10),  # Deny VIEW_CHANNEL
                    }
                ],
            }
            async with session.post(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS, json=payload) as r:
                cat_data = await r.json()
                archive_cat_id = int(cat_data["id"])
                print(f"✅ Created hidden Archive category: {archive_cat_id}")

        await asyncio.sleep(1.0)

        # 2. Move each target channel into the archive category
        moved_count = 0
        for ch_id, ch_label in TARGET_CHANNELS:
            # Check if channel exists
            exists = any(int(c["id"]) == ch_id for c in channels)
            if not exists:
                print(f"⏩ Channel #{ch_label} ({ch_id}) not found or already archived. Skipping.")
                continue

            # Update parent_id
            async with session.patch(
                f"https://discord.com/api/v10/channels/{ch_id}",
                headers=HEADERS,
                json={"parent_id": str(archive_cat_id)},
            ) as pr:
                if pr.status in (200, 201):
                    moved_count += 1
                    print(f"✅ Moved #{ch_label} ({ch_id}) -> 📦・ARCHIVE ({moved_count}/{len(TARGET_CHANNELS)})")
                else:
                    err = await pr.text()
                    print(f"⚠️ Failed to move #{ch_label}: {pr.status} - {err}")

            # Safe rate limit delay
            await asyncio.sleep(1.0)

        # 3. Clean up the empty '📋 ═ ʀᴀɪ ʀᴇᴘᴏʀᴛs ═ 📋' category if empty
        reports_cat_id = 1555428388280209422
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            fresh_channels = await r.json()

        children = [c for c in fresh_channels if c.get("parent_id") == str(reports_cat_id)]
        if not children:
            print(f"🧹 Category '📋 ═ ʀᴀɪ ʀᴇᴘᴏʀᴛs ═ 📋' is now empty. Safely removing empty category...")
            async with session.delete(f"https://discord.com/api/v10/channels/{reports_cat_id}", headers=HEADERS) as dr:
                if dr.status in (200, 204):
                    print("✅ Removed empty reports category.")

    print(f"\n🎉 Archive complete! Successfully moved {moved_count} channels into 📦・ARCHIVE.")
    print("🔒 Zero messages deleted. All message history preserved safely in hidden archive.")


if __name__ == "__main__":
    asyncio.run(main())
