import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
INFO_CAT_ID = 1545803464712650844  # Information category
FOCUS_CAT_ID = 1554891470325031013  # Focus & AFK category
AFK_VC_ID = 1554891485818921042     # 💤・𝓐ғᴋ・𝓢ʟᴇᴇᴘ

TICKET_OPTIONS = [
    {
        "label": "General Support & Inquiries",
        "value": "general",
        "description": "Questions about community, roles, or bot features",
        "emoji": {"name": "❓"},
    },
    {
        "label": "Security & Rule Violations",
        "value": "security",
        "description": "Report raids, phishing, toxic behavior, or scams",
        "emoji": {"name": "🛡️"},
    },
    {
        "label": "VIP, Nitro & Booster Support",
        "value": "vip",
        "description": "Claim booster roles, custom perks, or donor rewards",
        "emoji": {"name": "💎"},
    },
    {
        "label": "Staff Applications & Help",
        "value": "staff",
        "description": "Apply for moderator, event host, or helper positions",
        "emoji": {"name": "📋"},
    },
    {
        "label": "Partnerships & Collaborations",
        "value": "partnership",
        "description": "Cross-server partnerships, promotions, and sponsorships",
        "emoji": {"name": "🤝"},
    },
]

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        # Fetch current channels
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers) as r:
            channels = await r.json()

        support_ch = None
        afk_text_ch = None

        for ch in channels:
            name = ch.get("name", "")
            if "SUPPORT" in name.upper() or "𝓢ᴜᴘᴘᴏʀᴛ" in name:
                support_ch = ch
            if ("AFK" in name.upper() or "𝓢ʟᴇᴇᴘɪɴɢ" in name) and ch.get("type") == 0:
                afk_text_ch = ch

        # 1. Create or verify Support Desk Channel
        if not support_ch:
            print("Creating Support Desk Channel...")
            payload = {
                "name": "🎫・𝓢ᴜᴘᴘᴏʀᴛ-𝕯ᴇsᴋ",
                "type": 0,
                "parent_id": str(INFO_CAT_ID),
                "position": 5,
            }
            async with s.post(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=payload) as cr:
                support_ch = await cr.json()
                print("Support desk created:", support_ch.get("id"))
        else:
            print(f"Support desk exists: {support_ch.get('id')}")

        # 2. Create or verify AFK Sleeping Pods Text Channel
        if not afk_text_ch:
            print("Creating Sleeping Pods Channel...")
            payload = {
                "name": "💤・𝓢ʟᴇᴇᴘɪɴɢ-𝕻ᴏᴅs",
                "type": 0,
                "parent_id": str(FOCUS_CAT_ID),
                "position": 0,
            }
            async with s.post(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=payload) as cr:
                afk_text_ch = await cr.json()
                print("Sleeping pods channel created:", afk_text_ch.get("id"))
        else:
            print(f"Sleeping pods channel exists: {afk_text_ch.get('id')}")

        await asyncio.sleep(1)

        # 3. Post / Update Support Desk Console
        support_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓢ᴜᴘᴘᴏʀᴛ & 𝕳ᴇʟᴘ 𝕯ᴇsᴋ ✦",
            "description": (
                "Welcome to the **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦** Support Portal.\n\n"
                "Need help with roles, security, community questions, or partnerships? "
                "Select a category from the dropdown or click a quick action button below to "
                "open a private concierge ticket with our staff team.\n\n"
                "⚡ **Average Staff Response**: `< 5 Minutes`\n"
                "🛡️ **Privacy Guarantee**: All tickets are completely private between you and authorized staff."
            ),
            "color": 0x3498DB,  # Crisp Luxury Blue
            "fields": [
                {
                    "name": "🎫 ╏ Available Concierge Services",
                    "value": (
                        "• **General Support**: Bot commands, server roles, permissions\n"
                        "• **Security Reports**: Urgent harassment, raid, or scam alerts\n"
                        "• **VIP Concierge**: Booster perks, custom role requests\n"
                        "• **Collabs**: Server partnerships & joint events"
                    ),
                    "inline": False,
                }
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Member Concierge • 24/7 Available ✦"},
        }

        support_payload = {
            "embeds": [support_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 3,
                            "custom_id": "sentinel_ticket_category_select",
                            "placeholder": "📩 Select a support category to open ticket...",
                            "min_values": 1,
                            "max_values": 1,
                            "options": TICKET_OPTIONS,
                        }
                    ],
                },
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 1,  # Primary (Blurple)
                            "label": "Open General Ticket",
                            "custom_id": "sentinel_ticket_create",
                            "emoji": {"name": "🎫"},
                        },
                        {
                            "type": 2,
                            "style": 4,  # Danger (Red)
                            "label": "Urgent Security Report",
                            "custom_id": "sentinel_ticket_security_fast",
                            "emoji": {"name": "🚨"},
                        },
                        {
                            "type": 2,
                            "style": 2,  # Secondary
                            "label": "Server FAQ",
                            "custom_id": "sentinel_support_faq",
                            "emoji": {"name": "📜"},
                        },
                    ],
                },
            ],
        }

        # Clear old messages in support channel and send fresh console
        supp_id = support_ch.get("id")
        async with s.get(f"https://discord.com/api/v10/channels/{supp_id}/messages?limit=10", headers=headers) as mr:
            m_list = await mr.json()
            if isinstance(m_list, list):
                for m in m_list:
                    await s.delete(f"https://discord.com/api/v10/channels/{supp_id}/messages/{m['id']}", headers=headers)
                    await asyncio.sleep(0.3)

        async with s.post(f"https://discord.com/api/v10/channels/{supp_id}/messages", headers=headers, json=support_payload) as pr:
            print("Support Desk post status:", pr.status)

        await asyncio.sleep(1)

        # 4. Post / Update AFK Sleeping Pods Console
        afk_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓢ʟᴇᴇᴘɪɴɢ 𝕻ᴏᴅs & 𝕬ғᴋ 𝕷ᴏᴜɴɢᴇ ✦",
            "description": (
                "Welcome to the **✦ 𝓡ᴀɪ 𝕱ᴀᴍ ✦** Rest Sanctuary & Quiet Pods.\n\n"
                "Stepping away for a meal, work, or sleep? Move into the Sleeping Pod to "
                "prevent disruptive noise and keep active voice lounges lively.\n\n"
                f"🛌 **Dedicated AFK Lounge**: <#{AFK_VC_ID}>\n\n"
                "✨ **Automated Rest Features**:\n"
                "• Automatically saves your previous voice channel.\n"
                "• Silence guaranteed: no incoming speech or loud pings.\n"
                "• Click **[🔔 Wake Up & Reconnect]** anytime to jump straight back into the action!"
            ),
            "color": 0x5C6BC0,  # Midnight Indigo
            "fields": [
                {
                    "name": "💤 ╏ Sleeping Pod Rules",
                    "value": (
                        "• Members deafened or inactive for > 15 minutes are gently moved here.\n"
                        "• Microphones are auto-muted for tranquility.\n"
                        "• You can return to your squad with a single click below."
                    ),
                    "inline": False,
                }
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Voice Guard & Rest Management ✦"},
        }

        afk_payload = {
            "embeds": [afk_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 2,  # Secondary
                            "label": "Enter Sleeping Pod",
                            "custom_id": "rai_afk_enter",
                            "emoji": {"name": "💤"},
                        },
                        {
                            "type": 2,
                            "style": 3,  # Success
                            "label": "Wake Up & Reconnect",
                            "custom_id": "rai_afk_wake",
                            "emoji": {"name": "🔔"},
                        },
                        {
                            "type": 2,
                            "style": 2,  # Secondary
                            "label": "Silent Focus Mode",
                            "custom_id": "rai_afk_focus",
                            "emoji": {"name": "🎧"},
                        },
                    ],
                }
            ],
        }

        afk_id = afk_text_ch.get("id")
        async with s.get(f"https://discord.com/api/v10/channels/{afk_id}/messages?limit=10", headers=headers) as mr:
            m_list = await mr.json()
            if isinstance(m_list, list):
                for m in m_list:
                    await s.delete(f"https://discord.com/api/v10/channels/{afk_id}/messages/{m['id']}", headers=headers)
                    await asyncio.sleep(0.3)

        async with s.post(f"https://discord.com/api/v10/channels/{afk_id}/messages", headers=headers, json=afk_payload) as pr:
            print("AFK Sleeping Pods post status:", pr.status)

if __name__ == "__main__":
    asyncio.run(main())
