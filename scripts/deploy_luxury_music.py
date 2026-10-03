import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
CH_MUSIC = 1555255695933186228
TARGET_MSG = "1555281107606577294"
DELETE_MSG = "1555422111932350565"

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    embed = {
        "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓜ᴜsɪᴄ 𝕵ᴜᴋᴇʙᴏx 𝕮ᴏɴsᴏʟᴇ ✦",
        "description": (
            "Welcome to the **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦** 24/7 High-Fidelity Audio Center.\n\n"
            "Connect to any voice lounge (`🎧・𝓝ᴏᴡ-𝕻ʟᴀʏɪɴɢ`, `📻・𝓡ᴀᴅɪᴏ`, or a Dynamic Room) "
            "and use the interactive console below to queue songs, control playback, and manage audio without typing commands!\n\n"
            "🎵 **Audio Engine**: `🟢 Online (384kbps Hi-Fi Audio)`\n"
            "🎧 **Supported Sources**: `YouTube`, `Spotify`, `SoundCloud`, `Direct MP3 Streams`\n"
            "✨ **Audio Features**: `Lossless Equalizer`, `Smart Queue Rotation`, `DJ Controls`"
        ),
        "color": 15277699,  # 0xE91E63 Luxury Fuchsia / Neon Pink
        "fields": [
            {
                "name": "⏯️ ╏ Playback Controls",
                "value": (
                    "• `Play / Pause`: Resume or halt current stream.\n"
                    "• `Skip & Prev`: Transition between track history.\n"
                    "• `Shuffle & Loop`: Reorder playlist or loop current track."
                ),
                "inline": False,
            },
            {
                "name": "➕ ╏ Request Music Instantly",
                "value": (
                    "Click **[➕ Request Song]** below to open the search modal. "
                    "Type any song title, artist, or paste a link to immediately start streaming!"
                ),
                "inline": False,
            },
        ],
        "footer": {
            "text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ High-Fidelity Autonomous Jukebox • Click below ✦"
        },
    }

    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,  # Primary (Blurple)
                    "label": "Play / Pause",
                    "custom_id": "mc_toggle_play",
                    "emoji": {"name": "⏯️"},
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary (Gray)
                    "label": "Skip",
                    "custom_id": "mc_skip",
                    "emoji": {"name": "⏭️"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Shuffle",
                    "custom_id": "mc_shuffle",
                    "emoji": {"name": "🔀"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Loop",
                    "custom_id": "mc_loop",
                    "emoji": {"name": "🔁"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "View Queue",
                    "custom_id": "mc_queue",
                    "emoji": {"name": "📋"},
                },
            ],
        },
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 2,
                    "label": "Previous",
                    "custom_id": "mc_previous",
                    "emoji": {"name": "⏮️"},
                },
                {
                    "type": 2,
                    "style": 4,  # Danger (Red)
                    "label": "Stop & Clear",
                    "custom_id": "mc_stop",
                    "emoji": {"name": "⏹️"},
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Volume Cycle",
                    "custom_id": "mc_volume",
                    "emoji": {"name": "🔊"},
                },
                {
                    "type": 2,
                    "style": 3,  # Success (Green)
                    "label": "Request Song",
                    "custom_id": "mc_request_modal",
                    "emoji": {"name": "➕"},
                },
            ],
        },
    ]

    payload = {
        "content": "",
        "embeds": [embed],
        "components": components,
    }

    async with aiohttp.ClientSession() as s:
        # Delete old voice required message
        try:
            print(f"Deleting old prompt {DELETE_MSG}...")
            async with s.delete(f"https://discord.com/api/v10/channels/{CH_MUSIC}/messages/{DELETE_MSG}", headers=headers) as dr:
                print("Delete status:", dr.status)
        except Exception as e:
            print("Delete error:", e)

        await asyncio.sleep(1)

        # Update target message with persistent Jukebox
        print(f"Updating message {TARGET_MSG} with permanent Jukebox console...")
        async with s.patch(f"https://discord.com/api/v10/channels/{CH_MUSIC}/messages/{TARGET_MSG}", headers=headers, json=payload) as pr:
            print("Update status:", pr.status)
            if pr.status != 200:
                print("Posting new message...")
                async with s.post(f"https://discord.com/api/v10/channels/{CH_MUSIC}/messages", headers=headers, json=payload) as cr:
                    print("Create status:", cr.status)

if __name__ == "__main__":
    asyncio.run(main())
