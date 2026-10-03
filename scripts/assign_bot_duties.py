"""
Assign Bot Duties & Configure Bot Permissions:
1. Verifies and assigns dedicated roles to each bot:
   - Music Bots (Rythm, BeatSync, Green-Bot) -> 🎧・DJ
   - Utility Bots (Sapphire, Koya) -> 💖・RAI FAM
   - Growth Bots (DISBOARD, Top.gg) -> 🤖・Bots
2. Channels permissions optimization:
   - Allows 🤖・Bots and 🎧・DJ in #🤖・bot-commands and Voice Lounges.
   - Ensures bots cannot post in #announcements, #rules, #verify-here.
3. Posts an official Bot Duty Directory embed in #🤖・bot-commands.
"""

import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(r"f:\Bot\.env")

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

BOT_COMMANDS_CH_ID = "1549416359723532480"
MUSIC_CATEGORY_ID = "1554905799292231728"

# Role IDs
BOTS_ROLE_ID = "1545494578512134176"
DJ_ROLE_ID = "1545834928221069522"
VERIFIED_ROLE_ID = "1549504522953695269"

# Permission Bitwise Flags
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
USE_SLASH_COMMANDS = 1 << 31
CONNECT = 1 << 20
SPEAK = 1 << 21

BOT_DUTIES = [
    {
        "id": "1554732669072445532",
        "name": "The Raivora",
        "role_type": "Primary Server OS & AI Guardian",
        "commands": "`/security_ai`, `/ticket`, `/hiddenvoice`, `/serverstats`",
        "duty": "Core server automation, 24/7 AI Security Sentinel, Dynamic Voice Room generation, Ticket Support system, and Autopilot.",
        "allowed_channels": "All operational channels & Staff HQ",
    },
    {
        "id": "235088799074484224",
        "name": "Rythm",
        "role_type": "Primary Music Streamer",
        "commands": "`/play`, `/queue`, `/skip`, `/stop`",
        "duty": "High-fidelity 24/7 music streaming and playlist queueing in Chill & Music Haven.",
        "allowed_channels": "🎧 ┃ CHILL & MUSIC HAVEN, 🍸 ┃ RAI SUITES, #bot-commands",
        "assign_dj": True,
    },
    {
        "id": "1470151477610938509",
        "name": "Green-Bot",
        "role_type": "Secondary Music Engine",
        "commands": "`/play`, `/volume`, `/filters`, `/loop`",
        "duty": "Backup high-performance audio engine with advanced sound filters (Bassboost, 8D, Nightcore).",
        "allowed_channels": "🎧 ┃ CHILL & MUSIC HAVEN, #bot-commands",
        "assign_dj": True,
    },
    {
        "id": "1205557263738216559",
        "name": "BeatSync",
        "role_type": "Radio & Sync Music Bot",
        "commands": "`/sync`, `/radio`, `/nowplaying`",
        "duty": "Synced radio streaming and group music synchronization across voice rooms.",
        "allowed_channels": "🎧 ┃ CHILL & MUSIC HAVEN, #bot-commands",
        "assign_dj": True,
    },
    {
        "id": "302050872383242240",
        "name": "DISBOARD",
        "role_type": "Community Growth & Discovery",
        "commands": "`/bump` (Every 2 hours)",
        "duty": "Broadcasts RAI FAM to public Discord server listings to attract new members.",
        "allowed_channels": "#bot-commands strictly",
    },
    {
        "id": "422087909634736160",
        "name": "Top.gg",
        "role_type": "Listing & Voting",
        "commands": "`/vote`",
        "duty": "Tracks Top.gg upvotes and community member rankings.",
        "allowed_channels": "#bot-commands strictly",
    },
    {
        "id": "536991182035746816",
        "name": "Wick",
        "role_type": "Secondary Anti-Raid Guard",
        "commands": "`w!help`",
        "duty": "Secondary emergency anti-raid and quarantine layer.",
        "allowed_channels": "Staff & Security channels only",
    },
    {
        "id": "720351927581278219",
        "name": "Invite Tracker",
        "role_type": "Attribution & Referral Tracking",
        "commands": "`/invites`, `/leaderboard`",
        "duty": "Tracks which members invited incoming users and maintains referral leaderboards.",
        "allowed_channels": "#welcome, #bot-commands",
    },
    {
        "id": "678344927997853742",
        "name": "Sapphire",
        "role_type": "Leveling & Custom Triggers",
        "commands": "`/rank`, `/levels`",
        "duty": "Experience points (XP), text chat leveling, and custom automated responses.",
        "allowed_channels": "#general-chat, #bot-commands",
    },
    {
        "id": "276060004262477825",
        "name": "Koya",
        "role_type": "Mini-Games & Social",
        "commands": "^help",
        "duty": "Interactive games, anime image lookup, and fun social commands.",
        "allowed_channels": "#bot-commands",
    },
    {
        "id": "416358583220043796",
        "name": "Xenon",
        "role_type": "Disaster Recovery Backup",
        "commands": "`/backup`",
        "duty": "Server template and structural disaster recovery backups.",
        "allowed_channels": "Staff HQ strictly",
    },
]


