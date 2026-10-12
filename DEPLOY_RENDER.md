# 🌐 RAI & NEKO SONGS — 24/7 DUAL-BOT CLOUD DEPLOYMENT GUIDE (RENDER + UPTIMEROBOT)

Deploy **The Raivora** (Security & Community Platform) and **Neko Songs / MusicMaid** (320kbps Music Engine & Web Player) together on [Render](https://render.com) (free tier), and keep both bots online 24/7 without sleeping using [UptimeRobot](https://uptimerobot.com).

---

## ⚡ Architecture Overview

1. **Dual-Bot Autonomous Ecosystem (`main.py`)**:
   - **The Raivora**: Anti-Nuke, AutoMod, Economy, Dynamic Voice Rooms, Autopilot, and Community OS.
   - **Neko Songs / MusicMaid**: 320kbps Opus Audio, YouTube/Spotify search, 10-Band EQ, Auto-DJ, persistent session memory, and 13-button UI.
2. **Built-in Master Web Platform (`web/server.py`)**:
   - Hosts the **Raivora Music Web Player** at `/music`.
   - Hosts the **Midnight Community OS Dashboard** at `/`.
   - Hosts the **Health Monitor** at `/health` and `/api/health`.
   - Binds to `0.0.0.0:$PORT` provided dynamically by Render.
3. **UptimeRobot 24/7 Keep-Alive**:
   - Render's free tier spins down idle apps after 15 minutes of zero HTTP traffic.
   - UptimeRobot sends an HTTP `GET` request every 5 minutes to `https://<your-app>.onrender.com/health`, preventing spin-down and keeping Discord Gateway voice connections running 24/7.

---

## Step 1: Push Your Latest Code to GitHub

Open your terminal in `f:/Bot` and run:

```bash
# 1. Stage all updated files
git add .

# 2. Commit the changes
git commit -m "feat: Raivora Music Web platform & 24/7 Render keep-alive ecosystem"

# 3. Ensure branch is main
git branch -M main

# 4. Push to GitHub
git push origin main
```

*(Note: Your `.env` tokens, `.lock` files, and `.db` databases are protected by `.gitignore` and are never exposed to GitHub.)*

---

## Step 2: Create Web Service on Render

1. Log in to [Render](https://render.com) (or sign in with your GitHub account).
2. Click **New +** (top right) ➔ Select **Web Service**.
3. Choose **Build and deploy from a Git repository** ➔ Click **Next**.
4. Select your repository: `kishorerai390/Rai-discord-bot`.
5. Configure the service settings:
   - **Name**: `rai-discord-bot` (or your preferred name)
   - **Region**: Choose closest region (e.g. `Oregon (US West)` or `Frankfurt (EU Central)`)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: **Free** ($0/month)

---

## Step 3: Add Environment Variables in Render

In your Render service setup (or under **Environment** in the left sidebar), add the following environment variables:

| Key | Value | Description |
|---|---|---|
| `DISCORD_TOKEN` | *Your Security Bot Token* | Bot token for **The Raivora** |
| `MUSIC_BOT_TOKEN` | *Your Music Bot Token* | Bot token for **Neko Songs / MusicMaid** |
| `NEKO_SONGS_BOT_TOKEN` | *Your Music Bot Token* | Alias for the music bot token |
| `APPLICATION_ID` | `1554732669072445532` | Discord Application ID |
| `BOT_NAME` | `Rai` | Ecosystem bot name |
| `LOG_LEVEL` | `INFO` | Console logging verbosity |
| `DATABASE_PATH` | `data/bot.db` | Primary database path |
| `MUSIC_DATABASE_PATH` | `data/music.db` | Dedicated music database path |
| `COMMAND_SYNC_MODE` | `global` | Auto-registers slash commands |
| `PYTHON_VERSION` | `3.11.9` | Python runtime version on Render |

Click **Create Web Service** (or **Save Changes**).

---

## Step 4: Verify Deployment Logs

In your Render Dashboard, click **Logs**. Within 1–2 minutes you will see:

```text
[ECOSYSTEM] Music Bot configured. Running alongside Rai Sentinel 24/7.
Starting Rai Sentinel and Neko Songs concurrently...
✦ Rai Master Platform & Keep-Alive online at http://0.0.0.0:10000 (Music: /music, Health: /health) ✦
✦ Rai Realtime Gateway online (WebSockets + SSE + Event Bus) ✦
✦ Raivora Music Web Platform online at http://0.0.0.0:10000/music ✦
🎵 Neko Songs online as MusicMaid#4596
Synchronized 45 global slash commands for Neko Songs
Rai Bot online as: The Raivora#7883
Synchronized 43 global slash commands for The Raivora
```

Copy your live Render URL at the top of your dashboard:
`https://your-app-name.onrender.com`

---

## Step 5: Keep It Online 24/7 with UptimeRobot (Free)

1. Go to [UptimeRobot](https://uptimerobot.com) and create a free account (or log in).
2. Click **+ Add New Monitor** (top left).
3. Set the monitor details:
   - **Monitor Type**: `HTTP(s)`
   - **Friendly Name**: `Raivora Dual Bot 24/7`
   - **URL (or IP)**: `https://your-app-name.onrender.com/health`
   - **Monitoring Interval**: `Every 5 minutes`
   - **Monitor Timeout**: `30 seconds`
4. Click **Create Monitor**.

🎉 **Your bots are now running 24 hours a day, 7 days a week!**
UptimeRobot pings `/health` every 5 minutes, preventing Render from sleeping and ensuring your Discord bots, music voice connections, and website remain active continuously.

---

## Step 6: Access Your Live Web Platforms

- 🎵 **Music Web Player**: `https://your-app-name.onrender.com/music`
- 🛡️ **Midnight Security Dashboard**: `https://your-app-name.onrender.com/`
- 💓 **Health & Telemetry Endpoint**: `https://your-app-name.onrender.com/health`
