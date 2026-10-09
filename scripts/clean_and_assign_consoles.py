"""
Master Console Purge and Bot Assignment Script for Rai Ecosystem.
1. Purges older messages and clutter from designated console channels.
2. Redeploys clean, high-fidelity interactive consoles.
3. Pins the active consoles to the top of each channel.
4. Assigns channel topics reflecting The Raivora (Security/Admin) and Neko Songs (Audio).
"""

import asyncio
import datetime
import os
import sys

sys.path.insert(0, "F:/Bot")

import aiohttp
import discord
from dotenv import load_dotenv

from utils.community_features import (
    build_welcome_hub_embed,
    build_welcome_hub_view,
    build_media_showcase_embed,
    build_media_showcase_view,
    build_command_catalog_embed,
    build_command_catalog_view,
    build_staff_rapid_mod_embed,
    build_staff_rapid_mod_view,
    build_room_theme_embed,
    build_room_theme_view,
)
from utils.music_consoles import (
    build_requests_console_embed,
    build_requests_console_view,
    build_queue_console_embed,
    build_queue_console_view,
    build_dj_console_embed,
    build_dj_console_view,
    build_playlists_console_embed,
    build_playlists_console_view,
)

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

# Target Console Channels
CONSOLE_CHANNELS = {
    # Main Bot (The Raivora) Consoles
    "welcome": 1545502705643167876,          # #🌸・WELCOME
    "rules": 1545502710101704714,            # #📜・RULES
    "support": 1558154630876102778,          # #🎫・SUPPORT-DESK
    "commands": 1549416359723532480,         # #🤖・BOT-COMMANDS
    "media": 1551184138932068373,            # #📸・MEDIA-AND-CLIPS
    "pods": 1558154633258602569,             # #💤・SLEEPING-PODS
    "admin": 1555283409465778218,            # #👑・ADMIN-CONTROL
    "room_ctrl": 1555459478155960421,        # #🛠️・ROOM-CONTROL

    # Music Bot (Neko Songs) Consoles
    "music_ctrl": 1555255695933186228,       # #🎵・MUSIC-CONTROL
    "queue": 1555283393242206301,            # #📜・MUSIC-QUEUE
    "dj_ctrl": 1555283394274005092,          # #🔊・DJ-CONTROL
    "playlists": 1555283395330842714,        # #💿・PLAYLISTS
}

def view_to_action_rows(view: discord.ui.View):
    rows = []
    current_row = []
    for item in view.children:
        current_row.append(item.to_component_dict())
        if len(current_row) == 5:
            rows.append({"type": 1, "components": current_row})
            current_row = []
    if current_row:
        rows.append({"type": 1, "components": current_row})
    return rows


async def purge_channel(session: aiohttp.ClientSession, channel_id: int, headers: dict) -> int:
    """Deletes messages in the target channel to ensure a pristine slate."""
    deleted_count = 0
    try:
        async with session.get(
            f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=100",
            headers=headers,
        ) as r:
            if r.status != 200:
                return 0
            messages = await r.json()

        if not messages:
            return 0

        now = datetime.datetime.now(datetime.timezone.utc)
        bulk_deletable = []
        individual_delete = []

        for msg in messages:
            msg_id = msg["id"]
            # Discord snowflake timestamp
            created_at = datetime.datetime.fromtimestamp(
                ((int(msg_id) >> 22) + 1420070400000) / 1000, datetime.timezone.utc
            )
            age_days = (now - created_at).total_seconds() / 86400
            if age_days < 14:
                bulk_deletable.append(msg_id)
            else:
                individual_delete.append(msg_id)

        # Bulk delete eligible
        if len(bulk_deletable) >= 2:
            async with session.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages/bulk-delete",
                headers=headers,
                json={"messages": bulk_deletable[:100]},
            ) as bdr:
                if bdr.status in (200, 204):
                    deleted_count += len(bulk_deletable)
                else:
                    individual_delete.extend(bulk_deletable)
        elif len(bulk_deletable) == 1:
            individual_delete.append(bulk_deletable[0])

        # Delete older individual messages
        for mid in individual_delete:
            async with session.delete(
                f"https://discord.com/api/v10/channels/{channel_id}/messages/{mid}",
                headers=headers,
            ) as dr:
                if dr.status in (200, 204):
                    deleted_count += 1
            await asyncio.sleep(0.3)

    except Exception as e:
        print(f"Error purging channel {channel_id}: {e}")

    return deleted_count


async def post_console(session: aiohttp.ClientSession, channel_id: int, embed: dict, view: discord.ui.View, headers: dict, topic: str = ""):
    """Posts and pins a fresh console."""
    payload = {
        "embeds": [embed],
        "components": view_to_action_rows(view) if view else [],
    }
    msg_id = None
    async with session.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers=headers,
        json=payload,
    ) as r:
        if r.status in (200, 201):
            res = await r.json()
            msg_id = res.get("id")
        else:
            txt = await r.text()
            print(f"Failed to post to {channel_id}: {r.status} - {txt}")

    # Pin console
    if msg_id:
        async with session.put(
            f"https://discord.com/api/v10/channels/{channel_id}/pins/{msg_id}",
            headers=headers,
        ) as pr:
            pass

    # Update topic
    if topic:
        async with session.patch(
            f"https://discord.com/api/v10/channels/{channel_id}",
            headers=headers,
            json={"topic": topic},
        ) as tr:
            pass

    return msg_id


