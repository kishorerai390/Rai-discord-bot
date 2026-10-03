"""
Rai Luxury Midnight Web Dashboard & Keep-Alive Server.
Provides:
- Stunning dark-mode glassmorphic web dashboard on port 8080.
- Real-time telemetry: Server stats, Shield Score (100/100), Bot uptime, AutoMod status.
- Live REST API endpoints: /api/stats, /api/leaderboard, /health.
- UptimeRobot & Render keep-alive compatibility.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, Optional
from aiohttp import web

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("RaiWeb")

_start_time = time.time()


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>✦ RAI FAM — Midnight Operations Dashboard ✦</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0b10;
      --card-bg: rgba(22, 24, 38, 0.7);
      --card-border: rgba(147, 51, 234, 0.25);
      --primary: #9333ea;
      --cyan: #06b6d4;
      --pink: #ec4899;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background-color: var(--bg-dark);
      background-image: 
        radial-gradient(at 0% 0%, rgba(147, 51, 234, 0.15) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.12) 0px, transparent 50%);
      color: var(--text);
      font-family: 'Outfit', sans-serif;
      min-height: 100vh;
      padding: 2.5rem 1.5rem;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    .container {
      width: 100%;
      max-width: 1100px;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 2.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 1rem;
    }
    .brand-icon {
      width: 50px;
      height: 50px;
      background: linear-gradient(135deg, var(--primary), var(--pink));
      border-radius: 14px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.6rem;
      box-shadow: 0 0 25px rgba(236, 72, 153, 0.35);
    }
    .brand-title h1 {
      font-size: 1.7rem;
      font-weight: 800;
      letter-spacing: 0.5px;
      background: linear-gradient(to right, #ffffff, #d8b4fe, #a5f3fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .brand-title p {
      font-size: 0.85rem;
      color: var(--text-muted);
    }
    .status-badge {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: var(--success);
      padding: 0.5rem 1rem;
      border-radius: 9999px;
      font-size: 0.85rem;
      font-weight: 600;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      background: var(--success);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--success);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.95); opacity: 0.8; }
      50% { transform: scale(1.2); opacity: 1; }
      100% { transform: scale(0.95); opacity: 0.8; }
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1.5rem;
      margin-bottom: 2.5rem;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 18px;
      padding: 1.5rem;
      backdrop-filter: blur(16px);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
      transition: transform 0.2s, border-color 0.2s;
    }
    .card:hover {
      transform: translateY(-3px);
      border-color: rgba(147, 51, 234, 0.5);
    }
    .card-label {
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--text-muted);
      margin-bottom: 0.5rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .card-value {
      font-size: 1.8rem;
      font-weight: 700;
      color: #fff;
    }
    .card-sub {
      font-size: 0.8rem;
      color: var(--cyan);
      margin-top: 0.3rem;
    }
    .section-title {
      font-size: 1.25rem;
      font-weight: 700;
      margin-bottom: 1.2rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .leaderboard-table {
      width: 100%;
      border-collapse: collapse;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }
    .leaderboard-table th, .leaderboard-table td {
      padding: 1rem 1.5rem;
      text-align: left;
    }
    .leaderboard-table th {
      background: rgba(255, 255, 255, 0.03);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--text-muted);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .leaderboard-table tr:not(:last-child) td {
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    .leaderboard-table tr:hover {
      background: rgba(255, 255, 255, 0.02);
    }
    .rank-medal {
      font-size: 1.2rem;
    }
    .user-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      font-weight: 600;
    }
    .coins-pill {
      font-family: 'JetBrains Mono', monospace;
      color: #fbbf24;
      font-weight: 600;
    }
    footer {
      margin-top: 3rem;
      text-align: center;
      font-size: 0.85rem;
      color: var(--text-muted);
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">🍸</div>
        <div class="brand-title">
          <h1>RAI FAM OPERATION PORTAL</h1>
          <p>Official 24/7 Security & Server Management Telemetry</p>
        </div>
      </div>
      <div class="status-badge">
        <span class="status-dot"></span>
        <span id="uptime-badge">ONLINE • 24/7</span>
      </div>
    </header>

    <div class="grid">
      <div class="card">
        <div class="card-label">🛡️ Security Shield Score</div>
        <div class="card-value" style="color: #10b981;">100 / 100</div>
        <div class="card-sub">🟢 Optimal Baseline Active</div>
      </div>
      <div class="card">
        <div class="card-label">🚫 AutoMod Mode</div>
        <div class="card-value" style="color: #ec4899;">AUTO-TIMEOUT</div>
        <div class="card-sub">10m Mute on Misbehaviour</div>
      </div>
      <div class="card">
        <div class="card-label">⏱️ Gateway Latency</div>
        <div class="card-value" id="ping-val">-- ms</div>
        <div class="card-sub">Discord Gateway WebSockets</div>
      </div>
      <div class="card">
        <div class="card-label">⚡ Global Slash Registry</div>
        <div class="card-value" id="cmd-val">68+</div>
        <div class="card-sub">Synced Across Discord</div>
      </div>
    </div>

    <div class="section-title">
      <span>🏆</span> RAI FAM — Midnight Wealth & Hall of Fame
    </div>
    <table class="leaderboard-table">
      <thead>
        <tr>
          <th style="width: 80px;">Rank</th>
          <th>Member</th>
          <th>Level</th>
          <th>Daily Streak</th>
          <th style="text-align: right;">Wallet Balance</th>
        </tr>
      </thead>
      <tbody id="leaderboard-body">
        <tr>
          <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">Loading live telemetry from SQLite...</td>
        </tr>
      </tbody>
    </table>

    <footer>
      ✦ RAI FAM💗 ✦ • Powered by The Raivora Core 2.5 • Dual-Core AI Sentinel
    </footer>
  </div>

  <script>
    async function loadData() {
      try {
        const statsRes = await fetch('/api/stats');
        const stats = await statsRes.json();
        document.getElementById('ping-val').innerText = stats.ping + ' ms';
        document.getElementById('cmd-val').innerText = stats.commands;
        document.getElementById('uptime-badge').innerText = 'ONLINE (' + stats.uptime + ')';

        const lbRes = await fetch('/api/leaderboard');
        const lb = await lbRes.json();
        const tbody = document.getElementById('leaderboard-body');
        if (lb.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">No economy activity recorded yet. Chat in #general-chat to earn!</td></tr>';
          return;
        }
        let html = '';
        const medals = ['🥇', '🥈', '🥉'];
        lb.forEach((u, i) => {
          const medal = i < 3 ? medals[i] : '#' + (i + 1);
          html += `
            <tr>
              <td><span class="rank-medal">${medal}</span></td>
              <td><div class="user-pill">👤 ${u.name}</div></td>
              <td>Level ${u.level}</td>
              <td>🔥 ${u.streak} Days</td>
              <td style="text-align: right;"><span class="coins-pill">${u.coins.toLocaleString()} Coins</span></td>
            </tr>
          `;
        });
        tbody.innerHTML = html;
      } catch (e) {
        console.error('Failed to load dashboard telemetry:', e);
      }
    }
    loadData();
    setInterval(loadData, 15000);
  </script>
</body>
</html>
"""


