"""
Deploy Community Server Layout & Automation for Rai.
Provisions categories, text channels, and voice channels according to the Rai Community Architecture.
Configures proper permission overwrites for verification gating and hidden voice privacy.
Saves configuration IDs directly to the SQLite database.
"""

import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv
import aiosqlite

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
VERIFIED_ROLE_ID = 1549504522953695269
DB_PATH = "data/bot.db"

BASE_URL = "https://discord.com/api/v10"
HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# Specification of Categories and Channels
LAYOUT = [
    {
        "category": "📊 ┃ INFORMATION",
        "type": "info",  # Visible to @everyone
        "text": [
            "📢・announcements",
            "🌱・welcome",
            "💬・general",
            "👋・introductions",
            "🔗・invites",
            "📜・rules",
            "📰・server-news",
            "💡・suggestions",
        ],
        "voice": [
            "🌱・SOLO",
            "🌱・DUO",
            "🌱・DUO 2",
            "🌱・TRIO",
            "🌱・SQUAD",
        ],
    },
    {
        "category": "😸 ┃ FUN & SOCIAL",
        "type": "verified_community",
        "text": [
            "💬・chat",
            "😂・memes",
            "📸・media",
            "🎥・videos",
            "💭・random",
            "🌙・late-night",
            "🗣️・discussions",
            "❤️・community",
        ],
        "voice": [
            "🐣・FUN TIME",
            "🎙️・VOICE 1",
            "🎙️・VOICE 2",
            "🎙️・VOICE 3",
            "🌊・OPEN VOICE",
            "🎤・KARAOKE",
            "🛋️・LOUNGE",
            "☕・COFFEE ROOM",
            "🌌・MIDNIGHT",
        ],
    },
    {
        "category": "🎮 ┃ GAMING ZONE",
        "type": "verified_community",
        "text": [
            "🎮・gaming-chat",
            "👥・find-teammates",
            "📢・game-updates",
            "🏆・tournaments",
            "📅・gaming-events",
            "📹・gaming-clips",
            "🎯・game-strategies",
            "⭐・game-recommendations",
            "🏅・achievements",
        ],
        "voice": [
            "⚡・FREE FIRE",
            "⚡・BGMI",
            "⚡・ROBLOX",
            "⚡・OTHER GAMES",
            "🔥・RANKED",
            "🏆・COMPETITIVE",
            "🎯・DUO GAMING",
            "👥・SQUAD GAMING",
            "🕹️・CASUAL GAMING",
        ],
    },
    {
        "category": "🎧 ┃ MUSIC ZONE",
        "type": "verified_community",
        "text": [
            "🎵・music-chat",
            "🎶・song-sharing",
            "🎧・currently-listening",
            "🎤・artist-talk",
            "💿・album-discussion",
            "📻・music-discovery",
            "🎼・playlists",
            "⭐・music-recommendations",
            "🔥・song-of-the-day",
        ],
        "voice": [
            "🎧・LISTENING ROOM",
            "🎵・MUSIC LOUNGE",
            "🌃・NIGHT VIBES",
            "🎤・KARAOKE",
            "🎹・JAM ROOM",
            "🎶・SING TOGETHER",
            "📻・RADIO ROOM",
        ],
    },
    {
        "category": "🎬 ┃ THEATER & MOVIES",
        "type": "verified_community",
        "text": [
            "🍿・movie-chat",
            "📺・series-chat",
            "⭐・reviews",
            "🎞️・recommendations",
            "🎥・trailers",
            "📅・watch-events",
            "🏆・favorite-movies",
            "🗳️・movie-polls",
        ],
        "voice": [
            "📺・MOVIE 01",
            "📺・MOVIE 02",
            "🍿・WATCH PARTY",
            "🎬・CINEMA",
            "🌙・LATE NIGHT MOVIE",
            "📺・SERIES ROOM",
        ],
    },
    {
        "category": "🎨 ┃ CREATOR & EDITING",
        "type": "verified_community",
        "text": [
            "🎨・creator-chat",
            "🖼️・photo-editing",
            "🎬・video-editing",
            "📱・mobile-editing",
            "💻・pc-editing",
            "✨・showcase",
            "🤝・feedback",
            "💡・editing-tips",
            "📦・resources",
            "🎨・design-inspiration",
            "🏆・creator-challenges",
        ],
        "voice": [
            "🎯・PC EDITING",
            "🎯・MOBILE EDITING",
            "🎨・CREATOR ROOM",
            "🎬・VIDEO STUDIO",
            "🖥️・WORK TOGETHER",
            "🎙️・AUDIO STUDIO",
            "🔒・PRIVATE EDITING",
        ],
    },
    {
        "category": "🌙 ┃ CHILL ZONE",
        "type": "verified_community",
        "text": [
            "💭・chill-chat",
            "🌌・late-night",
            "☕・daily-talk",
            "🫂・community",
            "🌠・random-thoughts",
            "📸・daily-media",
            "💡・ideas",
        ],
        "voice": [
            "🌙・CHILL",
            "☕・COFFEE",
            "🛋️・LOUNGE",
            "🌌・MIDNIGHT",
            "🗣️・DEEP TALK",
            "💤・RELAX",
        ],
    },
    {
        "category": "🎉 ┃ COMMUNITY EVENTS",
        "type": "verified_community",
        "text": [
            "📅・event-calendar",
            "🎉・community-events",
            "🏆・competitions",
            "🎁・giveaways",
            "📊・event-results",
            "🗳️・polls",
            "🎯・challenges",
        ],
        "voice": [
            "🎙️・COMMUNITY STAGE",
            "🏆・EVENT ROOM",
            "👥・EVENT LOBBY",
            "🎤・OPEN MIC",
        ],
    },
    {
        "category": "👤 ┃ DYNAMIC VOICE ROOMS",
        "type": "verified_community",
        "text": [],
        "voice": [
            "➕・CREATE YOUR ROOM",
            "🔐・CREATE PRIVATE ROOM",
        ],
    },
    {
        "category": "🔐 ┃ PRIVATE ZONE",
        "type": "private_staff",
        "text": [
            "🔒・private-chat",
            "🔒・private-work",
            "🔒・private-stream",
        ],
        "voice": [
            "🔒・PRIVATE LOUNGE",
            "🔒・PRIVATE ROOM",
            "🔒・CREATOR ROOM",
            "🔒・PRIVATE STREAM",
            "🚫・ONLY ADMINS",
        ],
    },
    {
        "category": "🤖 ┃ RAI HUB",
        "type": "verified_community",
        "text": [
            "🤖・rai",
            "🎫・support",
            "💡・bot-suggestions",
            "📊・server-stats",
        ],
        "voice": [],
    },
    {
        "category": "🛡️ ┃ STAFF & SECURITY",
        "type": "private_staff",
        "text": [
            "🚨・security-alerts",
            "📋・moderation-log",
            "🛡️・security-log",
            "🎫・ticket-log",
            "⚙️・automation-log",
            "📊・staff-dashboard",
        ],
        "voice": [],
    },
    {
        "category": "💤 ┃ SYSTEM",
        "type": "system",
        "text": [
            "🤖・RAI CONTROL",
            "💾・backup-log",
            "❤️・health-status",
        ],
        "voice": [
            "💤・AFK",
        ],
    },
    {
        "category": "🔐 ┃ HIDDEN ROOMS",
        "type": "hidden_rooms_category",
        "text": [],
        "voice": [],  # Automatically managed by Rai
    },
]


