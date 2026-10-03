# 『RΛI』 Multi-Database Production Architecture

## 1. Executive Summary & Golden Principle

『RΛI』 implements an ultra-resilient, enterprise-grade **four-database architecture** designed to guarantee continuous operational security under arbitrary cloud outages, network partitions, or infrastructure degradation.

```text
                     『RΛI』
                        │
                ┌───────▼───────┐
                │   SECURITY    │
                │  CONTAINMENT  │
                └───────┬───────┘
                        │
                ┌───────▼───────┐
                │  INCIDENT MGR │
                └───────┬───────┘
                        │
                  ┌─────▼─────┐
                  │  SQLITE   │ (Local Authoritative Survival)
                  └─────┬─────┘
                        │
               PRIORITY SYNC QUEUE
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
     POSTGRESQL       REDIS        FIREBASE
     (Permanent      (Fast       (Realtime
      Storage)       State)      Dashboard)
```

### The Cardinal Rule:
> **SECURITY > STABILITY > RECOVERY > PERFORMANCE > MODERATION > MUSIC > NON-CRITICAL FEATURES**

Under NO circumstance will the security engine block or wait for cloud services (PostgreSQL, Firebase, Redis, or external AI) before executing urgent server protection actions.

```text
CORRECT FLOW:
DETECT ➔ PROTECT ➔ RECORD LOCALLY (SQLite) ➔ QUEUE SYNC ➔ CLOUD SYNC

NEVER:
DETECT ➔ WAIT FOR CLOUD ➔ WAIT FOR AI ➔ PROTECT
```

---

## 2. Database Responsibilities & Source of Truth

| Engine | Storage Role | Source of Truth Scope | Failure Behavior & Recovery |
| :--- | :--- | :--- | :--- |
| **SQLite** | Local survival database (WAL mode) | Security incidents, active containment state, pending cloud queues, local config cache | Authoritative local runtime. If network drops, security continues locally without interruption. |
| **PostgreSQL** | Permanent production storage (asyncpg pool) | Long-term historical records, guild audit trails, analytics, threat timeline | Non-fatal. Operations queue into `pending_sync_operations` in SQLite. Automatically re-drained upon reconnect. |
| **Redis** | High-speed temporary counters & locks | Rate limits, sliding windows, mention frequency, distributed locks | Circuit breaker triggers in-memory fallback (`_local_buckets` and `asyncio.Lock`). Zero crashes. |
| **Firebase** | Cloud realtime sync & web dashboard | Live dashboard metrics, incident summaries, owner notifications | Non-fatal. Enqueued in SQLite sync queue. Re-drained asynchronously without blocking gateway. |

---

## 3. SQLite Synchronization Queue & Priority Tiers

All cloud writes pass through SQLite table `pending_sync_operations` before being drained asynchronously:

### Schema:
```sql
CREATE TABLE IF NOT EXISTS pending_sync_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT UNIQUE NOT NULL,
    guild_id INTEGER NOT NULL,
    incident_id TEXT,
    target TEXT NOT NULL,           -- 'POSTGRESQL', 'FIREBASE', 'SQLITE'
    operation_type TEXT NOT NULL,   -- 'save_incident', 'save_security_event', etc.
    payload TEXT NOT NULL,          -- JSON payload
    priority TEXT NOT NULL,         -- Priority enum
    created_at TEXT NOT NULL,
    attempt_count INTEGER DEFAULT 0,
    last_attempt TEXT,
    next_attempt TEXT,
    status TEXT NOT NULL,           -- 'PENDING', 'PROCESSING', 'SYNCED', 'RETRYING', 'DEAD_LETTER'
    error_code TEXT
);
```

### Strict Priority Order:
1. `CRITICAL_SECURITY` (Emergency lockdowns, mass bans, raid mitigations)
2. `SECURITY` (Standard security events)
3. `INCIDENT` (Security incident lifecycle tracking)
4. `MODERATION` (Kicks, warns, timeouts)
5. `SYSTEM` (Worker heartbeats, supervisor logs)
6. `MUSIC` (Player states, queue backups)
7. `ANALYTICS` (Activity aggregations)
8. `NON_CRITICAL` (Telemetry, routine metrics)

---

## 4. Idempotency & Retry Mechanism

- **Deterministic Idempotency Key:** `SHA256(f"{target}:{operation_type}:{entity_id}")[:24]`. Duplicate writes are safely ignored by SQLite unique constraints, preventing duplicate cloud records.
- **Exponential Backoff with Jitter:**
  - Attempt 1: 1.0s + jitter (0.1–1.0s)
  - Attempt 2: 2.0s + jitter
  - Attempt 3: 5.0s + jitter
  - Attempt 4: 10.0s + jitter
  - Attempt 5: 30.0s + jitter
  - Exceeded: Automatically routed to `DEAD_LETTER` queue for administrator inspection.

---

## 5. Circuit Breaker Isolation

Each external database maintains an independent circuit breaker:
- `PostgresConnectionPool`: Opens circuit after 3 consecutive connection timeouts. Reverts to local SQLite queue.
- `RedisConnectionManager`: Opens circuit after 3 Redis errors. Instantly flips `is_fallback_active = True` and activates memory sliding windows.
- `FirebaseConnectionManager`: Handles credential absence and network timeouts gracefully without raising uncaught exceptions.

---

## 6. Administrative Status & Verification

Administrators can inspect live database health and sync backlog using:

```text
/rai database status
```

**Diagnostic Embed Matrix:**
```text
『RΛI』 • DATABASE STATUS

SQLite:
🟢 ONLINE

PostgreSQL:
🟢 ONLINE

Redis:
🟢 ONLINE

Firebase:
🟢 ONLINE

Sync Queue:
🟢 HEALTHY

Pending PostgreSQL:
0

Pending Firebase:
0

Redis Fallback:
OFF

Last Health Check:
Just now
```
