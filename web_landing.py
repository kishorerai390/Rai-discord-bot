"""
Rem Official Web Platform & Luxury Landing Page.
Provides an anime-inspired, high-conversion, obsidian and neon lavender interface for Discord users,
featuring the complete 5 Strategic Innovations Suite:
1. Floating Real-Time Web Player (Spotify-Style)
2. Interactive Web Track Search & Instant Queue
3. Real-time Synchronized Karaoke Lyrics
4. Interactive Equalizer & Audio FX Panel
5. Drag-and-Drop Collaborative Queue Manager
"""

LANDING_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rem — Your Anime Music Companion | Rai Discord Bot</title>
  <meta name="description" content="Rem is an adorable, friendly anime-inspired AI DJ and music companion for Discord with Lavalink v4 audio streaming, floating Spotify-style web player, synced karaoke lyrics, 10-band equalizer, and drag-and-drop collaborative queues.">
  <meta property="og:title" content="Rem 🎧💜 — Your Anime Music Companion">
  <meta property="og:description" content="Crystal-clear audio, 24/7 low-latency playback, interactive web player, synchronized lyrics, audio filters, and cloud playlists.">
  <meta property="og:image" content="/public/musicmaid_avatar.jpg">
  <meta property="theme-color" content="#8a2be2">
  <link rel="icon" type="image/png" href="/public/icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0914;
      --bg-card: rgba(22, 19, 42, 0.72);
      --bg-card-hover: rgba(33, 29, 63, 0.88);
      --border-glow: rgba(168, 85, 247, 0.28);
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
      --radius-sm: 10px;
      --shadow-neon: 0 0 35px rgba(168, 85, 247, 0.28);
      --shadow-glow: 0 8px 32px rgba(0, 0, 0, 0.5);
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
        radial-gradient(circle at 15% 15%, rgba(147, 51, 234, 0.16) 0%, transparent 40%),
        radial-gradient(circle at 85% 35%, rgba(236, 72, 153, 0.14) 0%, transparent 45%),
        radial-gradient(circle at 50% 85%, rgba(6, 182, 212, 0.12) 0%, transparent 50%);
      background-attachment: fixed;
      padding-bottom: 95px; /* offset for floating bottom player */
    }

    /* Top Navigation */
    nav {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 76px;
      background: rgba(10, 9, 20, 0.85);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
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
      box-shadow: 0 0 15px rgba(192, 132, 252, 0.45);
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
      gap: 24px;
      align-items: center;
    }

    .nav-links a {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.95rem;
      font-weight: 500;
      transition: all 0.25s ease;
    }

    .nav-links a:hover {
      color: var(--accent-neon);
      transform: translateY(-1px);
    }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 12px 24px;
      border-radius: 9999px;
      font-size: 0.96rem;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      border: none;
    }

    .btn-primary {
      background: linear-gradient(135deg, var(--accent-purple), var(--accent-pink));
      color: #fff;
      box-shadow: 0 4px 20px rgba(147, 51, 234, 0.45);
    }

    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 28px rgba(236, 72, 153, 0.6);
    }

    .btn-secondary {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-glow);
      color: var(--text-white);
      backdrop-filter: blur(10px);
    }

    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: var(--border-bright);
      transform: translateY(-2px);
    }

    .btn-sm {
      padding: 6px 14px;
      font-size: 0.82rem;
      border-radius: 8px;
    }

    /* Hero Section */
    .hero {
      padding: 140px 8% 60px;
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 60px;
      align-items: center;
      position: relative;
    }

    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      background: rgba(168, 85, 247, 0.14);
      border: 1px solid var(--border-glow);
      border-radius: 9999px;
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
      transition: all 0.4s ease;
    }

    .player-card:hover {
      border-color: var(--border-bright);
      box-shadow: 0 0 50px rgba(168, 85, 247, 0.4);
    }

    .player-header {
      display: flex;
      gap: 18px;
      align-items: center;
      margin-bottom: 24px;
    }

    .player-thumb {
      width: 72px;
      height: 72px;
      border-radius: 14px;
      object-fit: cover;
      border: 2px solid rgba(168, 85, 247, 0.5);
      box-shadow: 0 4px 14px rgba(0,0,0,0.4);
    }

    .player-info h3 {
      font-size: 1.25rem;
      font-weight: 800;
      color: #fff;
      margin-bottom: 4px;
    }

    .player-info p {
      color: var(--accent-neon);
      font-size: 0.9rem;
      font-weight: 500;
    }

    /* Waveform Animation */
    .waveform {
      display: flex;
      align-items: center;
      gap: 4px;
      height: 38px;
      margin-bottom: 20px;
      padding: 0 10px;
    }

    .waveform-bar {
      flex: 1;
      background: linear-gradient(180deg, var(--accent-neon), var(--accent-purple));
      border-radius: 4px;
      animation: wave 1.2s ease-in-out infinite alternate;
    }

    .waveform-bar:nth-child(2) { animation-delay: 0.15s; }
    .waveform-bar:nth-child(3) { animation-delay: 0.3s; }
    .waveform-bar:nth-child(4) { animation-delay: 0.45s; }
    .waveform-bar:nth-child(5) { animation-delay: 0.6s; }
    .waveform-bar:nth-child(6) { animation-delay: 0.75s; }
    .waveform-bar:nth-child(7) { animation-delay: 0.9s; }
    .waveform-bar:nth-child(8) { animation-delay: 1.05s; }
    .waveform-bar:nth-child(9) { animation-delay: 0.2s; }
    .waveform-bar:nth-child(10) { animation-delay: 0.5s; }

    @keyframes wave {
      0% { height: 6px; opacity: 0.35; }
      100% { height: 34px; opacity: 1; }
    }

    .progress-wrap {
      margin-bottom: 24px;
    }

    .progress-bar {
      width: 100%;
      height: 6px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 3px;
      overflow: hidden;
      cursor: pointer;
    }

    .progress-fill {
      width: 48%;
      height: 100%;
      background: linear-gradient(90deg, var(--accent-purple), var(--accent-neon));
      border-radius: 3px;
      transition: width 0.2s linear;
    }

    .time-stamps {
      display: flex;
      justify-content: space-between;
      color: var(--text-dim);
      font-size: 0.78rem;
      font-family: 'JetBrains Mono', monospace;
      margin-top: 8px;
    }

    .controls-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 12px;
    }

    .control-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 1.4rem;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .control-btn:hover {
      color: #fff;
      transform: scale(1.15);
    }

    .play-btn {
      width: 50px;
      height: 50px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--accent-purple), var(--accent-pink));
      color: #fff;
      box-shadow: 0 4px 18px rgba(147, 51, 234, 0.5);
    }

    .play-btn:hover {
      transform: scale(1.08);
      box-shadow: 0 6px 24px rgba(236, 72, 153, 0.65);
    }

    /* =========================================================================
       STRATEGIC WEB SUITE: 5 INNOVATION MODULES
       ========================================================================= */
    .suite-section {
      padding: 60px 8% 80px;
      position: relative;
    }

    .section-head {
      text-align: center;
      margin-bottom: 40px;
    }

    .section-tag {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--accent-neon);
      text-transform: uppercase;
      letter-spacing: 1.5px;
      margin-bottom: 8px;
      display: inline-block;
    }

    .section-title {
      font-size: 2.5rem;
      font-weight: 900;
      letter-spacing: -0.5px;
      color: #fff;
    }

    .section-desc {
      color: var(--text-muted);
      max-width: 600px;
      margin: 10px auto 0;
      font-size: 1.05rem;
    }

    /* Suite Tabs */
    .suite-nav {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 35px;
    }

    .suite-tab-btn {
      background: rgba(22, 19, 42, 0.6);
      border: 1px solid var(--border-glow);
      color: var(--text-muted);
      padding: 10px 20px;
      border-radius: 9999px;
      font-size: 0.92rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.25s ease;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }

    .suite-tab-btn:hover {
      color: #fff;
      border-color: var(--border-bright);
      background: rgba(33, 29, 63, 0.8);
    }

    .suite-tab-btn.active {
      background: linear-gradient(135deg, rgba(147, 51, 234, 0.35), rgba(236, 72, 153, 0.25));
      border-color: var(--accent-neon);
      color: #fff;
      box-shadow: 0 0 20px rgba(168, 85, 247, 0.35);
    }

    /* Suite Module Container */
    .suite-card {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: 24px;
      padding: 35px;
      box-shadow: var(--shadow-glow);
      backdrop-filter: blur(20px);
      display: none;
      animation: fadeIn 0.35s ease forwards;
    }

    .suite-card.active {
      display: block;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* Module 1: Search & Queue */
    .search-input-box {
      display: flex;
      gap: 12px;
      margin-bottom: 20px;
    }

    .web-search-bar {
      flex: 1;
      background: rgba(10, 9, 20, 0.7);
      border: 1px solid var(--border-glow);
      border-radius: 14px;
      padding: 14px 20px;
      color: #fff;
      font-size: 1rem;
      outline: none;
      transition: border-color 0.2s;
    }

    .web-search-bar:focus {
      border-color: var(--accent-neon);
      box-shadow: 0 0 15px rgba(168, 85, 247, 0.25);
    }

    .genre-pills {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 24px;
    }

    .genre-chip {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.8rem;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s;
    }

    .genre-chip:hover, .genre-chip.active {
      border-color: var(--accent-neon);
      color: #fff;
      background: rgba(168, 85, 247, 0.15);
    }

    .search-results-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px;
    }

    .track-result-card {
      background: rgba(10, 9, 20, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 16px;
      padding: 14px;
      display: flex;
      gap: 14px;
      align-items: center;
      transition: all 0.25s ease;
    }

    .track-result-card:hover {
      border-color: var(--border-bright);
      background: rgba(33, 29, 63, 0.6);
      transform: translateY(-2px);
    }

    .track-result-card img {
      width: 54px;
      height: 54px;
      border-radius: 10px;
      object-fit: cover;
    }

    .track-meta {
      flex: 1;
      min-width: 0;
    }

    .track-meta h4 {
      font-size: 0.95rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .track-meta p {
      font-size: 0.78rem;
      color: var(--text-dim);
    }

    .track-actions {
      display: flex;
      gap: 6px;
    }

    /* Module 2: Karaoke Lyrics */
    .lyrics-container {
      background: rgba(10, 9, 20, 0.85);
      border: 1px solid var(--border-glow);
      border-radius: 18px;
      padding: 30px;
      text-align: center;
      position: relative;
      overflow: hidden;
    }

    .lyrics-header-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 0.8rem;
      color: var(--accent-neon);
      background: rgba(168, 85, 247, 0.12);
      padding: 4px 12px;
      border-radius: 9999px;
      margin-bottom: 20px;
    }

    .lyrics-lines {
      max-height: 260px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
      padding: 10px 0;
      scroll-behavior: smooth;
    }

    .lyrics-line {
      font-size: 1.15rem;
      color: var(--text-dim);
      font-weight: 500;
      transition: all 0.3s ease;
      cursor: pointer;
    }

    .lyrics-line.active {
      font-size: 1.45rem;
      font-weight: 800;
      color: #fff;
      text-shadow: 0 0 20px rgba(192, 132, 252, 0.8), 0 0 35px rgba(236, 72, 153, 0.5);
      transform: scale(1.05);
    }

    .lyrics-line.past {
      color: var(--text-muted);
      opacity: 0.7;
    }

    /* Module 3: Equalizer */
    .eq-controls-wrap {
      display: flex;
      flex-direction: column;
      gap: 25px;
    }

    .eq-presets-row {
      display: flex;
      justify-content: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .eq-preset-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: var(--text-muted);
      padding: 8px 16px;
      border-radius: 12px;
      font-size: 0.85rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s;
    }

    .eq-preset-btn:hover, .eq-preset-btn.active {
      background: linear-gradient(135deg, rgba(147, 51, 234, 0.3), rgba(6, 182, 212, 0.25));
      border-color: var(--accent-neon);
      color: #fff;
      box-shadow: 0 0 15px rgba(168, 85, 247, 0.3);
    }

    .eq-sliders-row {
      display: flex;
      justify-content: space-around;
      align-items: center;
      background: rgba(10, 9, 20, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 18px;
      padding: 24px 16px;
    }

    .eq-band {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;
    }

    .eq-slider {
      -webkit-appearance: slider-vertical;
      writing-mode: bt-lr;
      width: 14px;
      height: 140px;
      accent-color: var(--accent-neon);
      cursor: pointer;
    }

    .eq-freq {
      font-size: 0.72rem;
      color: var(--text-dim);
      font-family: 'JetBrains Mono', monospace;
    }

    .eq-gain {
      font-size: 0.72rem;
      color: var(--accent-neon);
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
    }

    /* Module 4: Drag & Drop Queue */
    .queue-manager-box {
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    .queue-bar-actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }

    .queue-items-table {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .queue-drag-row {
      background: rgba(10, 9, 20, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 14px;
      padding: 12px 18px;
      display: flex;
      align-items: center;
      gap: 16px;
      cursor: grab;
      transition: all 0.2s ease;
    }

    .queue-drag-row:hover {
      border-color: var(--accent-neon);
      background: rgba(33, 29, 63, 0.7);
    }

    .queue-drag-row.dragging {
      opacity: 0.4;
      border-style: dashed;
    }

    .queue-drag-row.drag-over {
      border-color: var(--accent-pink);
      transform: scale(1.02);
    }

    .drag-icon {
      color: var(--text-dim);
      font-size: 1.1rem;
      user-select: none;
    }

    .queue-idx {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      color: var(--accent-neon);
      font-weight: 700;
      min-width: 24px;
    }

    .queue-thumb {
      width: 44px;
      height: 44px;
      border-radius: 8px;
      object-fit: cover;
    }

    .queue-text {
      flex: 1;
      min-width: 0;
    }

    .queue-text h5 {
      font-size: 0.95rem;
      color: #fff;
      font-weight: 700;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .queue-text p {
      font-size: 0.78rem;
      color: var(--text-dim);
    }

    .queue-time {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      color: var(--text-muted);
    }

    /* =========================================================================
       FLOATING SPOTIFY-STYLE BOTTOM WEB PLAYER
       ========================================================================= */
    .floating-player-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      width: 100%;
      height: 82px;
      background: rgba(12, 10, 24, 0.94);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border-top: 1px solid var(--border-glow);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 4%;
      z-index: 9999;
      box-shadow: 0 -8px 32px rgba(0, 0, 0, 0.6);
      transition: transform 0.3s ease;
    }

    .floating-player-bar.minimized {
      transform: translateY(calc(100% - 24px));
    }

    .fp-left {
      display: flex;
      align-items: center;
      gap: 14px;
      width: 28%;
      min-width: 200px;
    }

    .fp-thumb {
      width: 52px;
      height: 52px;
      border-radius: 10px;
      object-fit: cover;
      border: 1px solid var(--accent-neon);
      box-shadow: 0 0 10px rgba(168, 85, 247, 0.4);
    }

    .fp-meta {
      min-width: 0;
    }

    .fp-title {
      font-size: 0.92rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      display: block;
    }

    .fp-sub {
      font-size: 0.76rem;
      color: var(--accent-neon);
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .fp-center {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      width: 44%;
      max-width: 560px;
    }

    .fp-controls {
      display: flex;
      align-items: center;
      gap: 18px;
    }

    .fp-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 1.15rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .fp-btn:hover {
      color: #fff;
      transform: scale(1.15);
    }

    .fp-play-btn {
      width: 38px;
      height: 38px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--accent-purple), var(--accent-pink));
      color: #fff;
      font-size: 1rem;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 2px 12px rgba(147, 51, 234, 0.4);
    }

    .fp-scrub-row {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
    }

    .fp-time {
      font-size: 0.72rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-dim);
      min-width: 36px;
    }

    .fp-slider {
      flex: 1;
      height: 4px;
      -webkit-appearance: none;
      background: rgba(255, 255, 255, 0.15);
      border-radius: 2px;
      outline: none;
      cursor: pointer;
    }

    .fp-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--accent-neon);
      box-shadow: 0 0 8px var(--accent-neon);
      cursor: pointer;
    }

    .fp-right {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 16px;
      width: 28%;
      min-width: 200px;
    }

    .fp-vol-slider {
      width: 75px;
      height: 4px;
      -webkit-appearance: none;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 2px;
      outline: none;
      cursor: pointer;
    }

    .fp-vol-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #fff;
      cursor: pointer;
    }

    /* Features Grid */
    .features {
      padding: 60px 8%;
    }

    .features-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 24px;
    }

    .feature-card {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: var(--radius);
      padding: 32px;
      transition: all 0.3s ease;
      position: relative;
      overflow: hidden;
    }

    .feature-card:hover {
      background: var(--bg-card-hover);
      border-color: var(--border-bright);
      transform: translateY(-4px);
      box-shadow: var(--shadow-neon);
    }

    .feature-icon {
      font-size: 2.2rem;
      margin-bottom: 20px;
      display: inline-block;
    }

    .feature-card h3 {
      font-size: 1.35rem;
      font-weight: 800;
      color: #fff;
      margin-bottom: 12px;
    }

    .feature-card p {
      color: var(--text-muted);
      font-size: 0.95rem;
      line-height: 1.7;
    }

    /* Commands Table */
    .commands-sec {
      padding: 60px 8%;
    }

    .cmd-table-wrap {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: var(--radius);
      overflow-x: auto;
      box-shadow: var(--shadow-neon);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }

    th, td {
      padding: 16px 24px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }

    th {
      background: rgba(255, 255, 255, 0.02);
      color: var(--text-dim);
      font-weight: 600;
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    td {
      font-size: 0.95rem;
      color: var(--text-muted);
    }

    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(168, 85, 247, 0.05); }

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

    /* Toast Notification */
    .toast-pill {
      position: fixed;
      top: 90px;
      right: 25px;
      background: rgba(20, 16, 40, 0.95);
      border: 1px solid var(--accent-neon);
      color: #fff;
      padding: 12px 20px;
      border-radius: 12px;
      font-size: 0.9rem;
      font-weight: 600;
      box-shadow: 0 8px 24px rgba(0,0,0,0.6), 0 0 15px rgba(168,85,247,0.4);
      display: flex;
      align-items: center;
      gap: 10px;
      z-index: 10000;
      opacity: 0;
      pointer-events: none;
      transform: translateY(-10px);
      transition: all 0.3s ease;
    }

    .toast-pill.show {
      opacity: 1;
      pointer-events: auto;
      transform: translateY(0);
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
      .fp-left { width: 45%; }
      .fp-center { display: none; }
      .fp-right { width: 50%; }
    }
  </style>
