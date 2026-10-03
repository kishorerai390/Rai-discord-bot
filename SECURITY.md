# 🛡️ RAI — SECURITY & ABUSE SAFEGUARDS

This document details the security model, threat mitigation mechanisms, risk engine, and operational boundaries implemented in **Rai** (The Raivora).

---

## 1. Security Architecture Overview

Rai operates on an autonomous, explainable defense-in-depth model:

```text
Security Modules (Anti-Raid, Anti-Nuke, Anti-Spam, VoiceGuard, Webhook/Permission Guardians)
       ↓
Event Normalizer (Structured Security Event)
       ↓
Rai Security Brain (Rolling Windows: 1m, 5m, 15m, 30m)
       ↓
Incident Correlation & Risk Engine (0-100 Score with Explicit Observable Reasons)
       ↓
Threat Timeline & Alert Escalation (Cooldown-managed Dispatch)
       ↓
Proactive Protection & Safe Mode Fallback
       ↓
Automated Recovery & Periodic Maintenance
```

### Core Principles

1. **Explainable AI / No Black Box Decisions**: Every automated risk score and moderation decision is backed by observable, human-auditable metrics (e.g. `Join rate 6x baseline`, `Mass role deletions detected: 4 in 10s`).
2. **Alert + Log + Monitor First**: Irreversible actions (mass-bans, channel purges) are never executed purely on statistical anomalies or new account age alone.
3. **Hierarchy & Permission Boundary Respect**: Rai strictly enforces Discord role hierarchy before taking any action. Rai will never attempt to manipulate roles equal to or higher than its own highest role, and will never bypass Discord permissions.

---

## 2. Threat Vector Protections

### 2.1 Anti-Raid & Mass Joins

- **Multi-Window Tracking**: Evaluates join bursts across rolling 1-minute, 5-minute, 15-minute, and 30-minute windows.
- **Dynamic Baselines**: Automatically tracks historical server join rates. A sudden 5×–10× spike triggers escalating risk levels (`NORMAL` → `ELEVATED` → `SUSPICIOUS` → `HIGH` → `CRITICAL`).
- **Account Age Protection**: Checks account age distribution without penalizing legitimate new Discord accounts unless correlated with flood or invite spam.
- **Hysteresis & Recovery**: Incidents remain under active monitoring until activity normalizes below decay thresholds for a consecutive grace period.

### 2.2 Anti-Nuke & Rogue Administrators

- **Audit Log Verification**: Queries server audit logs with exponential backoff to accurately attribute executor identity.
- **Action Rate Limiting**: Intercepts rapid channel deletion, role deletion, mass bans, mass kicks, and mass webhook creation.
- **Whitelisting**: Trusted roles, administrators, and bot integrations can be whitelisted to avoid operational disruption during planned server maintenance.
- **Configurable Responses**:
  - `LOG_ONLY`: Generates security audit log and alert.
  - `STAFF_ALERT`: Pings configured security role in the designated security log channel.
  - `RESTRICT`: Temporarily removes dangerous permissions from the rogue executor role.
  - `LOCKDOWN`: Triggers emergency lockdown on affected channels.

### 2.3 Permission Guardian

- **Monitored Permissions**:
  - `Administrator`
  - `Manage Server`
  - `Manage Roles`
  - `Manage Channels`
  - `Ban Members`
  - `Kick Members`
  - `Manage Webhooks`
- **Executor & Target Logging**: Every dangerous role modification or permission grant is logged with executor attribution and suspicion rating.

### 2.4 Webhook Guardian

- Intercepts webhook creations, modifications, and deletions.
- Detects unauthenticated or suspicious webhook token activity.
- Automatically records threat timeline events when unknown webhooks are generated during an active incident.

### 2.5 VoiceGuard & Audio Threat Detection

- **Mathematical RMS Analysis**: Uses Root-Mean-Square energy calculation and exponential smoothing over PCM audio frames rather than uncalibrated decibels.
- **Privacy Preservation**: Raw audio frames are immediately processed and discarded from memory. No audio is ever recorded, stored on disk, or transmitted to third parties.
- **Strike Escalation**:
  - 1st strike: In-channel warning embed.
  - 2nd strike: Escalated warning embed.
  - 3rd strike: Configured server mute or disconnect containment.
- **Graceful Degradation**: If the deployment environment lacks native voice-receive binaries, VoiceGuard automatically operates in Interface Mode with full reporting without crashing the bot.

---

## 3. Emergency Mode & Safe Mode

### 3.1 Emergency Mode (`/security emergency`)

Administrators can trigger server-wide heightened defense immediately during an active raid or brigade:
- Join rate sensitivity is multiplied (thresholds lowered).
- Anti-spam and mention filters operate in maximum enforcement mode.
- Non-verified new accounts are restricted from sending links or role mentions.
- Staff channels receive immediate real-time incident updates.

Commands:
- `/security emergency activate [reason]`
- `/security emergency disable`
- `/security emergency status`

### 3.2 Safe Mode

If multiple critical subsystems detect cascading failures or extreme unverified state divergences:
- Destructive automated actions (kicks/bans/channel alters) are suspended.
- Logging, monitoring, and threat timeline tracking continue uninterrupted.
- Server administrators are alerted with failure diagnostics.
- Preserves database state and requires manual staff confirmation to exit.

---

## 4. Privacy & Data Handling

Rai strictly adheres to data minimization and Discord Developer Terms:
- **No Token Storage**: Discord tokens and environment secrets are loaded strictly from `.env` or system environment variables into memory.
- **No Message Scraping**: Message content is processed in volatile memory for spam/link/mention analysis and immediately discarded unless stored as a sanitized moderation warning record.
- **Data Retention & Maintenance**:
  - Automated maintenance worker cleans expired cooldowns, obsolete verification records, and archived incidents older than 90 days.
  - Backups are stored in `data/backups/` with strict file permissions and automatic rotation.

---

## 5. Vulnerability Disclosure

If you discover any security vulnerability in Rai, please report it privately:

1. Do not open public issues or pull requests detailing the exploit.
2. Contact the server owner or core maintainers directly via Discord or private communication.
3. Allow up to 48 hours for patch verification and emergency deployment.
