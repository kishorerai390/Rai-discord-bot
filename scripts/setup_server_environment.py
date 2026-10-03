"""
Autonomous Server Setup and Configuration Engine for RAI FAM (Guild 1457382179981099090).
Deploys interactive verification, ticket, suggestion, and rules panels,
and links all channels to Rai's database configurations.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = 1457382179981099090

# Target Channels in RAI FAM
CH_VERIFY = 1545502700840427702
CH_WELCOME = 1545502705643167876
CH_RULES = 1545502710101704714
CH_ANNOUNCEMENTS = 1545502718792175646
CH_GENERAL = 1545502730699808768
CH_COMMANDS = 1549416359723532480
CH_VOICE_HUB = 1550187295821402114
CH_TICKETS = 1545514505520545886
CH_SECURITY_LOGS = 1546593526073135107
CH_MOD_LOGS = 1546540192343523399
CH_AUDIT_LOGS = 1545502850057244762
CAT_COMMUNITY = 1545803478490812578
CAT_TICKETS = 1545803487093456906

# Roles
ROLE_VERIFIED = 1549504522953695269
ROLE_MOD = 1545494600347680918
ROLE_EXECUTIVE = 1545494610489643038

async def setup():
    print("=" * 60)
    print("AUTONOMOUS SERVER SETUP & CONFIGURATION")
    print("Guild: RAI FAM (1457382179981099090)")
    print("=" * 60)

    from database.database import Database
    db = Database()
    await db.connect()
    print("[1] Database connected.")

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        # A. Check or Create Suggestions Channel
        ch_suggestions_id = None
        async with session.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers) as r:
            channels = await r.json()
            for ch in channels:
                name = ch.get("name", "").lower()
                if "suggestion" in name:
                    ch_suggestions_id = int(ch["id"])
                    break

        if not ch_suggestions_id:
            print("Creating suggestions channel...")
            create_payload = {
                "name": "💡・suggestions",
                "type": 0,
                "parent_id": str(CAT_COMMUNITY),
                "topic": "Submit your community suggestions and vote on improvements!",
            }
            async with session.post(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, json=create_payload) as r:
                if r.status in (200, 201):
                    new_ch = await r.json()
                    ch_suggestions_id = int(new_ch["id"])
                    print(f"  [+] Created suggestions channel ({ch_suggestions_id})")
        else:
            print(f"  [+] Found existing suggestions channel ({ch_suggestions_id})")

        # B. Deploy Rules & Info Embed
        print("\n[2] Deploying Server Rules & Information...")
        rules_embed = {
            "title": "📜 RAI FAM — OFFICIAL COMMUNITY GUIDELINES",
            "description": (
                "Welcome to **RAI FAM**! To ensure a safe, welcoming, and high-energy environment "
                "for all members, everyone must adhere to the community rules outlined below.\n\n"
                "*Rai's Autonomous Autopilot & Security Brain monitor all activity 24/7.*"
            ),
            "color": 0x5865F2,
            "fields": [
                {
                    "name": "1. 🤝 Respect & Civil Conduct",
                    "value": "Harassment, hate speech, slurs, targeted toxicity, and excessive drama are strictly prohibited.",
                    "inline": False,
                },
                {
                    "name": "2. 🚫 Anti-Spam & Flooding",
                    "value": "Do not flood channels, spam emojis, mention spam (@everyone / @here), or repeat identical messages.",
                    "inline": False,
                },
                {
                    "name": "3. 🔗 Unsolicited Links & Invites",
                    "value": "Unsolicited advertising, Discord server invite links, phishing domains, and malicious links will result in immediate timeout.",
                    "inline": False,
                },
                {
                    "name": "4. 🔊 Voice & Soundboard Etiquette",
                    "value": "Do not scream into microphones, play ear-rape audio, or abuse soundboards. VoiceGuard acoustic monitoring is active.",
                    "inline": False,
                },
                {
                    "name": "5. 🛡️ Staff & Enforcement",
                    "value": "Follow instructions from moderators and executives. Evading punishments or abusing tickets will lead to a permanent ban.",
                    "inline": False,
                },
            ],
            "footer": {
                "text": "Discord Terms of Service & Community Guidelines Apply • RAI FAM Security",
            },
        }
        async with session.post(f"https://discord.com/api/v10/channels/{CH_RULES}/messages", headers=headers, json={"embeds": [rules_embed]}) as r:
            print(f"  Rules embed post status: {r.status}")

        # C. Deploy Interactive Verification Panel
        print("\n[3] Deploying Verification Panel...")
        verify_embed = {
            "title": "🛡️ RAI FAM — MEMBER VERIFICATION",
            "description": (
                "Welcome to **RAI FAM**! To safeguard our community against automated bot attacks, "
                "phishing raids, and malicious accounts, all new members must verify before accessing channels.\n\n"
                "**Verification Requirements:**\n"
                "• Your account must meet basic age criteria.\n"
                "• You agree to adhere to the server rules in <#1545502710101704714>.\n\n"
                "Click the button below to complete verification and unlock full access!"
            ),
            "color": 0x2ECC71,
            "footer": {"text": "Powered by Rai Autonomous Security System"},
        }
        verify_payload = {
            "embeds": [verify_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 3,  # Success (Green)
                            "label": "Complete Verification",
                            "custom_id": "btn_verify_member",
                            "emoji": {"name": "✅"},
                        }
                    ],
                }
            ],
        }
        async with session.post(f"https://discord.com/api/v10/channels/{CH_VERIFY}/messages", headers=headers, json=verify_payload) as r:
            print(f"  Verification panel post status: {r.status}")

        # D. Deploy Interactive Support Ticket Panel
        print("\n[4] Deploying Support Ticket Panel...")
        ticket_embed = {
            "title": "🎫 RAI FAM — SUPPORT & HELP DESK",
            "description": (
                "Need assistance, have a moderation inquiry, or want to report an issue?\n\n"
                "Click the button below to create a **private support ticket** with our Executive Staff. "
                "A dedicated private room will be created for you automatically."
            ),
            "color": 0x9B59B6,
            "fields": [
                {"name": "⏰ Support Hours", "value": "Staff respond 24/7.", "inline": True},
                {"name": "📜 Policy", "value": "No duplicate tickets.", "inline": True},
            ],
            "footer": {"text": "Rai Support Ticket System"},
        }
        ticket_payload = {
            "embeds": [ticket_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 1,  # Primary (Blurple)
                            "label": "Open Support Ticket",
                            "custom_id": "create_ticket_btn",
                            "emoji": {"name": "🎫"},
                        }
                    ],
                }
            ],
        }
        async with session.post(f"https://discord.com/api/v10/channels/{CH_TICKETS}/messages", headers=headers, json=ticket_payload) as r:
            print(f"  Ticket panel post status: {r.status}")

        # E. Update All Configurations in SQLite
        print("\n[5] Updating Database Configurations...")
        # 1. Verification Config
        await db.update_verification_config(
            guild_id,
            enabled=1,
            role_id=ROLE_VERIFIED,
            channel_id=CH_VERIFY,
            min_account_age_hours=0,
        )
        print("  [+] verification_config updated")

        # 2. Welcome Config
        await db.update_welcome_config(
            guild_id,
            welcome_enabled=1,
            welcome_channel_id=CH_WELCOME,
            welcome_message="✨ Welcome {user} to **RAI FAM**! Check out <#1545502700840427702> to verify and <#1545502710101704714> for our rules. Member #{count}!",
            goodbye_enabled=1,
            goodbye_channel_id=CH_WELCOME,
            goodbye_message="👋 Goodbye {user}. We hope to see you back in **RAI FAM** soon!",
            welcome_role_id=ROLE_VERIFIED,
        )
        print("  [+] welcome_config updated")

        # 3. Ticket Config
        await db.update_ticket_config(
            guild_id,
            category_id=CAT_TICKETS,
            log_channel_id=CH_AUDIT_LOGS,
            staff_role_id=ROLE_MOD,
        )
        print("  [+] ticket_config updated")

        # 4. Suggestions Config
        if ch_suggestions_id:
            await db.update_suggestion_config(
                guild_id,
                channel_id=ch_suggestions_id,
                review_channel_id=CH_MOD_LOGS,
                staff_role_id=ROLE_MOD,
            )
            print("  [+] suggestion_config updated")

        # 5. Temp Voice Config
        await db.update_temp_voice_config(
            guild_id,
            enabled=1,
            hub_channel_id=CH_VOICE_HUB,
            category_id=None,
            default_user_limit=0,
        )
        print("  [+] temp_voice_config updated")

        # 6. Logging & Security Config
        await db.update_logging_config(
            guild_id,
            general_channel_id=CH_AUDIT_LOGS,
            moderation_channel_id=CH_MOD_LOGS,
            security_channel_id=CH_SECURITY_LOGS,
        )
        await db.update_autopilot_config(
            guild_id,
            enabled=1,
            dry_run=0,
            alert_channel_id=CH_SECURITY_LOGS,
            max_safety_level="HIGH",
        )
        await db.update_security_config(
            guild_id,
            enabled=1,
            log_channel_id=CH_SECURITY_LOGS,
        )
        print("  [+] security_config, logging_config, autopilot_config updated")

    await db.close()
    print("\n" + "=" * 60)
    print("SUCCESS: SERVER SETUP & CONFIGURATION COMPLETE!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(setup())
