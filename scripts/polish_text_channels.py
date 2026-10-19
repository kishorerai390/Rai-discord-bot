import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('f:/Bot/.env')
TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
GUILD_ID = '1457382179981099090'

# Aesthetic topics and slowmodes for text channels
CHANNEL_POLISH = {
    # ✦ START HERE ✦
    '1545502700840427702': { # verify-here
        'topic': 'ᯓ ⋆ Click the button below to verify & unlock all server channels ⋆ ᯓ',
        'rate_limit_per_user': 0
    },
    '1545502705643167876': { # welcome
        'topic': '🌸・Welcome Hub ―― Claim your roles below and begin your journey • discord.gg/d7T8cJK3XF',
        'rate_limit_per_user': 0
    },
    '1545502710101704714': { # rules
        'topic': '📜・Community Guidelines ―― Respect the fam, no toxicity, zero malicious links • discord.gg/d7T8cJK3XF',
        'rate_limit_per_user': 0
    },
    '1545502718792175646': { # announcements
        'topic': '📢・Official Updates ―― Server news, special announcements & community highlights',
        'rate_limit_per_user': 0
    },
    '1545502722739150898': { # get-roles
        'topic': '🎭・Self Roles ―― Select your gaming pings & notification preferences below',
        'rate_limit_per_user': 0
    },

    # ✦ COMMUNITY ✦
    '1545502730699808768': { # general-chat
        'topic': '💬・Main Hub ―― Hang out, talk, and meet the community. Be kind & respectful',
        'rate_limit_per_user': 2
    },
    '1551184138932068373': { # media-dump
        'topic': '📸・Visual Showcase ―― Clips, gameplay highlights, photography, and creative artwork',
        'rate_limit_per_user': 10
    },
    '1557475853175234660': { # gaming-chat
        'topic': '🎮・Gaming Hub ―― Squad up, share stats, find teammates & discuss your favorite games',
        'rate_limit_per_user': 2
    },
    '1558482941817004143': { # editing-chat
        'topic': '🎨・Editing Lab ―― Share edits, presets, color grades, VFX & get constructive feedback',
        'rate_limit_per_user': 5
    },

    # ✦ SUPPORT ✦
    '1555641079137706014': { # support
        'topic': '🎫・Support Desk ―― Open a ticket to reach out directly to our server staff team',
        'rate_limit_per_user': 0
    },
    '1557469924379852860': { # suggestions
        'topic': '💡・Community Ideas ―― Propose features and improvements. Use /suggest to submit',
        'rate_limit_per_user': 30
    },

    # ✦ BOT ✦
    '1549416359723532480': { # bot-commands
        'topic': '🤖・Bot Playground ―― Run slash commands, check profiles, stats & play mini-games',
        'rate_limit_per_user': 5
    },
    '1555283393242206301': { # music-queue
        'topic': '🎵・Audio Studio ―― View current song queues, lyrics & upcoming playback tracks',
        'rate_limit_per_user': 0
    },
}

async def main():
    headers = {
        'Authorization': f'Bot {TOKEN}',
        'Content-Type': 'application/json'
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        print("=== APPLYING POLISH TO TEXT CHANNELS ===")
        for cid, payload in CHANNEL_POLISH.items():
            async with session.patch(f'https://discord.com/api/v10/channels/{cid}', json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Polished #{data['name']} (Slowmode: {data.get('rate_limit_per_user')}s)")
                else:
                    text = await resp.text()
                    print(f"❌ Failed to polish {cid}: {resp.status} - {text}")
            await asyncio.sleep(1.2) # Rate limit avoidance

if __name__ == '__main__':
    asyncio.run(main())
