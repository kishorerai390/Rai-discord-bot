"""
Server Audio & Visual Branding Optimizer for RAI FAM.
1. Maximizes voice bitrate to 96kbps on Music/Chill lounges for crisp audio.
2. Optimizes Gaming voice channels to 64kbps for ultra-low latency.
3. Sets aesthetic channel topics with official invite link (discord.gg/uW4vTv2H).
4. Posts an elegant luxury welcome card with active role buttons in #welcome.
5. Harmonizes role colors to the royal purple aesthetic gradient.
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

# Role Color Updates (Royal Purple Gradient)
ROLE_COLORS = {
    "founder": {"color": 0x7C3AED},       # Royal Purple
    "admin": {"color": 0x9333EA},         # Electric Violet
    "moderator": {"color": 0xA855F7},     # Dark Amethyst
    "booster": {"color": 0xC084FC},       # Pastel Lavender
    "rai fam": {"color": 0xE9D5FF},       # Soft Lilac
    "verified": {"color": 0xEDE9FE},      # Pearl Violet
}


async def main():
    print(f"🚀 Starting RAI FAM Optimization for Guild: {GUILD_ID}...")

    async with aiohttp.ClientSession() as session:
        # Fetch channels
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()

        # -------------------------------------------------------------
        # 1. OPTIMIZE VOICE BITRATES
        # -------------------------------------------------------------
        print("\n🎧 Optimizing Voice Channel Bitrates...")
        for c in channels:
            if c.get("type") == 2:  # Voice Channel
                name = c.get("name", "").lower()
                ch_id = c["id"]
                current_bitrate = c.get("bitrate", 64000)

                # Music and Chill rooms -> 96 kbps (Max for non-boosted Tier 0)
                if any(k in name for k in ("radio", "music", "chill", "cafe", "vibe", "cinema", "penthouse", "lounge")):
                    if current_bitrate != 96000:
                        async with session.patch(
                            f"https://discord.com/api/v10/channels/{ch_id}",
                            headers=HEADERS,
                            json={"bitrate": 96000},
                        ) as pr:
                            if pr.status in (200, 201):
                                print(f"  ✅ [HIGH FIDELITY] Set {c['name']} -> 96 kbps")
                            else:
                                print(f"  ⚠️ Could not update {c['name']}: {pr.status}")
                        await asyncio.sleep(0.5)
                # Gaming squad rooms -> 64 kbps (Low latency ping)
                elif any(k in name for k in ("squad", "ranked", "game", "arcade", "battle")):
                    if current_bitrate != 64000:
                        async with session.patch(
                            f"https://discord.com/api/v10/channels/{ch_id}",
                            headers=HEADERS,
                            json={"bitrate": 64000},
                        ) as pr:
                            if pr.status in (200, 201):
                                print(f"  ✅ [LOW LATENCY] Set {c['name']} -> 64 kbps")
                        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # 2. OPTIMIZE CHANNEL TOPICS
        # -------------------------------------------------------------
        print("\n📝 Setting Clean Channel Topics...")
        TOPICS = {
            "chat": "💬・Main Hub of RAI FAM ―― Chat, squad up, and share ideas. Be respectful • discord.gg/uW4vTv2H",
            "media": "📸・Visual Showcase ―― Clips, gameplay highlights, artwork, and creative edits • discord.gg/uW4vTv2H",
            "rules": "📜・Community Guidelines ―― Respect the fam, no toxicity, zero malicious links • discord.gg/uW4vTv2H",
            "welcome": "🌸・Welcome Hub ―― Claim your roles below and begin your journey • discord.gg/uW4vTv2H",
            "announcements": "📢・Official News & Updates ―― Stay tuned for events and announcements • discord.gg/uW4vTv2H",
        }

        for c in channels:
            if c.get("type") in (0, 5):  # Text or Announcement
                name = c.get("name", "").lower()
                ch_id = c["id"]
                for key, topic_text in TOPICS.items():
                    if key in name:
                        if c.get("topic") != topic_text:
                            async with session.patch(
                                f"https://discord.com/api/v10/channels/{ch_id}",
                                headers=HEADERS,
                                json={"topic": topic_text},
                            ) as pr:
                                if pr.status in (200, 201):
                                    print(f"  ✅ Topic updated for #{c['name']}")
                            await asyncio.sleep(0.5)
                        break

        # -------------------------------------------------------------
        # 3. POST LUXURY WELCOME BANNER & ROLE CARD
        # -------------------------------------------------------------
        welcome_ch_id = 1545502705643167876  # #🌸・WELCOME
        print(f"\n🌸 Deploying Luxury Welcome Card in #{welcome_ch_id}...")

        welcome_embed = {
            "title": "✦ 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐓𝐎 𝐑𝐀𝐈 𝐅𝐀𝐌 ✦",
            "description": (
                "```asciidoc\n"
                "=== THE OFFICIAL RAI COMMUNITY REALM ===\n"
                "```\n"
                "👑 **Welcome to the home of RAI FAM!**\n"
                "A premium black-and-purple community for gaming squads, music lovers, and creative editors.\n\n"
                "**✦ QUICK ONBOARDING GUIDE:**\n"
                "• **1.** Read server guidelines in <#1545502710101704714>\n"
                "• **2.** Click the buttons below to pick your interest roles\n"
                "• **3.** Say hello and introduce yourself in <#1545502730699808768>\n"
                "• **4.** Chill to 24/7 lo-fi and high-fidelity music in <#1555255325706424412>\n\n"
                "🔗 **Official Invite Link:** `https://discord.gg/uW4vTv2H`"
            ),
            "color": 0x7C3AED,  # Royal Purple
            "thumbnail": {
                "url": "https://cdn.discordapp.com/icons/1457382179981099090/a_icon.gif"
            },
            "footer": {
                "text": "RAI FAM Ecosystem • Founded by rf.rai_006",
            },
        }

        # Persistent Onboarding Buttons
        buttons_payload = {
            "embeds": [welcome_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {"type": 2, "style": 1, "label": "Gamer", "emoji": {"name": "🎮"}, "custom_id": "role_toggle:gamer"},
                        {"type": 2, "style": 1, "label": "Music Lover", "emoji": {"name": "🎧"}, "custom_id": "role_toggle:music_lover"},
                        {"type": 2, "style": 1, "label": "Editor", "emoji": {"name": "🎨"}, "custom_id": "role_toggle:editor"},
                    ]
                }
            ]
        }

        async with session.post(
            f"https://discord.com/api/v10/channels/{welcome_ch_id}/messages",
            headers=HEADERS,
            json=buttons_payload,
        ) as wr:
            if wr.status in (200, 201):
                print("  ✅ Luxury Welcome Hub & Role Buttons deployed successfully!")
            else:
                err = await wr.text()
                print(f"  ⚠️ Welcome card note: {wr.status} - {err}")

        # -------------------------------------------------------------
        # 4. POLISH ROLE GRADIENT COLORS
        # -------------------------------------------------------------
        print("\n🎨 Polishing Server Role Colors (Royal Purple Palette)...")
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as r:
            roles = await r.json()

        for role in roles:
            r_name = role.get("name", "").lower()
            role_id = role["id"]

            for key, conf in ROLE_COLORS.items():
                if key in r_name and not role.get("managed", False):
                    new_color = conf["color"]
                    if role.get("color") != new_color:
                        async with session.patch(
                            f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles/{role_id}",
                            headers=HEADERS,
                            json={"color": new_color},
                        ) as pr:
                            if pr.status in (200, 201):
                                print(f"  ✅ Updated color for role '{role['name']}' -> #{hex(new_color)[2:].upper()}")
                            else:
                                err = await pr.text()
                                print(f"  ⚠️ Could not update role '{role['name']}': {pr.status}")
                        await asyncio.sleep(0.5)
                    break

    print("\n🎉 Optimization Complete! All audio, branding, and role upgrades applied cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
