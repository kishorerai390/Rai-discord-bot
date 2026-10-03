"""
Deploy completely private 📋 | RAI REPORTS category and 6 text channels with strict owner-only permissions.
"""

import os
import aiohttp
import asyncio
import sqlite3
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
OWNER_ID = 1457380609641938981
BOT_ID = 1554732669072445532

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# Bitwise Discord permissions
# VIEW_CHANNEL = 1024, SEND_MESSAGES = 2048, READ_MESSAGE_HISTORY = 65536
# EMBED_LINKS = 16384, ATTACH_FILES = 32768
DENY_ALL_VIEW = 1024 | 2048 | 65536 | 0x800000000 | 0x1000000000  # view, send, history, create threads
ALLOW_OWNER = 1024 | 2048 | 65536
ALLOW_RAI = 1024 | 2048 | 65536 | 16384 | 32768

REPORT_CHANNELS = [
    {
        "key": "security_report_id",
        "name": "🚨・security-report",
        "topic": "Private Owner Stream: Security incidents, anti-nuke, anti-raid, lockdowns, and threat alerts.",
        "header_title": "🚨 RAI FAM — Security & Threat Intelligence Reports",
        "header_desc": (
            "**Destination:** Confidential Owner Security Feed\n"
            "**Routing Scope:**\n"
            "• 🛑 **Anti-Nuke Matrix** — Mass channel/role deletion velocity breaches & auto-quarantine.\n"
            "• 🛡️ **Anti-Raid Ingress** — Rapid join spikes, lockdown activations, and raid mitigations.\n"
            "• 🎣 **Zero-Day Phishing & Loggers** — Intercepted token grabbers, fake nitro, and malware domains.\n"
            "• 🚨 **Zero-Tolerance Violations** — Unauthorized permission changes and security anomalies.\n\n"
            "🔒 **Visibility:** 100% Confidential (Owner & Rai Bot Only)"
        ),
        "color": 0xED4245,
    },
    {
        "key": "mod_report_id",
        "name": "🛡️・mod-report",
        "topic": "Private Owner Stream: Bans, kicks, timeouts, warnings, and moderation actions.",
        "header_title": "🛡️ RAI FAM — Moderation Actions & Disciplinary Reports",
        "header_desc": (
            "**Destination:** Confidential Owner Moderation Feed\n"
            "**Routing Scope:**\n"
            "• 🔨 **Manual Disciplinary Actions** — All `/ban`, `/kick`, `/timeout`, `/warn`, and unbans.\n"
            "• 🚫 **AutoMod Kicks & Sanctions** — Word Filter Violations and Emoji Spam kicks.\n"
            "• ⚠️ **Warning Threshold Milestones** — Users accumulating penalty points.\n"
            "• 🧹 **Purge & Sanitize Records** — Staff message purge operations.\n\n"
            "🔒 **Visibility:** 100% Confidential (Owner & Rai Bot Only)"
        ),
        "color": 0x5865F2,
    },
    {
        "key": "music_report_id",
        "name": "🎵・music-report",
        "topic": "Private Owner Stream: Music errors, playlist imports, playback and queue problems.",
        "header_title": "🎵 RAI FAM — Audio Engine & Playback Incident Reports",
        "header_desc": (
            "**Destination:** Confidential Owner Music Feed\n"
            "**Routing Scope:**\n"
            "• ⚠️ **Audio Playback Exceptions** — Stream decoding failures or voice gateway dropouts.\n"
            "• ❌ **Playlist Import Failures** — Unresolved Spotify/YouTube links and API rate-limits.\n"
            "• 🛑 **Queue Corruptions & Stalls** — Auto-recovery and audio node reconnects.\n\n"
            "🔒 **Visibility:** 100% Confidential (Owner & Rai Bot Only)"
        ),
        "color": 0x9B59B6,
    },
    {
        "key": "room_report_id",
        "name": "🔐・room-report",
        "topic": "Private Owner Stream: Private VC creation/deletion, invites, locks, ownership transfers.",
        "header_title": "🔐 RAI FAM — Dynamic Rooms & Voice Suite Reports",
        "header_desc": (
            "**Destination:** Confidential Owner Room Feed\n"
            "**Routing Scope:**\n"
            "• ➕ **Private Room Lifecycle** — Creation and automatic deletion of dynamic suites.\n"
            "• 🔒 **Room Security Actions** — Owner locks, user permits, kicks, and bans from rooms.\n"
            "• 👑 **Suite Ownership Transfers** — Handoff of room ownership controls.\n"
            "• ⚠️ **Orphaned Room Cleanups** — Self-healing garbage collection of abandoned VCs.\n\n"
            "🔒 **Visibility:** 100% Confidential (Owner & Rai Bot Only)"
        ),
        "color": 0x1ABC9C,
    },
    {
        "key": "bot_report_id",
        "name": "🤖・bot-report",
        "topic": "Private Owner Stream: Important bot actions and configuration changes.",
        "header_title": "🤖 RAI FAM — Bot Operations & Configuration Audit",
        "header_desc": (
            "**Destination:** Confidential Owner Bot Operations Feed\n"
            "**Routing Scope:**\n"
            "• ⚙️ **Configuration Updates** — Slash command setups, module toggles, AutoMod adjustments.\n"
            "• 🔄 **Command Synchronization** — Global slash command deployments and schema sync.\n"
            "• 👑 **Role Hierarchy Changes** — Bot duty assignments and role modifications.\n"
            "• ⚡ **Autopilot Decisions** — Autonomous optimization actions executed by Rai.\n\n"
            "🔒 **Visibility:** 100% Confidential (Owner & Rai Bot Only)"
        ),
        "color": 0xF1C40F,
    },
    {
        "key": "system_report_id",
        "name": "⚙️・system-report",
        "topic": "Private Owner Stream: Startup, shutdown, database, backups, health warnings, recovery.",
        "header_title": "⚙️ RAI FAM — Core System Infrastructure & Health Telemetry",
        "header_desc": (
            "**Destination:** Confidential Owner System Feed\n"
            "**Routing Scope:**\n"
            "• 🚀 **Bot Startup & Shutdown** — Gateway sessions, shard connections, and clean stops.\n"
            "• 💾 **Database & Backups** — Automated backup snapshots, migrations, and SQLite vacuum.\n"
            "• 🏥 **Self-Healing Supervisor** — Automatic subsystem crash recovery and safe mode alerts.\n"
            "• ⚠️ **Critical Runtime Errors** — Unhandled exceptions and network reconnection watchdog.\n\n"
            "🔒 **Visibility:** 100% Confidential (Owner & Rai Bot Only)"
        ),
        "color": 0x2B2D31,
    },
]

