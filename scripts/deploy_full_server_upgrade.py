"""
Full Server Upgrade:
1. Deploys Aesthetic Status Counters (Server Status & Vc Status from screenshot).
2. Deploys Simplified Text Channels:
   - ✦ START HERE ✦ (welcome, rules, announcements, get-roles, verify-here)
   - ✦ COMMUNITY ✦ (general-chat, media-dump, gaming-chat, editing-chat)
   - ✦ SUPPORT ✦ (support, suggestions)
   - ✦ STAFF ✦ (staff-chat, mod-logs)
   - ✦ BOT ✦ (bot-commands, music-queue)
3. Safely archives remaining secondary text channels into 📦・ARCHIVE (Zero data loss).
4. Updates SQLite configuration for autonomous bot syncing.
"""

from __future__ import annotations

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

ARCHIVE_CAT_ID = "1558532566544551947"


async def api_patch(session: aiohttp.ClientSession, url: str, data: dict, desc: str = ""):
    async with session.patch(url, headers=HEADERS, json=data) as resp:
        if resp.status in (200, 204):
            print(f"  [SUCCESS] {desc}")
            return await resp.json()
        else:
            err = await resp.text()
            print(f"  [ERROR] {desc} -> HTTP {resp.status}: {err}")
            return None


async def api_post(session: aiohttp.ClientSession, url: str, data: dict, desc: str = ""):
    async with session.post(url, headers=HEADERS, json=data) as resp:
        if resp.status in (200, 201):
            res = await resp.json()
            print(f"  [CREATED] {desc} (ID: {res.get('id')})")
            return res
        else:
            err = await resp.text()
            print(f"  [ERROR] {desc} -> HTTP {resp.status}: {err}")
            return None


