# 🤖 Rai — System Architecture & Platform Design

## Overview

**Rai** is an enterprise-grade, all-in-one Discord security, moderation, automation, and server-management platform. It combines autonomous defense systems with native Discord UI components (Slash Commands, Buttons, Select Menus, Modals) and an embedded SQLite database running with Write-Ahead Logging (WAL) and strict foreign key integrity.

---

## 🏛️ High-Level System Architecture

```text
                                     🤖 RAI
                                       │
                ┌──────────────────────┴──────────────────────┐
                │                                             │
          🛡️ SECURITY                                   ⚙️ MANAGEMENT
                │                                             │
      ┌─────────┼─────────┐                         ┌─────────┼─────────┐
      ↓         ↓         ↓                         ↓         ↓         ↓
  Anti-Raid  Anti-Nuke Anti-Spam                 Tickets  Suggestions Welcome
      ↓         ↓         ↓                         ↓         ↓         ↓
 VoiceGuard  Webhook  Permission                 TempVC   AutoRoles Verification
      │         │         │                         │         │         │
      └─────────┼─────────┘                         └─────────┼─────────┘
                │                                             │
                └──────────────────────┬──────────────────────┘
                                       ↓
                               🧠 SECURITY BRAIN
                                       ↓
                             🧬 INCIDENT CORRELATION
                                       ↓
                                📈 RISK ENGINE
                                       ↓
                              🧬 THREAT TIMELINE
                                       ↓
                                🔔 SMART ALERTS
                                       ↓
                             🛡️ CONFIGURED RESPONSE
                                       ↓
                                🔄 SELF-HEALING
                                       ↓
                                  🟢 RECOVERY
```

---

## 🧠 1. Rai Security Brain (`utils/security_brain.py`)

The **Security Brain** is the central intelligence engine that correlates events from all security subsystems.

### Core Components:
1. **Rolling Activity Windows (`RollingWindowTracker`)**:
   * Uses in-memory double-ended queues (`collections.deque`) to track event frequencies across 60s, 300s, 900s, and 1800s windows.
   * Tracks joins, new accounts (<24h old), message velocity, mention bursts, unauthorized invites, and repeated duplicate content.
   * Periodically prunes expired timestamps to maintain constant $O(1)$ memory usage.
2. **Server-Specific Baselines**:
   * Dynamically tracks typical server join velocity (default 2.0 joins/min) to avoid false-positive alarms on naturally high-traffic servers.
   * Uses both an absolute threshold (`join_threshold`) and a relative multiplier (`join_multiplier`) before escalating.
3. **Multi-Signal Composite Scoring**:
   * **Join spike**: +30
   * **New-account concentration (5+ accounts < 24h)**: +20
   * **Message bursts from new accounts**: +20
   * **Repeated duplicate messages**: +15
   * **Unauthorized Discord invites**: +15
   * **Mention flooding**: +10
4. **Hysteresis & Threat Levels**:
   * `0–29`: **NORMAL**
   * `30–49`: **ELEVATED**
   * `50–69`: **SUSPICIOUS**
   * `70–89`: **HIGH**
   * `90+`: **CRITICAL**
   * Employs hysteresis: Enters HIGH at 70, leaves HIGH at 55 to prevent flapping.
5. **Unified Incident & Threat Timeline Engine**:
   * Automatically assigns a persistent tracking ID (e.g. `RAID-20260930-0001` or `SEC-20260930-0001`).
   * Every triggering event is logged with chronological microsecond timestamps in `security_threat_timeline`.
   * Accessible by staff via `/security incident <id>`.

---

## 🔊 2. VoiceGuard Architecture (`cogs/voiceguard.py`)

VoiceGuard detects microphone abuse, acoustic spikes, and voice raids.

### Mathematical Audio Pipeline:
```text
Voice Frames (16-bit PCM)
           ↓
Unpack Signed 16-bit Samples (-32768 to 32767)
           ↓
Root Mean Square (RMS) Calculation
           ↓
Normalized Relative Energy (0.0 to 1.0)
           ↓
500ms Rolling Window Smoothing
           ↓
Sustained Duration Evaluation (>3.0s loud, >1.5s extreme)
           ↓
VoiceGuard Risk Score & Escalation Engine
```

### Safety & Graceful Degradation:
* **No Real-World Decibel Faking**: Explicitly named *Relative Audio Energy / Audio Level*.
* **Interface-Driven**: Built behind `AudioReceiverInterface`. When standard discord.py is deployed without third-party voice-receive sinks, VoiceGuard safely reports its interface mode in `/voiceguard status` and `/voiceguard test` without crashing.
* **Gradual Escalation**:
  * Strike 1: Ephemeral / DM notice to adjust microphone sensitivity.
  * Strike 2: DM notice + Security channel staff log.
  * Strike 3: Automatic Server Mute (if configured) with audit log attribution.

---

## 🗄️ 3. Database Architecture (`data/bot.db`)

* **Engine**: SQLite 3 with `aiosqlite`.
* **Pragmas**:
  * `PRAGMA foreign_keys = ON;` (Strict referential integrity with cascading deletes)
  * `PRAGMA journal_mode = WAL;` (Concurrent reads while write operations execute)
  * `PRAGMA synchronous = NORMAL;` (High throughput durability)
  * `PRAGMA busy_timeout = 5000;` (Resistant to database locks)
* **Migrations**: Incremental schema migrations (`schema_version` table) up to version **4**.
* **Automatic Backups**:
  * Background worker runs every 6 hours (`tasks.loop(hours=6)`).
  * Safely snapshots SQLite database into `data/backups/bot-<timestamp>.db`.
  * Automatically retains the newest 10 backups and prunes older files.

---

## 🔁 4. Autonomous Maintenance & Self-Healing

1. **Maintenance Loop (`tasks.loop(minutes=10)`)**:
   * Purges expired in-memory cooldown buckets.
   * Removes expired persistent cooldowns from `persistent_cooldowns`.
   * Cleans stale moderation warnings past their `expires_at`.
2. **Central Dashboard (`/settings automation`)**:
   * Interactive Discord buttons allow administrators to toggle any autonomous monitor.
   * Offers on-demand maintenance runs and manual backup snapshots directly from Discord.