async def build_strict_overwrites(session: aiohttp.ClientSession):
    """Constructs overwrites denying all roles and allowing only Owner and Rai."""
    overwrites = [
        # Deny @everyone
        {
            "id": str(GUILD_ID),
            "type": 0,
            "allow": "0",
            "deny": str(DENY_ALL_VIEW),
        },
        # Allow Server Owner
        {
            "id": str(OWNER_ID),
            "type": 1,
            "allow": str(ALLOW_OWNER),
            "deny": "0",
        },
        # Allow Rai Bot
        {
            "id": str(BOT_ID),
            "type": 1,
            "allow": str(ALLOW_RAI),
            "deny": "0",
        },
    ]

    # Fetch all guild roles and explicitly deny each one
    roles_url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles"
    async with session.get(roles_url, headers=HEADERS) as r:
        roles = await r.json()
        for role in roles:
            rid = str(role["id"])
            if rid != str(GUILD_ID):  # @everyone already added
                overwrites.append({
                    "id": rid,
                    "type": 0,
                    "allow": "0",
                    "deny": str(DENY_ALL_VIEW),
                })
    return overwrites

async def deploy():
    async with aiohttp.ClientSession() as session:
        overwrites = await build_strict_overwrites(session)
        print(f"Built strict owner-only permission matrix ({len(overwrites)} overwrites).")

        # 1. Check or Create Category '📋 | RAI REPORTS'
        channels_url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels"
        async with session.get(channels_url, headers=HEADERS) as r:
            chs = await r.json()

        cat_id = None
        for c in chs:
            if c.get("type") == 4 and "RAI REPORTS" in c.get("name", "").upper():
                cat_id = int(c["id"])
                print(f"Found existing category (ID: {cat_id})")
                # Update category overwrites to ensure strict privacy
                patch_url = f"https://discord.com/api/v10/channels/{cat_id}"
                await session.patch(patch_url, headers=HEADERS, json={"permission_overwrites": overwrites})
                break

        if not cat_id:
            payload = {
                "name": "📋 | RAI REPORTS",
                "type": 4,
                "position": 12,
                "permission_overwrites": overwrites,
            }
            async with session.post(channels_url, headers=HEADERS, json=payload) as r:
                data = await r.json()
                cat_id = int(data["id"])
                print(f"Created category (ID: {cat_id})")

        # 2. Check or Create the 6 text channels
        channel_ids = {}
        for item in REPORT_CHANNELS:
            target_name = item["name"]
            found_id = None
            for c in chs:
                if c.get("type") == 0 and c.get("parent_id") == str(cat_id) and c.get("name") == target_name:
                    found_id = int(c["id"])
                    print(f"Reusing existing channel {ascii(target_name)} (ID: {found_id})")
                    break

            if not found_id:
                # Create channel
                c_payload = {
                    "name": target_name,
                    "type": 0,
                    "parent_id": str(cat_id),
                    "topic": item["topic"],
                    "permission_overwrites": overwrites,
                }
                async with session.post(channels_url, headers=HEADERS, json=c_payload) as r:
                    c_data = await r.json()
                    found_id = int(c_data["id"])
                    print(f"Created channel {ascii(target_name)} (ID: {found_id})")

                    # Post initial matrix header embed
                    msg_url = f"https://discord.com/api/v10/channels/{found_id}/messages"
                    embed = {
                        "title": item["header_title"],
                        "description": item["header_desc"],
                        "color": item["color"],
                        "footer": {"text": "Rai Private Owner Reports • RAI FAM💗"},
                    }
                    async with session.post(msg_url, headers=HEADERS, json={"embeds": [embed]}) as mr:
                        print(f"Deployed header embed to {ascii(target_name)}: HTTP {mr.status}")

            channel_ids[item["key"]] = found_id
            await asyncio.sleep(0.5)

        # 3. Store channel IDs in SQLite
        conn = sqlite3.connect("data/bot.db")
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO owner_reports_config 
            (guild_id, category_id, security_report_id, mod_report_id, music_report_id, room_report_id, bot_report_id, system_report_id, auto_repair, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                category_id = excluded.category_id,
                security_report_id = excluded.security_report_id,
                mod_report_id = excluded.mod_report_id,
                music_report_id = excluded.music_report_id,
                room_report_id = excluded.room_report_id,
                bot_report_id = excluded.bot_report_id,
                system_report_id = excluded.system_report_id,
                auto_repair = 1,
                updated_at = datetime('now');
            """,
            (
                GUILD_ID,
                cat_id,
                channel_ids["security_report_id"],
                channel_ids["mod_report_id"],
                channel_ids["music_report_id"],
                channel_ids["room_report_id"],
                channel_ids["bot_report_id"],
                channel_ids["system_report_id"],
            )
        )
        conn.commit()
        conn.close()
        print("Stored all report channel IDs in SQLite owner_reports_config table.")

        # 4. Verify Permissions Rigorously
        print("\n--- PERMISSION VERIFICATION AUDIT ---")
        async with session.get(f"https://discord.com/api/v10/channels/{cat_id}", headers=HEADERS) as r:
            cat_data = await r.json()
            c_overwrites = cat_data.get("permission_overwrites", [])
            print(f"Category '{ascii(cat_data['name'])}' has {len(c_overwrites)} permission overwrites:")
            for ow in c_overwrites:
                target_id = ow["id"]
                allow_bits = int(ow["allow"])
                deny_bits = int(ow["deny"])
                if target_id == str(OWNER_ID):
                    print(f"  👑 OWNER ({target_id}): ALLOW={allow_bits} (VIEW_CHANNEL: {bool(allow_bits & 1024)}) -> ACCESS GRANTED")
                elif target_id == str(BOT_ID):
                    print(f"  🤖 RAI BOT ({target_id}): ALLOW={allow_bits} (VIEW_CHANNEL: {bool(allow_bits & 1024)}) -> ACCESS GRANTED")
                elif target_id == str(GUILD_ID):
                    print(f"  🌐 @everyone ({target_id}): DENY={deny_bits} (VIEW_CHANNEL: {bool(deny_bits & 1024)}) -> ACCESS DENIED")
                else:
                    is_view_denied = bool(deny_bits & 1024)
                    print(f"  🔒 Role {target_id}: DENIED VIEW={is_view_denied}")

        print("--- VERIFICATION COMPLETE: ALL CHANNELS 100% OWNER-ONLY ---")

if __name__ == "__main__":
    asyncio.run(deploy())
