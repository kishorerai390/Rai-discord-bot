import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "f:/Bot")

import aiohttp
from dotenv import load_dotenv
from database.database import Database

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_GUILD_ID = 1457382179981099090

async def review():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json"
    }

    db = Database(Path("data/bot.db"))
    await db.connect()

    async with aiohttp.ClientSession() as session:
        # Fetch Guild
        async with session.get(f"https://discord.com/api/v10/guilds/{TARGET_GUILD_ID}?with_counts=true", headers=headers) as resp:
            if resp.status != 200:
                print(f"Error fetching guild: {resp.status}")
                return
            guild_data = await resp.json()

        # Fetch Channels
        async with session.get(f"https://discord.com/api/v10/guilds/{TARGET_GUILD_ID}/channels", headers=headers) as resp:
            channels = await resp.json()

        # Fetch Roles
        async with session.get(f"https://discord.com/api/v10/guilds/{TARGET_GUILD_ID}/roles", headers=headers) as resp:
            roles = await resp.json()

    print("=" * 60)
    print(f"🏰 SERVER AUDIT & REVIEW: {guild_data.get('name')} ({guild_data.get('id')})")
    print("=" * 60)

    total_members = guild_data.get("approximate_member_count", 0)
    online_members = guild_data.get("approximate_presence_count", 0)
    owner_id = guild_data.get("owner_id")
    boost_tier = guild_data.get("premium_tier", 0)
    boosts = guild_data.get("premium_subscription_count", 0)

    print(f"👑 Server Owner ID: {owner_id}")
    print(f"👥 Approx Members: {total_members} Total | {online_members} Active / Online")
    print(f"✨ Server Boosts: Tier {boost_tier} ({boosts} Boosts)")
    print(f"📁 Total Channels & Categories: {len(channels)}")
    print(f"🎭 Total Roles: {len(roles)}")

    # Channel categorization
    categories = [c for c in channels if c.get("type") == 4]
    categories.sort(key=lambda c: c.get("position", 0))

    text_channels = [c for c in channels if c.get("type") in (0, 5)]  # text or announcement
    voice_channels = [c for c in channels if c.get("type") == 2]

    print(f"\nBreakdown: {len(categories)} Categories | {len(text_channels)} Text Channels | {len(voice_channels)} Voice Channels")

    print("\n--- CATEGORY ARCHITECTURE ---")
    for cat in categories:
        cat_id = cat.get("id")
        cat_channels = [c for c in channels if c.get("parent_id") == cat_id]
        cat_channels.sort(key=lambda c: c.get("position", 0))
        print(f"📁 [{cat.get('position', 0):02d}] {cat.get('name')} ({len(cat_channels)} channels)")
        for c in cat_channels[:3]:
            icon = "💬" if c.get("type") in (0, 5) else "🔊"
            print(f"    {icon} {c.get('name')}")
        if len(cat_channels) > 3:
            print(f"    ... and {len(cat_channels) - 3} more")

    # Verification channel check
    print("\n--- ONBOARDING & VERIFICATION AUDIT ---")
    verify_ch = next((c for c in channels if "verify" in c.get("name", "").lower()), None)
    if verify_ch:
        print(f"✅ Entry Channel: #{verify_ch.get('name')} (ID: {verify_ch.get('id')}, Position: {verify_ch.get('position')})")
        # Check permissions for @everyone
        overwrites = verify_ch.get("permission_overwrites", [])
        everyone_ow = next((o for o in overwrites if o.get("id") == TARGET_GUILD_ID), None)
        if everyone_ow:
            print(f"   @everyone Overwrite: Allow={everyone_ow.get('allow')}, Deny={everyone_ow.get('deny')}")
    else:
        print("⚠️ No verify channel found!")

    # Hidden Rooms Check
    print("\n--- HIDDEN ROOMS SUBSYSTEM AUDIT ---")
    hidden_cat = next((c for c in categories if "HIDDEN ROOMS" in c.get("name", "").upper()), None)
    hidden_entry = next((c for c in voice_channels if "CREATE PRIVATE ROOM" in c.get("name", "").upper()), None)
    hidden_cfg = await db.get_hidden_voice_config(TARGET_GUILD_ID)

    if hidden_cat:
        print(f"✅ Category: {hidden_cat.get('name')} (ID: {hidden_cat.get('id')})")
    else:
        print("⚠️ Hidden Rooms category missing!")

    if hidden_entry:
        print(f"✅ Voice Entry: {hidden_entry.get('name')} (ID: {hidden_entry.get('id')})")
    else:
        print("⚠️ Hidden Voice entry missing!")

    print(f"   Database Setting: Category ID={hidden_cfg.category_id}, Generator ID={hidden_cfg.entry_channel_id}, Staff Visibility={hidden_cfg.staff_can_view_hidden_rooms}")

    # Security & Roles
    print("\n--- SECURITY & PERMISSION POSTURE ---")
    admin_roles = []
    mention_roles = []
    for r in roles:
        if r.get("name") == "@everyone":
            continue
        perms = int(r.get("permissions", 0))
        # 0x8 is ADMINISTRATOR
        if perms & 0x8:
            admin_roles.append(r.get("name"))
        # 0x20000 is MENTION_EVERYONE
        if perms & 0x20000:
            mention_roles.append(r.get("name"))

    print(f"🛡️ Roles with Administrator: {admin_roles}")
    print(f"📢 Roles with @everyone Mention: {mention_roles}")

    sec_cfg = await db.get_security_config(TARGET_GUILD_ID)
    print(f"🔒 Anti-Nuke: {'🟢 Active' if sec_cfg.anti_nuke else '⚪ Disabled'}")
    print(f"🔒 Anti-Raid: {'🟢 Active' if sec_cfg.anti_raid else '⚪ Disabled'}")
    print(f"🔒 Anti-Spam: {'🟢 Active' if sec_cfg.anti_spam else '⚪ Disabled'}")
    print(f"🚨 Panic Mode: {'🔴 Active' if sec_cfg.panic_mode else '🟢 Normal'}")

    # Database health
    print("\n--- RAI DATABASE EXTENSIONS ---")
    events = await db.list_events(TARGET_GUILD_ID)
    music_an = await db.get_music_analytics(TARGET_GUILD_ID)
    print(f"📅 Community Events: {len(events)}")
    print(f"🎧 Music Analytics: {music_an.tracks_played} plays, {music_an.total_playtime_seconds}s playtime")

    await db.close()

if __name__ == "__main__":
    asyncio.run(review())