class KeepAliveServer:
    def __init__(self, bot: Optional[SentinelBot] = None, port: Optional[int] = None):
        self.bot = bot
        self.port = port or int(os.environ.get("PORT", 8080))
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

    async def handle_root(self, request: web.Request) -> web.Response:
        """Render modern Midnight Web Dashboard."""
        return web.Response(text=DASHBOARD_HTML, content_type="text/html")

    async def handle_stats(self, request: web.Request) -> web.Response:
        """JSON Telemetry API."""
        uptime_sec = int(time.time() - _start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)

        ping = int(self.bot.latency * 1000) if self.bot else 0
        cmd_count = len(self.bot.tree.get_commands()) if self.bot else 68
        guild_count = len(self.bot.guilds) if self.bot else 1

        return web.json_response({
            "status": "online",
            "bot": "The Raivora#7883",
            "guild": "✦ RAI FAM💗 ✦",
            "guild_count": guild_count,
            "ping": ping,
            "commands": cmd_count,
            "uptime": f"{hours}h {minutes}m {seconds}s",
            "shield_score": 100,
            "automod_mode": "timeout",
        })

    async def handle_leaderboard(self, request: web.Request) -> web.Response:
        """JSON Economy Leaderboard API."""
        if not self.bot:
            return web.json_response([])

        guild_id = 1457382179981099090
        guild = self.bot.get_guild(guild_id)
        users = await self.bot.db.get_top_economy_users(guild_id, limit=10, order_by="coins")

        results = []
        for u in users:
            member = guild.get_member(u.user_id) if guild else None
            name = member.display_name if member else f"Member {u.user_id}"
            results.append({
                "id": u.user_id,
                "name": name,
                "coins": u.coins,
                "level": u.level,
                "streak": u.daily_streak,
            })

        return web.json_response(results)

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "bot": "The Raivora",
            "timestamp": int(time.time()),
        })

    async def start(self) -> None:
        try:
            app = web.Application()
            app.router.add_get("/", self.handle_root)
            app.router.add_get("/dashboard", self.handle_root)
            app.router.add_get("/api/stats", self.handle_stats)
            app.router.add_get("/api/leaderboard", self.handle_leaderboard)
            app.router.add_get("/health", self.handle_health)
            app.router.add_get("/healthz", self.handle_health)
            self.runner = web.AppRunner(app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, "0.0.0.0", self.port)
            await self.site.start()
            logger.info(f"Rai Midnight Web Dashboard online at http://0.0.0.0:{self.port}")
        except Exception as e:
            logger.warning(f"Could not start Web Dashboard on port {self.port}: {e}")

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            logger.info("Web Dashboard stopped.")
