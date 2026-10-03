# 📜 RAI — CHANGELOG & MIGRATION HISTORY

All notable changes, architectural overhauls, database schema migrations, and feature deployments for **Rai** (The Raivora) are documented in this file.

---

## [v2.0.0] — Final Master Upgrade (2026-09-30)

### 🚨 Removed (Purged)

- **Fun Command Subsystem Completely Removed**:
  - Deleted `cogs/fun.py` (8ball, dice, coinflip, ship, meme, joke).
  - Purged all fun command schemas, test assertions, and references from `cogs/utility.py`, `database/models.py`, `scripts/validate.py`, and `scripts/healthcheck.py`.
  - Dropped any legacy fun-related configurations or mock handlers.

---

### 🛡️ Security Brain & Threat Engine (NEW)

- **Central Security Brain (`utils/security_brain.py`)**:
  - Implemented `RollingWindowTracker` supporting 1-minute, 5-minute, 15-minute, and 30-minute sliding windows.
  - Multi-signal composite risk score calculation (0–100 scale) with explicit observable risk reasons.
  - Server join baseline tracker with automatic spike multiplier detection.
  - Incident correlation engine: aggregates join bursts, spam flooding, mention attacks, unknown webhooks, and abnormal audio into single unified incidents.
  - Threat Timeline tracking: chronological event log per incident (`/security incident <id>`).
  - Hysteresis and automated incident resolution state machine (`OPEN` → `MONITORING` → `RESOLVED`).
  - Alert debouncing and escalation cooldowns to prevent staff channel spam.
- **Advanced Anti-Raid Subsystem (`cogs/raid.py`)**:
  - Real-time `on_member_join` and `on_message` telemetry feed into Security Brain.
  - Risk categorization: `NORMAL`, `ELEVATED`, `SUSPICIOUS`, `HIGH`, `CRITICAL`.
  - Slash commands: `/raid status`, `/raid resolve`, and `/raid incidents`.
- **Emergency Protection & Safe Mode (`cogs/security.py`)**:
  - `/security emergency activate [reason]`, `/security emergency disable`, `/security emergency status`.
  - Live ASCII Cyberpunk Dashboard: `/security dashboard`.
  - Granular Threat Timeline inspection: `/security incident <id>`.
  - Aggregated Security Analytics: `/security analytics` (1d / 7d / 30d).

---

### 🔊 VoiceGuard Subsystem (NEW)

- **Audio Threat Detection (`cogs/voiceguard.py`)**:
  - Mathematical Root-Mean-Square (RMS) relative audio energy calculation with exponential moving average smoothing.
  - Configurable energy thresholds, spike duration requirements, and sensitivity levels.
  - Three-strike escalation model: Warn 1 → Warn 2 → Temporary Server Mute containment.
  - Privacy-preserving zero-retention pipeline: audio frames are processed and immediately discarded; raw audio is never written to disk or transmitted.
  - Graceful backend detection: runs seamlessly in Interface Mode when voice-receive binaries are absent, without throwing exceptions or degrading other bot services.
  - Slash commands: `/voiceguard status`, `/voiceguard enable`, `/voiceguard disable`, `/voiceguard threshold`, `/voiceguard configure`, `/voiceguard incidents`, `/voiceguard test`.

---

### 💡 Advanced Suggestion System (NEW)

- **Persistent Community Suggestions (`cogs/suggestions.py`)**:
  - Slash command: `/suggest <content>`.
  - Discord UI View (`SuggestionView`) with interactive buttons: 👍 Upvote, 👎 Downvote, 💬 Discuss.
  - Atomic SQLite voting engine: prevents duplicate votes, allows vote switching, and disallows authors from inflating their own vote tallies.
  - Automated forum/thread discussion creation for eligible suggestions.
  - Comprehensive staff management suite: `/suggest approve`, `/suggest reject`, `/suggest implement`, `/suggest archive`, `/suggest reopen`, `/suggest view`, `/suggest delete`, `/suggest setup`.
  - Automatic DM notifications to authors when suggestion statuses change.

---

### 👤 Smart Verification Subsystem (NEW)

- **New Member Gatekeeping (`cogs/verification.py`)**:
  - Persistent interactive button verification view (`VerificationButtonView`).
  - Configurable minimum account age requirements with automated denial of underage accounts.
  - Verification role assignment and restricted role revocation.
  - Verification audit logging.
  - Slash commands: `/verification setup`, `/verification status`, `/verification disable`.

---

### 🔊 Temporary Voice Channels (NEW)

- **Dynamic "Join to Create" Hubs (`cogs/temp_voice.py`)**:
  - Intercepts voice state updates in designated generator channels.
  - Dynamically provisions private voice channels for users with automatic member move.
  - Creator control commands: `/tempvoice lock`, `/tempvoice unlock`, `/tempvoice limit`, `/tempvoice rename`, `/tempvoice status`.
  - Self-cleaning lifecycle: automatically deletes temporary voice channels the moment they become empty. Permanent server channels are strictly untouched.

---

### ⚙️ Central Settings, Automation & Self-Healing (NEW)

- **Consolidated Administration (`cogs/settings.py`)**:
  - Central `/settings automation` interactive dashboard.
  - Modular configuration subcommands: `/settings security`, `/settings automation`, `/settings moderation`, `/settings welcome`, `/settings tickets`, `/settings suggestions`, `/settings verification`, `/settings voiceguard`, `/settings roles`.
  - Self-healing background tasks with exponential backoff.
  - Automated SQLite database backups to `data/backups/` (daily rotation and retention limit).
  - Automated data maintenance worker cleaning expired cooldowns, stale verifications, and obsolete logs.
- **Diagnostic Health Monitoring (`cogs/utility.py`)**:
  - `/health`: Live system diagnostic reporting latency, SQLite connection status, WAL mode, Cog statuses, background tasks, and OS memory consumption.

---

### 🗄️ Database Migrations

- **Migration 3**:
  - Added tables: `suggestions`, `suggestion_votes`, `suggestion_config`.
  - Added tables: `raid_incidents`, `raid_events`, `raid_config`.
  - Added tables: `voice_guard_config`, `voice_incidents`, `voice_warnings`.
  - Added tables: `automation_config`.
- **Migration 4**:
  - Added tables: `verification_config`, `verification_records`.
  - Added tables: `temp_voice_config`, `temp_voice_channels`.
  - Added table: `threat_timeline_events`.
  - Added indexes for incident timeline queries and guild filtering.
  - Upgraded schema version to **4**.

---

### 🎨 Visual Identity & Branding

- **Cyberpunk Anime Theme**:
  - Palette: Neon Cyan (`#00f0ff`), Royal Indigo (`#7289da`), Crimson Warning (`#ff4757`), Emerald Success (`#2ed573`), Charcoal Dark (`#0f111a`).
  - Master logo: `assets/logo.jpg` (3D anime aesthetic, silver hair, cybernetic headset, neon cat companion).
  - Master banners: `assets/banner.jpg` and `assets/banner_ultrawide.jpg` (Cherry blossom moonlight cyberpunk pagoda with 3D chrome "RAI" typography).
  - Complete Brand Kit documented in `anime_brand_kit.md`.
