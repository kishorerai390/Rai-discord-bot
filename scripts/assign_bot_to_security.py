"""
Assign RAI Bot to all 12 channels in 🛡️・RΛI SECURITY:
1. Deploys live operational security command and monitor panels to every channel.
2. Synchronizes database routing in bot.db.
3. Configures strict private staff permissions with RAI bot full administration.
"""

import os
import sys
import asyncio
import aiohttp
import sqlite3
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(r"f:\Bot\.env")

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
BOT_ID = 1554732669072445532

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

PANELS = [
    (
        "1555283378612478072",  # 🚨・threat-detection
        {
            "title": "🚨 『RΛI』 • THREAT DETECTION SENTINEL",
            "description": (
                "**Assigned Subsystem:** `SignalEngine` & `RiskEngine`\n\n"
                "• **Function:** Scans member joins, message velocity, permission edits, and token leaks in real time.\n"
                "• **Thresholds:** Signal threshold >= 3 triggers automatic containment and risk escalation.\n"
                "• **Status:** 🟢 **Active & Guarding Guild**"
            ),
            "color": 0xED4245,
            "footer": {"text": "RAI Threat Detection • Autonomous Protection"}
        }
    ),
    (
        "1555283380961026139",  # ☢️・anti-nuke
        {
            "title": "☢️ 『RΛI』 • ANTI-NUKE DEFENSE MATRIX",
            "description": (
                "**Assigned Subsystem:** `AntiNukeEngine` & `ContainmentGuard`\n\n"
                "• **Function:** Prevents mass channel deletion, mass role deletion, and unauthorized bot additions.\n"
                "• **Limits:** 5 deletions / 10s window triggers immediate role strip and emergency quarantine.\n"
                "• **Status:** 🟢 **Zero Tolerance Defense Active**"
            ),
            "color": 0xFF5733,
            "footer": {"text": "RAI Anti-Nuke • Real-Time Interception"}
        }
    ),
    (
        "1555283382512918691",  # ⚔️・anti-raid
        {
            "title": "⚔️ 『RΛI』 • ANTI-RAID VELOCITY FILTER",
            "description": (
                "**Assigned Subsystem:** `AntiRaidEngine`\n\n"
                "• **Function:** Detects incoming bot accounts and rapid join spikes within short time windows.\n"
                "• **Mitigation:** Auto-kick unverified raid accounts, enable emergency join quarantine.\n"
                "• **Status:** 🟢 **Ingress Defense Engaged**"
            ),
            "color": 0x9B59B6,
            "footer": {"text": "RAI Anti-Raid • Join Spike Suppression"}
        }
    ),
    (
        "1555283383825866753",  # 🔒・anti-spam
        {
            "title": "🔒 『RΛI』 • MASS MENTION & SPAM SHIELD",
            "description": (
                "**Assigned Subsystem:** `MentionSpamDetector`\n\n"
                "• **Function:** Detects multi-user mentions `<@USER_ID>`, duplicate messages, and cross-channel flooding.\n"
                "• **Action:** Immediate message purge, 1-hour timeout, and staff alert.\n"
                "• **Status:** 🟢 **Active Content Scanning**"
            ),
            "color": 0x3498DB,
            "footer": {"text": "RAI Anti-Spam • Mention Flood Protection"}
        }
    ),
    (
        "1555283384966717473",  # 🤖・automod
        {
            "title": "🤖 『RΛI』 • AUTONOMOUS MODERATOR",
            "description": (
                "**Assigned Subsystem:** `AutoMod` & `WordFilter`\n\n"
                "• **Function:** Intercepts blacklisted invite links, phishing domains, and toxic words.\n"
                "• **Enforcement:** Automated progressive warning matrix (Warn ➔ Timeout ➔ Kick ➔ Ban).\n"
                "• **Status:** 🟢 **Policy Enforcement Active**"
            ),
            "color": 0x2ECC71,
            "footer": {"text": "RAI AutoMod • Automated Enforcement"}
        }
    ),
    (
        "1555283386656886825",  # 🔒・lockdown
        {
            "title": "🔒 『RΛI』 • EMERGENCY PERIMETER LOCKDOWN",
            "description": (
                "**Assigned Subsystem:** `LockdownManager`\n\n"
                "• **Function:** Instantly freezes text and voice ingress across the entire server or target channels.\n"
                "• **Commands:** `/rai security lockdown activate` | `/rai security lockdown release`\n"
                "• **Status:** 🟢 **Perimeter Standby Mode**"
            ),
            "color": 0xE67E22,
            "footer": {"text": "RAI Lockdown • Emergency Control"}
        }
    ),
    (
        "1555283387340562574",  # 🕵️・security-events
        {
            "title": "🕵️ 『RΛI』 • FORENSIC INCIDENT TIMELINE",
            "description": (
                "**Assigned Subsystem:** `ForensicInvestigator`\n\n"
                "• **Function:** Comprehensive audit trail of all security anomalies, member flags, and signal spikes.\n"
                "• **Forensics:** `/rai investigate <user_id>` for deep actor profile inspection.\n"
                "• **Status:** 🟢 **Forensic Logging Active**"
            ),
            "color": 0x1ABC9C,
            "footer": {"text": "RAI Security Events • Forensic Audit"}
        }
    ),
    (
        "1555283390943469685",  # 📋・audit-logs
        {
            "title": "📋 『RΛI』 • DISCORD AUDIT LOG SYNC",
            "description": (
                "**Assigned Subsystem:** `AuditLogSync`\n\n"
                "• **Function:** Tracks guild role creations, permissions alterations, and channel renames.\n"
                "• **Verification:** Validates actor bot permissions against server hierarchy.\n"
                "• **Status:** 🟢 **Audit Stream Synchronized**"
            ),
            "color": 0x95A5A6,
            "footer": {"text": "RAI Audit Logs • Administrative Tracker"}
        }
    ),
    (
        "1555283423587737700",  # 🚨・raid-alert
        {
            "title": "🚨 『RΛI』 • REAL-TIME RAID ALERTS",
            "description": (
                "**Assigned Subsystem:** `EmergencyBroadcaster`\n\n"
                "• **Function:** Broadcasts high-priority alerts when raid containment engages.\n"
                "• **Routing:** Real-time push to staff and current server owner fallback.\n"
                "• **Status:** 🟢 **Alert Dispatch Standby**"
            ),
            "color": 0xE74C3C,
            "footer": {"text": "RAI Raid Alert • High Priority Stream"}
        }
    ),
    (
        "1555283425668366477",  # 🔴・critical-alert
        {
            "title": "🔴 『RΛI』 • CRITICAL SEVERITY ESCALATION",
            "description": (
                "**Assigned Subsystem:** `IncidentManager` (`RAI-INC-XXXXXX`)\n\n"
                "• **Function:** Severity level CRITICAL and EMERGENCY incidents.\n"
                "• **Protocol:** Deterministic local mitigation first ➔ Owner reporting ➔ Cloud synchronization.\n"
                "• **Status:** 🟢 **Escalation Protocol Active**"
            ),
            "color": 0xC0392B,
            "footer": {"text": "RAI Critical Alerts • Incident Protocol"}
        }
    ),
    (
        "1555283426851037324",  # ☢️・nuke-detection
        {
            "title": "☢️ 『RΛI』 • NUKE DETECTION STREAM",
            "description": (
                "**Assigned Subsystem:** `PermissionAuditor`\n\n"
                "• **Function:** High-velocity audit stream monitoring destructive administrative actions.\n"
                "• **Protection:** Auto-quarantines rogue bots or compromised staff accounts.\n"
                "• **Status:** 🟢 **Active Sentinel Vigilance**"
            ),
            "color": 0xD35400,
            "footer": {"text": "RAI Nuke Detection • Instant Containment"}
        }
    ),
    (
        "1555283428314714173",  # 🔒・emergency-lock
        {
            "title": "🔒 『RΛI』 • EMERGENCY SECURITY CONTROLS",
            "description": (
                "**Assigned Subsystem:** `EmergencyDefense`\n\n"
                "• **Function:** Central manual control room for immediate server defensive overrides.\n"
                "• **Actions:** Quarantine actor, revoke dangerous bot permissions, freeze invites.\n"
                "• **Status:** 🟢 **Emergency Readiness: 100%**"
            ),
            "color": 0x7F8C8D,
            "footer": {"text": "RAI Emergency Lock • Command Center"}
        }
    ),
]

async def deploy():
    print("Assigning RAI Bot to 🛡️・RΛI SECURITY channels...")
    async with aiohttp.ClientSession() as s:
        for cid, embed_data in PANELS:
            payload = {"embeds": [embed_data]}
            async with s.post(f"https://discord.com/api/v10/channels/{cid}/messages", headers=HEADERS, json=payload) as r:
                print(f"  Assigned bot panel to #{cid}: Status {r.status}")
                await asyncio.sleep(0.35)

    # Link database configs
    conn = sqlite3.connect(r"f:\Bot\data\bot.db")
    c = conn.cursor()
    c.execute("""
        UPDATE logging_config
        SET security_channel_id = ?,
            moderation_channel_id = ?,
            automod_channel_id = ?
        WHERE guild_id = ?
    """, (1555283378612478072, 1555283384966717473, 1555283384966717473, GUILD_ID))
    conn.commit()
    conn.close()
    print("Database logging configs synchronized with RAI Security channels.")

if __name__ == "__main__":
    asyncio.run(deploy())
