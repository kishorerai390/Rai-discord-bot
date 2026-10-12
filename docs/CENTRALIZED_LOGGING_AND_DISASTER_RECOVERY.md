# Rai Centralized Logging, Moderation Audit, Support, Backup & Disaster Recovery System

## 1. System Overview & Architecture

The Raivora Discord Bot has been upgraded with an enterprise-grade, resilient **Centralized Logging, Moderation Audit, Support, Backup & Disaster Recovery System** while strictly preserving all existing music, anti-raid, anti-nuke, dynamic voice rooms, welcome, and security subsystems.

All events, configurations, and recovery records are persistently managed via SQLite with non-blocking async queries and WAL-mode integrity.

---

## 2. Centralized Logging (15 Dedicated Channels)

The centralized logging architecture routes discrete event streams to 15 dedicated channels under a parent category (default: `📜 | AUDIT & LOGS`). If a specific channel is not configured, logs safely fall back to the server's general log channel without crashing or flooding.

| Channel Name | Config Attribute | Routed Events & Payloads |
| :--- | :--- | :--- |
| `#mod-logs` | `moderation_channel_id` | Bans, unbans, kicks (audit-correlated), timeouts/communication disabled, ghost pings, warning records |
| `#security-logs` | `security_channel_id` | Anti-raid triggers, anti-nuke thresholds, suspicious alt detections, dangerous permission grants |
| `#message-logs` | `message_channel_id` | Message edits, message deletions, bulk purges (consolidated flood-protected embed) |
| `#member-logs` | `member_channel_id` | Member joins (account age analysis), member leaves (non-kick leaves), nickname changes |
| `#voice-logs` | `voice_channel_id` | VC connections, disconnects, rapid hopping alerts, screen-shares, camera toggles, mute/deafen |
| `#channel-logs` | `channel_logs_channel_id` | Text/voice channel creation, deletion, rename, topic changes, permission overwrite modifications |
| `#role-logs` | `role_logs_channel_id` | Role creation, deletion, rename, color changes, hoist/mentionable toggles, permission grants/revocations |
| `#server-audit-logs` | `server_audit_channel_id` | Guild name, verification level, default notifications, AFK settings, webhook creation/deletion |
| `#backup-logs` | `backup_logs_channel_id` | Automated snapshot generation, manual backups, disaster recovery restorations, checksum results |
| `#report-logs` | `report_logs_channel_id` | Member reports, bug reports, security reports, moderation appeals, tracking receipts |
| `#ticket-logs` | `ticket_logs_channel_id` | Ticket creation, staff assignments, transcript exports, closures, re-openings, archives |
| `#staff-logs` | `staff_logs_channel_id` | Staff internal escalations, high-priority ticket notices, moderation staff notes |
| `#bot-logs` | `bot_logs_channel_id` | Command usage, configuration modifications, background maintenance tasks |
| `#error-logs` | `error_logs_channel_id` | Operational exceptions, unhandled slash errors with `ERR-XXXXXX` / `RAI-XXXXXX` IDs |
| `#system-status` | `system_status_channel_id` | Gateway heartbeat latency, bot startup broadcasts, reconnect status, cluster health |

### Configuration Commands:
- `/logging auto_setup [category_name]` — Automatically provisions or links all 15 audit channels with private staff overwrites (`@everyone` deny view). Reuses existing matching channels without creating duplicates.
- `/logging set category: channel:` — Assign any individual channel destination from the 15 categories.
- `/logging status` — Displays the live status and channel links for all 15 destinations.
- `/logging founder_dm` & `/logging founder_recipient` — Toggles real-time AI security incident alerts in DM to the Server Founder.

---

## 3. Moderation Audit & Attribution Safeguards

Discord API audit logs are asynchronous and external integrations often perform automated tasks. The logging engine adheres to strict attribution rules:
1. **Audit-Log Correlation**: Actions (bans, kicks, timeouts, role updates) are queried within a strict 12-second time window with bounded retries (0.4s delay).
2. **Fail-Safe Identity**: If an audit log entry does not explicitly match the target or timestamp, the bot explicitly marks the actor as `Unknown / External Integration` or `Staff (Uncertain Attribution)` to prevent false accusations.
3. **Flood Protection**: Bulk message deletions (`on_raw_bulk_message_delete`) emit a single consolidated summary embed instead of flooding log channels.

---

## 4. Support, Reports & Tickets System

### Available Commands:
- `/report` — Submit a confidential report (`Member Report`, `Bug Report`, `Security Incident`, `Moderation Appeal`, or `Technical Support`).
  - Generates unique tracking ID (`REP-XXXXXX`).
  - Routes directly to `#report-logs` and `#security-logs` / `#mod-logs`.
  - Optionally spins up a private support ticket for interactive investigation.
- `/support` — Displays the official support server button (`MRL GAMING`) and an interactive button to open a private ticket locally.
- `/ticket create [category] [subject]` — Directly opens a private support ticket channel.
- `/ticket claim` — Staff member assigns themselves to the active ticket, updating channel topic and dispatching notifications to `#ticket-logs`.
- `/ticket close [reason]` — Closes the ticket, generates dark-mode HTML & TXT transcripts, saves them to disk (`data/transcripts/`), sends copies to staff channels and user DMs, and deletes the channel.
- `/ticket reopen` — Reopens an archived or closed ticket channel.
- `/ticket transcript` — On-demand export of HTML and TXT transcripts without closing the ticket.
- `/ticket archive` — Locks ticket channel permissions to read-only and archives the status.
- `/ticket add [user]` & `/ticket remove [user]` — Grants or revokes ticket channel access.
- `/ticket list` — Displays all active/claimed tickets in the server.

