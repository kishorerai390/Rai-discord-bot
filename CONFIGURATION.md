# ⚙️ Rai — Configuration & Slash Command Reference

This document outlines all administrative slash commands, configuration parameters, and default settings in **Rai**.

---

## 🛡️ Security Commands (`/security`)

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/security dashboard` | None | Visual ASCII & embed security status with live incident count |
| `/security incident` | `incident_id` | View full chronological threat timeline for an incident |
| `/security emergency` | `action: activate/disable/status` | Instant server-wide enhanced security and surveillance mode |
| `/security analytics` | `period: 1/7/30 days` | High-level server security, raid, and moderation metrics |
| `/security setup` | `punishment, limits, window` | Configure anti-nuke thresholds and automated containment actions |
| `/security enable` | None | Arm automated security defenses |
| `/security disable` | None | Disarm automated security defenses (with confirmation) |
| `/security status` | None | Display active anti-nuke limits and whitelist count |
| `/security whitelist` | `action: add/remove/list` | Manage trusted members and roles exempt from security limits |
| `/security lockdown` | None | Emergency server-wide channel lockdown |
| `/security unlock` | None | Lift lockdown and restore channel permissions |
| `/security emergency-stop` | None | Kill switch: halts destructive punishments while logging continues |
| `/security emergency-resume` | None | Resume automated security punishments |

---

## 🚨 Raid Detection Commands (`/raid`)

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/raid status` | None | Real-time join velocity, rolling windows (1m/5m/15m), and risk score |
| `/raid resolve` | `[incident_id]` | Manually resolve an active raid incident and restore threat level |
| `/raid incidents` | None | Review historical raid incidents and peak scores |

---

## 🔊 VoiceGuard Commands (`/voiceguard`)

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/voiceguard status` | None | View acoustic engine state, thresholds, and recent incidents |
| `/voiceguard enable` | None | Arm voice channel loud audio monitoring |
| `/voiceguard disable` | None | Deactivate voice channel audio monitoring |
| `/voiceguard threshold` | `default, extreme, duration` | Adjust relative RMS energy thresholds (0.1–1.0) and duration |
| `/voiceguard configure` | `action, warning_limit, decay` | Configure automatic action (warn, mute, log) and strike limit |
| `/voiceguard incidents` | None | Review historical voice abuse incidents and peak levels |
| `/voiceguard test` | None | Run non-destructive diagnostic check of the voice pipeline |

---

## 💡 Suggestion System (`/suggest` & `/suggestion`)

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/suggest` | `suggestion: str` | Submit an idea for community voting |
| `/suggestion setup` | `channel, review_channel, voting, threads` | Configure suggestions channel, voting, and discussion threads |
| `/suggestion approve` | `id: int` | Approve suggestion and notify author |
| `/suggestion reject` | `id: int, [reason]` | Reject suggestion with optional reason |
| `/suggestion implement` | `id: int` | Mark suggestion as implemented |
| `/suggestion archive` | `id: int` | Archive a suggestion and close voting |
| `/suggestion reopen` | `id: int` | Reopen an archived/rejected suggestion |
| `/suggestion view` | `id: int` | View details and live vote counts |
| `/suggestion delete` | `id: int` | Permanently delete a suggestion |

---

## ✅ Smart Verification (`/verification`)

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/verification setup` | `role, channel, min_age_hours` | Deploy interactive button verification panel |
| `/verification status` | None | View current verification settings |
| `/verification disable` | None | Deactivate member verification |

---

## 🔊 Temporary Voice (`/tempvoice`)

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/tempvoice setup` | `hub_channel, [category], [limit]` | Configure Join-to-Create voice hub |
| `/tempvoice lock` | None | Lock temporary room to prevent new joins |
| `/tempvoice unlock` | None | Unlock temporary room |
| `/tempvoice limit` | `limit: int` | Set member capacity on room |
| `/tempvoice rename` | `name: str` | Rename your temporary room |
| `/tempvoice status` | None | Inspect TempVoice configuration |

---

## ⚙️ Central Settings (`/settings`)

| Command | Description |
| :--- | :--- |
| `/settings automation` | Central dashboard with buttons to toggle monitors, trigger backups, or run cleanup |
| `/settings raid` | Configure raid multipliers, thresholds, and auto-containment |
| `/settings security` | Review anti-nuke configuration |
| `/settings moderation` | Review AutoMod spam and link filters |
| `/settings welcome` | Review welcome and departure announcements |
| `/settings tickets` | Review support ticket routing |
| `/settings suggestions` | Review suggestions configuration |
| `/settings verification` | Review verification settings |
| `/settings voiceguard` | Review VoiceGuard parameters |
| `/settings roles` | Review autorole settings |
