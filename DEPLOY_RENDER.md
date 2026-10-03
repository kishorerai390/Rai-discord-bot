# 🌐 RAI — 24/7 CLOUD DEPLOYMENT GUIDE (RENDER + UPTIMEROBOT)

This guide walks you through deploying **Rai** on [Render](https://render.com) (free tier) and using [UptimeRobot](https://uptimerobot.com) to keep it online 24/7 without sleeping.

---

## ⚡ How It Works

1. **Render Free Web Service**: Hosts the Python Discord bot and runs our built-in `KeepAliveServer` on `0.0.0.0:$PORT`.
2. **UptimeRobot Ping**: Render free web services go to sleep after 15 minutes of inactivity. UptimeRobot sends an HTTP `GET` request every 5 minutes to your Render URL (`http` ping to `/health`), keeping Render awake 24/7!

---

## Step 1: Push Your Project to GitHub

1. Open your browser and go to [GitHub](https://github.com) ➔ Click **New Repository**.
2. Name your repository (e.g. `Rai-Discord-Bot`) and set it to **Private** (or Public).
   * Do NOT check "Add a README" or ".gitignore" (these are already configured in your project).
3. Click **Create repository**.
4. In your terminal in `f:/Bot`, run the following commands:

```bash
# 1. Stage all project files
git add .

# 2. Commit the changes
git commit -m "feat: complete Rai autonomous security bot with keep-alive"

# 3. Rename branch to main
git branch -M main

# 4. Link your GitHub repository
git remote add origin https://github.com/kishorerai390/Rai-discord-bot.git

# 5. Push code to GitHub
git push -u origin main
```

*(Note: Your `.env` and `.db` database files are safely excluded by `.gitignore` and will never be pushed to GitHub.)*

---

## Step 2: Deploy on Render

1. Go to [Render](https://render.com) and Sign In (or Sign Up with GitHub).
2. Click **New +** in the top right ➔ Select **Web Service**.
3. Select **Build and deploy from a Git repository** ➔ Click **Next**.
4. Connect your GitHub account and select your `Rai-Discord-Bot` repository.
5. Fill in the settings:
   * **Name**: `rai-discord-bot` (or any unique name)
   * **Region**: Choose the closest region (e.g. `Oregon (US West)` or `Frankfurt (EU Central)`)
   * **Branch**: `main`
   * **Runtime**: `Python 3`
   * **Build Command**: `pip install -r requirements.txt`
   * **Start Command**: `python main.py`
   * **Instance Type**: **Free** ($0/month)
6. Scroll down to **Environment Variables** and click **Add Environment Variable**:
   * Key: `DISCORD_TOKEN`
     Value: `your_discord_bot_token_here`
   * Key: `APPLICATION_ID`
     Value: `1554732669072445532`
   * Key: `BOT_NAME`
     Value: `Rai`
   * Key: `LOG_LEVEL`
     Value: `INFO`
   * Key: `COMMAND_SYNC_MODE`
     Value: `global`
7. Click **Create Web Service**!

Render will build and start the bot. In the logs, you will see:

```text
Keep-Alive Web Server started on http://0.0.0.0:10000
Rai Bot online as: The Raivora#7883
Commands synchronized globally: 43
```

Copy your Render URL at the top left of the dashboard:
`<https://rai-discord-bot-xxxx.onrender.com>`

---

## Step 3: Setup UptimeRobot (Keeps It Online 24/7)

1. Go to [UptimeRobot](https://uptimerobot.com) and create a free account (or log in).
2. Click **+ Add New Monitor** (top left).
3. Fill in the monitor settings:
   * **Monitor Type**: Select **HTTP(s)**
   * **Friendly Name**: `Rai Discord Bot`
   * **URL (or IP)**: Paste your Render URL:
     `<https://your-app-name.onrender.com>`
   * **Monitoring Interval**: `Every 5 minutes`
   * **Monitor Timeout**: `30 seconds`
4. Click **Create Monitor**.

🎉 **Done!**
UptimeRobot will now ping your bot's web server every 5 minutes. Render will recognize the traffic, prevent the server from sleeping, and keep **Rai** online 24 hours a day, 7 days a week!