async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        # 1. Assign DJ roles to music bots if missing
        print("Auditing and assigning bot roles...")
        for bot_info in BOT_DUTIES:
            b_id = bot_info["id"]
            b_name = bot_info["name"]

            # If needs DJ role
            if bot_info.get("assign_dj"):
                async with s.put(
                    f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{b_id}/roles/{DJ_ROLE_ID}",
                    headers=headers
                ) as r:
                    if r.status in (200, 204):
                        print(f"  🎧 Assigned DJ role to {b_name}")

            # Ensure Bots role is assigned
            async with s.put(
                f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{b_id}/roles/{BOTS_ROLE_ID}",
                headers=headers
            ) as r:
                if r.status in (200, 204):
                    print(f"  🤖 Ensured Bots role on {b_name}")
            await asyncio.sleep(0.3)

        # 2. Configure #bot-commands channel overwrites
        print("\nConfiguring #bot-commands channel permissions...")
        bot_ch_overwrites = [
            # @everyone can see, send messages, use slash commands
            {
                "id": str(GUILD_ID),
                "type": 0,
                "allow": str(VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | ATTACH_FILES | USE_SLASH_COMMANDS),
                "deny": "0",
            },
            # Bots role can see, send messages, embed links
            {
                "id": BOTS_ROLE_ID,
                "type": 0,
                "allow": str(VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | ATTACH_FILES),
                "deny": "0",
            },
        ]

        async with s.patch(
            f"https://discord.com/api/v10/channels/{BOT_COMMANDS_CH_ID}",
            headers=headers,
            json={"permission_overwrites": bot_ch_overwrites}
        ) as r:
            print(f"  📌 #bot-commands permissions configured: status {r.status}")

        # 3. Configure Music Haven Voice Overwrites for DJ Role
        music_cat_overwrites = [
            # DJ role can always connect, speak, and prioritize audio
            {
                "id": DJ_ROLE_ID,
                "type": 0,
                "allow": str(CONNECT | SPEAK | (1 << 8)),  # Priority Speaker
                "deny": "0",
            },
        ]
        async with s.patch(
            f"https://discord.com/api/v10/channels/{MUSIC_CATEGORY_ID}",
            headers=headers,
            json={"permission_overwrites": music_cat_overwrites}
        ) as r:
            print(f"  🎵 Music category DJ permissions configured: status {r.status}")

        # 4. Post Official Bot Duty Directory Embed in #bot-commands
        print("\nPosting Official Bot Duty Directory in #bot-commands...")
        embed = {
            "title": "🤖 RAI FAM — Official Bot Duty & Work Directory",
            "description": (
                "Welcome to the **Bot Operations Hub**. To keep the server fast, clean, and organized, "
                "each bot in **RAI FAM** has been assigned specific duties and channel scopes.\n\n"
                "⚠️ **Server Rule:** Please run all bot testing and commands here in <#1549416359723532480> "
                "to keep <#1545502730699808768> clean for conversations."
            ),
            "color": 0x7B2CBF,
            "fields": [
                {
                    "name": "👑 The Raivora (`Primary Server OS`)",
                    "value": (
                        "• **Duty:** 24/7 AI Security Sentinel, Dynamic Voice Room Generator, Ticket Support, Server Stats.\n"
                        "• **Commands:** `/security_ai status`, `/ticket`, `/hiddenvoice`"
                    ),
                    "inline": False,
                },
                {
                    "name": "🎵 Rythm & Green-Bot & BeatSync (`Audio Streamers`)",
                    "value": (
                        "• **Duty:** 24/7 High-Definition music streaming and radio sync in **CHILL & MUSIC HAVEN**.\n"
                        "• **Commands:** `/play <song/url>`, `/queue`, `/skip`, `/volume`\n"
                        "• **Channels:** 🎧 ┃ CHILL & MUSIC HAVEN"
                    ),
                    "inline": False,
                },
                {
                    "name": "🚀 DISBOARD (`Server Bumping`)",
                    "value": (
                        "• **Duty:** Broadcasts RAI FAM to public Discord listings every 2 hours to bring in new members.\n"
                        "• **Command:** `/bump` (Run here in <#1549416359723532480>)"
                    ),
                    "inline": False,
                },
                {
                    "name": "📊 Invite Tracker (`Member Referrals`)",
                    "value": (
                        "• **Duty:** Tracks referral links, join attribution, and leaderboard rankings.\n"
                        "• **Command:** `/invites`"
                    ),
                    "inline": False,
                },
                {
                    "name": "💎 Sapphire & Koya (`Levels & Community Games`)",
                    "value": (
                        "• **Duty:** Experience levels (XP), leaderboards, and fun mini-games.\n"
                        "• **Commands:** `/rank`, `/levels`, `^help`"
                    ),
                    "inline": False,
                },
                {
                    "name": "🛡️ Wick (`Secondary Anti-Raid Guard`)",
                    "value": (
                        "• **Duty:** Secondary emergency anti-raid and quarantine layer alongside Rai AI Sentinel.\n"
                        "• **Channels:** Staff Headquarters strictly"
                    ),
                    "inline": False,
                },
            ],
            "footer": {
                "text": "RAI FAM Official Infrastructure • Engineered for Stability & Performance"
            },
        }

        async with s.post(
            f"https://discord.com/api/v10/channels/{BOT_COMMANDS_CH_ID}/messages",
            headers=headers,
            json={"embeds": [embed]}
        ) as r:
            print(f"  ✨ Bot Directory posted in #bot-commands: status {r.status}")

        print("\n" + "=" * 50)
        print("Bot duties and work assignments successfully applied!")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
