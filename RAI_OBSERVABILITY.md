# 『RΛI』 Production Observability, Monitoring & Disaster Recovery

## 1. Overview & Golden Principle

The Observability, Monitoring, and Disaster Recovery subsystem delivers real-time visibility into the health and performance of 『RΛI』 without introducing single points of failure.

### Core Resilience Guarantee:
If Prometheus, Grafana, Sentry, or S3 object storage go offline:
- **RAI security engine remains 100% OPERATIONAL.**
- **No uncaught exceptions escape into event handlers.**
- **Local SQLite audit trails preserve all telemetry.**

---

## 2. Prometheus Metrics Telemetry

The metrics engine runs a standalone HTTP exporter on port `9100` (`http://localhost:9100/metrics`), configured via `PROMETHEUS_PORT`.

### Strict Low-Cardinality Enforcement Rule:
**Never label Prometheus metrics with uncontrolled identifiers** such as `user_id`, `message_id`, `channel_id`, or `incident_id`. All labels are strictly bounded to categorical enumerations to prevent Prometheus memory explosion.

### Metric Inventory:
| Metric | Type | Labels | Description |
| :--- | :--- | :--- | :--- |
| `rai_security_events_total` | Counter | `event_type`, `severity` | Total security threats processed |
| `rai_security_incidents_total`| Counter | `severity`, `status` | Total unique security incidents |
| `rai_security_incidents_active`| Gauge | None | Number of open/mitigating incidents |
| `rai_raid_detections_total` | Counter | `classification` | Server raid attacks detected |
| `rai_antinuke_events_total` | Counter | `action_type` | Unauthorized administrative actions intercepted |
| `rai_antispam_events_total` | Counter | `spam_type` | Spam events intercepted |
| `rai_mass_mention_events_total`| Counter | `severity` | Mass user mention attacks contained |
| `rai_security_actions_total` | Counter | `action`, `status` | Mitigations executed (timeout, purge, ban) |
| `rai_emergency_mode_active` | Gauge | None | Whether Emergency Protection Mode is active |
| `rai_discord_events_total` | Counter | `event_name` | Total Discord gateway events handled |
| `rai_discord_api_errors_total`| Counter | `status_code`, `error_code` | Discord HTTP API errors intercepted |
| `rai_discord_rate_limits_total`| Counter | `endpoint` | Discord HTTP 429 rate limit events hit |
| `rai_discord_event_latency_seconds` | Histogram | `event_name` | Event loop execution duration |
| `rai_sqlite_operations_total` | Counter | `operation`, `status` | SQLite operations |
| `rai_postgres_operations_total`| Counter | `operation`, `status` | PostgreSQL operations |
| `rai_redis_operations_total` | Counter | `operation`, `status` | Redis operations |
| `rai_firebase_operations_total`| Counter | `operation`, `status` | Firebase operations |
| `rai_sync_queue_size` | Gauge | `target` | Pending sync backlog in SQLite |
| `rai_sync_operations_total` | Counter | `target`, `status` | Sync worker attempts |
| `rai_sync_dead_letter_total` | Counter | `target` | Failed operations sent to DLQ |
| `rai_worker_health` | Gauge | `worker_name` | Internal worker state (1=Healthy, 0=Degraded) |
| `rai_worker_restarts_total` | Counter | `worker_name` | Self-healing automatic worker restarts |
| `rai_music_sessions` | Gauge | None | Active music voice sessions |
| `rai_ai_requests_total` | Counter | `provider`, `task`, `status`| AI threat inference requests |
| `rai_ai_latency_seconds` | Histogram | `provider` | AI response latency distribution |

---

## 3. Sentry Error Tracking with Automatic Secret Sanitization

The Sentry layer captures exceptions and background worker crashes. Before any payload leaves the server, a global event scrubber (`before_send`) strips:
- Discord Bot Tokens (`TOKEN_REGEX`)
- Database Connection Strings and Passwords (`DB_URL_REGEX`)
- External API Keys (`API_KEY_REGEX`)
- Authorization Headers (`Bearer`, `Basic`, `Token`)
- Sensitive Dictionary Keys (`token`, `password`, `secret`, `credential`, `key`)

---

## 4. Grafana Dashboards

A complete, production-ready dashboard JSON specification is generated programmatically and saved to `config/grafana_dashboard.json` (UID: `rai-production-overview`).

### Included Dashboard Panels:
1. **Platform Overview:** Active incidents, emergency mode, sync backlog, active music players, Discord API error rate.
2. **Security & Threats:** Threat detections by type, mitigation actions breakdown.
3. **Multi-Database Telemetry:** SQLite, PostgreSQL, Redis, and Firebase operational rates, sync queue depth.
4. **Workers & AI:** Self-healing restart frequencies, AI p95 latency quantiles.

---

## 5. S3-Compatible Disaster Recovery & Backups

The `backups/` subsystem provides enterprise disaster recovery for SQLite and PostgreSQL databases.

### Key Capabilities:
- **Atomic Online SQLite Backup:** Uses SQLite Online Backup API (`conn.backup`) to snapshot SQLite databases while under active concurrent WAL-mode writes without corruption.
- **Cryptographic Checksums:** Calculates SHA256 hashes of all generated snapshots.
- **S3-Compatible Cloud Upload:** Compatible with AWS S3, Cloudflare R2, MinIO, and Wasabi. Verifies `ContentLength` and `ETag` metadata after upload.
- **Tiered GFS Retention Rotation:** Automatically rotates backups (configurable hourly, daily, weekly, monthly limits) and preserves files marked with `RECOVERY_LOCK`.
- **Safe Disaster Recovery Restoration:**
  - Strict administrative confirmation required: `CONFIRM_RESTORE_<filename>`.
  - Automatically takes a pre-restore safety snapshot before altering target files.
  - Verifies SQLite integrity (`PRAGMA integrity_check`) after restore, automatically rolling back if corrupt.

---

## 6. Administrative Slash Commands

| Command | Purpose | Permissions |
| :--- | :--- | :--- |
| `/rai health` | Comprehensive system health matrix across all 4 databases, security, and workers | Administrator |
| `/rai metrics` | Prometheus scrape endpoint telemetry and tracked metrics summary | Administrator |
| `/rai database status` | Multi-database status matrix, pending sync counts, and fallback states | Administrator |
| `/rai workers` | Status of master supervisor, database sync worker, and watchdog fleets | Administrator |
| `/rai backup status` | Latest disaster recovery backup state, SHA256 checksum, and cloud key | Administrator |
| `/rai backup create` | Dispatches an on-demand atomic backup cycle | Administrator |
| `/rai backup list` | Lists local backup snapshots on disk with sizes and timestamps | Administrator |
| `/rai recovery status` | Verifies disaster recovery restoration readiness and rollback points | Administrator |
| `/rai observability status` | Prometheus, Sentry, and Grafana template availability | Administrator |