async def api_call(session, method, endpoint, json_data=None):
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(5):
        async with session.request(method, url, headers=HEADERS, json=json_data) as resp:
            if resp.status == 429:
                data = await resp.json()
                retry_after = data.get("retry_after", 1.0)
                print(f"[429 Rate Limit] Sleeping {retry_after}s...")
                await asyncio.sleep(retry_after + 0.2)
                continue
            if resp.status >= 400:
                text = await resp.text()
                print(f"Error {resp.status} on {method} {endpoint}: {text}")
                return None
            return await resp.json()
    return None


async def main():
    print(f"Starting server layout automation for Guild {GUILD_ID}...")

    async with aiohttp.ClientSession() as session:
        # 1. Fetch current channels and roles
        channels = await api_call(session, "GET", f"/guilds/{GUILD_ID}/channels")
        if not channels:
            print("Failed to fetch channels.")
            return

        roles = await api_call(session, "GET", f"/guilds/{GUILD_ID}/roles")
        everyone_role = next((r for r in roles if r["name"] == "@everyone"), None)
        everyone_id = everyone_role["id"] if everyone_role else str(GUILD_ID)

        # Existing maps
        existing_cats = {c["name"]: c for c in channels if c.get("type") == 4}
        existing_channels = {c["name"]: c for c in channels if c.get("type") != 4}

        created_cat_ids = {}
        created_channel_ids = {}

        # Permission overwrite presets
        # Permissions: VIEW_CHANNEL = 1024 (0x400), CONNECT = 1048576 (0x100000)
        VIEW_CHANNEL = 1024
        CONNECT = 1048576
        SEND_MESSAGES = 2048
        SPEAK = 2097152

        for item in LAYOUT:
            cat_name = item["category"]
            cat_type = item["type"]
            cat_data = existing_cats.get(cat_name)

            # Build permission overwrites for category
            overwrites = []
            if cat_type == "info":
                # Visible to everyone
                overwrites = [
                    {"id": str(everyone_id), "type": 0, "allow": str(VIEW_CHANNEL | CONNECT), "deny": "0"},
                ]
            elif cat_type == "verified_community":
                # Locked from unverified @everyone, visible to verified
                overwrites = [
                    {"id": str(everyone_id), "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL | CONNECT)},
                    {"id": str(VERIFIED_ROLE_ID), "type": 0, "allow": str(VIEW_CHANNEL | CONNECT), "deny": "0"},
                ]
            elif cat_type == "private_staff":
                # Denied to @everyone and verified members
                overwrites = [
                    {"id": str(everyone_id), "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL | CONNECT)},
                    {"id": str(VERIFIED_ROLE_ID), "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL | CONNECT)},
                ]
            elif cat_type == "hidden_rooms_category":
                # Completely hidden from everyone by default
                overwrites = [
                    {"id": str(everyone_id), "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL | CONNECT)},
                    {"id": str(VERIFIED_ROLE_ID), "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL | CONNECT)},
                ]
            elif cat_type == "system":
                # Denied to @everyone
                overwrites = [
                    {"id": str(everyone_id), "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL | CONNECT)},
                ]

            if not cat_data:
                print(f"[Create Category] {cat_name}")
                payload = {
                    "name": cat_name,
                    "type": 4,
                    "permission_overwrites": overwrites,
                }
                cat_data = await api_call(session, "POST", f"/guilds/{GUILD_ID}/channels", payload)
                await asyncio.sleep(0.4)

            if cat_data:
                cat_id = cat_data["id"]
                created_cat_ids[cat_name] = cat_id

                # Create text channels
                for t_name in item.get("text", []):
                    # Check if channel already exists
                    ch = existing_channels.get(t_name)
                    if not ch:
                        print(f"  [Create Text] {t_name}")
                        ch_payload = {
                            "name": t_name,
                            "type": 0,
                            "parent_id": str(cat_id),
                        }
                        new_ch = await api_call(session, "POST", f"/guilds/{GUILD_ID}/channels", ch_payload)
                        if new_ch:
                            created_channel_ids[t_name] = new_ch["id"]
                        await asyncio.sleep(0.3)
                    else:
                        created_channel_ids[t_name] = ch["id"]

                # Create voice channels
                for v_name in item.get("voice", []):
                    ch = existing_channels.get(v_name)
                    if not ch:
                        print(f"  [Create Voice] {v_name}")
                        ch_payload = {
                            "name": v_name,
                            "type": 2,
                            "parent_id": str(cat_id),
                        }
                        new_ch = await api_call(session, "POST", f"/guilds/{GUILD_ID}/channels", ch_payload)
                        if new_ch:
                            created_channel_ids[v_name] = new_ch["id"]
                        await asyncio.sleep(0.3)
                    else:
                        created_channel_ids[v_name] = ch["id"]

        # 3. Update SQLite configurations with the new channel IDs
        print("\nUpdating database configurations with new channel IDs...")
        hidden_cat_id = created_cat_ids.get("🔐 ┃ HIDDEN ROOMS")
        create_private_ch_id = created_channel_ids.get("🔐・CREATE PRIVATE ROOM")
        create_temp_ch_id = created_channel_ids.get("➕・CREATE YOUR ROOM")
        dynamic_cat_id = created_cat_ids.get("👤 ┃ DYNAMIC VOICE ROOMS")

        async with aiosqlite.connect(DB_PATH) as db:
            now = "2026-09-30T16:20:00+00:00"
            # Update hidden_voice_config
            if hidden_cat_id and create_private_ch_id:
                await db.execute(
                    """
                    INSERT INTO hidden_voice_config (
                        guild_id, enabled, category_id, entry_channel_id, max_rooms_per_user,
                        max_users_per_room, empty_grace_period, allow_invited_members,
                        allow_ownership_transfer, staff_can_view_hidden_rooms, automatic_cleanup,
                        automatic_owner_transfer, room_name_format, updated_at
                    ) VALUES (?, 1, ?, ?, 1, 99, 60, 1, 1, 0, 1, 0, '🔒・{username}-private', ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        category_id = excluded.category_id,
                        entry_channel_id = excluded.entry_channel_id,
                        updated_at = excluded.updated_at;
                    """,
                    (GUILD_ID, int(hidden_cat_id), int(create_private_ch_id), now),
                )
                print(f"Updated hidden_voice_config: category_id={hidden_cat_id}, entry_channel_id={create_private_ch_id}")

            # Update temp_voice_config
            if dynamic_cat_id and create_temp_ch_id:
                await db.execute(
                    """
                    INSERT INTO temp_voice_config (
                        guild_id, enabled, hub_channel_id, category_id, default_user_limit, updated_at
                    ) VALUES (?, 1, ?, ?, 0, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        hub_channel_id = excluded.hub_channel_id,
                        category_id = excluded.category_id,
                        enabled = 1,
                        updated_at = excluded.updated_at;
                    """,
                    (GUILD_ID, int(create_temp_ch_id), int(dynamic_cat_id), now),
                )
                print(f"Updated temp_voice_config: hub_channel_id={create_temp_ch_id}, category_id={dynamic_cat_id}")

            await db.commit()

        print("\nServer layout deployment complete!")


if __name__ == "__main__":
    asyncio.run(main())