### Rate Limiting & Anti-Spam:
- Cooldown: 30 seconds per ticket creation.
- Concurrency Cap: Max 3 open support tickets per user per guild to prevent spam attacks.

---

## 5. Server Backups & Disaster Recovery

### Available Commands:
- `/backup create` — Generates a validated disaster recovery `.zip` archive containing:
  - `server_config.json`: Server settings, roles (color, hoist, permissions), categories, channels, and permission overwrites.
  - `bot_database.sqlite`: Atomic snapshot of all SQLite bot records.
  - `manifest.json`: Metadata, timestamps, counts, and SHA-256 hash.
  - Excludes all bot tokens, passwords, and sensitive credentials.
  - Computes and verifies SHA-256 cryptographic checksum.
  - Persists record in SQLite `server_backups` table and notifies `#backup-logs`.
- `/backup list` — Displays recent server configuration backups with IDs, sizes, checksums, and verification states.
- `/backup status` — Displays backup health, retention, and alerts if backups are stale (> 7 days).
- `/backup restore backup_id:... dry_run:True/False`:
  - `dry_run: True` (Default): Simulates restoration, displaying exact missing roles, categories, and channels that will be created without making changes.
  - `dry_run: False`: Requires interactive two-step confirmation (`ConfirmView`). Creates an automatic pre-restore safety snapshot before executing live restoration with rate-limit pacing (0.5s per action).
- `/backup download` — Downloads the latest verified `.zip` archive directly.

---

## 6. Required Discord Gateway Intents & Permissions

### Privileged Gateway Intents:
Enable the following in the **Discord Developer Portal -> Bot -> Privileged Gateway Intents**:
- [x] **Server Members Intent** (`discord.Intents.members`): Required for member joins, leaves, kicks, timeouts, and role changes.
- [x] **Message Content Intent** (`discord.Intents.message_content`): Required for message edit/delete content and ghost ping detection.
- [x] **Presence Intent** (`discord.Intents.presences`): Used for member status tracking.

### Bot Role Permissions Checklist (Least-Privilege Hierarchy):
Ensure the bot's highest role is positioned **above** the roles it manages, with the following permissions:
- [x] `View Audit Log` (`view_audit_log`) — Correlate bans, kicks, timeouts, channel/role creators.
- [x] `Manage Channels` (`manage_channels`) — Create private tickets, audit channels, and disaster recovery channels.
- [x] `Manage Roles` (`manage_roles`) — Role audit logging and disaster recovery role restoration.
- [x] `Manage Messages` (`manage_messages`) — Purge messages, ghost ping notifications.
- [x] `Send Messages` & `Embed Links` — Send rich embed logs and notifications.
- [x] `Attach Files` — Export transcripts and backup archives.
- [x] `Read Message History` — Generate ticket transcripts.

---

## 7. Database Migration & Schema (Migration v48)

Applied migration **v48** to SQLite database:
1. **`logging_config` Table Additions**:
   - `channel_logs_channel_id INTEGER`
   - `role_logs_channel_id INTEGER`
   - `server_audit_channel_id INTEGER`
   - `backup_logs_channel_id INTEGER`
   - `report_logs_channel_id INTEGER`
   - `ticket_logs_channel_id INTEGER`
   - `staff_logs_channel_id INTEGER`
   - `bot_logs_channel_id INTEGER`
   - `error_logs_channel_id INTEGER`
   - `system_status_channel_id INTEGER`
2. **`server_backups` Table**:
   - `backup_id TEXT PRIMARY KEY`, `guild_id INTEGER`, `created_by INTEGER`, `backup_type TEXT`, `file_path TEXT`, `file_size INTEGER`, `checksum TEXT`, `categories_count INTEGER`, `channels_count INTEGER`, `roles_count INTEGER`, `verified INTEGER`, `created_at TEXT`, `metadata_json TEXT`.
   - Index: `idx_server_backups_guild`
3. **`support_tickets` Table**:
   - `ticket_id TEXT PRIMARY KEY`, `numeric_id INTEGER`, `guild_id INTEGER`, `channel_id INTEGER`, `creator_id INTEGER`, `category TEXT`, `status TEXT`, `title TEXT`, `claimed_by INTEGER`, `closed_by INTEGER`, `closed_at TEXT`, `transcript_path TEXT`, `created_at TEXT`, `updated_at TEXT`.
   - Indexes: `idx_support_tickets_guild`, `idx_support_tickets_creator`
4. **`system_error_logs` Table**:
   - `error_id TEXT PRIMARY KEY`, `guild_id INTEGER`, `subsystem TEXT`, `error_type TEXT`, `error_message TEXT`, `stack_trace TEXT`, `retry_count INTEGER`, `resolved INTEGER`, `created_at TEXT`.
   - Index: `idx_system_error_logs_created`

---

## 8. Verification & Test Summary

All automated test suites executed with 100% pass rate:
- `tests/test_centralized_logging.py` — 3/3 tests passed.
- `tests/test_support_tickets_system.py` — 2/2 tests passed.
- `tests/test_server_backup_restore.py` — 3/3 tests passed.
- `tests/test_health_and_errors.py` — 2/2 tests passed.
- `tests/test_database.py` — 8/8 tests passed.
- `tests/test_backup_system.py` — 7/7 tests passed.
- `tests/test_tickets.py` — 2/2 tests passed.
- **Total Suite**: 27/27 tests passed.
