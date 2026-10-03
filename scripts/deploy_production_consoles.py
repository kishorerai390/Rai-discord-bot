import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

CHANNELS = {
    "antinuke": 1555283380961026139,
    "lockdown": 1555283386656886825,
    "audit": 1555283390943469685,
    "health": 1555283419355676787,
    "backup": 1555283418126876856,
}

async def update_or_post(s, headers, channel_id, embed, components):
    # Fetch messages in channel
    async with s.get(f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=5", headers=headers) as r:
        msgs = await r.json()

    target_id = None
    if isinstance(msgs, list) and len(msgs) > 0:
        # If there are duplicate bot messages, keep only the latest and delete older
        bot_msgs = [m for m in msgs if m.get("author", {}).get("bot")]
        if bot_msgs:
            target_id = bot_msgs[0]["id"]
            for extra in bot_msgs[1:]:
                print(f"Deleting older duplicate {extra['id']} in {channel_id}...")
                await s.delete(f"https://discord.com/api/v10/channels/{channel_id}/messages/{extra['id']}", headers=headers)
                await asyncio.sleep(0.3)

    payload = {"content": "", "embeds": [embed], "components": components}

    if target_id:
        print(f"Updating message {target_id} in {channel_id}...")
        async with s.patch(f"https://discord.com/api/v10/channels/{channel_id}/messages/{target_id}", headers=headers, json=payload) as pr:
            print("Update status:", pr.status)
    else:
        print(f"Posting new message to {channel_id}...")
        async with s.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", headers=headers, json=payload) as cr:
            print("Post status:", cr.status)


async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        # 1. Anti-Nuke Console
        antinuke_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓐ɴᴛɪ-𝕹ᴜᴋᴇ 𝕯ᴇғᴇɴsᴇ 𝕮ᴏɴsᴏʟᴇ ✦",
            "description": (
                "Autonomous sliding-window threat mitigation is **ACTIVE**.\n\n"
                "Rai continuously audits audit-log mutations, API spikes, and administrative events "
                "to isolate rogue moderators, compromised staff tokens, and malicious bots.\n\n"
                "🛡️ **Status**: `🟢 Armed & Guarded`\n"
                "⚡ **Sliding Window**: `10 Seconds Rolling Engine`\n"
                "🛑 **Breach Response**: `Immediate Role Strip & Quarantine`"
            ),
            "color": 3066993,  # Emerald
            "fields": [
                {
                    "name": "⚙️ ╏ Active Defensive Traps",
                    "value": (
                        "• **Channel Delete Trap**: Max 3 / 10s\n"
                        "• **Role Delete Trap**: Max 3 / 10s\n"
                        "• **Mass Ban Trap**: Max 3 / 10s\n"
                        "• **Mass Kick Trap**: Max 3 / 10s\n"
                        "• **Webhook Abuse Trap**: Max 5 / 10s"
                    ),
                    "inline": False,
                }
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Autonomous Security Engine ✦"},
        }
        antinuke_comps = [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 3,  # Success
                        "label": "Arm Anti-Nuke",
                        "custom_id": "sec_antinuke_arm",
                        "emoji": {"name": "🛡️"},
                    },
                    {
                        "type": 2,
                        "style": 2,  # Secondary
                        "label": "View Thresholds",
                        "custom_id": "sec_antinuke_thresholds",
                        "emoji": {"name": "⚙️"},
                    },
                    {
                        "type": 2,
                        "style": 2,
                        "label": "Quarantine Status",
                        "custom_id": "sec_antinuke_quarantine",
                        "emoji": {"name": "🛑"},
                    },
                    {
                        "type": 2,
                        "style": 2,
                        "label": "Incident History",
                        "custom_id": "sec_antinuke_history",
                        "emoji": {"name": "📜"},
                    },
                ],
            }
        ]
        await update_or_post(s, headers, CHANNELS["antinuke"], antinuke_embed, antinuke_comps)
        await asyncio.sleep(1)

        # 2. Lockdown Control Console
        lockdown_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓔ᴍᴇʀɢᴇɴᴄʏ 𝓛ᴏᴄᴋᴅᴏᴡɴ 𝕮ᴏɴsᴏʟᴇ ✦",
            "description": (
                "Executive emergency perimeter controls for server security.\n\n"
                "In the event of an active raid, bot spam wave, or severe server incident, "
                "use the controls below to instantly secure all community channels.\n\n"
                "⚠️ **Emergency Lockdown**: Overwrites `@everyone` send_messages to False across all channels.\n"
                "🟢 **Lift Lockdown**: Restores original channel permissions smoothly from cache."
            ),
            "color": 15158332,  # Red (0xE74C3C)
            "fields": [
                {
                    "name": "🚨 ╏ Containment Options",
                    "value": (
                        "• **Initiate Lockdown**: Secures all public text channels instantly.\n"
                        "• **Anti-Raid Mode**: Stricter verification & new-member quarantine.\n"
                        "• **Fast Slowmode**: Enforces 30s delay to halt text floods."
                    ),
                    "inline": False,
                }
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Perimeter Defense Controls ✦"},
        }
        lockdown_comps = [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 4,  # Danger
                        "label": "Emergency Lockdown",
                        "custom_id": "sec_lockdown_execute",
                        "emoji": {"name": "🔒"},
                    },
                    {
                        "type": 2,
                        "style": 3,  # Success
                        "label": "Lift Lockdown",
                        "custom_id": "sec_lockdown_lift",
                        "emoji": {"name": "🔓"},
                    },
                    {
                        "type": 2,
                        "style": 2,  # Secondary
                        "label": "Toggle Anti-Raid",
                        "custom_id": "sec_antiraid_toggle",
                        "emoji": {"name": "🛑"},
                    },
                    {
                        "type": 2,
                        "style": 2,
                        "label": "Fast Slowmode (30s)",
                        "custom_id": "sec_slowmode_30",
                        "emoji": {"name": "⏱️"},
                    },
                ],
            }
        ]
        await update_or_post(s, headers, CHANNELS["lockdown"], lockdown_embed, lockdown_comps)
        await asyncio.sleep(1)

        # 3. Audit Monitor Console
        audit_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓐ᴜᴅɪᴛ 𝕷ᴏɢ 𝓜ᴏɴɪᴛᴏʀ ✦",
            "description": (
                "Real-time forensic synchronization with the Discord Audit Log API.\n\n"
                "All administrative actions, channel creations/deletions, role updates, and bans "
                "are captured, correlated with actor user IDs, and preserved in the immutable SQLite log."
            ),
            "color": 3447003,  # Blue
            "fields": [
                {
                    "name": "🔎 ╏ Forensic Telemetry",
                    "value": (
                        "• **Audit State**: `🟢 Live Sync Active`\n"
                        "• **Incident Correlation**: `RAI-INC-000001 Pattern`\n"
                        "• **Actor Resolution**: `Automated Fallback to Executor ID`"
                    ),
                    "inline": False,
                }
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Forensic Audit Stream ✦"},
        }
        audit_comps = [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 1,  # Primary
                        "label": "Refresh Audit Stream",
                        "custom_id": "audit_sync_refresh",
                        "emoji": {"name": "🔄"},
                    },
                ],
            }
        ]
        await update_or_post(s, headers, CHANNELS["audit"], audit_embed, audit_comps)
        await asyncio.sleep(1)

        # 4. System Health Console
        health_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓢ʏsᴛᴇᴍ 𝓗ᴇᴀʟᴛʜ & 𝕎ᴀᴛᴄʜᴅᴏɢ ✦",
            "description": (
                "Verified multi-database telemetry and self-healing subsystem watchdog.\n\n"
                "Rai's supervisor loop monitors background workers, queue depths, and database "
                "latencies every 15 seconds, recovering any faulted workers without bot restarts."
            ),
            "color": 242424,  # Dark Purple / Charcoal
            "fields": [
                {
                    "name": "❤️ ╏ Subsystem Architecture",
                    "value": (
                        "• **Primary Local DB**: `SQLite (sentinel.db)` 🟢\n"
                        "• **Cache & Cooldowns**: `In-Memory Fallback` 🟢\n"
                        "• **Watchdog Grid**: `Master Supervisor Active` 🟢\n"
                        "• **Graceful Degradation**: `Enabled across all tiers` 🟢"
                    ),
                    "inline": False,
                }
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Production Health Grid ✦"},
        }
        health_comps = [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 1,  # Primary
                        "label": "Full Audit Audit",
                        "custom_id": "sys_health_refresh",
                        "emoji": {"name": "🔄"},
                    },
                    {
                        "type": 2,
                        "style": 3,  # Success
                        "label": "Self-Healing Diagnostic",
                        "custom_id": "sys_health_diag",
                        "emoji": {"name": "🩺"},
                    },
                    {
                        "type": 2,
                        "style": 2,  # Secondary
                        "label": "Latency Matrix",
                        "custom_id": "sys_health_stats",
                        "emoji": {"name": "📊"},
                    },
                ],
            }
        ]
        await update_or_post(s, headers, CHANNELS["health"], health_embed, health_comps)
        await asyncio.sleep(1)

        # 5. Backup & Disaster Recovery Console
        backup_embed = {
            "title": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓓ɪsᴀsᴛᴇʀ 𝕽ᴇᴄᴏᴠᴇʀʏ & 𝓑ᴀᴄᴋᴜᴘs ✦",
            "description": (
                "Point-in-time database snapshotting and cryptographic disaster recovery.\n\n"
                "Automated atomic backups generate SHA-256 verified ZIP archives containing "
                "the SQLite database, security incident logs, server configurations, and room states."
            ),
            "color": 15844367,  # Gold
            "fields": [
                {
                    "name": "📦 ╏ Backup Safeguards",
                    "value": (
                        "• **Snapshot Integrity**: `Cryptographic SHA-256 Validation`\n"
                        "• **Retention Policy**: `Sliding archive rotation`\n"
                        "• **Storage**: `Local Persistent Disk + Cloud Replication`"
                    ),
                    "inline": False,
                }
            ],
            "footer": {"text": "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ Disaster Recovery Manager ✦"},
        }
        backup_comps = [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 1,  # Primary
                        "label": "Instant Snapshot",
                        "custom_id": "sys_backup_create",
                        "emoji": {"name": "💾"},
                    },
                    {
                        "type": 2,
                        "style": 2,  # Secondary
                        "label": "Verify Checksums",
                        "custom_id": "sys_backup_verify",
                        "emoji": {"name": "🔍"},
                    },
                    {
                        "type": 2,
                        "style": 2,  # Secondary
                        "label": "Backup Catalog",
                        "custom_id": "sys_backup_catalog",
                        "emoji": {"name": "📜"},
                    },
                ],
            }
        ]
        await update_or_post(s, headers, CHANNELS["backup"], backup_embed, backup_comps)

if __name__ == "__main__":
    asyncio.run(main())