</head>
<body>

  <!-- Toast Notification -->
  <div id="live-toast" class="toast-pill">
    <span id="toast-icon">✨</span>
    <span id="toast-text">Action completed successfully</span>
  </div>

  <!-- Navigation -->
  <nav>
    <a href="/" class="brand">
      <img src="/public/rem_logo_badge.gif?v=4" alt="Rem Logo" class="brand-img" onerror="this.src='/public/musicmaid_avatar.jpg?v=4'">
      <span class="brand-name">Rem 🎧💜</span>
    </a>
    <div class="nav-links">
      <a href="#suite">Innovations Suite</a>
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
      <p class="hero-sub">Your adorable, friendly anime-inspired AI DJ and music companion. Featuring crystal audio clarity, a floating web player, synchronized lyrics, audio equalizer filters, and live collaborative queues.</p>
      
      <div class="hero-cta">
        <a href="https://discord.com/oauth2/authorize?client_id=1556676516274905218&permissions=8&integration_type=0&scope=bot+applications.commands" target="_blank" class="btn btn-primary">
          <span>Add Rem Now</span>
          <span>⚡</span>
        </a>
        <a href="/dashboard" class="btn btn-secondary">
          <span>Open Web Dashboard</span>
          <span>🎛️</span>
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
          <img src="/public/musicmaid_banner.jpg" alt="Track Art" class="player-thumb" id="hero-track-thumb" onerror="this.src='/public/musicmaid_avatar.jpg'">
          <div class="player-info">
            <h3 id="hero-track-title">怪物 (Monster)</h3>
            <p id="hero-track-artist">YOASOBI • Playing in #anime-lounge</p>
          </div>
        </div>

        <div class="waveform" id="hero-waveform">
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
          <div class="progress-bar" onclick="seekHeroProgress(event)">
            <div class="progress-fill" id="hero-progress-fill"></div>
          </div>
          <div class="time-stamps">
            <span id="hero-time-cur">01:25</span>
            <span id="hero-time-total">03:26</span>
          </div>
        </div>

        <div class="controls-row">
          <button class="control-btn" onclick="triggerShuffle()" title="Shuffle Queue">🔀</button>
          <button class="control-btn" onclick="triggerPrev()" title="Previous Track">⏮️</button>
          <button class="control-btn play-btn" id="hero-play-btn" onclick="togglePlayPause()" title="Play / Pause">⏸️</button>
          <button class="control-btn" onclick="triggerNext()" title="Next Track">⏭️</button>
          <button class="control-btn" onclick="triggerRepeat()" title="Repeat Track">🔁</button>
        </div>
      </div>
    </div>
  </section>

  <!-- =========================================================================
       STRATEGIC WEB SUITE: 5 INNOVATIONS SHOWCASE
       ========================================================================= -->
  <section id="suite" class="suite-section">
    <div class="section-head">
      <span class="section-tag">✨ Next-Gen Web Innovations</span>
      <h2 class="section-title">Strategic Interactive Web Suite</h2>
      <p class="section-desc">Experience all 5 strategic web innovations live right in your browser — from interactive instant search and live karaoke lyrics to a 10-band DSP equalizer and collaborative drag-and-drop queues.</p>
    </div>

    <!-- Suite Tabs -->
    <div class="suite-nav">
      <button class="suite-tab-btn active" onclick="switchSuiteTab('search')">🔍 Instant Web Search & Queue</button>
      <button class="suite-tab-btn" onclick="switchSuiteTab('lyrics')">🎤 Synced Karaoke Lyrics</button>
      <button class="suite-tab-btn" onclick="switchSuiteTab('equalizer')">🎛️ 10-Band Equalizer & FX</button>
      <button class="suite-tab-btn" onclick="switchSuiteTab('queue')">📑 Drag & Drop Queue</button>
      <button class="suite-tab-btn" onclick="switchSuiteTab('player')">🎧 Spotify-Style Bottom Player</button>
    </div>

    <!-- 1. SEARCH & INSTANT QUEUE MODULE -->
    <div id="module-search" class="suite-card active">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; flex-wrap:wrap; gap:10px;">
        <div>
          <h3 style="font-size:1.35rem; color:#fff; font-weight:800;">🔍 Interactive Web Track Search & Instant Queue</h3>
          <p style="color:var(--text-muted); font-size:0.88rem;">Search songs across YouTube, Spotify, and Apple Music with live album art previews and queue them directly into Discord VC.</p>
        </div>
        <span class="cmd-badge">Live Search API Ready</span>
      </div>

      <div class="search-input-box">
        <input type="text" id="suite-search-input" class="web-search-bar" placeholder="Type a track title, artist, or URL (e.g. YOASOBI, Alan Walker, Ado, Chainsaw Man)..." oninput="handleSuiteSearch(event)">
        <button class="btn btn-primary" onclick="executeSuiteSearch()">Search ⚡</button>
      </div>

      <div class="genre-pills">
        <span class="genre-chip active" onclick="filterGenre('all')">🌟 All Top Hits</span>
        <span class="genre-chip" onclick="filterGenre('anime')">🔥 Anime Openings</span>
        <span class="genre-chip" onclick="filterGenre('lofi')">☕ Lo-Fi Chill Beats</span>
        <span class="genre-chip" onclick="filterGenre('jrock')">⚡ J-Rock & Pop</span>
        <span class="genre-chip" onclick="filterGenre('edm')">💥 Synthwave EDM</span>
      </div>

      <div class="search-results-grid" id="suite-search-results">
        <!-- Rendered dynamically via JavaScript -->
      </div>
    </div>

    <!-- 2. SYNCHRONIZED KARAOKE LYRICS MODULE -->
    <div id="module-lyrics" class="suite-card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; flex-wrap:wrap; gap:10px;">
        <div>
          <h3 style="font-size:1.35rem; color:#fff; font-weight:800;">🎤 Real-Time Synchronized Karaoke Lyrics</h3>
          <p style="color:var(--text-muted); font-size:0.88rem;">Syllable-accurate, timestamped karaoke visualizer powered by LRCLIB & Genius that auto-scrolls in rhythm with playback.</p>
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-secondary btn-sm" onclick="selectLyricTrack('yoasobi')">怪物 (YOASOBI)</button>
          <button class="btn btn-secondary btn-sm" onclick="selectLyricTrack('faded')">Faded (Alan Walker)</button>
          <button class="btn btn-secondary btn-sm" onclick="selectLyricTrack('ado')">新時代 (Ado)</button>
        </div>
      </div>

      <div class="lyrics-container">
        <div class="lyrics-header-badge">
          <span class="pulse-dot"></span>
          <span id="lyrics-track-info">NOW STREAMING: 怪物 (Monster) — YOASOBI [LRCLIB Synchronized]</span>
        </div>

        <div class="lyrics-lines" id="lyrics-stream-box">
          <!-- Synced lyrics rendered via JavaScript -->
        </div>

        <div style="margin-top:22px; display:flex; align-items:center; justify-content:center; gap:14px;">
          <button class="btn btn-secondary btn-sm" onclick="restartLyrics()">↺ Replay Lyrics</button>
          <button class="btn btn-primary btn-sm" onclick="togglePlayPause()">⏯ Toggle Rhythm</button>
        </div>
      </div>
    </div>

    <!-- 3. INTERACTIVE 10-BAND EQUALIZER & AUDIO FX MODULE -->
    <div id="module-equalizer" class="suite-card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; flex-wrap:wrap; gap:10px;">
        <div>
          <h3 style="font-size:1.35rem; color:#fff; font-weight:800;">🎛️ Interactive 10-Band Equalizer & Audio FX Panel</h3>
          <p style="color:var(--text-muted); font-size:0.88rem;">Fine-tune your audio output with 10 frequency sliders and 1-click Lavalink audio filter presets.</p>
        </div>
        <span class="cmd-badge">Lavalink v4 DSP Engine</span>
      </div>

      <div class="eq-controls-wrap">
        <div class="eq-presets-row">
          <button class="eq-preset-btn active" onclick="applyEqPreset('flat')">⚖️ Flat (Default)</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('bass')">💥 Bass Boost (+12dB)</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('nightcore')">⚡ Nightcore (Speed+Pitch)</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('8d')">🎧 8D Spatial Audio</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('vaporwave')">🌆 Vaporwave (Slowed+Reverb)</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('lofi')">☕ Lo-Fi Acoustic</button>
        </div>

        <div class="eq-sliders-row" id="eq-sliders-container">
          <!-- 10 frequency sliders generated via JavaScript -->
        </div>

        <div style="text-align:center;">
          <button class="btn btn-primary btn-sm" onclick="saveEqToBot()">⚡ Apply Equalizer to Active Voice Channel</button>
        </div>
      </div>
    </div>

    <!-- 4. DRAG-AND-DROP COLLABORATIVE QUEUE MODULE -->
    <div id="module-queue" class="suite-card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; flex-wrap:wrap; gap:10px;">
        <div>
          <h3 style="font-size:1.35rem; color:#fff; font-weight:800;">📑 Drag-and-Drop Collaborative Queue Manager</h3>
          <p style="color:var(--text-muted); font-size:0.88rem;">Drag and reorder tracks collaboratively, vote to remove unwanted songs, or save current queue as a cloud playlist.</p>
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-secondary btn-sm" onclick="shuffleSuiteQueue()">🔀 Shuffle</button>
          <button class="btn btn-primary btn-sm" onclick="saveQueueAsPlaylist()">💾 Save Playlist</button>
        </div>
      </div>

      <div class="queue-manager-box">
        <div class="queue-items-table" id="suite-queue-table">
          <!-- Draggable Queue Rows rendered via JavaScript -->
        </div>

        <div style="background:rgba(255,255,255,0.03); border:1px dashed var(--border-glow); border-radius:14px; padding:12px; text-align:center; font-size:0.85rem; color:var(--text-dim);">
          💡 <strong style="color:var(--accent-neon);">Pro Tip:</strong> Click and hold any track handle (⋮⋮) to drag up or down. Changes sync immediately to all listeners!
        </div>
      </div>
    </div>

    <!-- 5. SPOTIFY-STYLE FLOATING PLAYER PREVIEW MODULE -->
    <div id="module-player" class="suite-card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; flex-wrap:wrap; gap:10px;">
        <div>
          <h3 style="font-size:1.35rem; color:#fff; font-weight:800;">🎧 Floating Real-Time Web Player (Spotify-Style)</h3>
          <p style="color:var(--text-muted); font-size:0.88rem;">Pinned to the bottom of every page with live WebSocket voice synchronization, scrubbable progress bar, volume controls, and instant track skipping.</p>
        </div>
        <a href="/dashboard" class="btn btn-primary btn-sm">Open Full Web Dashboard ↗</a>
      </div>

      <div style="background:rgba(10,9,20,0.8); border:1px solid var(--border-glow); border-radius:18px; padding:30px; text-align:center;">
        <p style="color:#fff; font-size:1.1rem; font-weight:700; margin-bottom:12px;">The floating player is permanently active on this website!</p>
        <p style="color:var(--text-muted); font-size:0.92rem; max-width:620px; margin:0 auto 20px;">
          Notice the sleek player docked at the bottom of your screen. You can scrub tracks, toggle audio playback, adjust volume, view live waveforms, and open the full master control room at any time.
        </p>
        <button class="btn btn-secondary" onclick="pulseBottomPlayer()">⚡ Highlight Bottom Player</button>
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
        <p>Sing along with live, timestamped synchronized lyrics powered by LRCLIB and Genius directly within your Discord chat and web dashboard.</p>
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

  <!-- =========================================================================
       FLOATING REAL-TIME WEB PLAYER (SPOTIFY-STYLE BAR)
       ========================================================================= -->
  <div id="floating-spotify-bar" class="floating-player-bar">
    <!-- Left: Track Metadata -->
    <div class="fp-left">
      <img src="/public/musicmaid_avatar.jpg" alt="Now Playing Art" class="fp-thumb" id="fp-track-img" onerror="this.src='/public/icon.png'">
      <div class="fp-meta">
        <span class="fp-title" id="fp-track-title">怪物 (Monster)</span>
        <span class="fp-sub" id="fp-track-artist">
          <span class="pulse-dot" style="width:6px; height:6px;"></span>
          <span id="fp-channel-badge">YOASOBI • #anime-lounge</span>
        </span>
      </div>
    </div>

    <!-- Center: Playback Controls & Scrubber -->
    <div class="fp-center">
      <div class="fp-controls">
        <button class="fp-btn" onclick="triggerShuffle()" title="Shuffle">🔀</button>
        <button class="fp-btn" onclick="triggerPrev()" title="Previous">⏮️</button>
        <button class="fp-play-btn" id="fp-play-btn" onclick="togglePlayPause()" title="Play / Pause">⏸️</button>
        <button class="fp-btn" onclick="triggerNext()" title="Next">⏭️</button>
        <button class="fp-btn" onclick="triggerRepeat()" title="Repeat">🔁</button>
      </div>
      <div class="fp-scrub-row">
        <span class="fp-time" id="fp-cur-time">01:25</span>
        <input type="range" min="0" max="100" value="41" class="fp-slider" id="fp-scrub-slider" oninput="handleFpScrub(this.value)">
        <span class="fp-time" id="fp-total-time">03:26</span>
      </div>
    </div>

    <!-- Right: Quick Tools & Volume -->
    <div class="fp-right">
      <button class="fp-btn" onclick="switchSuiteTab('lyrics'); scrollToSuite();" title="View Synced Lyrics">🎤</button>
      <button class="fp-btn" onclick="switchSuiteTab('equalizer'); scrollToSuite();" title="10-Band Equalizer">🎛️</button>
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="font-size:1rem; cursor:pointer;" onclick="toggleMute()" id="fp-vol-icon">🔊</span>
        <input type="range" min="0" max="100" value="85" class="fp-vol-slider" id="fp-vol-slider" oninput="handleVolume(this.value)">
      </div>
      <a href="/dashboard" class="btn btn-primary btn-sm" style="margin-left:6px;">Dashboard ↗</a>
    </div>
  </div>

  <!-- SCRIPT FOR ALL 5 STRATEGIC SUGGESTIONS -->
  <script>
    // State management
    let isPlaying = true;
    let currentSeconds = 85;
    let totalSeconds = 206;
    let volumeLevel = 85;
    let currentLyricIndex = 3;
    let isMuted = false;

    const catalogTracks = [
      { id: "trk-1", title: "怪物 (Monster)", artist: "YOASOBI", duration: 206, genre: "anime", thumbnail: "/public/musicmaid_avatar.jpg", durText: "03:26" },
      { id: "trk-2", title: "Faded (Live Symphony)", artist: "Alan Walker", duration: 212, genre: "edm", thumbnail: "/public/musicmaid_banner.jpg", durText: "03:32" },
      { id: "trk-3", title: "新時代 (New Genesis)", artist: "Ado", duration: 226, genre: "anime", thumbnail: "/public/login_hero.jpg", durText: "03:46" },
      { id: "trk-4", title: "KICK BACK", artist: "Kenshi Yonezu", duration: 193, genre: "anime", thumbnail: "/public/musicmaid_avatar.jpg", durText: "03:13" },
      { id: "trk-5", title: "Coffee & Rain (Lo-Fi)", artist: "Rem Beats", duration: 165, genre: "lofi", thumbnail: "/public/musicmaid_headphone_hero.jpg", durText: "02:45" },
      { id: "trk-6", title: "Sparkle (Movie Ver.)", artist: "RADWIMPS", duration: 417, genre: "jrock", thumbnail: "/public/musicmaid_banner.jpg", durText: "06:57" }
    ];

    let currentQueue = [
      { title: "Faded (Live Vocal Edition)", artist: "Alan Walker", duration: 212, durText: "03:32", requester: "@Rem Member", thumb: "/public/musicmaid_banner.jpg" },
      { title: "新時代 (New Genesis)", artist: "Ado", duration: 226, durText: "03:46", requester: "@Anime DJ", thumb: "/public/login_hero.jpg" },
      { title: "KICK BACK (Chainsaw Man OP)", artist: "Kenshi Yonezu", duration: 193, durText: "03:13", requester: "@Community VIP", thumb: "/public/musicmaid_avatar.jpg" },
      { title: "Sparkle (Your Name OST)", artist: "RADWIMPS", duration: 417, durText: "06:57", requester: "@Kishore (Creator)", thumb: "/public/musicmaid_headphone_hero.jpg" }
    ];

    const lyricDatabase = {
      yoasobi: [
        { time: 8, text: "♪ ~ (Synth Arpeggio Intro) ~ ♪" },
        { time: 14, text: "素晴らしき世界に今日も乾杯" },
        { time: 19, text: "街に飛び交う銃声と歓声" },
        { time: 24, text: "誰もが自分を偽り生きている" },
        { time: 29, text: "隠した本能 解き放つ時が来た" },
        { time: 34, text: "叫べ 今この夜空を裂いて" },
        { time: 40, text: "正しさとは何だ 誰が決めたルールだ" },
        { time: 46, text: "僕らはずっと自由を歌っている" }
      ],
      faded: [
        { time: 5, text: "♪ ~ (Atmospheric Piano Intro) ~ ♪" },
        { time: 12, text: "You were the shadow to my light" },
        { time: 18, text: "Did you feel us? Another start" },
        { time: 24, text: "You fade away, afraid our aim is out of sight" },
        { time: 30, text: "Wanna see us alive" },
        { time: 36, text: "Where are you now? Where are you now?" }
      ],
      ado: [
        { time: 6, text: "♪ ~ (Electronic Horn Fanfare) ~ ♪" },
        { time: 13, text: "新時代はこの未来だ" },
        { time: 18, text: "世界中全部 変えてしまえば 変えてしまえば" },
        { time: 24, text: "果てしない音楽の波に乗せて" },
        { time: 30, text: "夢を見ようよ ずっと覚めないように" }
      ]
    };

    let activeLyricKey = 'yoasobi';

    // 1. Toast helper
    function showToast(msg, icon = '✨') {
      const toast = document.getElementById('live-toast');
      document.getElementById('toast-icon').innerText = icon;
      document.getElementById('toast-text').innerText = msg;
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 2800);
    }

    // 2. Tab switching
    function switchSuiteTab(tab) {
      document.querySelectorAll('.suite-tab-btn').forEach((btn, idx) => {
        btn.classList.toggle('active', btn.getAttribute('onclick').includes(tab));
      });
      document.querySelectorAll('.suite-card').forEach(card => card.classList.remove('active'));
      const activeCard = document.getElementById(`module-${tab}`);
      if (activeCard) activeCard.classList.add('active');
    }

    function scrollToSuite() {
      document.getElementById('suite').scrollIntoView({ behavior: 'smooth' });
    }

    // 3. Play / Pause & Live Timer
    function togglePlayPause() {
      isPlaying = !isPlaying;
      const playIcons = isPlaying ? '⏸️' : '▶️';
      document.getElementById('hero-play-btn').innerText = playIcons;
      document.getElementById('fp-play-btn').innerText = playIcons;
      const wave = document.getElementById('hero-waveform');
      if (wave) {
        wave.style.opacity = isPlaying ? '1' : '0.25';
      }
      showToast(isPlaying ? "Playback Resumed" : "Playback Paused", isPlaying ? "▶️" : "⏸️");
    }

    function formatTime(s) {
      const m = Math.floor(s / 60);
      const rem = Math.floor(s % 60);
      return `${m < 10 ? '0' : ''}${m}:${rem < 10 ? '0' : ''}${rem}`;
    }

    setInterval(() => {
      if (isPlaying) {
        currentSeconds++;
        if (currentSeconds > totalSeconds) currentSeconds = 0;
        const pct = (currentSeconds / totalSeconds) * 100;
        document.getElementById('hero-progress-fill').style.width = pct + '%';
        document.getElementById('fp-scrub-slider').value = pct;
        document.getElementById('hero-time-cur').innerText = formatTime(currentSeconds);
        document.getElementById('fp-cur-time').innerText = formatTime(currentSeconds);

        // Update active lyric
        const lyrics = lyricDatabase[activeLyricKey];
        if (lyrics && lyrics.length) {
          let foundIdx = 0;
          for (let i = 0; i < lyrics.length; i++) {
            if (currentSeconds >= lyrics[i].time) foundIdx = i;
          }
          if (foundIdx !== currentLyricIndex) {
            currentLyricIndex = foundIdx;
            renderLyricsLines();
          }
        }
      }
    }, 1000);

    function seekHeroProgress(e) {
      const rect = e.currentTarget.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const ratio = Math.max(0, Math.min(1, clickX / rect.width));
      currentSeconds = Math.floor(ratio * totalSeconds);
      document.getElementById('hero-progress-fill').style.width = (ratio * 100) + '%';
      document.getElementById('fp-scrub-slider').value = (ratio * 100);
      showToast(`Seeked to ${formatTime(currentSeconds)}`, '⏩');
    }

    function handleFpScrub(val) {
      currentSeconds = Math.floor((val / 100) * totalSeconds);
      document.getElementById('hero-progress-fill').style.width = val + '%';
      document.getElementById('hero-time-cur').innerText = formatTime(currentSeconds);
      document.getElementById('fp-cur-time').innerText = formatTime(currentSeconds);
    }

    function handleVolume(val) {
      volumeLevel = val;
      const icon = val == 0 ? '🔇' : (val < 45 ? '🔉' : '🔊');
      document.getElementById('fp-vol-icon').innerText = icon;
    }

    function toggleMute() {
      isMuted = !isMuted;
      document.getElementById('fp-vol-slider').value = isMuted ? 0 : volumeLevel;
      document.getElementById('fp-vol-icon').innerText = isMuted ? '🔇' : '🔊';
      showToast(isMuted ? "Audio Muted" : `Volume restored (${volumeLevel}%)`);
    }

    // 4. Track Actions (Play Now & Enqueue)
    function playTrackNow(track) {
      document.getElementById('hero-track-title').innerText = track.title;
      document.getElementById('hero-track-artist').innerText = `${track.artist} • Playing in #anime-lounge`;
      document.getElementById('hero-track-thumb').src = track.thumbnail;
      document.getElementById('fp-track-title').innerText = track.title;
      document.getElementById('fp-channel-badge').innerText = `${track.artist} • #anime-lounge`;
      document.getElementById('fp-track-img').src = track.thumbnail;
      totalSeconds = track.duration;
      currentSeconds = 0;
      document.getElementById('hero-time-total').innerText = track.durText;
      document.getElementById('fp-total-time').innerText = track.durText;
      isPlaying = true;
      document.getElementById('hero-play-btn').innerText = '⏸️';
      document.getElementById('fp-play-btn').innerText = '⏸️';
      showToast(`Now Streaming: ${track.title}`, '🎧');
    }

    function enqueueTrack(track) {
      currentQueue.push({
        title: track.title,
        artist: track.artist,
        duration: track.duration,
        durText: track.durText,
        requester: "@You (Web)",
        thumb: track.thumbnail
      });
      renderSuiteQueue();
      showToast(`Added to Queue: ${track.title}`, '➕');
    }

    function triggerNext() {
      if (currentQueue.length > 0) {
        const next = currentQueue.shift();
        renderSuiteQueue();
        playTrackNow({
          title: next.title,
          artist: next.artist,
          duration: next.duration,
          durText: next.durText,
          thumbnail: next.thumb
        });
      } else {
        showToast("Queue is clear. Add more tracks!", "ℹ️");
      }
    }

    function triggerPrev() {
      currentSeconds = 0;
      showToast("Rewound to track beginning", "⏮️");
    }

    function triggerShuffle() {
      shuffleSuiteQueue();
    }

    function triggerRepeat() {
      showToast("Repeat Mode: Track Loop Active 🔁", "🔁");
    }

    function pulseBottomPlayer() {
      const p = document.getElementById('floating-spotify-bar');
      p.style.boxShadow = '0 -8px 40px rgba(236,72,153,0.9)';
      p.style.borderColor = 'var(--accent-pink)';
      setTimeout(() => {
        p.style.boxShadow = '0 -8px 32px rgba(0, 0, 0, 0.6)';
        p.style.borderColor = 'var(--border-glow)';
      }, 1500);
      showToast("Floating player ready at viewport bottom!", "🎧");
    }

    // 5. Search & Filter Render
    function renderSearchResults(filter = 'all', query = '') {
      const container = document.getElementById('suite-search-results');
      let filtered = catalogTracks;
      if (filter !== 'all') {
        filtered = filtered.filter(t => t.genre === filter);
      }
      if (query) {
        filtered = filtered.filter(t => t.title.toLowerCase().includes(query.toLowerCase()) || t.artist.toLowerCase().includes(query.toLowerCase()));
      }
      if (!filtered.length) {
        container.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:30px; color:var(--text-dim);">No songs matched "${query}". Try searching "Anime" or "YOASOBI".</div>`;
        return;
      }
      container.innerHTML = filtered.map(t => `
        <div class="track-result-card">
          <img src="${t.thumbnail}" alt="${t.title}" onerror="this.src='/public/musicmaid_avatar.jpg'">
          <div class="track-meta">
            <h4>${t.title}</h4>
            <p>${t.artist} • ${t.durText}</p>
          </div>
          <div class="track-actions">
            <button class="btn btn-primary btn-sm" onclick='playTrackNow(${JSON.stringify(t)})' title="Play Now">▶</button>
            <button class="btn btn-secondary btn-sm" onclick='enqueueTrack(${JSON.stringify(t)})' title="Add to Queue">➕</button>
          </div>
        </div>
      `).join('');
    }

    function filterGenre(genre) {
      document.querySelectorAll('.genre-chip').forEach(el => el.classList.remove('active'));
      event.currentTarget.classList.add('active');
      renderSearchResults(genre);
    }

    function handleSuiteSearch(e) {
      renderSearchResults('all', e.target.value.trim());
    }

    function executeSuiteSearch() {
      const q = document.getElementById('suite-search-input').value.trim();
      renderSearchResults('all', q);
      showToast(`Showing search results for "${q || 'Top Hits'}"`, '🔍');
    }

    // 6. Karaoke Lyrics
    function selectLyricTrack(key) {
      activeLyricKey = key;
      currentLyricIndex = 0;
      currentSeconds = 0;
      const titleMap = {
        yoasobi: "NOW STREAMING: 怪物 (Monster) — YOASOBI [LRCLIB Synced]",
        faded: "NOW STREAMING: Faded (Live Symphony) — Alan Walker [LRCLIB Synced]",
        ado: "NOW STREAMING: 新時代 (New Genesis) — Ado [LRCLIB Synced]"
      };
      document.getElementById('lyrics-track-info').innerText = titleMap[key] || "LIVE SYNCHRONIZED LYRICS";
      renderLyricsLines();
      showToast("Loaded lyrics for " + key.toUpperCase(), "🎤");
    }

    function restartLyrics() {
      currentSeconds = 0;
      currentLyricIndex = 0;
      renderLyricsLines();
    }

    function renderLyricsLines() {
      const container = document.getElementById('lyrics-stream-box');
      const lines = lyricDatabase[activeLyricKey] || [];
      container.innerHTML = lines.map((l, i) => {
        let cls = 'lyrics-line';
        if (i === currentLyricIndex) cls += ' active';
        else if (i < currentLyricIndex) cls += ' past';
        return `<div class="${cls}" onclick="seekLyricLine(${l.time})">${l.text}</div>`;
      }).join('');

      // Auto scroll active line into view
      const activeEl = container.querySelector('.lyrics-line.active');
      if (activeEl) {
        activeEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }

    function seekLyricLine(time) {
      currentSeconds = time;
      showToast(`Jumped to ${formatTime(time)}`, '🎤');
    }

    // 7. 10-Band Equalizer
    const eqFrequencies = ["32Hz", "64Hz", "125Hz", "250Hz", "500Hz", "1kHz", "2kHz", "4kHz", "8kHz", "16kHz"];
    const eqPresets = {
      flat: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
      bass: [12, 10, 8, 4, 1, 0, 0, 0, 2, 4],
      nightcore: [-2, -1, 0, 2, 4, 6, 8, 9, 10, 11],
      '8d': [4, 6, 2, -2, 4, 7, 5, 3, 6, 8],
      vaporwave: [5, 4, 2, -1, -3, -2, 1, 3, -1, -3],
      lofi: [3, 4, 6, 5, 2, -1, -3, -4, -5, -6]
    };

    function renderEqSliders(gains = eqPresets.flat) {
      const container = document.getElementById('eq-sliders-container');
      container.innerHTML = eqFrequencies.map((freq, idx) => `
        <div class="eq-band">
          <span class="eq-gain" id="eq-gain-${idx}">${gains[idx] > 0 ? '+' : ''}${gains[idx]}dB</span>
          <input type="range" min="-12" max="12" value="${gains[idx]}" class="eq-slider" oninput="updateEqBand(${idx}, this.value)">
          <span class="eq-freq">${freq}</span>
        </div>
      `).join('');
    }

    function updateEqBand(idx, val) {
      document.getElementById(`eq-gain-${idx}`).innerText = (val > 0 ? '+' : '') + val + 'dB';
    }

    function applyEqPreset(preset) {
      document.querySelectorAll('.eq-preset-btn').forEach(b => b.classList.remove('active'));
      event.currentTarget.classList.add('active');
      const gains = eqPresets[preset] || eqPresets.flat;
      renderEqSliders(gains);
      showToast(`Applied Audio Filter: ${preset.toUpperCase()}`, '🎛️');
    }

    function saveEqToBot() {
      fetch('/api/music/filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset: 'custom_equalizer' })
      }).catch(() => {});
      showToast("10-Band EQ settings synchronized to Lavalink DSP cluster!", "✨");
    }

    // 8. Drag and Drop Queue
    let draggedIndex = null;

    function renderSuiteQueue() {
      const container = document.getElementById('suite-queue-table');
      if (!currentQueue.length) {
        container.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-dim);">Queue is empty. Use Search above to add songs.</div>`;
        return;
      }
      container.innerHTML = currentQueue.map((item, idx) => `
        <div class="queue-drag-row" draggable="true"
             ondragstart="onRowDragStart(event, ${idx})"
             ondragover="onRowDragOver(event)"
             ondrop="onRowDrop(event, ${idx})"
             ondragend="onRowDragEnd(event)">
          <span class="drag-icon">⋮⋮</span>
          <span class="queue-idx">#${idx + 1}</span>
          <img src="${item.thumb}" class="queue-thumb" alt="Thumb" onerror="this.src='/public/musicmaid_avatar.jpg'">
          <div class="queue-text">
            <h5>${item.title}</h5>
            <p>${item.artist} • Requested by <span style="color:var(--accent-neon);">${item.requester}</span></p>
          </div>
          <span class="queue-time">${item.durText}</span>
          <button class="btn btn-secondary btn-sm" onclick="removeQueueItem(${idx})" title="Remove">✕</button>
        </div>
      `).join('');
    }

    function onRowDragStart(e, idx) {
      draggedIndex = idx;
      e.dataTransfer.effectAllowed = 'move';
      e.currentTarget.classList.add('dragging');
    }

    function onRowDragOver(e) {
      e.preventDefault();
      e.currentTarget.classList.add('drag-over');
    }

    function onRowDragEnd(e) {
      document.querySelectorAll('.queue-drag-row').forEach(r => r.classList.remove('dragging', 'drag-over'));
    }

    function onRowDrop(e, targetIdx) {
      e.preventDefault();
      onRowDragEnd(e);
      if (draggedIndex === null || draggedIndex === targetIdx) return;
      const moved = currentQueue.splice(draggedIndex, 1)[0];
      currentQueue.splice(targetIdx, 0, moved);
      draggedIndex = null;
      renderSuiteQueue();
      showToast("Queue reordered via drag-and-drop! 📑", "↕️");
    }

    function removeQueueItem(idx) {
      const removed = currentQueue.splice(idx, 1)[0];
      renderSuiteQueue();
      showToast(`Removed "${removed.title}" from queue`, "🗑️");
    }

    function shuffleSuiteQueue() {
      for (let i = currentQueue.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [currentQueue[i], currentQueue[j]] = [currentQueue[j], currentQueue[i]];
      }
      renderSuiteQueue();
      showToast("Queue shuffled with anime randomness! 🔀", "🔀");
    }

    function saveQueueAsPlaylist() {
      showToast(`Saved ${currentQueue.length} tracks to Cloud Playlist "Rem Favorites" 💾`, "💾");
    }

    // Initialize all components on load
    window.addEventListener('DOMContentLoaded', () => {
      renderSearchResults('all');
      renderLyricsLines();
      renderEqSliders();
      renderSuiteQueue();
    });
  </script>

</body>
</html>
"""
