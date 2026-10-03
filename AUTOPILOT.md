# 🤖 RAI — AUTONOMOUS AUTOPILOT ENGINE

The **Rai Autopilot Engine** is an always-on, autonomous platform coordinator designed to eliminate the need for administrators to manually monitor and execute routine security, containment, maintenance, and server-management operations.

---

## 1. Autopilot Decision Cycle

Rai continuously operates on an eight-stage autonomous loop:

```text
MONITOR
   ↓
DETECT
   ↓
ANALYZE
   ↓
DECIDE
   ↓
ACT
   ↓
VERIFY
   ↓
LOG
   ↓
RECOVER
```

1. **MONITOR**: Ingests continuous event streams (member joins/leaves, message bursts, mentions, invites, role/channel changes, voice activity, audit logs).
2. **DETECT**: Identifies statistical deviations, burst thresholds, and policy violations.
3. **ANALYZE**: Evaluates multi-signal correlation, server behavior baselines, and historical incident patterns.
4. **DECIDE**: Determines proportional response according to configured Safety Levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), checking role hierarchy and target immunity.
5. **ACT**: Dispatches actions through a controlled rate-limited action queue (`asyncio.Queue`). In Dry-Run mode, actions are simulated safely without making destructive Discord API calls.
6. **VERIFY**: Confirms Discord API action execution, catches permission boundary exceptions, and verifies desired state.
7. **LOG**: Records an immutable audit record in `autopilot_actions` and injects microsecond chronological events into `security_threat_timeline`.
8. **RECOVER**: Automatically tracks active incident decay, restores normal server states, and restarts failed background workers with exponential backoff.

---

## 2. Architecture & Pipeline

```text
Discord Gateway Events
          ↓
   Event Collector
          ↓
   Event Normalizer
          ↓
Security Brain / Automation Engine
          ↓
Risk & Confidence Analysis (0-100 Score)
          ↓
    Decision Engine (Safety Gatekeeper & Dry Run Check)
          ↓
   Action Queue (FIFO Priority with Debouncing & Backoff)
          ↓
   Discord Execution
          ↓
  Verification Engine
          ↓
Internal Audit Log (`autopilot_actions`) & Threat Timeline
```

---

## 3. Automation Safety Levels

Every automated action is classified by impact risk:

| Safety Level | Typical Autonomous Actions | Default Execution Mode |
| :--- | :--- | :--- |
| **LOW** | Spam message deletion, Welcome cards, Autoroles, Temp VC cleanup | Fully Automatic |
| **MEDIUM** | Repeat spammer timeout (10m), unverified account restrictions | Automatic + Staff Alert |
| **HIGH** | Channel lock, Rogue executor role revocation, Raid containment | Configured Containment + Staff Alert |
| **CRITICAL** | Server-wide Emergency Mode lockdown, safe mode failover | Containment + Administrator Priority |

---

## 4. Supervised Background Subsystems

The Autopilot Engine manages dedicated background supervisors:

1. **Action Consumer (`_action_consumer`)**: Controlled single-worker task processing queued events with rate limiting, hierarchy verification, and error handling.
2. **Ticket Supervisor (`ticket_autopilot_loop`)**: Runs every 30 minutes. Identifies inactive support tickets, sends warning reminders, auto-closes tickets past 72h inactivity, and archives transcripts.
3. **Temp Voice Supervisor (`temp_voice_autopilot_loop`)**: Runs every 45 seconds. Scans temporary voice rooms and safely deletes empty rooms older than 15 seconds. Permanent channels are strictly untouched.
4. **Adaptive Baseline Supervisor (`baseline_autopilot_loop`)**: Runs hourly. Updates exponential moving average server baselines (joins/hr, messages/min, voice users) to prevent false positives while resisting attack distortion.
5. **Health & Self-Healing Supervisor (`health_supervisor_loop`)**: Runs every 60 seconds. Monitors all internal workers. If a task crashes, restarts it automatically with backoff and records health state in `subsystem_health`.

---

## 5. Safe Mode & Emergency Mode Automation

### Automatic Safe Mode

If two or more critical background subsystems fail simultaneously:
- Rai automatically engages **Safe Mode**.
- Destructive automated actions (bans/kicks/channel locks) are immediately frozen.
- Monitoring, logging, audit records, and staff alerts remain 100% active.
- Server administrators receive an immediate diagnostic alert with failure causes.
- Safe Mode automatically disengages once subsystem health is verified.

### Automatic Emergency Mode

When the Security Brain calculates a composite risk score `>= 85` (CRITICAL):
- Autopilot engages heightened server defense posture automatically.
- Multiplies join rate and spam sensitivity.
- Non-verified new accounts are restricted from sending links or role mentions.
- Staff channels receive immediate real-time incident updates.

---

## 6. Threat Simulation Engine

Administrators can safely test the Autopilot and Security Brain without affecting real server members or channels:

```bash
/autopilot simulate threat:raid
/autopilot simulate threat:spam
/autopilot simulate threat:nuke
/autopilot simulate threat:webhook
```

In simulation mode:
- Synthetic threat telemetry is generated and evaluated.
- Risk scores, proposed actions, and threat timelines are produced.
- Zero destructive Discord API calls are executed on live server assets.

---

## 7. Slash Commands Reference

| Command | Description | Permissions |
| :--- | :--- | :--- |
| `/autopilot status` | Displays live dashboard with master status, modules, baseline, and health | Administrator |
| `/autopilot actions [limit]` | Inspects recent autonomous audit log records | Administrator |
| `/autopilot dryrun <enabled>` | Toggles Dry-Run mode (simulates actions without executing) | Administrator |
| `/autopilot safety <level>` | Sets maximum allowed autonomous safety action level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) | Administrator |
| `/autopilot simulate <threat>` | Runs a safe synthetic threat simulation | Administrator |
