# 🤖 RAI — Autonomous Discord Security & Server Management Platform

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![discord.py 2.x](https://img.shields.io/badge/discord.py-2.x-5865F2.svg)](https://github.com/Rapptz/discord.py)
[![SQLite WAL](https://img.shields.io/badge/database-SQLite%20WAL-00F0FF.svg)](https://sqlite.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-00F0FF.svg)](LICENSE)

**Rai** (The Raivora) is an enterprise-grade, all-in-one Discord security, moderation, and automated server-management platform infused with a distinctive 3D anime/cyberpunk identity.

Built for 24/7 autonomous server defense, Rai eliminates black-box decisions by powering every risk assessment with an explainable multi-signal threat correlation engine, rolling-window baselines, and granular threat timelines.

---

## 🎨 Visual Identity & Theme

* **Codename**: Rai / The Raivora
* **Theme**: 3D Anime / Futuristic Cyberpunk / Neon Shinto Pagoda
* **Palette**:
  - Neon Cyan (`#00F0FF`) — Primary Identity & Embed Borders
  - Royal Indigo (`#7289DA`) — Structural Accent
  - Crimson Alert (`#FF4757`) — Threat & Raid Escalation
  - Emerald Verified (`#2ED573`) — Safe & Verified Operations
  - Deep Charcoal (`#0F111A`) — Cyberpunk Backdrop
* **Assets**: High-resolution 3D anime mascot logos and banners located in `assets/logo.jpg` and `assets/banner.jpg`.

---

## 🛡️ Key Pillars & Architecture

```text
                                 🤖 RAI
                                   │
              ┌────────────────────┴────────────────────┐
              │                                         │
        🛡️ SECURITY                               ⚙️ MANAGEMENT
              │                                         │
       ┌──────┼──────┐                           ┌──────┼──────┐
       ↓      ↓      ↓                           ↓      ↓      ↓
   Anti-Raid Anti-Nuke AntiSpam              Tickets  Suggest Welcome
       ↓      ↓      ↓                           ↓      ↓      ↓
  VoiceGuard Webhook Permission               TempVC   Roles Verification
       │      │      │
       └──────┼──────┘
              ↓
       🧠 SECURITY BRAIN (Rolling Windows: 1m, 5m, 15m, 30m)
              ↓
       🧬 INCIDENT SYSTEM & THREAT TIMELINE
              ↓
        📈 RISK ENGINE (0-100 Score with Observable Reasons)
              ↓
       🔔 SMART ALERTS & ESCALATION
              ↓
       🛡️ PROACTIVE CONTAINMENT & SAFE MODE
              ↓
       🔄 SELF-HEALING & AUTOMATED BACKUPS
```

---

## 🚀 Feature Highlights

### 1. 🧠 Rai Security Brain & Anti-Raid

* **Multi-Window Tracking**: Evaluates join bursts across 1m, 5m, 15m, and 30m rolling windows.
* **Server Baselines & Multipliers**: Automatically learns historical join rates and detects abnormal spikes (e.g. 6× baseline).
* **Multi-Signal Incident Correlation**: Unifies join spikes, message bursts, mention attacks, and unknown webhooks into single correlated incidents with unique tracking IDs.
* **Threat Timelines**: Chronological step-by-step logs for every incident (`/security incident <id>`).
* **Explainable Risk Scoring**: Risk ratings (`NORMAL`, `ELEVATED`, `SUSPICIOUS`, `HIGH`, `CRITICAL`) with explicit observable reasons.
* **Emergency Mode**: Instant heightened defense posture via `/security emergency activate [reason]`.

### 2. 💥 Anti-Nuke & Guardians

* **Audit-Log Attribution**: Identifies rogue executors for mass channel/role deletions, mass bans, and mass kicks.
* **Permission Guardian**: Intercepts unauthorized grants of `Administrator`, `Manage Server`, `Manage Roles`, and other high-risk privileges.
* **Webhook Guardian**: Detects and logs unknown webhook creations or suspicious modifications.
* **Fail-Safe Response Modes**: Configurable `LOG_ONLY`, `STAFF_ALERT`, `RESTRICT`, and `LOCKDOWN`.

### 3. 🔊 VoiceGuard

* **Mathematical RMS Energy**: Computes Root-Mean-Square relative energy levels and exponential moving averages over PCM frames (no fake uncalibrated decibels).
* **Zero-Retention Audio Privacy**: Processed frames are immediately discarded; raw voice is never recorded or stored.
* **Three-Strike Escalation**: Warn 1 ➔ Warn 2 ➔ Temporary Server Mute.
* **Graceful Degradation**: Automatically runs in Interface Mode if native voice-receive sinks are absent without interrupting any bot services.

### 4. 💡 Advanced Community Suggestions

* **Interactive UI**: Slash command `/suggest <content>` with 👍 Upvote, 👎 Downvote, and 💬 Discuss buttons.
* **Atomic SQLite Voting**: Prevents double-voting, supports vote switching, and disallows authors from voting on their own submissions.
* **Forum / Thread Discussions**: Automatically creates threads for discussion.
* **Staff Controls**: `/suggest approve`, `reject`, `implement`, `archive`, `reopen`, `delete`, and `setup`.

### 5. 👤 Smart Verification

* **Button Verification**: Interactive `VerificationButtonView` for instant onboarding.
* **Account Age Filter**: Automatically protects against throwaway raid accounts.
* **Role Routing**: Assigns verified member roles while stripping unverified restrictions.

### 6. 🔊 Temporary Voice Channels ("Join to Create")

* **On-Demand Rooms**: Intercepts joins in creator hubs and spins up dynamic private voice channels.
* **Creator Controls**: `/tempvoice lock`, `unlock`, `limit`, `rename`, and `status`.
* **Zero-Ghost Cleanup**: Automatically cleans up and deletes temporary channels the instant they become empty. Permanent channels are never touched.

### 7. 🎫 Interactive Tickets & Moderation

* **Persistent Support Panels**: Category routing, staff assignment, claiming, and automatic HTML/TXT transcripts upon closure.
* **Enterprise Moderation**: Ban, kick, timeout, warn, clear, slowmode, channel locking, and persistent warning histories with violation decay.

### 8. 🩺 Central Settings, Self-Healing & Health Monitor

* **Consolidated Settings**: `/settings automation`, `security`, `moderation`, `welcome`, `tickets`, `suggestions`, `verification`, `voiceguard`, `roles`.
* **System Health**: `/health` diagnostic displaying live latency, database WAL status, cogs, tasks, and memory consumption.
* **Automated SQLite Backups**: Periodic snapshots to `data/backups/` with automated rotation.
* **Self-Healing Supervisor**: Background workers automatically restart with exponential backoff if errors occur.

---

## 📁 Repository Structure

```text
f:/Bot/
├── main.py                     # Entry point & bot lifecycle supervisor
├── config.py                   # Environment loader, token management & constants
├── requirements.txt            # Python dependencies
├── .env.example                # Template configuration
├── .env                        # Local secrets (never committed)
├── ARCHITECTURE.md             # In-depth architectural specification
├── CONFIGURATION.md            # Command & configuration manual
├── SECURITY.md                 # Threat vectors & abuse safeguards
├── SETUP.md                    # Step-by-step deployment guide
├── TROUBLESHOOTING.md          # Diagnostics & recovery procedures
├── CHANGELOG.md                # Migration & release notes
│
├── assets/                     # 3D Anime Brand Assets
│   ├── logo.jpg                # Master Cyberpunk Rai Mascot Logo
│   └── banner.jpg              # Master Cyberpunk Pagoda Banner
│
├── cogs/                       # Modular Subsystems (13 Active Cogs)
│   ├── security.py             # Security Dashboard, Emergency Mode, Threat Timeline
│   ├── raid.py                 # Anti-Raid detection, join bursts, incidents
│   ├── voiceguard.py           # Audio energy monitoring & strike escalation
│   ├── automod.py              # Anti-spam, link scanner, mention limiter
│   ├── verification.py         # Smart verification & account-age gatekeeping
│   ├── temp_voice.py           # Dynamic "Join to Create" voice channels
│   ├── suggestions.py          # Persistent suggestion system & atomic voting
│   ├── moderation.py           # Hierarchy-aware bans, kicks, timeouts, warnings
│   ├── tickets.py              # Interactive ticket panels & transcripts
│   ├── welcome.py              # Rich welcome embeds & auto-role
│   ├── autorole.py             # Persistent join role assignment
│   ├── logging.py              # Channel-specific security audit dispatching
│   ├── settings.py             # Central settings dashboard, backups & maintenance
│   ├── utility.py              # /help and /health diagnostic commands
│   └── music.py                # Voice streaming & player queue
│
├── database/                   # SQLite WAL Database Layer
│   ├── database.py             # Async connection, thread pool, atomic transactions
│   ├── models.py               # Typed dataclasses for all 32 tables
│   └── migrations.py           # Schema versioning & forward migrations
│
├── utils/                      # Shared Core Engines
│   ├── security_brain.py       # Central Security Brain, baseline tracker, risk engine
│   ├── cooldowns.py            # Sliding-window & persistent rate limiters
│   ├── permissions.py          # Discord role hierarchy safety checks
│   ├── embeds.py               # Cyberpunk-themed Discord embed builders
│   └── helpers.py              # UI views, confirmation modals, audit log resolvers
│
└── tests/                      # Automated Test Suite (27 Unit Tests)
    ├── test_analytics_and_timeline.py
    ├── test_cooldowns.py
    ├── test_database.py
    ├── test_raid.py
    ├── test_suggestions.py
    ├── test_temp_voice.py
    ├── test_verification.py
    └── test_voiceguard.py
```

---

## ⚡ Quick Start

### 1. Prerequisites

- Python 3.11 or 3.12 (`python --version`)
- FFmpeg (for music playback)

### 2. Setup Virtual Environment

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run Migrations & Validations

```bash
python scripts/migrate.py
python scripts/validate.py
```

### 4. Run Test Suite

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

### 5. Launch Rai

```bash
python main.py
```

---

## 🔐 Required Discord Permissions

In Discord **Server Settings ➔ Roles**, drag Rai's role to the **very top** of the role hierarchy.

Grant the following bot permissions:
* `Administrator` (Recommended for full security protection) OR:
  * `Manage Server`, `Manage Roles`, `Manage Channels`, `Ban Members`, `Kick Members`, `Moderate Members`
  * `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`, `Manage Messages`
  * `Connect`, `Speak`, `Move Members`, `Mute Members`

---

## 📄 License & Credits

Licensed under the [MIT License](LICENSE). Built for high-security community servers by the Rai Engineering Team.
