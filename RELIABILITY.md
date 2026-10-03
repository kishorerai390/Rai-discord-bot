# 🛡️ Rai Reliability & Autonomous Self-Healing Architecture

This document specifies the reliability engineering, fault recovery, interaction safety, and autonomous self-healing subsystems implemented in **Rai**.

---

## 1. 🔴 Root Cause Analysis: "Application Did Not Respond" (P0 Fix)

### The Underlying Problem

Discord interactions (slash commands, button clicks, select menus, and modals) enforce a strict **3.0-second acknowledgment window**. If a bot fails to issue either an initial response or an acknowledgment (`defer()`) within 3,000 milliseconds:
1. Discord Gateway cancels the pending interaction.
2. The Discord client renders:
   > ⚠️ **The application did not respond**
3. Any subsequent response from the bot fails with Discord error code `10062: Unknown interaction`.

### Identified Root Causes in Codebase

1. **Premature Synchronous / Database Operations**: Multiple commands performed async SQLite queries, guild chunking, or permission checks *before* acknowledging the interaction. Under concurrent load or SQLite write locks, the 3-second window was breached.
2. **Event-Loop Blocking**: Synchronous file operations (e.g. `shutil.copy2` for backups and `open().write()` for ticket transcripts) blocked asyncio's single event loop.
3. **Unhandled Exceptions**: Errors raised before or during acknowledgment left the interaction dangling without any response back to Discord.

### The Fix Implemented

* **Immediate Safe Deferral**: Commands use `safe_defer(interaction)` to acknowledge within $<50\text{ ms}$.
* **`safe_response` Helper**: Unified response dispatcher that intelligently checks `interaction.response.is_done()`, handling deferred responses, follow-ups, and edits while catching `discord.NotFound` (code 10062) and `discord.InteractionResponded`.
* **Sanitized Error Masking**: `safe_error_response` masks internal exceptions and displays a clean user-safe embed with a unique diagnostic Error ID (`RAI-XXXXXX`), while logging full tracebacks internally.
* **Non-Blocking I/O**: File copies and transcript writes are offloaded to worker threads via `asyncio.to_thread()`.

---

## 2. ⚡ Interaction Reliability Manager (`utils/interaction_reliability.py`)

```text
Slash Command / Interaction
            ↓
  safe_defer(interaction)   [ACK within < 50ms]
            ↓
     Command Logic Runs
            ↓
  safe_response(interaction)
     ├─ if deferred: edit_original_response / followup.send
     ├─ if not deferred: response.send_message
     └─ if error: safe_error_response(error_id)
```

### Safety Features

* **No Stack Traces to Users**: Errors display `❌ Rai couldn't complete this request. Error ID: RAI-XXXXXX`.
* **Zero Double-Initial-Responses**: Prevents `InteractionResponded` exceptions.
* **Expired Interaction Handling**: Catches expired interactions without throwing uncaught exceptions into the event loop.

---

## 3. 🧠 Command Watchdog (`utils/command_watchdog.py`)

The Command Watchdog tracks every command execution in real-time using in-memory ring buffers:

* **Latency Classification**:
  * `< 1,000 ms`: `NORMAL`
  * `1,000 – 3,000 ms`: `SLOW`
  * `3,000 – 10,000 ms`: `VERY_SLOW`
  * `> 10,000 ms`: `CRITICAL_SLOW`
* **Stuck Command Supervisor**: Background task checks active executions every 5 seconds. If any command executes for $>15\text{ seconds}$, an alert is logged with the interaction ID and user.
* **Percentiles Calculation**: Real-time calculation of median ($p_{50}$), 95th percentile ($p_{95}$), and error rates for `/rai performance`.

---

## 4. 🚦 Global Action Queue & Rate-Limit Manager (`utils/action_queue.py`)

Instead of multiple cogs directly calling Discord moderation APIs:

```text
Anti-Spam ───┐
Anti-Raid ───┤
Autopilot ───┼──> GlobalActionQueue ──> RateLimitManager ──> Discord API
Anti-Nuke ───┤       (Priority + Dedup)
Tickets ─────┘
```

### Key Capabilities

1. **Priority Scheduling**:
   * Priority 0: `CRITICAL` (anti-nuke lockdown, emergency stop)
   * Priority 1: `HIGH` (mass raid containment)
   * Priority 2: `MEDIUM` (spam timeouts, user warnings)
   * Priority 3: `LOW` (temporary room cleanup, cache maintenance)
2. **Action Deduplication**:
   * Deduplication key: `guild_id:target_id:action_type`
   * Deduplication window: 12 seconds
   * Prevents duplicate timeouts or locks if multiple modules trigger on the same attack.
3. **Rate-Limit Backoff**:
   * Inspects `discord.RateLimited` and HTTP 429 `Retry-After` headers.
   * Employs exponential backoff with jitter and paced inter-action delays (350ms).

---

## 5. 🧠 Autonomous Self-Healing Engine (`utils/self_healing.py`)

Continuously executes the loop:

$$\text{DETECT} \longrightarrow \text{DIAGNOSE} \longrightarrow \text{CLASSIFY} \longrightarrow \text{RECOVER} \longrightarrow \text{VERIFY} \longrightarrow \text{RESUME}$$

### Error Classification Matrix

| Category | Typical Causes | Autonomous Recovery Strategy |
| :--- | :--- | :--- |
| `RATE_LIMIT` | Discord HTTP 429 | Pause consumer, parse `Retry-After`, backoff |
| `DATABASE_ERROR` | SQLite locked | Exponential backoff retry with jitter |
| `COMPONENT_FAILURE` | Worker crash | Cancel stale task, restart worker, verify loop |
| `PERMISSION_ERROR` | Discord HTTP 403 | Log permission gap, alert server staff |
| `TRANSIENT` | Timeout, socket dropped | Retry operation once after brief pause |
| `CRITICAL` | Data corruption | Stop risky actions, isolate component, enter Safe Mode |

### Safe Mode Protection

* If a component fails $\ge 5$ times consecutively, it is isolated and marked `DEGRADED`.
* If a critical engine (`database`, `gateway`, `autopilot`) fails repeatedly, Rai automatically activates **Safe Mode**:
  * Preserves all database data and configurations.
  * Disables destructive automated punishments.
  * Maintains monitoring, logging, and health alerts.
  * Prevents crash/restart loops.

---

## 6. 📡 Discord Connection Watchdog (`utils/connection_watchdog.py`)

* Passively monitors Gateway latency every 15 seconds.
* Tracks rolling average latency and reconnect events.
* Flags Gateway instability when latency exceeds 500ms without interfering with Discord.py's native socket reconnect logic.

---

## 7. 🩺 Administrative Slash Commands (`/rai`)

| Command | Permissions | Purpose |
| :--- | :---: | :--- |
| `/rai health` | Administrator | Visual health status of all subsystems (Gateway, DB, Watchdog, Autopilot, Queue, Self-Healing) |
| `/rai diagnostics` | Administrator | Detailed technical audit trail of recent recoveries and command traces with zero exposed secrets |
| `/rai latency` | Administrator | Live round-trip measurements for Gateway, SQLite read/write, and interaction acknowledgment |
| `/rai performance` | Administrator | Execution duration percentiles ($p_{50}$, $p_{95}$), slow command counts, and queue throughput |
| `/rai simulate <failure>` | Administrator | Safe non-destructive simulation (`worker`, `database`, `api`, `command`) to verify self-healing |
