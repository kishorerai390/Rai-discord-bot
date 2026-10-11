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

### Issue F: "The Application Did Not Respond in Time" or "Interaction Failed"

**Symptoms**: Discord displays red error notices: *"The application did not respond"* or *"This interaction failed"* when clicking buttons, running slash commands, or submitting modals.

**Root Causes**:
1. **Interactions Endpoint URL Configured in Discord Developer Portal (Most Common)**:
   - If an HTTP URL is configured under **General Information ➔ Interactions Endpoint URL**, Discord will send all interactions as HTTP POST requests instead of over the Gateway WebSocket.
   - If that HTTP endpoint is unreachable, unhandled, or invalid, Discord instantly fails every command with *"Interaction failed"* or *"The application did not respond"*.
2. **Gateway Disconnection or DNS Outage**:
   - The bot host machine dropped network connection (`socket.gaierror: [Errno 11001] getaddrinfo failed` or `ClientConnectorDNSError`).
   - Discord's desktop/mobile clients still show cached slash commands, but because the bot is disconnected or reconnecting, Discord waits 3 seconds and aborts.
3. **The 3-Second Gateway Acknowledgement Deadline**:
   - Discord API strictly enforces that the bot must acknowledge an interaction (`await interaction.response.defer()` or `await interaction.response.send_message()`) within **3.0 seconds**.
   - If any command performs slow database queries, external web scraping, or AI API calls before calling `defer()`, Discord terminates the interaction.
4. **Modal Collision with Deferral (`40060: Interaction has already been acknowledged`)**:
   - Discord API forbids opening a modal (`send_modal()`) after an interaction has already been deferred or replied to.
   - If a button or slash command is prematurely deferred by a global guard, calling `send_modal()` afterwards will immediately throw a 400 Bad Request error.
5. **Duplicate Command Registration (Global vs Guild Desync)**:
   - Registering commands both globally and copying them directly to guilds creates duplicate command IDs in Discord's internal registry, causing ID lookup failures.
6. **Main Thread Blocking**:
   - Running synchronous calls (`time.sleep()`, synchronous `requests.get()`, heavy CPU loops) halts the asyncio event loop, causing heartbeats to stall and interactions to expire.

**Recommended Quick Check Steps**:
1. **Check Discord Developer Portal ➔ Ensure Interactions Endpoint URL is completely blank**:
   - Navigate to [Discord Developer Portal](https://discord.com/developers/applications).
   - Select your application ➔ **General Information**.
   - Check the **Interactions Endpoint URL** field.
   - **Ensure it is completely empty.** If any URL is present, delete it and click **Save Changes**.
2. **Check your bot terminal / logs ➔ Run `python main.py` and verify it connects without `getaddrinfo` or rate limit errors**:
   - Start the bot and verify the startup banner appears:
     ```bash
     python main.py
     ```
   - Confirm log line: `Shard ID None has connected to Gateway (Session ID: ...)`
   - Verify there are no `ClientConnectorDNSError`, `429 Too Many Requests`, or `LoginFailure` errors.
3. **If specific commands fail, check which command was typed so we can inspect that specific command's callback**:
   - Check `data/logs/sentinel.log` for the specific command name and diagnostic ID (e.g. `[RAI-XXXXXX]`).
   - Ensure long-running commands call `await interaction.response.defer(ephemeral=True)` on line 1 of the callback.
   - Ensure modal commands do NOT call `defer()` beforehand.
4. **Verify Discord Privileged Gateway Intents**:
   - In Discord Developer Portal ➔ **Bot** tab, verify **Server Members Intent** and **Message Content Intent** are toggled **ON**.

---

## 3. Server Architecture & Channel Suggestions

### 🎯 Key Structural Recommendations
1. **Restore `#bot-commands` to Community**:
   - Move `#bot-commands` out of `📦・ARCHIVE` back into `✦ COMMUNITY ✦` to prevent members from cluttering `#general-chat` with bot music, games, and economy commands.
2. **Relocate `#late-night-talks`**:
   - Move `#late-night-talks` from `✧ PODS & AFK ✧` to `✦ CHILL & HAVEN ✦` (AFK categories should remain voice-only).
3. **Consolidate Fragmented Staff Categories**:
   - Merge `✧ EXECUTIVE HQ ✧`, `✦ STAFF & SECURITY ✦`, `⚙️ RAI ADMIN ⚙️`, and `✦ PRIVATE REPORTING ✦` into two unified categories:
     - `🛡️ ═ STAFF OPERATIONS ═ 🛡️` (Staff Lounge, Member Reports, Security Alerts)
     - `⚙️ ═ RAI SYSTEM & LOGS ═ ⚙️` (Bot Config, Server Dashboard, Security Log, Honeypot)

### 🎨 Channel Naming Styles

#### Option A: Midnight Luxe (Small-Caps + Curated Emojis)
- Information: `📌・ʀᴜʟᴇs-ᴀɴᴅ-ɪɴғᴏ`, `📢・ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛs`, `✅・ᴠᴇʀɪғʏ-ʜᴇʀᴇ`, `👋・ᴡᴇʟᴄᴏᴍᴇ`, `🎭・ʀᴏʟᴇ-ᴘɪᴄᴋᴇʀ`, `🎫・sᴜᴘᴘᴏʀᴛ-ᴛɪᴄᴋᴇᴛs`
- Community: `💬・ɢᴇɴᴇʀᴀʟ-ᴄʜᴀᴛ`, `🤖・ʙᴏᴛ-ᴄᴏᴍᴍᴀɴᴅs`, `📸・ᴍᴇᴅɪᴀ-sʜᴀʀᴇ`, `💡・sᴜɢɢᴇsᴛɪᴏɴs`, `🎉・ɢɪᴠᴇᴀᴡᴀʏs`, `🏆・ʟᴇᴠᴇʟ-ᴜᴘs`
- Creators: `🎬・ᴍᴏᴠɪᴇ-ᴄʜᴀᴛ`, `✂️・ᴄʟɪᴘs-ᴀɴᴅ-ᴇᴅɪᴛs`, `🎨・ɢʀᴀᴘʜɪᴄs-ᴀɴᴅ-ʙᴀɴɴᴇʀs`, `🤝・ᴄᴏʟʟᴀʙ-ʀᴇǫᴜᴇsᴛs`
- Voice: `➕・Join to Create`, `☕・Night Owl Lounge`, `🌊・Vibe & Chill`, `⚡・24/7 Lo-Fi Radio`, `🎯・Ranked Comms I & II`, `💤・AFK Sleeper`

#### Option B: Clean Sans (Modern Minimalist)
- Information: `rules-and-info`, `announcements`, `verify-here`, `welcome`, `roles`, `support`
- Community: `general-chat`, `bot-commands`, `media`, `suggestions`, `giveaways`, `levels`
- Voice: `Join to Create`, `Lounge 01 (Chill)`, `Squad 01 (Ranked)`, `Radio 24/7`, `AFK`

---

## 4. Database Recovery Procedures

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