async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    print("=" * 65)
    print("✦ PURGING CONSOLE CLUTTER & ASSIGNING CHANNELS TO BOTS ✦")
    print("=" * 65)

    async with aiohttp.ClientSession() as s:
        # Fetch Guild Info
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}?with_counts=true", headers=headers) as gr:
            guild_data = await gr.json()

        class MockGuild:
            name = guild_data.get("name", "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦")
            id = GUILD_ID
            icon = type("MockIcon", (), {"url": f"https://cdn.discordapp.com/icons/{GUILD_ID}/{guild_data.get('icon')}.png" if guild_data.get("icon") else None})()

        mock_guild = MockGuild()

        # Step 1: Purge all target channels
        print("\n[PHASE 1] Purging stale messages from console channels...")
        for name, ch_id in CONSOLE_CHANNELS.items():
            purged = await purge_channel(s, ch_id, headers)
            print(f"  • Cleared #{name} ({ch_id}): {purged} messages purged")

        await asyncio.sleep(1)

        # Step 2: Deploy The Raivora (Main Bot) Consoles
        print("\n[PHASE 2] Assigning & Deploying The Raivora Consoles...")
        
        # 1. Welcome Hub
        await post_console(
            s, CONSOLE_CHANNELS["welcome"],
            build_welcome_hub_embed(mock_guild),
            build_welcome_hub_view(),
            headers,
            topic="🌸 Official Community Entrance & Orientation Hub | Powered by The Raivora"
        )
        print("  ✅ Pinned Welcome Hub in #welcome")

        # 2. Official Rules
        rules_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓞ғғɪᴄɪᴀʟ 𝕾ᴇʀᴠᴇʀ 𝕲ᴜɪᴅᴇ & 𝕽ᴜʟᴇs ✦",
            "description": (
                "Welcome to the official constitution of **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
                "Our community is dedicated to providing an elite, welcoming environment for gaming, "
                "music, and genuine friendships. All members must uphold these standards.\n\n"
                "👇 Click any category button below to view guidelines and perks."
            ),
            "color": 0x9B59B6,
            "fields": [
                {"name": "📜 ╏ General Conduct", "value": "Mutual respect, zero harassment, no toxic behavior, and strict SFW policy.", "inline": False},
                {"name": "🎙️ ╏ Voice & Music Lounges", "value": "Respect dynamic room owners and fair DJ queue rotation.", "inline": False},
                {"name": "🛡️ ╏ Autonomous Security", "value": "Zero-trust phishing shield active 24/7. Immediate ban for token loggers/scams.", "inline": False},
                {"name": "💎 ╏ VIP Perks", "value": "Custom roles, private rooms, and booster concierge perks.", "inline": False},
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Governance • Powered by The Raivora ✦"}
        }
        await post_console(
            s, CONSOLE_CHANNELS["rules"],
            rules_embed,
            None,
            headers,
            topic="📜 Community Constitution & Etiquette Rules | Powered by The Raivora"
        )
        print("  ✅ Pinned Rules in #rules")

        # 3. Support Desk
        support_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓢ᴜᴘᴘᴏʀᴛ & 𝕳ᴇʟᴘ 𝕯ᴇsᴋ ✦",
            "description": (
                "Need assistance with roles, security, community questions, or partnerships?\n\n"
                "Use the interactive buttons below to open an encrypted ticket with our staff.\n\n"
                "⚡ **Average Staff Response**: `< 5 Minutes`\n"
                "🛡️ **Privacy Guarantee**: All tickets are strictly private."
            ),
            "color": 0x3498DB,
            "fields": [
                {"name": "🎫 ╏ Concierge Services", "value": "• General Support\n• Security Incident Reporting\n• VIP & Booster Rewards\n• Partnerships", "inline": False}
            ],
            "footer": {"text": "Rai Concierge Service • Powered by The Raivora"}
        }
        support_view = discord.ui.View()
        support_view.add_item(discord.ui.Button(label="Open Support Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="rai_ticket:create"))
        support_view.add_item(discord.ui.Button(label="Report Security Breach", style=discord.ButtonStyle.danger, emoji="🚨", custom_id="rai_ticket:security"))
        await post_console(
            s, CONSOLE_CHANNELS["support"],
            support_embed,
            support_view,
            headers,
            topic="🎫 Member Concierge & Encrypted Staff Ticket Portal | Powered by The Raivora"
        )
        print("  ✅ Pinned Support Desk in #support-desk")

        # 4. Commands Catalog
        await post_console(
            s, CONSOLE_CHANNELS["commands"],
            build_command_catalog_embed(),
            build_command_catalog_view(),
            headers,
            topic="🤖 Interactive Slash Command Catalog & Documentation | Powered by The Raivora"
        )
        print("  ✅ Pinned Commands Catalog in #bot-commands")

        # 5. Media Showcase
        await post_console(
            s, CONSOLE_CHANNELS["media"],
            build_media_showcase_embed(),
            build_media_showcase_view(),
            headers,
            topic="📸 Creator Spotlight, Gameplay Clips & Art Showcase | Powered by The Raivora"
        )
        print("  ✅ Pinned Media Showcase in #media-and-clips")

        # 6. Sleeping Pods & Focus
        pods_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓢ʟᴇᴇᴘɪɴɢ 𝕻ᴏᴅs & 𝓕ᴏᴄᴜs 𝓢ᴛᴜᴅɪᴏ ✦",
            "description": (
                "Quiet sanctuary for sleeping, studying, or late-night AFK relaxation.\n\n"
                "• Members are automatically moved here after 15 minutes of inactivity.\n"
                "• Audio is optimized for low-volume ambient Lo-Fi.\n"
                "• Zero ping notifications allowed in this channel."
            ),
            "color": 0x7289DA,
            "footer": {"text": "Sleep Lounge • Powered by The Raivora"}
        }
        await post_console(
            s, CONSOLE_CHANNELS["pods"],
            pods_embed,
            None,
            headers,
            topic="💤 Ambient AFK Pods & Lo-Fi Lounge | Powered by The Raivora"
        )
        print("  ✅ Pinned Sleeping Pods Console")

        # 7. Admin & Staff Deck
        await post_console(
            s, CONSOLE_CHANNELS["admin"],
            build_staff_rapid_mod_embed(mock_guild),
            build_staff_rapid_mod_view(),
            headers,
            topic="👑 Executive Moderation Command Deck | Restricted to Authorized Staff"
        )
        print("  ✅ Pinned Staff Rapid-Mod Deck in #admin-control")

        # 8. Room Control
        await post_console(
            s, CONSOLE_CHANNELS["room_ctrl"],
            build_room_theme_embed(),
            build_room_theme_view(),
            headers,
            topic="🛠️ Dynamic Voice Room Manager & Custom Mood Styler | Powered by The Raivora"
        )
        print("  ✅ Pinned Room Control in #room-control")

        # Step 3: Deploy Neko Songs (Music Bot) Consoles
        print("\n[PHASE 3] Assigning & Deploying Neko Songs Audio Consoles...")

        # 1. Music Request Hub
        await post_console(
            s, CONSOLE_CHANNELS["music_ctrl"],
            build_requests_console_embed(mock_guild),
            build_requests_console_view(),
            headers,
            topic="🎵 Dedicated Music Studio | Powered by Neko Songs | Use /music play or click controls below"
        )
        print("  🐱 Pinned Music Player Console in #music-control")

        # 2. Live Queue Board
        await post_console(
            s, CONSOLE_CHANNELS["queue"],
            build_queue_console_embed(mock_guild, None),
            build_queue_console_view(),
            headers,
            topic="📜 Live Audio Queue & Upcoming Tracks | Powered by Neko Songs"
        )
        print("  🐱 Pinned Live Queue Board in #music-queue")

        # 3. DJ Studio & Audio EQ
        await post_console(
            s, CONSOLE_CHANNELS["dj_ctrl"],
            build_dj_console_embed(mock_guild),
            build_dj_console_view(),
            headers,
            topic="🔊 DJ Studio, Bass Boost & Volume Equalizer | Powered by Neko Songs"
        )
        print("  🐱 Pinned DJ Studio Console in #dj-control")

        # 4. Playlists Hub
        await post_console(
            s, CONSOLE_CHANNELS["playlists"],
            build_playlists_console_embed(mock_guild),
            build_playlists_console_view(),
            headers,
            topic="💿 Curated Playlists, Favorites & Import Hub | Powered by Neko Songs"
        )
        print("  🐱 Pinned Playlists Hub in #playlists")

        # Step 4: Clean up duplicate categories
        print("\n[PHASE 4] Cleaning duplicate categories...")
        # Check if redundant category 1557717563834765342 exists
        async with s.get(f"https://discord.com/api/v10/channels/1557717563834765342", headers=headers) as dcr:
            if dcr.status == 200:
                # Delete duplicate bot-report channel and category
                async with s.delete("https://discord.com/api/v10/channels/1557717565835317259", headers=headers) as dbr:
                    print("  • Removed redundant #bot-report channel")
                async with s.delete("https://discord.com/api/v10/channels/1557717563834765342", headers=headers) as dcr2:
                    print("  • Removed duplicate 'RAI REPORTS' category")

    print("\n" + "=" * 65)
    print("✦ ALL CONSOLES PURGED, FRESHLY DEPLOYED & PINNED SUCCESSFULLY! ✦")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
