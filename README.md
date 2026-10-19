# 🎵 MusicMaid — 24/7 Hi-Fi Lossless Discord Music Engine & Web Dashboard

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![discord.py 2.x](https://img.shields.io/badge/discord.py-2.x-5865F2.svg)](https://github.com/Rapptz/discord.py)
[![Next.js 16](https://img.shields.io/badge/next.js-16-black.svg)](https://nextjs.org/)
[![SQLite WAL](https://img.shields.io/badge/database-SQLite%20WAL-00F0FF.svg)](https://sqlite.org/)
[![Lossless Audio](https://img.shields.io/badge/audio-320kbps%20Opus-2ED573.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-00F0FF.svg)](LICENSE)

**MusicMaid** (by Noctyra Studio) is an enterprise-grade, 24/7 lossless Discord music streaming engine and full-stack interactive dashboard. Built with an obsessive focus on pristine 320kbps audio fidelity, zero-stutter voice playback, and intuitive web-based playback controls, MusicMaid elevates your community's listening experience to a studio-grade standard.

---

## 🎧 Core Capabilities

```text
                           🎵 MUSICMAID PLATFORM
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       │                            │                            │
 🔊 AUDIO ENGINE             🌐 MUIFY DASHBOARD          ⚡ CREATOR CONTROL
       │                            │                            │
 ┌─────┴─────┐                ┌─────┴─────┐                ┌─────┴─────┐
 ↓           ↓                ↓           ↓                ↓           ↓
320k Lossless 24/7 Voice     Live Player  Queue Manager  Telemetry   Feature Flags
Auto-DJ      DSP Equalizer   Lyrics View  Guild Settings Incidents   DB Backups
```

### 1. 🔊 Lossless Voice Streaming & DSP
* **Audiophile 320kbps Opus**: Pristine 48kHz audio pipeline with high-throughput FFmpeg stream buffers.
* **Smart Auto-DJ**: Intelligently recommends and queues matching tracks when the current playlist concludes.
* **Studio Equalizer (DSP)**: Real-time hardware-grade audio filters including Bass Boost, Nightcore, 8D Spatial Audio, Vaporwave, and Treble Clarity.
* **Persistent Session Recovery**: Voice state and song position are tracked continuously in SQLite WAL mode. On restart, tracks resume at their exact timestamp.

### 2. 🎛️ Muify Web Dashboard (`/dashboard`)
* **Responsive Web Player**: Sleek glassmorphic dark theme featuring real-time playback progress, play/pause/skip controls, seek slider, and volume management.
* **Interactive Music Search**: Search YouTube, Spotify, and direct audio streams with instant track previews and one-click queue addition.
* **Dynamic Queue & History**: Drag-and-drop playlist reordering, queue clearing, and playback history.
* **Lyrics Viewer**: Synchronized scrolling lyrics for currently playing songs.
* **Guild Switcher & Settings**: Server administrators can configure custom prefixes, default playback volume, and 24/7 voice channel assignments.

### 3. 🛡️ Creator Control Center (`/owner`)
* **Infini-Dash Architecture**: Dedicated control room strictly restricted to authorized bot creators and operators.
* **Live System Telemetry**: Real-time monitoring of CPU, RAM, WebSocket latency, active voice streams, and cache hit rates.
* **Correlated Incident Center**: Structured operational logs with unique correlation IDs, timestamps, and manual acknowledgement tracking.
* **Dynamic Feature Flags**: Toggle features (Web Audio Player, Auto-DJ, DSP Filters, Payment Checkouts) on the fly without restarting services.
* **Entitlement Management**: Search users by Discord ID to view, grant, or revoke promotional and lifetime Premium passes.
* **SQLite Snapshot Backups**: One-click database backup and rotation directly into `data/backups/`.

### 4. 💎 Premium & Tiered Entitlements
* **Authoritative Role Resolution**: Automatic recognition of bot owner IDs with lifetime unlocked access to all premium features.
* **Guild Volume Expansion**: Unlocks audio volumes up to 200% with software limiter protection.
* **24/7 Channel Presence**: Keeps the bot connected in voice channels indefinitely, even when the queue is idle.
* **Priority Queue & Audio Processing**: Instantaneous track caching and elevated bitrate allocations.

---

## ⌨️ Discord Slash Commands

| Command | Description |
| :--- | :--- |
| `/play <query>` | Play a track from YouTube, Spotify, or audio URL |
| `/pause` / `/resume` | Pause or resume current playback |
| `/skip` | Skip the current track |
| `/queue` | View the upcoming playlist and pagination |
| `/nowplaying` | Display detailed embed with playback progress and bitrate |
| `/volume <1-200>` | Adjust player volume (Volumes >100% require Premium) |
| `/seek <timestamp>` | Seek to a specific timestamp in the track |
| `/247` | Toggle 24/7 voice channel stay mode (Premium) |
| `/loop <off|track|queue>` | Set repeat mode for track or entire queue |
| `/shuffle` | Randomize upcoming playlist tracks |
| `/clear` | Clear upcoming tracks from the queue |
| `/setup` | Quick server audio channel setup wizard |

---

## 📁 Repository Structure

```text
f:/Bot/
├── music_main.py               # Top-level bot entry point
├── config.py                   # Master environment & bot configuration
├── requirements.txt            # Python dependencies
│
├── music_bot/                  # Core Discord Music Bot Engine
│   ├── main.py                 # Bot lifecycle & startup verification
│   ├── bot.py                  # Discord Gateway client & interaction interceptor
│   ├── config.py               # Music bot constants & environment loader
│   ├── commands/               # Slash & prefix command suites
│   │   └── music_cog.py        # Master Music cog (playback, queue, DSP, setup)
│   ├── database/               # Dedicated Music SQLite WAL storage
│   ├── services/               # Audio diagnostics, session & recovery services
│   └── theme.py                # Visual embeds & styling tokens
│
├── web/                        # Web Dashboard & Control Center Backend
│   ├── server.py               # Web application server (AIOHTTP / Starlette)
│   ├── ui.py                   # Muify dashboard & Infini-Dash HTML/CSS views
│   ├── auth.py                 # Discord OAuth2 & authoritative entitlement engine
│   ├── music_api.py            # REST endpoints for search, queue, & player controls
│   └── owner_api.py            # Creator Control Room telemetry & management API
│
├── src/                        # Full-Stack Next.js 16 Web Dashboard
│   ├── app/                    # App Router pages (/dashboard, /premium, /terms)
│   ├── components/             # Glassmorphic React UI components
│   └── lib/                    # Shared SQLite database adapters & OAuth handlers
│
└── tests/                      # Automated Verification Test Suite
    ├── test_audit_and_repair.py     # SPA routing, search, & player test suite
    └── test_master_build_suite.py   # Creator API, auth, & guild settings test suite
```

---

## ⚡ Quick Start & Deployment

For an always-on VM deployment option, see [Oracle Cloud setup](./deploy/oracle-cloud/README.md). Oracle's Always Free compute is subject to capacity and idle-reclamation limits; it does not guarantee 24/7 production uptime.

### 1. Prerequisites
* Python 3.11+
* Node.js 18+ (for Next.js web application)
* FFmpeg (pre-bundled with `static-ffmpeg` or installed system-wide)

### 2. Environment Setup
Create a `.env` file from the provided template:

```env
# Discord Bot Credentials
MUSIC_BOT_TOKEN=your_discord_bot_token_here
BOT_OWNER_ID=your_discord_user_id

# Web Platform & OAuth2
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret
SESSION_SECRET=a_random_32_byte_secret_key
NEXT_PUBLIC_BASE_URL=https://rai-discord-bot.onrender.com

# Optional Payment Gateway
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
```

### 3. Running Locally

**Terminal 1 — Python Web Server & Bot:**
```bash
# Setup virtual environment
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run automated test suites (26 passing tests)
python -m unittest tests/test_audit_and_repair.py tests/test_master_build_suite.py -v

# Start the music bot
python music_main.py
```

**Terminal 2 — Next.js Web Dashboard:**
```bash
# Install dependencies & run development server
npm install
npm run dev
```

---

## 🧪 Verification & Test Coverage

The platform includes full automated test coverage validating SPA routing, OAuth2 security boundaries, player action contracts, guild settings permission gates, and creator control room authorization:

```bash
.venv\Scripts\python.exe -m unittest tests/test_audit_and_repair.py tests/test_master_build_suite.py -v
```

```text
Ran 26 tests in 13.6s
OK
```

---

## 📄 License & Credits

Licensed under the [MIT License](LICENSE).  
Crafted with passion by **Kishore** and the **Noctyra Studio** team for audiophiles and Discord communities everywhere.
