"""
Rem Official Web Platform & Luxury Landing Page.
Provides an anime-inspired, high-conversion, obsidian and neon lavender interface for Discord users.
"""

LANDING_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rem — Your Anime Music Companion | Rai Discord Bot</title>
  <meta name="description" content="Rem is an adorable, friendly anime-inspired AI DJ and music companion for Discord with Lavalink v4 audio streaming, custom playlists, equalizer effects, and zero-lag 24/7 voice playback.">
  <meta property="og:title" content="Rem 🎧💜 — Your Anime Music Companion">
  <meta property="og:description" content="Crystal-clear audio, 24/7 low-latency playback, custom playlists, and multi-source streaming with Rem, your anime music companion.">
  <meta property="og:image" content="/public/musicmaid_avatar.jpg">
  <meta property="theme-color" content="#8a2be2">
  <link rel="icon" type="image/png" href="/public/icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0914;
      --bg-card: rgba(22, 19, 42, 0.7);
      --bg-card-hover: rgba(33, 29, 63, 0.85);
      --border-glow: rgba(168, 85, 247, 0.25);
      --border-bright: rgba(192, 132, 252, 0.6);
      --accent-purple: #9333ea;
      --accent-violet: #a855f7;
      --accent-neon: #c084fc;
      --accent-cyan: #06b6d4;
      --accent-pink: #ec4899;
      --text-white: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --radius: 16px;
      --shadow-neon: 0 0 35px rgba(168, 85, 247, 0.28);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: 'Outfit', sans-serif;
      scroll-behavior: smooth;
    }

    body {
      background: var(--bg-dark);
      color: var(--text-white);
      min-height: 100vh;
      overflow-x: hidden;
      line-height: 1.6;
      background-image: 
        radial-gradient(circle at 15% 15%, rgba(147, 51, 234, 0.15) 0%, transparent 40%),
        radial-gradient(circle at 85% 35%, rgba(236, 72, 153, 0.12) 0%, transparent 45%),
        radial-gradient(circle at 50% 85%, rgba(6, 182, 212, 0.1) 0%, transparent 50%);
      background-attachment: fixed;
    }

    /* Top Navigation */
    nav {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 76px;
      background: rgba(10, 9, 20, 0.82);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border-glow);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 8%;
      z-index: 1000;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      text-decoration: none;
    }

    .brand-img {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      border: 2px solid var(--accent-neon);
      box-shadow: 0 0 15px rgba(192, 132, 252, 0.4);
      object-fit: cover;
    }

    .brand-name {
      font-size: 1.45rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #fff 20%, var(--accent-neon) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .nav-links {
      display: flex;
      gap: 28px;
      align-items: center;
    }

    .nav-links a {
      color: var(--text-muted);
      text-decoration: none;
      font-weight: 500;
      font-size: 0.95rem;
      transition: all 0.25s ease;
    }

    .nav-links a:hover {
      color: var(--accent-neon);
      text-shadow: 0 0 12px rgba(192, 132, 252, 0.5);
    }

    .btn {
      padding: 11px 22px;
      border-radius: 12px;
      font-weight: 700;
      font-size: 0.95rem;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 9px;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      border: none;
    }

    .btn-primary {
      background: linear-gradient(135deg, #9333ea, #c084fc);
      color: #fff;
      box-shadow: 0 6px 20px rgba(147, 51, 234, 0.4);
    }

    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 10px 28px rgba(192, 132, 252, 0.55);
      background: linear-gradient(135deg, #a855f7, #d8b4fe);
    }

    .btn-secondary {
      background: rgba(255, 255, 255, 0.05);
      color: var(--text-white);
      border: 1px solid var(--border-glow);
    }

    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: var(--accent-neon);
      transform: translateY(-2px);
    }

    /* Hero Section */
    .hero {
      padding: 160px 8% 80px;
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 60px;
      align-items: center;
      max-width: 1350px;
      margin: 0 auto;
    }

    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      border-radius: 20px;
      background: rgba(147, 51, 234, 0.15);
      border: 1px solid rgba(192, 132, 252, 0.35);
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--accent-neon);
      margin-bottom: 24px;
      backdrop-filter: blur(8px);
    }

    .pulse-dot {
      width: 8px;
      height: 8px;
      background: #22c55e;
      border-radius: 50%;
      box-shadow: 0 0 10px #22c55e;
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0% { transform: scale(0.95); opacity: 0.7; }
      50% { transform: scale(1.2); opacity: 1; }
      100% { transform: scale(0.95); opacity: 0.7; }
    }

    .hero-title {
      font-size: 3.8rem;
      font-weight: 900;
      line-height: 1.1;
      letter-spacing: -1.5px;
      margin-bottom: 22px;
    }

    .gradient-text {
      background: linear-gradient(135deg, #c084fc 10%, #06b6d4 90%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .hero-sub {
      font-size: 1.22rem;
      color: var(--text-muted);
      margin-bottom: 36px;
      max-width: 540px;
    }

    .hero-cta {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 40px;
    }

    .hero-stats {
      display: flex;
      gap: 36px;
      padding-top: 24px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
    }

    .stat-num {
      font-size: 1.6rem;
      font-weight: 800;
      color: #fff;
    }

    .stat-label {
      font-size: 0.85rem;
      color: var(--text-dim);
      font-weight: 500;
    }

    /* Music Player Card Showcase */
    .player-showcase {
      position: relative;
    }

    .player-card {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: 24px;
      padding: 30px;
      box-shadow: var(--shadow-neon);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      position: relative;
      overflow: hidden;
      transition: transform 0.3s ease;
    }

    .player-card:hover {
      transform: translateY(-4px);
      border-color: var(--border-bright);
    }

    .player-header {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 24px;
    }

    .player-thumb {
      width: 72px;
      height: 72px;
      border-radius: 14px;
      object-fit: cover;
      box-shadow: 0 6px 18px rgba(0, 0, 0, 0.5);
    }

    .player-info h3 {
      font-size: 1.25rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 4px;
    }

    .player-info p {
      font-size: 0.9rem;
      color: var(--accent-neon);
      font-weight: 500;
    }

    /* Waveform Animation */
    .waveform {
      display: flex;
      align-items: center;
      gap: 4px;
      height: 38px;
      margin: 18px 0;
    }

    .waveform-bar {
      flex: 1;
      background: linear-gradient(180deg, var(--accent-neon), var(--accent-purple));
      border-radius: 3px;
      height: 20%;
      animation: wave 1.2s ease-in-out infinite alternate;
    }

    .waveform-bar:nth-child(2) { animation-delay: 0.15s; }
    .waveform-bar:nth-child(3) { animation-delay: 0.3s; }
    .waveform-bar:nth-child(4) { animation-delay: 0.45s; }
    .waveform-bar:nth-child(5) { animation-delay: 0.2s; }
    .waveform-bar:nth-child(6) { animation-delay: 0.5s; }
    .waveform-bar:nth-child(7) { animation-delay: 0.1s; }
    .waveform-bar:nth-child(8) { animation-delay: 0.35s; }
    .waveform-bar:nth-child(9) { animation-delay: 0.25s; }
    .waveform-bar:nth-child(10) { animation-delay: 0.4s; }

    @keyframes wave {
      0% { height: 15%; }
      100% { height: 95%; }
    }

    .progress-wrap {
      margin-bottom: 20px;
    }

    .progress-bar {
      height: 6px;
      background: rgba(255, 255, 255, 0.12);
      border-radius: 6px;
      overflow: hidden;
      margin-bottom: 6px;
    }

    .progress-fill {
      width: 48%;
      height: 100%;
      background: linear-gradient(90deg, var(--accent-purple), var(--accent-cyan));
      border-radius: 6px;
    }

    .time-stamps {
      display: flex;
      justify-content: space-between;
      font-size: 0.78rem;
      color: var(--text-dim);
      font-family: 'JetBrains Mono', monospace;
    }

    .controls-row {
      display: flex;
      justify-content: center;
      gap: 16px;
      align-items: center;
      padding-top: 10px;
    }

    .control-btn {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 1.1rem;
      transition: all 0.2s ease;
    }

    .control-btn:hover {
      background: rgba(168, 85, 247, 0.3);
      border-color: var(--accent-neon);
      transform: scale(1.08);
    }

    .control-btn.play-btn {
      width: 56px;
      height: 56px;
      background: linear-gradient(135deg, var(--accent-purple), var(--accent-neon));
      font-size: 1.35rem;
      box-shadow: 0 0 20px rgba(168, 85, 247, 0.5);
    }

    /* Features Grid */
    .features {
      padding: 100px 8%;
      max-width: 1350px;
      margin: 0 auto;
    }

    .section-head {
      text-align: center;
      margin-bottom: 60px;
    }

    .section-tag {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--accent-neon);
      text-transform: uppercase;
      letter-spacing: 1.5px;
      margin-bottom: 12px;
      display: block;
    }

    .section-title {
      font-size: 2.6rem;
      font-weight: 800;
      letter-spacing: -0.5px;
    }

    .features-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 28px;
    }

    .feature-card {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: var(--radius);
      padding: 32px;
      transition: all 0.3s ease;
    }

    .feature-card:hover {
      background: var(--bg-card-hover);
      border-color: var(--border-bright);
      transform: translateY(-6px);
      box-shadow: var(--shadow-neon);
    }

    .feature-icon {
      font-size: 2.2rem;
      margin-bottom: 18px;
      display: inline-block;
    }

    .feature-card h3 {
      font-size: 1.3rem;
      font-weight: 700;
      margin-bottom: 10px;
    }

    .feature-card p {
      color: var(--text-muted);
      font-size: 0.95rem;
      line-height: 1.55;
    }

    /* Commands Section */
    .commands-sec {
      padding: 80px 8% 120px;
      max-width: 1200px;
      margin: 0 auto;
    }

    .cmd-table-wrap {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: 20px;
      overflow: hidden;
      backdrop-filter: blur(16px);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }

    th {
      background: rgba(255, 255, 255, 0.04);
      padding: 18px 24px;
      font-size: 0.88rem;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--text-dim);
      border-bottom: 1px solid var(--border-glow);
    }

    td {
      padding: 16px 24px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 0.95rem;
    }

    tr:last-child td { border-bottom: none; }

    tr:hover td {
      background: rgba(168, 85, 247, 0.05);
    }

    .cmd-badge {
      font-family: 'JetBrains Mono', monospace;
      background: rgba(192, 132, 252, 0.12);
      border: 1px solid rgba(192, 132, 252, 0.25);
      color: var(--accent-neon);
      padding: 4px 10px;
      border-radius: 8px;
      font-size: 0.88rem;
      font-weight: 600;
    }

    /* Footer */
    footer {
      border-top: 1px solid var(--border-glow);
      background: rgba(10, 9, 20, 0.95);
      padding: 60px 8% 40px;
      text-align: center;
    }

    .footer-links {
      display: flex;
      justify-content: center;
      gap: 32px;
      margin-bottom: 24px;
      flex-wrap: wrap;
    }

    .footer-links a {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.92rem;
      transition: color 0.2s;
    }

    .footer-links a:hover { color: var(--accent-neon); }

    .copyright {
      color: var(--text-dim);
      font-size: 0.85rem;
    }

    @media (max-width: 900px) {
      .hero {
        grid-template-columns: 1fr;
        padding-top: 120px;
        text-align: center;
      }
      .hero-sub { margin: 0 auto 32px; }
      .hero-cta { justify-content: center; }
      .hero-stats { justify-content: center; }
      .nav-links { display: none; }
      .hero-title { font-size: 2.8rem; }
    }
  </style>
