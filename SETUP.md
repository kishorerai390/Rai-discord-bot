# ⚙️ RAI — SETUP & INSTALLATION MANUAL

This manual walks through deploying, configuring, and maintaining **Rai** on Linux, Windows, or Docker.

---

## 1. Prerequisites

- **Python**: Version **3.11** or **3.12** (`python --version`)
- **FFmpeg**: Required for voice playback in music commands.
  - Windows: `winget install Gyan.FFmpeg` or extract from gyan.dev and add to PATH.
  - Ubuntu/Debian: `sudo apt update && sudo apt install -y ffmpeg`
  - macOS: `brew install ffmpeg`
- **Git**: For version tracking.
- **SQLite3**: Included with standard Python builds (with WAL support).

---

## 2. Discord Developer Portal Setup

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create or select your Application (**Rai** / The Raivora, Client ID: `1554732669072445532`).
3. Under **Bot**:
   - Reset and copy your **Token**.
   - Enable **Privileged Gateway Intents**:
     - ✅ **Server Members Intent** (Mandatory for welcome, verification, autorole, and anti-raid member joins)
     - ✅ **Message Content Intent** (Mandatory for spam detection, link filters, and mention protection)
4. Under **OAuth2 ➔ URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Administrator` (or `Manage Roles`, `Manage Channels`, `Kick Members`, `Ban Members`, `Moderate Members`, `Send Messages`, `Embed Links`, `Attach Files`, `Connect`, `Speak`, `Move Members`)
   - Invite the bot to your designated Discord server.
5. **Crucial Role Hierarchy Rule**:
   - In Discord **Server Settings ➔ Roles**, drag Rai's role to the **top** of the list (above all member, muted, and verified roles).
   - Discord's permission model strictly forbids bots from managing members or assigning roles higher than their own highest role.

---

## 3. Environment Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and fill in the required variables:

```ini
# Discord Application Secrets
DISCORD_TOKEN=your_bot_token_here
APPLICATION_ID=1554732669072445532

# Bot Identity
BOT_NAME=Rai
DEFAULT_PREFIX=!
EMBED_COLOR=0x00F0FF

# Optional Developer / Owner Settings
DEVELOPER_GUILD_ID=your_primary_test_guild_id
OWNER_IDS=your_discord_user_id

# Database Settings
DATABASE_PATH=data/bot.db
BACKUP_DIR=data/backups

# Logging Level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

---

## 4. Virtual Environment & Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Database Initialization & Migrations

Run the database migration runner to bring your database schema to the latest version (Version 4):

```bash
python scripts/migrate.py
```

To verify database integrity and model schemas:

```bash
python scripts/validate.py
```

---

## 6. Running Tests

Execute the automated test suite to ensure all security modules, voting logic, and database operations pass:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 7. Launching the Bot

To start Rai:

```bash
python main.py
```

For 24/7 background operation on Linux:

```bash
# systemd service example: /etc/systemd/system/rai.service
[Unit]
Description=Rai Discord Security Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/Rai
ExecStart=/opt/Rai/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rai
```
