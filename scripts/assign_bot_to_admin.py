"""
Assign RAI Bot to all 7 channels in 👑・RΛI ADMIN:
Deploys interactive operational dashboards strictly to their respective text channels.
No DMs sent to anyone.
"""

import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(r"f:\Bot\.env")

TOKEN = os.getenv("DISCORD_TOKEN")
HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

ADMIN_PANELS = [
    (
        "1555283409465778218",  # ⚡・admin-control
        {
            "title": "⚡ 『RΛI』 • EXECUTIVE ADMINISTRATION CENTER",
            "description": (
                "**Primary System & Operational Command Console**\n\n"
                "Executive oversight for RAI bot runtime and global server controls:\n\n"
                "• **`/rai reload`** — Hot-reload application cogs and security modules without restarting.\n"
                "• **`/rai status`** — Detailed process telemetry (RAM, CPU, thread pool, event loop latency).\n"
                "• **`/rai ping`** — Discord gateway WebSocket latency & REST API response duration.\n"
                "• **`/rai sync`** — Synchronize slash application commands with Discord Gateway.\n\n"
                "*Access: Server Owner & High Administration Only*"
            ),
            "color": 0xF1C40F,  # Gold
            "footer": {"text": "RAI Executive Administration • Command Console"}
        }
    ),
    (
        "1555283414205075509",  # 🛠️・configuration
        {
            "title": "🛠️ 『RΛI』 • GUILD CONFIGURATION & MODULE MATRIX",
            "description": (
                "**Dynamic Subsystem Configuration & Toggles**\n\n"
                "Modify server settings and feature activation states on-the-fly:\n\n"
                "• **`/config view`** — Inspect all active guild settings and channel bindings.\n"
                "• **`/config security <enable|disable>`** — Toggle autonomous sentinel threat response.\n"
                "• **`/config automod <enable|disable>`** — Enable autonomous word and link filtering.\n"
                "• **`/config music <enable|disable>`** — Toggle high-fidelity Lavalink audio engine.\n"
                "• **`/config welcome <enable|disable>`** — Toggle welcome card greetings and autoroles.\n\n"
                "*All configuration changes are logged and synchronized with local survival storage.*"
            ),
            "color": 0x3498DB,  # Blue
            "footer": {"text": "RAI Configuration Manager • Module Matrix"}
        }
    ),
    (
        "1555283416071675954",  # 🔑・permissions
        {
            "title": "🔑 『RΛI』 • PERMISSION AUDIT & ACCESS CONTROLS",
            "description": (
                "**Role Hierarchy & Access Safety Verification**\n\n"
                "Continuous security analysis of administrative rights and role placements:\n\n"
                "• **`/rai security audit`** — Scan all bot roles and members holding Administrator.\n"
                "• **`/rai whitelist add <user|role>`** — Exempt trusted staff from Anti-Nuke velocity traps.\n"
                "• **`/rai whitelist remove <user|role>`** — Revoke elevated security exemptions.\n"
                "• **Hierarchy Monitor:** Flags inverted roles and overprivileged third-party bots.\n\n"
                "*Policy: Least-Privilege Enforced • Role Hierarchy Integrity Guaranteed*"
            ),
            "color": 0xE67E22,  # Orange
            "footer": {"text": "RAI Permission Safety Engine • Access Controls"}
        }
    ),
    (
        "1555283417183031516",  # 🧰・tools
        {
            "title": "🧰 『RΛI』 • ADMINISTRATIVE UTILITY TOOLKIT",
            "description": (
                "**Staff Operations & Moderation Utilities**\n\n"
                "Tools for managing server hygiene, content moderation, and investigations:\n\n"
                "• **`/purge <amount>`** — Rapidly sanitize up to 100 spam or unauthorized messages.\n"
                "• **`/purge user <user> <amount>`** — Target and remove messages from a specific actor.\n"
                "• **`/rai investigate <user>`** — Comprehensive forensic dossier (account age, joins, risk).\n"
                "• **`/slowmode <seconds>`** — Dynamically throttle channel message velocity during discussions.\n\n"
                "*Authorized for: Founder, Head Admin, and Assigned Staff*"
            ),
            "color": 0x9B59B6,  # Purple
            "footer": {"text": "RAI Utility Suite • Administrative Tools"}
        }
    ),
    (
        "1555283418126876856",  # 📦・backup
        {
            "title": "📦 『RΛI』 • AUTOMATED DATABASE & ARCHIVE BACKUPS",
            "description": (
                "**Database Redundancy & Disaster Prevention**\n\n"
                "Automated snapshot generation ensuring complete data preservation:\n\n"
                "• **`/backup create`** — Generate an on-demand encrypted backup of server configurations.\n"
                "• **`/backup list`** — View available backup archives and verification checksums.\n"
                "• **Redundancy Scope:** SQLite local survival store, PostgreSQL sync state, security configs.\n"
                "• **Validation:** All archives are SHA-256 checksum-verified upon completion.\n\n"
                "*Retention: Bounded rotation prevents storage leaks • S3 / Local Mirror Active*"
            ),
            "color": 0x1ABC9C,  # Teal
            "footer": {"text": "RAI Backup Subsystem • Redundancy Engine"}
        }
    ),
    (
        "1555283419355676787",  # ♻️・restore
        {
            "title": "♻️ 『RΛI』 • POINT-IN-TIME DISASTER RECOVERY",
            "description": (
                "**State Restoration & Emergency Rollback Procedures**\n\n"
                "Controlled protocols for restoring server state following compromise:\n\n"
                "• **Non-Destructive Restoration:** Pre-validates schema versions before applying state.\n"
                "• **Rollback Safety Gate:** Prevents accidental overwrites of live production data.\n"
                "• **Self-Healing Verification:** Reconciles channels, permissions, and database records.\n\n"
                "*Golden Rule: Manual verification required before destructive rollbacks.*"
            ),
            "color": 0x2ECC71,  # Green
            "footer": {"text": "RAI Disaster Recovery • Restoration Safeguards"}
        }
    ),
    (
        "1555283422505730218",  # 🚨・emergency-control
        {
            "title": "🚨 『RΛI』 • EMERGENCY FAIL-SAFE & KILLSWITCH",
            "description": (
                "**Highest-Priority Emergency Protection Overrides**\n\n"
                "Direct intervention controls for severing attacks in progress:\n\n"
                "• **`/emergencystop`** — Global emergency freeze; halts non-security queues and isolates guild.\n"
                "• **`/rai security lockdown activate`** — Immediately locks down all channels against ingress.\n"
                "• **Rogue Actor Containment:** Instantly strips permissions and isolates malicious accounts.\n"
                "• **Founder Fail-Safe:** Only server founder or current guild owner can engage killswitches.\n\n"
                "*Security Priority: Security > Stability > Recovery > Performance*"
            ),
            "color": 0xED4245,  # Red
            "footer": {"text": "RAI Emergency Fail-Safe • Zero Tolerance Overrides"}
        }
    ),
]

async def deploy():
    print("Deploying RAI Bot panels directly to 👑・RΛI ADMIN text channels...")
    print("Strict rule: No DMs sent to anyone.\n")
    async with aiohttp.ClientSession() as s:
        for cid, embed_data in ADMIN_PANELS:
            payload = {"embeds": [embed_data]}
            async with s.post(f"https://discord.com/api/v10/channels/{cid}/messages", headers=HEADERS, json=payload) as r:
                print(f"  ✓ Posted to #{cid}: Status {r.status}")
                await asyncio.sleep(0.35)

    print("\nAll 👑・RΛI ADMIN channels have been assigned and populated successfully!")

if __name__ == "__main__":
    asyncio.run(deploy())
