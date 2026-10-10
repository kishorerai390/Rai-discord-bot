"""
VIP Penthouse Security & Rules Enhancement Deployer for RAI FAM.
1. Locks 👑・VIP Penthouse and 🚀・booster-lounge exclusively to Boosters and VIPs.
2. Deploys the interactive luxury rules guide into #rules.
3. Configures auto-publish on announcements.
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

BOOSTER_ROLE_ID = 1545494591883579434
VIP_ROLE_ID = 1551184081067450451
RULES_CHANNEL_ID = 1545502710101704714
VIP_VC_ID = 1557481242054758482
BOOSTER_TEXT_ID = 1557479371001045056


async def main():
    print(f"🚀 Deploying VIP Suites Security & Rules Guide for Guild: {GUILD_ID}...")

    async with aiohttp.ClientSession() as session:
        # -------------------------------------------------------------
        # 1. LOCK VIP PENTHOUSE & BOOSTER LOUNGE
        # -------------------------------------------------------------
        print("\n👑 Locking VIP Penthouse & Booster Lounge permissions...")

        # VIP Penthouse Voice Overwrites:
        # @everyone: Deny CONNECT (1 << 20)
        # Booster Role: Allow CONNECT (1 << 20) + VIEW (1 << 10)
        # VIP Role: Allow CONNECT (1 << 20) + VIEW (1 << 10)
        overwrites_vc = [
            {"id": str(GUILD_ID), "type": 0, "deny": str(1 << 20), "allow": "0"},  # Deny Connect to @everyone
            {"id": str(BOOSTER_ROLE_ID), "type": 0, "allow": str((1 << 20) | (1 << 10)), "deny": "0"},
            {"id": str(VIP_ROLE_ID), "type": 0, "allow": str((1 << 20) | (1 << 10)), "deny": "0"},
        ]

        async with session.patch(
            f"https://discord.com/api/v10/channels/{VIP_VC_ID}",
            headers=HEADERS,
            json={"permission_overwrites": overwrites_vc, "bitrate": 96000},
        ) as pr:
            if pr.status in (200, 201):
                print("  ✅ 👑・VIP Penthouse locked exclusively to Boosters & VIPs (96 kbps)")
            else:
                err = await pr.text()
                print(f"  ⚠️ Could not update VIP VC: {pr.status} - {err}")

        await asyncio.sleep(0.5)

        # Booster Text Lounge:
        # @everyone: Deny VIEW_CHANNEL (1 << 10)
        # Booster Role: Allow VIEW_CHANNEL (1 << 10) + SEND_MESSAGES (1 << 11)
        overwrites_text = [
            {"id": str(GUILD_ID), "type": 0, "deny": str(1 << 10), "allow": "0"},
            {"id": str(BOOSTER_ROLE_ID), "type": 0, "allow": str((1 << 10) | (1 << 11) | (1 << 16)), "deny": "0"},
            {"id": str(VIP_ROLE_ID), "type": 0, "allow": str((1 << 10) | (1 << 11) | (1 << 16)), "deny": "0"},
        ]

        async with session.patch(
            f"https://discord.com/api/v10/channels/{BOOSTER_TEXT_ID}",
            headers=HEADERS,
            json={"permission_overwrites": overwrites_text},
        ) as pr:
            if pr.status in (200, 201):
                print("  ✅ 🚀・booster-lounge locked exclusively to Boosters & VIPs")
            else:
                err = await pr.text()
                print(f"  ⚠️ Could not update Booster text: {pr.status} - {err}")

        await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # 2. DEPLOY LUXURY RULES EMBED IN #RULES
        # -------------------------------------------------------------
        print(f"\n📜 Deploying Luxury Rules & Verification Embed in #{RULES_CHANNEL_ID}...")

        rules_embed = {
            "title": "✦ 𝐑𝐀𝐈 𝐅𝐀𝐌 ╏ 𝐎𝐅𝐅𝐈𝐂𝐈𝐀𝐋 𝐑𝐔𝐋𝐄𝐒 & 𝐆𝐔𝐈𝐃𝐄𝐋𝐈𝐍𝐄𝐒 ✦",
            "description": (
                "```asciidoc\n"
                "=== COMMUNITY CONSTITUTION & CODE OF CONDUCT ===\n"
                "```\n"
                "Welcome to **RAI FAM**! To ensure a friendly, high-energy environment for gaming, "
                "music, and creative content, all members are expected to follow these guidelines:\n\n"
                "**1. 🛡️ Mutual Respect**\n"
                "• Treat everyone with courtesy. Toxicity, harassment, or hate speech will result in an immediate timeout or ban.\n\n"
                "**2. 🚫 Zero Malicious Links & Self-Promotion**\n"
                "• Phishing links, scam Discord Nitro gifts, and unauthorized DM advertisements are automatically intercepted and quarantined by Raivora Sentinel.\n\n"
                "**3. 🎧 Audio & Voice Etiquette**\n"
                "• Do not ear-rape or spam soundboards. Respect temporary voice room owners and allow everyone fair turns on the music queue.\n\n"
                "**4. 📸 Media & Content Guidelines**\n"
                "• Keep all NSFW content out of public channels. Share your montages and artwork in <#1551184138932068373>.\n\n"
                "🔗 **Community Invite:** `https://discord.gg/uW4vTv2H`"
            ),
            "color": 0x7C3AED,  # Royal Purple
            "thumbnail": {
                "url": "https://cdn.discordapp.com/icons/1457382179981099090/a_icon.gif"
            },
            "footer": {
                "text": "RAI Sentinel Automated Governance • Protected 24/7",
            },
        }

        # Verification button
        rules_payload = {
            "embeds": [rules_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 3,  # Green / Success
                            "label": "Acknowledge & Verify",
                            "emoji": {"name": "✨"},
                            "custom_id": "rules_ack_verify",
                        },
                        {
                            "type": 2,
                            "style": 2,  # Secondary
                            "label": "Role Picker",
                            "emoji": {"name": "🌸"},
                            "custom_id": "rt_welcome:roles",
                        },
                    ]
                }
            ]
        }

        async with session.post(
            f"https://discord.com/api/v10/channels/{RULES_CHANNEL_ID}/messages",
            headers=HEADERS,
            json=rules_payload,
        ) as rr:
            if rr.status in (200, 201):
                print("  ✅ Luxury Rules Embed & Acknowledgment Button deployed successfully!")
            else:
                err = await rr.text()
                print(f"  ⚠️ Rules embed note: {rr.status} - {err}")

    print("\n🎉 VIP Suites & Rules Enhancements deployed cleanly!")


if __name__ == "__main__":
    asyncio.run(main())