async def main():
    print("=" * 65)
    print("      UPGRADING SERVER: AESTHETIC STATUS & SIMPLIFIED TEXT")
    print("=" * 65)

    async with aiohttp.ClientSession() as session:
        # Fetch current channels
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()

        # Fetch guild details for counts
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}?with_counts=true", headers=HEADERS) as r:
            guild_info = await r.json()

        approx_members = guild_info.get("approximate_member_count", 46)
        approx_online = guild_info.get("approximate_presence_count", 28)

        # -----------------------------------------------------------------
        # 1. AESTHETIC STATUS COUNTERS (Matches Screenshot)
        # -----------------------------------------------------------------
        print("\n[1/5] Aesthetic Status Counters (Matching Screenshot)")
        cat_stats_id = "1546059369085534229"
        await api_patch(session, f"https://discord.com/api/v10/channels/{cat_stats_id}", {"name": "🔒 Server Status!"}, "Rename Category to 🔒 Server Status!")
        await asyncio.sleep(1.2)

        server_stat_ch_id = "1546099701496029194"
        stat_name = f"🦋 {approx_online} online 🦋 {approx_members} members"
        await api_patch(session, f"https://discord.com/api/v10/channels/{server_stat_ch_id}", {"name": stat_name, "parent_id": cat_stats_id}, f"Rename Server Status VC to {stat_name}")
        await asyncio.sleep(1.2)

        # Create or find 🔒 Vc Status! category
        existing_vc_cat = next((c for c in channels if c.get("name") == "🔒 Vc Status!" and c.get("type") == 4), None)
        if not existing_vc_cat:
            vc_cat = await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": "🔒 Vc Status!", "type": 4}, "Create Category 🔒 Vc Status!")
            vc_cat_id = vc_cat["id"] if vc_cat else cat_stats_id
            await asyncio.sleep(1.2)
        else:
            vc_cat_id = existing_vc_cat["id"]

        vc_stat_ch_id = "1546099703630798848"
        vc_stat_name = "🦋 0 vc user 🦋 0 Active vc"
        await api_patch(session, f"https://discord.com/api/v10/channels/{vc_stat_ch_id}", {"name": vc_stat_name, "parent_id": vc_cat_id}, f"Rename VC Status to {vc_stat_name}")
        await asyncio.sleep(1.2)

        # Move old Bot counter into Archive
        await api_patch(session, "https://discord.com/api/v10/channels/1546059375574130769", {"parent_id": ARCHIVE_CAT_ID}, "Archive redundant Bot counter")
        await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # 2. ✦ START HERE ✦ CATEGORY
        # -----------------------------------------------------------------
        print("\n[2/5] ✦ START HERE ✦ Category")
        start_cat_id = "1545803464712650844"
        await api_patch(session, f"https://discord.com/api/v10/channels/{start_cat_id}", {"name": "✦ START HERE ✦"}, "Rename Cat to ✦ START HERE ✦")
        await asyncio.sleep(1.2)

        start_renames = [
            ("1545502700840427702", "✅・verify-here"),
            ("1545502705643167876", "👋・welcome"),
            ("1545502710101704714", "📜・rules"),
            ("1545502718792175646", "📢・announcements"),
            ("1545502722739150898", "🎭・get-roles"),
        ]
        for cid, name in start_renames:
            await api_patch(session, f"https://discord.com/api/v10/channels/{cid}", {"name": name, "parent_id": start_cat_id}, f"Rename {name}")
            await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # 3. ✦ COMMUNITY ✦ CATEGORY
        # -----------------------------------------------------------------
        print("\n[3/5] ✦ COMMUNITY ✦ Category")
        comm_cat_id = "1545803478490812578"
        await api_patch(session, f"https://discord.com/api/v10/channels/{comm_cat_id}", {"name": "✦ COMMUNITY ✦"}, "Rename Cat to ✦ COMMUNITY ✦")
        await asyncio.sleep(1.2)

        comm_renames = [
            ("1545502730699808768", "💬・general-chat"),
            ("1551184138932068373", "📸・media-dump"),
            ("1557475853175234660", "🎮・gaming-chat"),
            ("1558482941817004143", "🎨・editing-chat"),
        ]
        for cid, name in comm_renames:
            await api_patch(session, f"https://discord.com/api/v10/channels/{cid}", {"name": name, "parent_id": comm_cat_id}, f"Rename {name}")
            await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # 4. ✦ SUPPORT ✦, ✦ STAFF ✦ & ✦ BOT ✦ CATEGORIES
        # -----------------------------------------------------------------
        print("\n[4/5] ✦ SUPPORT ✦, ✦ STAFF ✦ & ✦ BOT ✦ Categories")
        # Support Category
        existing_support = next((c for c in channels if c.get("name") == "✦ SUPPORT ✦" and c.get("type") == 4), None)
        if not existing_support:
            support_cat = await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": "✦ SUPPORT ✦", "type": 4}, "Create Cat ✦ SUPPORT ✦")
            support_cat_id = support_cat["id"] if support_cat else comm_cat_id
            await asyncio.sleep(1.2)
        else:
            support_cat_id = existing_support["id"]

        await api_patch(session, "https://discord.com/api/v10/channels/1555641079137706014", {"name": "🎫・support", "parent_id": support_cat_id}, "Move & Rename 🎫・support")
        await asyncio.sleep(1.2)
        await api_patch(session, "https://discord.com/api/v10/channels/1557469924379852860", {"name": "💡・suggestions", "parent_id": support_cat_id}, "Move & Rename 💡・suggestions")
        await asyncio.sleep(1.2)

        # Staff Category
        staff_cat_id = "1555283372488658954"
        await api_patch(session, f"https://discord.com/api/v10/channels/{staff_cat_id}", {"name": "✦ STAFF ✦"}, "Rename Cat to ✦ STAFF ✦")
        await asyncio.sleep(1.2)
        await api_patch(session, "https://discord.com/api/v10/channels/1545502845208629328", {"name": "🔒・staff-chat", "parent_id": staff_cat_id}, "Move & Rename 🔒・staff-chat")
        await asyncio.sleep(1.2)
        await api_patch(session, "https://discord.com/api/v10/channels/1555283387340562574", {"name": "🛡️・mod-logs", "parent_id": staff_cat_id}, "Move & Rename 🛡️・mod-logs")
        await asyncio.sleep(1.2)

        # Bot Category
        existing_bot = next((c for c in channels if c.get("name") == "✦ BOT ✦" and c.get("type") == 4), None)
        if not existing_bot:
            bot_cat = await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": "✦ BOT ✦", "type": 4}, "Create Cat ✦ BOT ✦")
            bot_cat_id = bot_cat["id"] if bot_cat else comm_cat_id
            await asyncio.sleep(1.2)
        else:
            bot_cat_id = existing_bot["id"]

        await api_patch(session, "https://discord.com/api/v10/channels/1549416359723532480", {"name": "🤖・bot-commands", "parent_id": bot_cat_id}, "Restore & Rename 🤖・bot-commands")
        await asyncio.sleep(1.2)
        await api_patch(session, "https://discord.com/api/v10/channels/1555283393242206301", {"name": "🎵・music-queue", "parent_id": bot_cat_id}, "Restore & Rename 🎵・music-queue")
        await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # 5. SAFELY MOVE SECONDARY TEXT CHANNELS TO ARCHIVE (ZERO DELETIONS)
        # -----------------------------------------------------------------
        print("\n[5/5] Safely Archiving Secondary Text Channels (Zero Data Loss)")
        secondary_channels = [
            ("1557481215731306526", "server-faq"),
            ("1557479971759333499", "partnerships"),
            ("1557481227693330554", "giveaways"),
            ("1558482965175078994", "gaming-montages"),
            ("1557477521661108315", "movie-lounge"),
            ("1558483065578197002", "pfp-and-banners"),
            ("1558483087283720352", "editing-tips"),
            ("1558483098553819228", "collab-requests"),
            ("1558483178862288987", "edit-of-the-week"),
            ("1555283378612478072", "security-alerts"),
            ("1558168338386129004", "honeypot-trap"),
            ("1555283409465778218", "admin-control"),
            ("1555283414205075509", "server-dashboard"),
            ("1555283416071675954", "bot-config"),
            ("1555428392181047366", "member-reports"),
            ("1555641081578782840", "late-night-talks"),
            ("1557479371001045056", "booster-lounge"),
        ]
        for cid, name in secondary_channels:
            await api_patch(session, f"https://discord.com/api/v10/channels/{cid}", {"parent_id": ARCHIVE_CAT_ID}, f"Archive #{name}")
            await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # 6. UPDATE DATABASE CONFIG FOR AUTONOMOUS SERVER STATS SYNCING
        # -----------------------------------------------------------------
        print("\n[DB] Updating ServerStatsConfig in SQLite...")
        from database.database import Database
        db = Database()
        await db.connect()
        cfg = await db.get_or_create_server_stats_config(GUILD_ID)
        cfg.category_id = int(cat_stats_id)
        cfg.all_members_channel_id = int(server_stat_ch_id)
        cfg.members_channel_id = int(vc_stat_ch_id)
        cfg.enabled = True
        await db.save_server_stats_config(cfg)
        await db.close()
        print("  [SUCCESS] ServerStatsConfig updated with aesthetic channels!")

    print("\n" + "=" * 65)
    print("   🍒 SERVER UPGRADE DEPLOYMENT COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