</head>
<body>

  <!-- Navigation -->
  <nav>
    <a href="/" class="brand">
      <img src="/public/musicmaid_avatar.jpg" alt="Rem Logo" class="brand-img" onerror="this.src='/public/icon.png'">
      <span class="brand-name">Rem 🎧💜</span>
    </a>
    <div class="nav-links">
      <a href="#features">Features</a>
      <a href="#commands">Commands</a>
      <a href="/dashboard">Dashboard</a>
      <a href="/login" style="color: var(--accent-neon); font-weight: 700;">Login</a>
      <a href="/api/logs" target="_blank">Live Logs</a>
      <a href="https://discord.gg/wRCgB7vBQv" target="_blank">Support</a>
    </div>
    <a href="https://discord.com/oauth2/authorize?client_id=1556676516274905218&permissions=8&integration_type=0&scope=bot+applications.commands" target="_blank" class="btn btn-primary">
      <span>Invite to Server</span>
      <span>🚀</span>
    </a>
  </nav>

  <!-- Hero Section -->
  <section class="hero">
    <div>
      <div class="hero-badge">
        <span class="pulse-dot"></span>
        <span>🌸 Cute & Powerful Anime Audio Companion Active</span>
      </div>
      <h1 class="hero-title">Elevate Your Discord with <span class="gradient-text">Rem</span> 🎧💜</h1>
      <p class="hero-sub">Your adorable, friendly anime-inspired AI DJ and music companion. Designed for crystal audio clarity, interactive controllers, multi-source streaming, and 24/7 music magic.</p>
      
      <div class="hero-cta">
        <a href="https://discord.com/oauth2/authorize?client_id=1556676516274905218&permissions=8&integration_type=0&scope=bot+applications.commands" target="_blank" class="btn btn-primary">
          <span>Add Rem Now</span>
          <span>⚡</span>
        </a>
        <a href="https://discord.gg/wRCgB7vBQv" target="_blank" class="btn btn-secondary">
          <span>Join Community Server</span>
          <span>💬</span>
        </a>
      </div>

      <div class="hero-stats">
        <div>
          <div class="stat-num">44+</div>
          <div class="stat-label">Slash Commands</div>
        </div>
        <div>
          <div class="stat-num">v4.2</div>
          <div class="stat-label">Lavalink Engine</div>
        </div>
        <div>
          <div class="stat-num">99.9%</div>
          <div class="stat-label">Voice Uptime</div>
        </div>
      </div>
    </div>

    <!-- Live Interactive Player Showcase -->
    <div class="player-showcase">
      <div class="player-card">
        <div class="player-header">
          <img src="/public/musicmaid_banner.jpg" alt="Track Art" class="player-thumb" onerror="this.src='/public/musicmaid_avatar.jpg'">
          <div class="player-info">
            <h3>Faded (Live Vocal Edition)</h3>
            <p>Alan Walker • Playing in #music-lounge</p>
          </div>
        </div>

        <div class="waveform">
          <div class="waveform-bar"></div>
          <div class="waveform-bar"></div>
          <div class="waveform-bar"></div>
          <div class="waveform-bar"></div>
          <div class="waveform-bar"></div>
          <div class="waveform-bar"></div>
          <div class="waveform-bar"></div>
          <div class="waveform-bar"></div>
          <div class="waveform-bar"></div>
          <div class="waveform-bar"></div>
        </div>

        <div class="progress-wrap">
          <div class="progress-bar">
            <div class="progress-fill"></div>
          </div>
          <div class="time-stamps">
            <span>01:42</span>
            <span>03:32</span>
          </div>
        </div>

        <div class="controls-row">
          <button class="control-btn" title="Previous Track">⏮️</button>
          <button class="control-btn play-btn" title="Play / Pause">⏸️</button>
          <button class="control-btn" title="Next Track">⏭️</button>
          <button class="control-btn" title="Repeat Track">🔁</button>
          <button class="control-btn" title="Shuffle Queue">🔀</button>
        </div>
      </div>
    </div>
  </section>

  <!-- Features Grid -->
  <section id="features" class="features">
    <div class="section-head">
      <span class="section-tag">Superior Technology</span>
      <h2 class="section-title">Engineered for Audiophiles</h2>
    </div>

    <div class="features-grid">
      <div class="feature-card">
        <span class="feature-icon">⚡</span>
        <h3>Zero Latency Lavalink v4</h3>
        <p>Built with robust audio nodes and concurrent failover, guaranteeing jitter-free sound across all voice regions worldwide.</p>
      </div>

      <div class="feature-card">
        <span class="feature-icon">🌐</span>
        <h3>Multi-Platform Streaming</h3>
        <p>Seamlessly queue songs, albums, and playlists from Spotify, YouTube, SoundCloud, Apple Music, and direct web streams.</p>
      </div>

      <div class="feature-card">
        <span class="feature-icon">🎛️</span>
        <h3>Rich Audio DSP & Filters</h3>
        <p>Enhance your listening with real-time BassBoost, Nightcore, 8D Surround, Vaporwave, and custom speed/pitch tuning.</p>
      </div>

      <div class="feature-card">
        <span class="feature-icon">💾</span>
        <h3>Cloud Playlists</h3>
        <p>Save personal or guild-wide playlists into MongoDB. Share them with friends and load them into any server with one command.</p>
      </div>

      <div class="feature-card">
        <span class="feature-icon">💬</span>
        <h3>Auto-Request Channels</h3>
        <p>Set up <code>#rem-song-requests</code> with <code>/settings setupchannel</code>. Members can post song names directly without prefix commands.</p>
      </div>

      <div class="feature-card">
        <span class="feature-icon">🎤</span>
        <h3>Synchronized Lyrics</h3>
        <p>Sing along with live, timestamped synchronized lyrics powered by LRCLIB and Genius directly within your Discord chat.</p>
      </div>
    </div>
  </section>

  <!-- Commands Table -->
  <section id="commands" class="commands-sec">
    <div class="section-head">
      <span class="section-tag">Quick Reference</span>
      <h2 class="section-title">Popular Slash Commands</h2>
    </div>

    <div class="cmd-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Command</th>
            <th>Description</th>
            <th>Permission</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><span class="cmd-badge">/play &lt;query&gt;</span></td>
            <td>Play any song, artist, playlist, or URL in your voice channel.</td>
            <td>Everyone</td>
          </tr>
          <tr>
            <td><span class="cmd-badge">/skip</span></td>
            <td>Vote or skip to the next track in queue.</td>
            <td>Everyone / DJ</td>
          </tr>
          <tr>
            <td><span class="cmd-badge">/queue</span></td>
            <td>View the active queue, upcoming tracks, and total length.</td>
            <td>Everyone</td>
          </tr>
          <tr>
            <td><span class="cmd-badge">/effect &lt;filter&gt;</span></td>
            <td>Apply audio filters like Nightcore, BassBoost, 8D, and Pop.</td>
            <td>DJ / Admin</td>
          </tr>
          <tr>
            <td><span class="cmd-badge">/playlist play &lt;name&gt;</span></td>
            <td>Load and play your custom saved cloud playlist.</td>
            <td>Everyone</td>
          </tr>
          <tr>
            <td><span class="cmd-badge">/settings setupchannel</span></td>
            <td>Create a dedicated song request channel with interactive controls.</td>
            <td>Manage Server</td>
          </tr>
          <tr>
            <td><span class="cmd-badge">/help</span></td>
            <td>Interactive help guide and command directory.</td>
            <td>Everyone</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <!-- Footer -->
  <footer>
    <div class="footer-links">
      <a href="https://discord.com/oauth2/authorize?client_id=1556676516274905218&permissions=8&integration_type=0&scope=bot+applications.commands" target="_blank">Invite Bot</a>
      <a href="https://discord.gg/wRCgB7vBQv" target="_blank">Discord Server</a>
      <a href="https://github.com/kishorerai390/Rai-discord-bot" target="_blank">GitHub Repository</a>
      <a href="/api/logs" target="_blank">System Logs</a>
    </div>
    <p class="copyright">© 2026 Rem • Rai Discord Bot Ecosystem. Built with 💜 by Kishore. Powered by Lavalink v4 & Discord.py.</p>
  </footer>

</body>
</html>
"""
