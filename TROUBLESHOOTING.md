# 🩺 RAI — TROUBLESHOOTING & RECOVERY GUIDE

This guide details common operational issues, diagnostics, recovery procedures, and solutions for **Rai** administrators.

---

## 1. Quick Diagnostics

Always start with the built-in diagnostic commands:

- `/health`: Displays live latency, database WAL status, cog health, and memory footprint.
- `/security dashboard`: Shows real-time security posture across all defense modules.
- `/security incident <id>`: Inspects full timeline and root causes of any security alert.
- `/voiceguard status`: Checks voice engine state and backend receiver capabilities.

---

## 2. Common Issues & Solutions

### Issue A: Slash Commands Do Not Appear in Discord

**Symptoms**: Typing `/` does not show Rai's commands or new subcommands.

**Causes**:
1. Discord global command synchronization takes up to 1 hour to propagate to all servers if registered globally.
2. Bot lacks the `applications.commands` OAuth2 scope.

**Solution**:
- Ensure the bot was invited with both `bot` and `applications.commands` scopes.
- In development, configure `DEVELOPER_GUILD_ID` in `.env`. When set, commands sync instantly to that specific guild upon bot boot.
- Check startup logs for: `Synced X application commands`.

---

### Issue B: "Cannot manage role" or "Forbidden (403)" on Moderation Actions

**Symptoms**: AutoMod, verification, or `/ban` fails with a 403 Forbidden error.

**Cause**: Discord Role Hierarchy restriction.

**Solution**:
1. Open Discord **Server Settings ➔ Roles**.
2. Find the bot's highest role (named `Rai` or `The Raivora`).
3. Drag it above all member roles and above any roles it needs to assign or moderate (e.g. `Verified`, `Muted`, `Member`).
4. Ensure Rai has `Manage Roles` and `Ban Members` permissions enabled on its role.

---

### Issue C: VoiceGuard Displays "Interface Mode"

**Symptoms**: `/voiceguard status` displays `Audio Monitoring: Interface Mode (voice receiver backend unavailable)`.

**Cause**:
- Standard `discord.py` 2.x natively handles audio transmission (playback), but requires specialized native C extensions (such as `discord-ext-voice-recv`) to intercept and decode incoming user voice packets.

**Solution**:
- This is intentional graceful degradation designed so that Rai operates at 100% capacity for all other security, moderation, ticket, and automation features even when native voice-receive sinks are absent.
- Simulated testing can still be executed via `/voiceguard test`.

---

### Issue D: Database Locking / "database is locked" Errors

**Symptoms**: Log entries mentioning `sqlite3.OperationalError: database is locked`.

**Cause**: Another process or background worker holds a transaction lock.

**Solution**:
- Rai enables SQLite WAL (`Write-Ahead Logging`) mode (`PRAGMA journal_mode=WAL;`) and sets `PRAGMA busy_timeout=15000;`.
- Ensure no external GUI tools (like DB Browser for SQLite) hold an open uncommitted write transaction on `data/bot.db`.
- The self-healing database layer automatically retries queries with exponential backoff.

---

### Issue E: Gateway Disconnects / Network Jitter

**Symptoms**: `ClientConnectorDNSError` or `Attempting a reconnect in Xs`.

**Cause**: Temporary network fluctuation between host machine and Discord gateway.

**Solution**:
- Rai has built-in resilient reconnect loops that automatically resume gateway sessions (`RESUMED session <id>`) with shard tracking.
- No manual restart is required; the bot reconnects automatically once DNS resolution or network connectivity stabilizes.

---

## 3. Database Recovery Procedures

If the main database `data/bot.db` becomes corrupt due to abrupt system power loss:

1. Stop the bot process.
2. Check the `data/backups/` directory for automated backups:
   ```bash
   ls -la data/backups/
   ```
3. Copy the latest backup over `data/bot.db`:
   ```bash
   cp data/backups/bot_backup_YYYYMMDD_HHMMSS.db data/bot.db
   ```
4. Verify schema version:
   ```bash
   python scripts/validate.py
   ```
5. Restart Rai.
