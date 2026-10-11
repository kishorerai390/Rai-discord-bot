import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
CHANNEL_ID = '1558482941817004143'  # 🎨・editing-chat

async def main():
    headers = {
        'Authorization': f'Bot {TOKEN}',
        'Content-Type': 'application/json'
    }
    
    embed = {
        "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 🎨 𝓒ʀᴇᴀᴛɪᴠᴇ 𝓔ᴅɪᴛɪɴɢ 𝕷ᴀʙ ✦",
        "description": (
            "The premier creative studio for editors, designers, and VFX artists in **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦**.\n\n"
            "Whether you craft in **After Effects**, **Premiere Pro**, **DaVinci Resolve**, **CapCut**, or **Alight Motion**, this is your collaborative home!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "✨ **WHAT YOU CAN SHARE & DO HERE:**\n"
            "• 🎬 **Video Edits & AMVs** — Drop your reels, montages, typography, and motion design.\n"
            "• 📦 **Assets & Presets** — Share custom LUTs, color grades, sound effects, velocity packs & fonts.\n"
            "• 💡 **Constructive Critiques** — Ask for feedback on timing, pacing, graphs, and flow.\n"
            "• 🤝 **Collaborations** — Team up with other creators for MEPs (Multi-Editor Projects) & dual edits."
        ),
        "color": 0xE91E63,  # Rose Petal Pink / Creative Vibrant
        "fields": [
            {
                "name": "🎞️ ┃ 𝓢ʜᴏᴡᴄᴀsᴇ 𝓖ᴜɪᴅᴇʟɪɴᴇs",
                "value": "• Post direct MP4/MOV files or high-bitrate Streamable/YouTube links.\n• Credit music and artists whenever possible.\n• Give honest, friendly feedback that helps fellow creators grow.",
                "inline": False
            },
            {
                "name": "🌟 ┃ 𝓒ʀᴇᴀᴛᴏʀ 𝓡ᴇᴘᴜᴛᴀᴛɪᴏɴ & 𝓡ᴇᴡᴀʀᴅs",
                "value": "Learned a neat trick or downloaded a great preset? Award the creator community recognition with `/rep give @creator` to boost their server standing!",
                "inline": False
            }
        ],
        "footer": {
            "text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Creative Studio • Drop your projects below ✦"
        }
    }

    components = [
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,  # Primary
                    "label": "Showcase Rules",
                    "emoji": {"name": "📜"},
                    "custom_id": "hub_edit:rules"
                },
                {
                    "type": 2,
                    "style": 2,  # Secondary
                    "label": "Asset & Preset Sharing",
                    "emoji": {"name": "📦"},
                    "custom_id": "hub_edit:assets"
                },
                {
                    "type": 2,
                    "style": 3,  # Success
                    "label": "Request Critique",
                    "emoji": {"name": "💡"},
                    "custom_id": "hub_edit:critique"
                }
            ]
        }
    ]

    payload = {
        "embeds": [embed],
        "components": components
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        # Check existing messages in editing-chat
        async with session.get(f'https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=5') as resp:
            msgs = await resp.json()
            if msgs:
                print(f"Found {len(msgs)} existing message(s), updating top bot message...")
                msg_id = msgs[0]['id']
                async with session.patch(f'https://discord.com/api/v10/channels/{CHANNEL_ID}/messages/{msg_id}', json=payload) as patch_resp:
                    if patch_resp.status == 200:
                        print(f"✅ Successfully updated Editing Showcase Console (Msg ID: {msg_id})")
                        return
            
            # Otherwise send new
            async with session.post(f'https://discord.com/api/v10/channels/{CHANNEL_ID}/messages', json=payload) as post_resp:
                if post_resp.status == 200:
                    data = await post_resp.json()
                    print(f"🎉 Successfully deployed Creative Editing Console (Msg ID: {data['id']})")
                else:
                    text = await post_resp.text()
                    print(f"❌ Failed to send message: {post_resp.status} - {text}")

if __name__ == '__main__':
    asyncio.run(main())
