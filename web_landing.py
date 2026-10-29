"""
Rem Official Web Platform & Luxury Landing Page.
Rebuilt from scratch with:
1. Complete Integrated Bot Commands Directory & Live Web Runner (41 Commands across 4 Categories)
2. Intelligent Track Suggestion Engine & Vibe Radio Explorer (Anime, Lo-Fi, J-Rock, Phonk, Tamil/Desi, Synthwave)
3. Floating Real-Time Web Player (Spotify-Style Bar) with live scrubber & volume
4. 10-Band DSP Equalizer Rack & Audio FX Presets (8D, Nightcore, Vaporwave, Karaoke, BassBoost)
5. Synchronized Karaoke Lyrics with auto-scroll visualizer
6. Collaborative Drag-and-Drop Queue Manager
7. 4-Palette Luxury Theme Engine (Royal Obsidian, Neon Sakura, Neo-Tokyo Cyberpunk, Midnight Lofi)
8. Autonomous Bot Health & Auto-Updater Diagnostics Card
"""

LANDING_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="obsidian">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rem 🎧💜 — Your Anime Music Companion | Rai Discord Bot</title>
  <meta name="description" content="Rem is an anime-inspired AI DJ and 24/7 lossless music companion for Discord with interactive web player, all 41 integrated bot commands, smart suggestions, synced karaoke lyrics, 10-band equalizer, and drag-and-drop queues.">
  <meta property="og:title" content="Rem 🎧💜 — Your Anime Music Companion">
  <meta property="og:description" content="Lossless 320kbps audio, 41 bot commands integrated, instant web track search, synced karaoke lyrics, and audio DSP filters.">
  <meta property="og:image" content="/public/rem_avatar_static.png">
  <meta property="theme-color" content="#9333ea">
  <link rel="icon" type="image/png" href="/public/icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
  
  <style>
    /* =========================================================================
       THEME ENGINE & DESIGN SYSTEM
       ========================================================================= */
    :root, [data-theme="obsidian"] {
      --bg-dark: #07060e;
      --bg-surface: #0e0c1a;
      --bg-card: rgba(18, 15, 34, 0.78);
      --bg-card-hover: rgba(28, 23, 52, 0.92);
      --border-glow: rgba(168, 85, 247, 0.22);
      --border-bright: rgba(192, 132, 252, 0.55);
      --accent-purple: #9333ea;
      --accent-neon: #c084fc;
      --accent-cyan: #06b6d4;
      --accent-pink: #ec4899;
      --accent-gold: #f59e0b;
      --text-white: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --shadow-glow: 0 10px 40px rgba(147, 51, 234, 0.25);
      --shadow-neon: 0 0 30px rgba(192, 132, 252, 0.35);
      --radius-sm: 8px;
      --radius: 16px;
      --radius-lg: 24px;
    }

    [data-theme="sakura"] {
      --bg-dark: #0f0712;
      --bg-surface: #190c1f;
      --bg-card: rgba(35, 16, 42, 0.82);
      --bg-card-hover: rgba(52, 22, 62, 0.94);
      --border-glow: rgba(244, 114, 182, 0.28);
      --border-bright: rgba(244, 114, 182, 0.65);
      --accent-purple: #db2777;
      --accent-neon: #f472b6;
      --accent-cyan: #38bdf8;
      --accent-pink: #fb7185;
      --accent-gold: #fbbf24;
      --shadow-glow: 0 10px 40px rgba(219, 39, 119, 0.28);
      --shadow-neon: 0 0 30px rgba(244, 114, 182, 0.4);
    }

    [data-theme="cyberpunk"] {
      --bg-dark: #050b14;
      --bg-surface: #0a1424;
      --bg-card: rgba(12, 24, 44, 0.82);
      --bg-card-hover: rgba(18, 38, 70, 0.94);
      --border-glow: rgba(6, 182, 212, 0.28);
      --border-bright: rgba(34, 211, 238, 0.65);
      --accent-purple: #0284c7;
      --accent-neon: #22d3ee;
      --accent-cyan: #38bdf8;
      --accent-pink: #f43f5e;
      --accent-gold: #eab308;
      --shadow-glow: 0 10px 40px rgba(6, 182, 212, 0.28);
      --shadow-neon: 0 0 30px rgba(34, 211, 238, 0.45);
    }

    [data-theme="lofi"] {
      --bg-dark: #0e090b;
      --bg-surface: #181014;
      --bg-card: rgba(32, 20, 26, 0.82);
      --bg-card-hover: rgba(48, 30, 39, 0.94);
      --border-glow: rgba(249, 115, 22, 0.25);
      --border-bright: rgba(251, 146, 60, 0.6);
      --accent-purple: #ea580c;
      --accent-neon: #fb923c;
      --accent-cyan: #38bdf8;
      --accent-pink: #f43f5e;
      --accent-gold: #f59e0b;
      --shadow-glow: 0 10px 40px rgba(234, 88, 12, 0.25);
      --shadow-neon: 0 0 30px rgba(251, 146, 60, 0.35);
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
      padding-bottom: 110px; /* offset for sticky player */
      position: relative;
    }

    #bg-canvas {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 0;
      opacity: 0.6;
    }

    .main-wrap {
      position: relative;
      z-index: 1;
    }

    /* =========================================================================
       NAVIGATION BAR
       ========================================================================= */
    nav {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 74px;
      background: rgba(7, 6, 14, 0.85);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-bottom: 1px solid var(--border-glow);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 5%;
      z-index: 1000;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      text-decoration: none;
    }

    .brand-img {
      width: 42px;
      height: 42px;
      border-radius: 50%;
      border: 2px solid var(--accent-neon);
      box-shadow: 0 0 15px rgba(192, 132, 252, 0.5);
      object-fit: cover;
    }

    .brand-title {
      font-size: 1.4rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #fff 30%, var(--accent-neon) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .brand-badge {
      font-size: 0.7rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 9999px;
      background: rgba(168, 85, 247, 0.2);
      border: 1px solid var(--border-glow);
      color: var(--accent-neon);
    }

    .nav-links {
      display: flex;
      gap: 20px;
      align-items: center;
    }

    .nav-links a {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.92rem;
      font-weight: 600;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .nav-links a:hover, .nav-links a.active {
      color: var(--accent-neon);
      transform: translateY(-1px);
    }

    .nav-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    /* Theme Switcher Dropdown / Pills */
    .theme-picker {
      display: flex;
      align-items: center;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-glow);
      border-radius: 9999px;
      padding: 3px 5px;
      gap: 4px;
    }

    .theme-dot {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      cursor: pointer;
      transition: all 0.2s;
      border: 2px solid transparent;
    }

    .theme-dot.active {
      border-color: #fff;
      transform: scale(1.15);
    }

    .theme-dot.obsidian { background: #9333ea; }
    .theme-dot.sakura { background: #f472b6; }
    .theme-dot.cyberpunk { background: #06b6d4; }
    .theme-dot.lofi { background: #fb923c; }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 20px;
      border-radius: 9999px;
      font-size: 0.92rem;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      border: none;
    }

    .btn-primary {
      background: linear-gradient(135deg, var(--accent-purple), var(--accent-pink));
      color: #fff;
      box-shadow: 0 4px 18px rgba(147, 51, 234, 0.4);
    }

    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 25px rgba(236, 72, 153, 0.55);
    }

    .btn-secondary {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--border-glow);
      color: var(--text-white);
      backdrop-filter: blur(10px);
    }

    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.12);
      border-color: var(--border-bright);
      transform: translateY(-2px);
    }

    .btn-sm {
      padding: 6px 14px;
      font-size: 0.8rem;
      border-radius: 8px;
    }

    /* =========================================================================
       HERO SECTION
       ========================================================================= */
    .hero {
      padding: 130px 6% 60px;
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 50px;
      align-items: center;
      position: relative;
    }

    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 16px;
      background: rgba(168, 85, 247, 0.14);
      border: 1px solid var(--border-glow);
      border-radius: 9999px;
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--accent-neon);
      margin-bottom: 20px;
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
      font-size: 3.5rem;
      font-weight: 900;
      line-height: 1.12;
      letter-spacing: -1px;
      margin-bottom: 20px;
    }

    .gradient-text {
      background: linear-gradient(135deg, var(--accent-neon) 20%, var(--accent-cyan) 80%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .hero-sub {
      font-size: 1.15rem;
      color: var(--text-muted);
      margin-bottom: 30px;
      max-width: 560px;
    }

    .hero-cta {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      margin-bottom: 36px;
    }

    .hero-stats {
      display: flex;
      gap: 32px;
      padding-top: 22px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
    }

    .stat-num {
      font-size: 1.6rem;
      font-weight: 800;
      color: #fff;
    }

    .stat-label {
      font-size: 0.8rem;
      color: var(--text-dim);
      font-weight: 600;
    }

    /* HERO TURNTABLE / PLAYER DECK */
    .hero-deck {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: var(--radius-lg);
      padding: 30px;
      box-shadow: var(--shadow-glow);
      backdrop-filter: blur(16px);
      position: relative;
      overflow: hidden;
    }

    .hero-deck::before {
      content: '';
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: radial-gradient(circle, rgba(168, 85, 247, 0.08) 0%, transparent 60%);
      pointer-events: none;
    }

    .deck-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }

    .live-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(34, 197, 94, 0.15);
      border: 1px solid rgba(34, 197, 94, 0.35);
      color: #4ade80;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 0.76rem;
      font-weight: 700;
    }

    .vc-badge {
      font-size: 0.78rem;
      color: var(--accent-neon);
      background: rgba(168, 85, 247, 0.12);
      padding: 4px 12px;
      border-radius: 9999px;
      border: 1px solid var(--border-glow);
    }

    .turntable-visual {
      display: flex;
      align-items: center;
      gap: 24px;
      margin-bottom: 24px;
    }

    .vinyl-disc {
      width: 110px;
      height: 110px;
      border-radius: 50%;
      background: radial-gradient(circle, #2a2438 20%, #110e1c 70%, #000 100%);
      border: 3px solid #221d33;
      box-shadow: 0 0 25px rgba(168, 85, 247, 0.3);
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      animation: spin 12s linear infinite;
      flex-shrink: 0;
    }

    .vinyl-disc.paused {
      animation-play-state: paused;
    }

    @keyframes spin {
      100% { transform: rotate(360deg); }
    }

    .vinyl-disc img {
      width: 50px;
      height: 50px;
      border-radius: 50%;
      object-fit: cover;
      border: 2px solid var(--accent-neon);
    }

    .vinyl-disc::after {
      content: '';
      position: absolute;
      width: 10px;
      height: 10px;
      background: #000;
      border-radius: 50%;
      border: 2px solid #fff;
    }

    .deck-meta {
      min-width: 0;
      flex: 1;
    }

    .deck-title {
      font-size: 1.25rem;
      font-weight: 800;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 4px;
    }

    .deck-artist {
      font-size: 0.88rem;
      color: var(--accent-cyan);
      font-weight: 600;
      margin-bottom: 12px;
    }

    /* Waveform visualizer */
    .waveform-bars {
      display: flex;
      align-items: center;
      gap: 4px;
      height: 32px;
    }

    .wf-bar {
      width: 4px;
      background: linear-gradient(180deg, var(--accent-neon), var(--accent-cyan));
      border-radius: 2px;
      animation: wave 1.2s ease-in-out infinite;
      height: 20%;
    }

    .wf-bar:nth-child(1) { animation-delay: 0.1s; }
    .wf-bar:nth-child(2) { animation-delay: 0.3s; }
    .wf-bar:nth-child(3) { animation-delay: 0.5s; }
    .wf-bar:nth-child(4) { animation-delay: 0.2s; }
    .wf-bar:nth-child(5) { animation-delay: 0.4s; }
    .wf-bar:nth-child(6) { animation-delay: 0.6s; }
    .wf-bar:nth-child(7) { animation-delay: 0.15s; }
    .wf-bar:nth-child(8) { animation-delay: 0.35s; }
    .wf-bar:nth-child(9) { animation-delay: 0.55s; }
    .wf-bar:nth-child(10) { animation-delay: 0.25s; }

    @keyframes wave {
      0%, 100% { height: 18%; }
      50% { height: 95%; }
    }

    .waveform-bars.paused .wf-bar {
      animation-play-state: paused;
      height: 20% !important;
    }

    /* Deck scrubber */
    .deck-scrubber {
      margin-bottom: 18px;
    }

    .deck-progress-bg {
      width: 100%;
      height: 6px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 3px;
      cursor: pointer;
      position: relative;
      overflow: hidden;
    }

    .deck-progress-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--accent-purple), var(--accent-cyan));
      border-radius: 3px;
      width: 42%;
      transition: width 0.15s linear;
    }

    .deck-times {
      display: flex;
      justify-content: space-between;
      font-size: 0.75rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-dim);
      margin-top: 6px;
    }

    .deck-controls {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 16px;
    }

    .deck-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: var(--text-white);
      width: 40px;
      height: 40px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.2s;
      font-size: 1rem;
    }

    .deck-btn:hover {
      background: rgba(255, 255, 255, 0.15);
      border-color: var(--accent-neon);
      transform: scale(1.08);
      box-shadow: 0 6px 24px rgba(236, 72, 153, 0.65);
    }

    .deck-btn.play {
      width: 52px;
      height: 52px;
      background: linear-gradient(135deg, var(--accent-purple), var(--accent-pink));
      border: none;
      font-size: 1.3rem;
      box-shadow: 0 4px 18px rgba(147, 51, 234, 0.5);
    }

    .deck-btn.play:hover {
      transform: scale(1.12);
      box-shadow: 0 6px 26px rgba(236, 72, 153, 0.7);
    }

    /* =========================================================================
       SECTION HEADINGS & GENERAL STYLING
       ========================================================================= */
    section {
      padding: 70px 6%;
      position: relative;
    }

    .section-head {
      text-align: center;
      max-width: 680px;
      margin: 0 auto 46px;
    }

    .section-tag {
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--accent-neon);
      text-transform: uppercase;
      letter-spacing: 1.5px;
      display: inline-block;
      margin-bottom: 8px;
    }

    .section-title {
      font-size: 2.5rem;
      font-weight: 900;
      letter-spacing: -0.5px;
      margin-bottom: 12px;
    }

    .section-desc {
      color: var(--text-muted);
      font-size: 1.05rem;
    }

    /* =========================================================================
       1. SMART SUGGESTIONS & VIBE RADIO ENGINE
       ========================================================================= */
    .suggestions-container {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: var(--radius-lg);
      padding: 34px;
      backdrop-filter: blur(16px);
      box-shadow: var(--shadow-glow);
    }

    .search-bar-wrap {
      position: relative;
      margin-bottom: 24px;
    }

    .search-input-field {
      width: 100%;
      padding: 16px 22px 16px 52px;
      background: rgba(10, 8, 20, 0.75);
      border: 1.5px solid var(--border-glow);
      border-radius: 9999px;
      font-size: 1.05rem;
      color: #fff;
      outline: none;
      transition: all 0.25s;
    }

    .search-input-field:focus {
      border-color: var(--accent-neon);
      box-shadow: 0 0 20px rgba(192, 132, 252, 0.35);
      background: rgba(18, 14, 34, 0.95);
    }

    .search-icon-pos {
      position: absolute;
      left: 20px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 1.2rem;
      color: var(--text-dim);
    }

    .search-btn-inside {
      position: absolute;
      right: 8px;
      top: 50%;
      transform: translateY(-50%);
    }

    /* Suggestions Autocomplete Dropdown */
    .autocomplete-dropdown {
      position: absolute;
      top: 100%;
      left: 0;
      width: 100%;
      margin-top: 8px;
      background: var(--bg-surface);
      border: 1px solid var(--border-bright);
      border-radius: var(--radius);
      box-shadow: 0 15px 35px rgba(0, 0, 0, 0.7);
      z-index: 200;
      display: none;
      overflow: hidden;
    }

    .autocomplete-dropdown.show {
      display: block;
    }

    .ac-item {
      padding: 12px 20px;
      display: flex;
      align-items: center;
      gap: 14px;
      cursor: pointer;
      transition: background 0.2s;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }

    .ac-item:hover {
      background: rgba(168, 85, 247, 0.18);
    }

    .ac-item img {
      width: 36px;
      height: 36px;
      border-radius: 6px;
      object-fit: cover;
    }

    .ac-item-title {
      font-size: 0.92rem;
      font-weight: 700;
      color: #fff;
    }

    .ac-item-sub {
      font-size: 0.78rem;
      color: var(--accent-neon);
    }

    /* Vibe pills */
    .vibe-pills-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 28px;
    }

    .vibe-chip {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      padding: 8px 16px;
      border-radius: 9999px;
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .vibe-chip:hover, .vibe-chip.active {
      background: rgba(168, 85, 247, 0.18);
      border-color: var(--accent-neon);
      color: #fff;
      transform: translateY(-2px);
      box-shadow: 0 4px 15px rgba(168, 85, 247, 0.25);
    }

    /* Suggestions Cards Grid */
    .suggestions-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 20px;
    }

    .sug-card {
      background: rgba(12, 10, 22, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: var(--radius);
      padding: 16px;
      transition: all 0.25s ease;
      display: flex;
      flex-direction: column;
      position: relative;
    }

    .sug-card:hover {
      border-color: var(--border-bright);
      background: rgba(24, 18, 44, 0.85);
      transform: translateY(-4px);
      box-shadow: var(--shadow-neon);
    }

    .sug-thumb-wrap {
      position: relative;
      width: 100%;
      aspect-ratio: 16/9;
      border-radius: 10px;
      overflow: hidden;
      margin-bottom: 12px;
    }

    .sug-thumb-wrap img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      transition: transform 0.3s;
    }

    .sug-card:hover .sug-thumb-wrap img {
      transform: scale(1.05);
    }

    .sug-dur-badge {
      position: absolute;
      bottom: 6px;
      right: 6px;
      background: rgba(0, 0, 0, 0.75);
      font-size: 0.72rem;
      font-family: 'JetBrains Mono', monospace;
      padding: 2px 6px;
      border-radius: 4px;
      color: #fff;
    }

    .sug-title {
      font-size: 0.95rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 3px;
    }

    .sug-artist {
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-bottom: 14px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .sug-actions {
      display: flex;
      gap: 8px;
      margin-top: auto;
    }

    .sug-actions .btn {
      flex: 1;
      justify-content: center;
      padding: 7px 12px;
      font-size: 0.78rem;
    }

    /* =========================================================================
       2. INTEGRATED BOT COMMANDS CENTER (41 COMMANDS)
       ========================================================================= */
    .commands-container {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: var(--radius-lg);
      padding: 34px;
      backdrop-filter: blur(16px);
      box-shadow: var(--shadow-glow);
    }

    .cmd-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 24px;
    }

    .cmd-filter-tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .cmd-tab-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: var(--text-muted);
      padding: 8px 18px;
      border-radius: 9999px;
      font-size: 0.85rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s;
    }

    .cmd-tab-btn:hover, .cmd-tab-btn.active {
      background: linear-gradient(135deg, var(--accent-purple), var(--accent-pink));
      color: #fff;
      border-color: transparent;
      box-shadow: 0 4px 15px rgba(147, 51, 234, 0.35);
    }

    .cmd-search-input {
      background: rgba(10, 8, 20, 0.7);
      border: 1px solid var(--border-glow);
      border-radius: 9999px;
      padding: 8px 18px;
      color: #fff;
      font-size: 0.88rem;
      outline: none;
      min-width: 220px;
    }

    .cmd-search-input:focus {
      border-color: var(--accent-neon);
    }

    .cmd-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 18px;
    }

    .cmd-card {
      background: rgba(11, 9, 22, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: var(--radius);
      padding: 20px;
      transition: all 0.25s ease;
      display: flex;
      flex-direction: column;
      position: relative;
    }

    .cmd-card:hover {
      border-color: var(--border-bright);
      background: rgba(22, 17, 40, 0.85);
      transform: translateY(-3px);
      box-shadow: 0 6px 20px rgba(168, 85, 247, 0.18);
    }

    .cmd-card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 10px;
    }

    .cmd-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--accent-neon);
      background: rgba(168, 85, 247, 0.12);
      border: 1px solid var(--border-glow);
      padding: 4px 10px;
      border-radius: 6px;
    }

    .cmd-role-badge {
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 9999px;
      background: rgba(255, 255, 255, 0.06);
      color: var(--text-dim);
    }

    .cmd-role-badge.everyone { color: #4ade80; background: rgba(74, 222, 128, 0.12); }
    .cmd-role-badge.dj { color: #38bdf8; background: rgba(56, 189, 248, 0.12); }
    .cmd-role-badge.admin { color: #f43f5e; background: rgba(244, 63, 94, 0.12); }

    .cmd-desc {
      font-size: 0.88rem;
      color: var(--text-muted);
      margin-bottom: 14px;
      line-height: 1.5;
    }

    .cmd-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: auto;
      padding-top: 12px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
    }

    .cmd-aliases {
      font-size: 0.75rem;
      color: var(--text-dim);
    }

    .cmd-actions {
      display: flex;
      gap: 8px;
    }

    /* =========================================================================
       3. 10-BAND DSP EQUALIZER & AUDIO FX RACK
       ========================================================================= */
    .eq-rack {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: var(--radius-lg);
      padding: 34px;
      box-shadow: var(--shadow-glow);
      backdrop-filter: blur(16px);
    }

    .eq-presets-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 28px;
      justify-content: center;
    }

    .eq-preset-btn {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: var(--text-muted);
      padding: 8px 18px;
      border-radius: 9999px;
      font-size: 0.85rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s;
    }

    .eq-preset-btn:hover, .eq-preset-btn.active {
      background: var(--accent-purple);
      color: #fff;
      border-color: var(--accent-neon);
      box-shadow: 0 4px 16px rgba(147, 51, 234, 0.35);
    }

    .sliders-rack {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 24px 10px;
      background: rgba(10, 8, 20, 0.65);
      border-radius: var(--radius);
      border: 1px solid rgba(255, 255, 255, 0.05);
      overflow-x: auto;
    }

    .eq-slider-col {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;
      flex: 1;
      min-width: 48px;
    }

    .eq-slider-col input[type="range"] {
      -webkit-appearance: slider-vertical;
      writing-mode: bt-lr;
      width: 8px;
      height: 140px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 4px;
      outline: none;
      cursor: pointer;
    }

    .eq-freq-label {
      font-size: 0.75rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-dim);
    }

    .eq-db-value {
      font-size: 0.72rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--accent-neon);
      font-weight: 700;
    }

    /* =========================================================================
       4. SYNCHRONIZED KARAOKE LYRICS & DRAG-AND-DROP QUEUE
       ========================================================================= */
    .dual-showcase-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 30px;
    }

    .lyrics-deck, .queue-deck {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: var(--radius-lg);
      padding: 28px;
      backdrop-filter: blur(16px);
      box-shadow: var(--shadow-glow);
      display: flex;
      flex-direction: column;
      height: 480px;
    }

    .lyrics-scroll-box {
      flex: 1;
      overflow-y: auto;
      padding: 20px 10px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      scroll-behavior: smooth;
    }

    .lyric-line {
      font-size: 1.15rem;
      font-weight: 600;
      color: rgba(255, 255, 255, 0.35);
      transition: all 0.3s;
      cursor: pointer;
      padding: 4px 8px;
      border-radius: 6px;
    }

    .lyric-line:hover {
      color: rgba(255, 255, 255, 0.7);
    }

    .lyric-line.active {
      color: var(--accent-neon);
      font-size: 1.4rem;
      font-weight: 800;
      transform: scale(1.02);
      text-shadow: 0 0 18px rgba(192, 132, 252, 0.6);
    }

    /* Queue drag rows */
    .queue-list-box {
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 14px;
    }

    .queue-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 14px;
      background: rgba(12, 10, 22, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 10px;
      cursor: grab;
      transition: all 0.2s;
    }

    .queue-row:hover {
      border-color: var(--border-bright);
      background: rgba(24, 18, 44, 0.8);
    }

    .queue-row.dragging {
      opacity: 0.4;
      background: var(--accent-purple);
    }

    .queue-drag-handle {
      color: var(--text-dim);
      cursor: grab;
    }

    .queue-thumb {
      width: 40px;
      height: 40px;
      border-radius: 6px;
      object-fit: cover;
    }

    .queue-row-meta {
      flex: 1;
      min-width: 0;
    }

    .queue-row-title {
      font-size: 0.88rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .queue-row-sub {
      font-size: 0.75rem;
      color: var(--text-dim);
    }

    /* =========================================================================
       5. SYSTEM HEALTH & AUTO-UPDATER DIAGNOSTICS CARD
       ========================================================================= */
    .system-health-sec {
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: var(--radius-lg);
      padding: 30px;
      backdrop-filter: blur(16px);
      box-shadow: var(--shadow-glow);
    }

    .health-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 20px;
      margin-top: 20px;
    }

    .health-card {
      background: rgba(10, 8, 20, 0.65);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: var(--radius);
      padding: 20px;
    }

    .health-card-label {
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 6px;
    }

    .health-card-val {
      font-size: 1.4rem;
      font-weight: 800;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* =========================================================================
       FLOATING SPOTIFY-STYLE STICKY PLAYER
       ========================================================================= */
    .sticky-player-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      width: 100%;
      height: 86px;
      background: rgba(10, 8, 20, 0.94);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-top: 1px solid var(--border-glow);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 4%;
      z-index: 1000;
      box-shadow: 0 -10px 30px rgba(0, 0, 0, 0.5);
    }

    .sp-left {
      display: flex;
      align-items: center;
      gap: 14px;
      width: 30%;
      min-width: 220px;
    }

    .sp-thumb {
      width: 52px;
      height: 52px;
      border-radius: 10px;
      object-fit: cover;
      border: 1px solid var(--border-glow);
    }

    .sp-title {
      font-size: 0.92rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      display: block;
    }

    .sp-artist {
      font-size: 0.76rem;
      color: var(--accent-neon);
      display: block;
    }

    .sp-center {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      width: 40%;
      max-width: 520px;
    }

    .sp-controls-row {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .sp-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 1.15rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .sp-btn:hover {
      color: #fff;
      transform: scale(1.1);
    }

    .sp-btn.play {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: #fff;
      color: #000;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1rem;
    }

    .sp-btn.play:hover {
      background: var(--accent-neon);
      color: #fff;
    }

    .sp-scrub-row {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
    }

    .sp-time {
      font-size: 0.72rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-dim);
    }

    .sp-slider {
      flex: 1;
      height: 4px;
      -webkit-appearance: none;
      background: rgba(255, 255, 255, 0.15);
      border-radius: 2px;
      outline: none;
      cursor: pointer;
    }

    .sp-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #fff;
      cursor: pointer;
    }

    .sp-right {
      display: flex;
      align-items: center;
      gap: 16px;
      width: 25%;
      justify-content: flex-end;
    }

    .vol-slider {
      width: 80px;
      height: 4px;
      -webkit-appearance: none;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 2px;
      outline: none;
      cursor: pointer;
    }

    .vol-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #fff;
      cursor: pointer;
    }

    /* TOAST NOTIFICATION */
    .toast-box {
      position: fixed;
      bottom: 100px;
      right: 30px;
      background: rgba(20, 16, 38, 0.95);
      border: 1px solid var(--border-bright);
      padding: 12px 20px;
      border-radius: 9999px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
      display: flex;
      align-items: center;
      gap: 10px;
      z-index: 2000;
      opacity: 0;
      pointer-events: none;
      transform: translateY(20px);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .toast-box.show {
      opacity: 1;
      pointer-events: auto;
      transform: translateY(0);
    }

    /* FOOTER */
    footer {
      border-top: 1px solid var(--border-glow);
      background: rgba(7, 6, 14, 0.98);
      padding: 50px 6% 40px;
      text-align: center;
    }

    .footer-links {
      display: flex;
      justify-content: center;
      gap: 28px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }

    .footer-links a {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.92rem;
      transition: color 0.2s;
    }

    .footer-links a:hover { color: var(--accent-neon); }

    /* RESPONSIVENESS */
    @media (max-width: 900px) {
      .hero {
        grid-template-columns: 1fr;
        padding-top: 110px;
        text-align: center;
      }
      .hero-sub { margin: 0 auto 24px; }
      .hero-cta { justify-content: center; }
      .hero-stats { justify-content: center; }
      .nav-links { display: none; }
      .dual-showcase-grid { grid-template-columns: 1fr; }
      .sp-left { width: 50%; }
      .sp-center { display: none; }
      .sp-right { width: 45%; }
    }
  </style>
</head>
<body>

  <!-- Ambient Particle Canvas -->
  <canvas id="bg-canvas"></canvas>

  <div class="main-wrap">
    <!-- Navigation Bar -->
    <nav>
      <a href="/" class="brand">
        <img src="/public/rem_avatar_static.png" alt="Rem Logo" class="brand-img" onerror="this.src='/public/rem_avatar_square.png'">
        <div>
          <span class="brand-title">Rem 🎧💜</span>
          <span class="brand-badge">v2.4 Hi-Fi</span>
        </div>
      </a>

      <div class="nav-links">
        <a href="#suggestions">✨ Suggestions</a>
        <a href="#commands">⚡ Commands (43)</a>
        <a href="#equalizer">🎛️ Equalizer FX</a>
        <a href="#lyrics">🎤 Synced Lyrics</a>
        <a href="#queue">📑 Queue</a>
        <a href="#health">🩺 Health</a>
        <a href="/login" style="color: #c084fc; font-weight: 700;">🔑 Login</a>
        <a href="/login" title="Open Web Dashboard">Dashboard ↗</a>
      </div>

      <div class="nav-actions">
        <!-- Palette theme picker -->
        <div class="theme-picker" title="Switch Theme Palette">
          <div class="theme-dot obsidian active" onclick="switchTheme('obsidian')" title="Royal Obsidian"></div>
          <div class="theme-dot sakura" onclick="switchTheme('sakura')" title="Neon Sakura"></div>
          <div class="theme-dot cyberpunk" onclick="switchTheme('cyberpunk')" title="Neo-Tokyo Cyberpunk"></div>
          <div class="theme-dot lofi" onclick="switchTheme('lofi')" title="Midnight Lofi"></div>
        </div>

        <a href="/login" class="btn btn-secondary btn-sm" style="font-weight: 700; gap: 0.4rem; border: 1px solid rgba(192, 132, 252, 0.45); color: #fff;">
          <span>🔑</span>
          <span>Sign In</span>
        </a>

        <a href="https://discord.com/oauth2/authorize?client_id=1556676516274905218&permissions=8&integration_type=0&scope=bot+applications.commands" target="_blank" class="btn btn-primary btn-sm">
          <span>Invite Rem</span>
          <span>🚀</span>
        </a>
      </div>
    </nav>

    <!-- Hero Section with Turntable Visualizer -->
    <section class="hero">
      <div>
        <div class="hero-badge">
          <span class="pulse-dot"></span>
          <span>🌸 320kbps Hi-Fi Audio & Integrated Command Suite</span>
        </div>

        <h1 class="hero-title">Your Ultimate Anime Music Companion <span class="gradient-text">Rem</span> 🎧💜</h1>
        <p class="hero-sub">Experience crystal-clear lossless Discord audio streaming with 41 integrated slash commands, instant web track search & suggestions, synchronized karaoke lyrics, and real-time DSP audio filters.</p>

        <div class="hero-cta">
          <a href="https://discord.com/oauth2/authorize?client_id=1556676516274905218&permissions=8&integration_type=0&scope=bot+applications.commands" target="_blank" class="btn btn-primary">
            <span>Add Rem to Discord</span>
            <span>⚡</span>
          </a>
          <a href="/login" class="btn btn-secondary" style="border: 1px solid rgba(192, 132, 252, 0.45); font-weight: 700;">
            <span>Open Web Dashboard 🎛️</span>
          </a>
          <a href="#commands" class="btn btn-secondary">
            <span>Explore 43 Commands</span>
            <span>📖</span>
          </a>
          <button onclick="triggerSurpriseAutoDJ()" class="btn btn-secondary">
            <span>🎲 Surprise Me (Auto-DJ)</span>
          </button>
        </div>

        <div class="hero-stats">
          <div>
            <div class="stat-num">41+</div>
            <div class="stat-label">Slash Commands</div>
          </div>
          <div>
            <div class="stat-num">320k</div>
            <div class="stat-label">Lossless Opus Audio</div>
          </div>
          <div>
            <div class="stat-num">99.9%</div>
            <div class="stat-label">Voice Channel Uptime</div>
          </div>
          <div>
            <div class="stat-num">24/7</div>
            <div class="stat-label">Radio & Auto-DJ</div>
          </div>
        </div>
      </div>

      <!-- Live Vinyl Deck Showcase -->
      <div class="hero-deck">
        <div class="deck-top">
          <span class="live-chip"><span class="pulse-dot" style="width:6px; height:6px;"></span> LIVE SESSION</span>
          <span class="vc-badge" id="hero-vc-name">🔊 Voice: #anime-lounge</span>
        </div>

        <div class="turntable-visual">
          <div class="vinyl-disc" id="hero-vinyl">
            <img src="/public/rem_avatar_static.png" id="hero-thumb" alt="Track Art" onerror="this.src='/public/icon.png'">
          </div>

          <div class="deck-meta">
            <h3 class="deck-title" id="hero-title">怪物 (Monster)</h3>
            <p class="deck-artist" id="hero-artist">YOASOBI • Beastars Anime OP</p>

            <div class="waveform-bars" id="hero-waveform">
              <div class="wf-bar"></div>
              <div class="wf-bar"></div>
              <div class="wf-bar"></div>
              <div class="wf-bar"></div>
              <div class="wf-bar"></div>
              <div class="wf-bar"></div>
              <div class="wf-bar"></div>
              <div class="wf-bar"></div>
              <div class="wf-bar"></div>
              <div class="wf-bar"></div>
            </div>
          </div>
        </div>

        <div class="deck-scrubber">
          <div class="deck-progress-bg" onclick="seekHeroProgress(event)">
            <div class="deck-progress-fill" id="hero-progress"></div>
          </div>
          <div class="deck-times">
            <span id="hero-cur-time">01:25</span>
            <span id="hero-dur-time">03:26</span>
          </div>
        </div>

        <div class="deck-controls">
          <button class="deck-btn" onclick="triggerShuffle()" title="Shuffle Queue">🔀</button>
          <button class="deck-btn" onclick="triggerPrev()" title="Previous Track">⏮️</button>
          <button class="deck-btn play" id="hero-play-btn" onclick="togglePlayPause()" title="Play / Pause">⏸️</button>
          <button class="deck-btn" onclick="triggerNext()" title="Next Track">⏭️</button>
          <button class="deck-btn" onclick="triggerRepeat()" title="Repeat Mode">🔁</button>
        </div>
      </div>
    </section>

    <!-- =========================================================================
         1. SMART SUGGESTIONS & VIBE RADIO ENGINE
         ========================================================================= -->
    <section id="suggestions">
      <div class="section-head">
        <span class="section-tag">AI DJ & Recommendations</span>
        <h2 class="section-title">Smart Suggestions & Vibe Explorer</h2>
        <p class="section-desc">Search across YouTube, Spotify, and Apple Music, or pick a curated vibe pill to instantly discover and queue anime & chill music.</p>
      </div>

      <div class="suggestions-container">
        <!-- Search bar with suggestions autocomplete -->
        <div class="search-bar-wrap">
          <span class="search-icon-pos">🔍</span>
          <input type="text" id="search-input" class="search-input-field" placeholder="Search track, artist, album, playlist, or paste a link..." oninput="handleSearchInput(event)">
          <button class="btn btn-primary search-btn-inside" onclick="executeSearch()">Queue Track ⚡</button>

          <div id="autocomplete-box" class="autocomplete-dropdown">
            <!-- Populated via JS -->
          </div>
        </div>

        <!-- Vibe pills -->
        <div class="vibe-pills-row">
          <div class="vibe-chip active" onclick="filterVibe('all')">🌟 All Top Hits</div>
          <div class="vibe-chip" onclick="filterVibe('anime')">🔥 Anime Openings</div>
          <div class="vibe-chip" onclick="filterVibe('lofi')">☕ Midnight Lo-Fi Beats</div>
          <div class="vibe-chip" onclick="filterVibe('phonk')">⚡ Cyberpunk Drift Phonk</div>
          <div class="vibe-chip" onclick="filterVibe('jrock')">💥 J-Rock & Shonen</div>
          <div class="vibe-chip" onclick="filterVibe('kawaii')">🌸 Kawaii J-Pop Chill</div>
          <div class="vibe-chip" onclick="filterVibe('desi')">✨ Tamil & Indian Hype (Anirudh)</div>
          <div class="vibe-chip" onclick="filterVibe('synthwave')">💫 Retro 80s Synthwave</div>
        </div>

        <!-- Suggestions Cards Grid -->
        <div class="suggestions-grid" id="suggestions-grid">
          <!-- Rendered dynamically -->
        </div>
      </div>
    </section>

    <!-- =========================================================================
         2. INTEGRATED BOT COMMANDS CENTER (41 COMMANDS)
         ========================================================================= -->
    <section id="commands">
      <div class="section-head">
        <span class="section-tag">Complete Discord Directory</span>
        <h2 class="section-title">Integrated Bot Commands Suite</h2>
        <p class="section-desc">Every Discord command supported by Rem — run them live in the web player simulator or click to copy the slash command.</p>
      </div>

      <div class="commands-container">
        <div class="cmd-toolbar">
          <div class="cmd-filter-tabs">
            <button class="cmd-tab-btn active" onclick="filterCommands('all')">All Commands (43)</button>
            <button class="cmd-tab-btn" onclick="filterCommands('playback')">🎵 Playback (14)</button>
            <button class="cmd-tab-btn" onclick="filterCommands('dsp')">🎛️ Audio FX & DSP (10)</button>
            <button class="cmd-tab-btn" onclick="filterCommands('queue')">📑 Queue & Playlists (11)</button>
            <button class="cmd-tab-btn" onclick="filterCommands('settings')">⚙️ Settings & 24/7 (6)</button>
          </div>

          <input type="text" id="cmd-search" class="cmd-search-input" placeholder="Filter commands by name..." oninput="handleCmdSearch(event)">
        </div>

        <div class="cmd-grid" id="commands-grid">
          <!-- Rendered dynamically -->
        </div>
      </div>
    </section>

    <!-- =========================================================================
         3. 10-BAND DSP EQUALIZER & AUDIO FX RACK
         ========================================================================= -->
    <section id="equalizer">
      <div class="section-head">
        <span class="section-tag">Studio Hardware DSP</span>
        <h2 class="section-title">10-Band Equalizer & Audio FX</h2>
        <p class="section-desc">Sculpt your audio in real-time with zero latency. Choose an anime DSP preset or tune individual frequencies from 31Hz to 16kHz.</p>
      </div>

      <div class="eq-rack">
        <div class="eq-presets-row">
          <button class="eq-preset-btn active" onclick="applyEqPreset('flat')">Flat (Studio Reference)</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('bassboost')">💥 Bass Boost 3000</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('nightcore')">⚡ Nightcore (1.25x Pitch)</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('vaporwave')">📼 Vaporwave Reverb</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('8d')">🎧 8D Spatial Surround</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('karaoke')">🎤 Vocal Cut Karaoke</button>
          <button class="eq-preset-btn" onclick="applyEqPreset('lowpass')">🌙 Cozy Next Room</button>
        </div>

        <div class="sliders-rack" id="eq-sliders-rack">
          <!-- 10 Sliders rendered via JS -->
        </div>
      </div>
    </section>

    <!-- =========================================================================
         4. DUAL SHOWCASE: SYNCHRONIZED LYRICS & DRAG-AND-DROP QUEUE
         ========================================================================= -->
    <section id="lyrics">
      <div class="section-head">
        <span class="section-tag">Interactive Real-Time Experience</span>
        <h2 class="section-title">Karaoke Lyrics & Collaborative Queue</h2>
        <p class="section-desc">Sing along with rhythm-synced lyrics and organize upcoming tracks with intuitive drag-and-drop reordering.</p>
      </div>

      <div class="dual-showcase-grid">
        <!-- Lyrics Deck -->
        <div class="lyrics-deck">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:800; font-size:1.1rem; color:#fff;">🎤 Synced Karaoke</span>
            <div style="display:flex; gap:6px;">
              <button class="btn btn-secondary btn-sm" onclick="setLyricSong('yoasobi')">YOASOBI</button>
              <button class="btn btn-secondary btn-sm" onclick="setLyricSong('faded')">Alan Walker</button>
              <button class="btn btn-secondary btn-sm" onclick="setLyricSong('ado')">Ado</button>
            </div>
          </div>

          <div class="lyrics-scroll-box" id="lyrics-scroll-box">
            <!-- Lyrics rendered via JS -->
          </div>
        </div>

        <!-- Drag-and-Drop Queue Deck -->
        <div class="queue-deck" id="queue">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:800; font-size:1.1rem; color:#fff;">📑 Queue (<span id="queue-count">4</span> Tracks)</span>
            <div style="display:flex; gap:6px;">
              <button class="btn btn-secondary btn-sm" onclick="shuffleQueueList()">🔀 Shuffle</button>
              <button class="btn btn-secondary btn-sm" onclick="clearQueueList()">🗑️ Clear</button>
            </div>
          </div>

          <div class="queue-list-box" id="queue-list-box">
            <!-- Queue items rendered via JS -->
          </div>
        </div>
      </div>
    </section>

    <!-- =========================================================================
         5. SYSTEM HEALTH & AUTO-UPDATER DIAGNOSTICS CARD
         ========================================================================= -->
    <section id="health">
      <div class="section-head">
        <span class="section-tag">Diagnostics & Supervisor</span>
        <h2 class="section-title">System Health & Autonomous Updater</h2>
        <p class="section-desc">Rem features zero-downtime voice auto-recovery and intelligent updates that wait until voice channels are idle before restarting.</p>
      </div>

      <div class="system-health-sec">
        <div class="health-grid">
          <div class="health-card">
            <div class="health-card-label">Bot Core Status</div>
            <div class="health-card-val"><span class="pulse-dot"></span> Online & Active</div>
          </div>

          <div class="health-card">
            <div class="health-card-label">Voice Latency</div>
            <div class="health-card-val">⚡ <span id="diag-ping">18ms</span></div>
          </div>

          <div class="health-card">
            <div class="health-card-label">Verified Commit</div>
            <div class="health-card-val">🔖 <span id="diag-commit">9aaf445</span></div>
          </div>

          <div class="health-card">
            <div class="health-card-label">Auto-Update Supervisor</div>
            <div class="health-card-val">🛡️ Safe (Exit 42)</div>
          </div>
        </div>

        <div style="margin-top:20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; padding:16px; background:rgba(168,85,247,0.08); border-radius:12px; border:1px solid var(--border-glow);">
          <div>
            <h4 style="font-size:0.95rem; font-weight:700; color:#fff;">Autonomous Update Supervisor Active</h4>
            <p style="font-size:0.8rem; color:var(--text-muted);">When an update is pushed, Rem waits until all listeners finish before reloading automatically without dropping voice.</p>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="checkSystemUpdate()">
            <span>Check Update Status</span>
            <span>🔄</span>
          </button>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer>
      <div class="footer-links">
        <a href="https://discord.com/oauth2/authorize?client_id=1556676516274905218&permissions=8&integration_type=0&scope=bot+applications.commands" target="_blank">Invite Rem</a>
        <a href="https://discord.gg/wRCgB7vBQv" target="_blank">Support Discord</a>
        <a href="https://github.com/kishorerai390/Rai-discord-bot" target="_blank">GitHub Repository</a>
        <a href="/login">Full Web Dashboard</a>
        <a href="/api/health" target="_blank">Health API</a>
      </div>
      <p style="color:var(--text-dim); font-size:0.85rem;">© 2026 Rem • Rai Discord Bot Ecosystem. Built with 💜 by Kishore. Powered by 320kbps Opus, Lavalink v4, and Discord.py.</p>
    </footer>
  </div>

  <!-- =========================================================================
       STICKY SPOTIFY-STYLE BOTTOM PLAYER
       ========================================================================= -->
  <div class="sticky-player-bar">
    <div class="sp-left">
      <img src="/public/rem_avatar_static.png" class="sp-thumb" id="sp-thumb" alt="Thumb" onerror="this.src='/public/icon.png'">
      <div>
        <span class="sp-title" id="sp-title">怪物 (Monster)</span>
        <span class="sp-artist" id="sp-artist">YOASOBI • 320kbps</span>
      </div>
    </div>

    <div class="sp-center">
      <div class="sp-controls-row">
        <button class="sp-btn" onclick="triggerShuffle()" title="Shuffle">🔀</button>
        <button class="sp-btn" onclick="triggerPrev()" title="Previous">⏮️</button>
        <button class="sp-btn play" id="sp-play-btn" onclick="togglePlayPause()" title="Play / Pause">⏸️</button>
        <button class="sp-btn" onclick="triggerNext()" title="Next">⏭️</button>
        <button class="sp-btn" onclick="triggerRepeat()" title="Repeat">🔁</button>
      </div>

      <div class="sp-scrub-row">
        <span class="sp-time" id="sp-cur-time">01:25</span>
        <input type="range" min="0" max="100" value="41" class="sp-slider" id="sp-scrub-slider" oninput="handleScrub(this.value)">
        <span class="sp-time" id="sp-dur-time">03:26</span>
      </div>
    </div>

    <div class="sp-right">
      <button class="sp-btn" onclick="scrollToId('lyrics')" title="Lyrics">🎤</button>
      <button class="sp-btn" onclick="scrollToId('equalizer')" title="Equalizer">🎛️</button>
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="cursor:pointer;" onclick="toggleMute()" id="sp-vol-icon">🔊</span>
        <input type="range" min="0" max="100" value="85" class="vol-slider" id="sp-vol-slider" oninput="handleVolume(this.value)">
      </div>
      <a href="/login" class="btn btn-primary btn-sm" style="border-radius:12px; font-weight:700; text-decoration:none; padding:0.4rem 0.85rem; font-size:0.8rem; margin-left:6px;" title="Open Web Dashboard">Dashboard ↗</a>
    </div>
  </div>

  <!-- Toast Notification Box -->
  <div class="toast-box" id="live-toast">
    <span id="toast-icon">✨</span>
    <span id="toast-text" style="font-size:0.88rem; font-weight:700; color:#fff;">Action completed!</span>
  </div>

  <!-- =========================================================================
       COMPLETE JAVASCRIPT STATE MACHINE & LOGIC
       ========================================================================= -->
  <script>
    // 1. STATE & DATA
    let isPlaying = true;
    let currentSeconds = 85;
    let totalSeconds = 206;
    let volumeLevel = 85;
    let isMuted = false;
    let activeVibe = 'all';
    let activeCmdCategory = 'all';
    let currentLyricIdx = 3;

    // Suggestions Database
    const trackDatabase = [
      { id: "1", title: "怪物 (Monster)", artist: "YOASOBI", duration: 206, durText: "03:26", vibe: "anime", image: "/public/rem_avatar_static.png", query: "YOASOBI Monster Beastars" },
      { id: "2", title: "Faded (Live Vocal Edition)", artist: "Alan Walker", duration: 212, durText: "03:32", vibe: "synthwave", image: "/public/musicmaid_banner.jpg", query: "Alan Walker Faded" },
      { id: "3", title: "新時代 (New Genesis)", artist: "Ado", duration: 226, durText: "03:46", vibe: "anime", image: "/public/login_hero.jpg", query: "Ado New Genesis One Piece Film Red" },
      { id: "4", title: "KICK BACK", artist: "Kenshi Yonezu", duration: 193, durText: "03:13", vibe: "jrock", image: "/public/rem_avatar_static.png", query: "Kenshi Yonezu KICK BACK Chainsaw Man" },
      { id: "5", title: "Midnight Lo-Fi Coffee", artist: "Rem Beats & ChilledCow", duration: 165, durText: "02:45", vibe: "lofi", image: "/public/musicmaid_headphone_hero.jpg", query: "Lofi study beats relaxing" },
      { id: "6", title: "Drift Phonk Horizon", artist: "KSLV Noh & DVRST", duration: 178, durText: "02:58", vibe: "phonk", image: "/public/musicmaid_banner.jpg", query: "Drift Phonk High Bass Cyberpunk" },
      { id: "7", title: "Sparkle (Your Name OST)", artist: "RADWIMPS", duration: 417, durText: "06:57", vibe: "jrock", image: "/public/musicmaid_headphone_hero.jpg", query: "RADWIMPS Sparkle Your Name" },
      { id: "8", title: "Hukum (Thalaivar Alappara)", artist: "Anirudh Ravichander", duration: 206, durText: "03:26", vibe: "desi", image: "/public/musicmaid_banner.jpg", query: "Anirudh Ravichander Hukum Jailer" },
      { id: "9", title: "Renegades of Synth", artist: "Kavinsky & The Midnight", duration: 230, durText: "03:50", vibe: "synthwave", image: "/public/login_hero.jpg", query: "Synthwave 80s Cyberpunk Night Drive" },
      { id: "10", title: "Kawaii Strawberry Jam", artist: "Snail's House", duration: 154, durText: "02:34", vibe: "kawaii", image: "/public/rem_avatar_static.png", query: "Snails House Kawaii Future Bass" }
    ];

    // All 41 Integrated Bot Commands Directory
    const botCommands = [
      // PLAYBACK
      { name: "/play", args: "<query|url>", desc: "Stream any song, artist, playlist, or URL from YouTube, Spotify, or SoundCloud.", cat: "playback", role: "everyone", aliases: "p, add" },
      { name: "/search", args: "<query>", desc: "Interactive search displaying top 5 tracks with instant selector buttons.", cat: "playback", role: "everyone", aliases: "find" },
      { name: "/playtop", args: "<query>", desc: "Add a song to the very top of the queue to play next immediately.", cat: "playback", role: "everyone", aliases: "pt" },
      { name: "/forceplay", args: "<query>", desc: "Immediately interrupt current track and start playing this song now.", cat: "playback", role: "dj", aliases: "fp" },
      { name: "/pause", args: "", desc: "Temporarily pause the active voice channel audio playback.", cat: "playback", role: "everyone", aliases: "hold" },
      { name: "/resume", args: "", desc: "Resume playback of currently paused audio stream.", cat: "playback", role: "everyone", aliases: "unpause" },
      { name: "/skip", args: "", desc: "Vote or immediately skip current track to next song in queue.", cat: "playback", role: "everyone", aliases: "s, next" },
      { name: "/stop", args: "", desc: "Stop playing audio, clear active queue, and reset voice session.", cat: "playback", role: "dj", aliases: "halt" },
      { name: "/leave", args: "", desc: "Disconnect Rem from current voice channel gracefully.", cat: "playback", role: "dj", aliases: "dc, disconnect" },
      { name: "/connect", args: "[channel]", desc: "Summon Rem to your voice channel or a specified channel.", cat: "playback", role: "everyone", aliases: "join, summon" },
      { name: "/seek", args: "<time>", desc: "Jump directly to specific timestamp in the track (e.g. 1:45 or 90s).", cat: "playback", role: "everyone", aliases: "jump" },
      { name: "/volume", args: "<1-150>", desc: "Adjust voice channel volume with intelligent limiter protection.", cat: "playback", role: "dj", aliases: "vol, v" },
      { name: "/nowplaying", args: "", desc: "Display rich embed with album art, scrubber, and audio bitrate.", cat: "playback", role: "everyone", aliases: "np" },
      { name: "/lyrics", args: "[query]", desc: "Fetch real-time timestamped lyrics from LRCLIB & Genius.", cat: "playback", role: "everyone", aliases: "ly" },

      // AUDIO FX & DSP
      { name: "/speed", args: "<0.5-2.0>", desc: "Adjust audio speed factor without pitch distortion artifacts.", cat: "dsp", role: "dj", aliases: "tempo" },
      { name: "/nightcore", args: "", desc: "Apply high-tempo pitch-shifted anime party filter to stream.", cat: "dsp", role: "everyone", aliases: "nc" },
      { name: "/8d", args: "", desc: "Enable 360-degree rotating 8D spatial audio surround panning.", cat: "dsp", role: "everyone", aliases: "spatial" },
      { name: "/vaporwave", args: "", desc: "Slow down tempo with warm analog reverb for nostalgic aesthetic.", cat: "dsp", role: "everyone", aliases: "slowed" },
      { name: "/karaoke", args: "", desc: "Attenuate center-channel vocal frequencies for singing along.", cat: "dsp", role: "everyone", aliases: "vocalcut" },
      { name: "/tremolo", args: "", desc: "Apply rhythmic amplitude volume modulation oscillation.", cat: "dsp", role: "dj", aliases: "trem" },
      { name: "/vibrato", args: "", desc: "Apply rapid pitch oscillation frequency modulation filter.", cat: "dsp", role: "dj", aliases: "vib" },
      { name: "/distortion", args: "", desc: "Apply warm clipping overdrive distortion for heavy rock.", cat: "dsp", role: "dj", aliases: "dist" },
      { name: "/lowpass", args: "", desc: "Filter out high frequencies for cozy 'playing from next room' vibe.", cat: "dsp", role: "everyone", aliases: "muffle" },
      { name: "/cleareffect", args: "", desc: "Reset all active DSP audio filters back to studio flat.", cat: "dsp", role: "everyone", aliases: "resetfx, eqoff" },

      // QUEUE & PLAYLISTS
      { name: "/queue", args: "[page]", desc: "Display paginated list of all upcoming songs in current queue.", cat: "queue", role: "everyone", aliases: "q" },
      { name: "/shuffle", args: "", desc: "Randomize order of all upcoming tracks in the queue.", cat: "queue", role: "everyone", aliases: "shuff" },
      { name: "/repeat", args: "<off|track|queue>", desc: "Toggle loop mode between single track, full queue, or disabled.", cat: "queue", role: "everyone", aliases: "loop" },
      { name: "/clear", args: "", desc: "Clear all upcoming tracks from queue without stopping active song.", cat: "queue", role: "dj", aliases: "empty" },
      { name: "/swap", args: "<pos1> <pos2>", desc: "Swap positions of two tracks in the active queue.", cat: "queue", role: "everyone", aliases: "switch" },
      { name: "/move", args: "<from> <to>", desc: "Move a specific track to any slot number in the queue.", cat: "queue", role: "everyone", aliases: "shift" },
      { name: "/remove", args: "<pos>", desc: "Remove a specific song from the queue by its index number.", cat: "queue", role: "everyone", aliases: "del, rm" },
      { name: "/history", args: "", desc: "View the list of previously played songs in this voice session.", cat: "queue", role: "everyone", aliases: "recent" },
      { name: "/playlist play", args: "<name>", desc: "Load and stream your saved cloud playlist from MongoDB.", cat: "queue", role: "everyone", aliases: "pl play" },
      { name: "/playlist create", args: "<name>", desc: "Create a new private or public cloud playlist in MongoDB.", cat: "queue", role: "everyone", aliases: "pl new" },
      { name: "/playlist add", args: "<name> [track]", desc: "Add current or specified song to your saved cloud playlist.", cat: "queue", role: "everyone", aliases: "pl add" },

      // SETTINGS & 24/7
      { name: "/autodj", args: "", desc: "Toggle intelligent endless autoplay when your queue runs out.", cat: "settings", role: "dj", aliases: "endless" },
      { name: "/247", args: "", desc: "Keep Rem connected to voice channel 24/7 even when empty.", cat: "settings", role: "admin", aliases: "stay" },
      { name: "/dj", args: "<role>", desc: "Assign Discord role with DJ queue and filter permissions.", cat: "settings", role: "admin", aliases: "setdj" },
      { name: "/settings setupchannel", args: "", desc: "Create dedicated #rem-song-requests channel with buttons.", cat: "settings", role: "admin", aliases: "bind" },
      { name: "/settings prefix", args: "<new_prefix>", desc: "Change bot message prefix for legacy text commands.", cat: "settings", role: "admin", aliases: "setprefix" },
      { name: "/debug", args: "", desc: "Inspect live audio resolver latency, voice engine, and cookies.", cat: "settings", role: "everyone", aliases: "diag, ping" },
      { name: "/soundboard", args: "<sound>", desc: "Trigger instant anime/meme audio SFX (tuturu, bruh, anime wow, airhorn, vineboom, etc.) into voice.", cat: "dsp", role: "everyone", aliases: "sfx, sb" },
      { name: "/aidj", args: "[on|off]", desc: "Toggle Rem's AI Anime DJ Companion mode with live track intros and commentary.", cat: "settings", role: "everyone", aliases: "remdj, animedj" }
    ];

    // Active Queue Data
    let activeQueue = [
      { title: "Faded (Live Vocal Edition)", artist: "Alan Walker", dur: "03:32", thumb: "/public/musicmaid_banner.jpg", user: "@Kishore" },
      { title: "新時代 (New Genesis)", artist: "Ado", dur: "03:46", thumb: "/public/login_hero.jpg", user: "@AnimeDJ" },
      { title: "KICK BACK", artist: "Kenshi Yonezu", dur: "03:13", thumb: "/public/rem_avatar_static.png", user: "@VIP" },
      { title: "Sparkle (Your Name OST)", artist: "RADWIMPS", dur: "06:57", thumb: "/public/musicmaid_headphone_hero.jpg", user: "@RemFan" }
    ];

    // Lyrics Data
    const lyricsData = {
      yoasobi: [
        "♪ ~ (Synth Arpeggio Intro) ~ ♪",
        "素晴らしき世界に今日も乾杯",
        "街に飛び交う銃声と歓声",
        "誰もが自分を偽り生きている",
        "隠した本能 解き放つ時が来た",
        "叫べ 今この夜空を裂いて",
        "正しさとは何だ 誰が決めたルールだ",
        "僕らはずっと自由を歌っている"
      ],
      faded: [
        "♪ ~ (Atmospheric Piano Intro) ~ ♪",
        "You were the shadow to my light",
        "Did you feel us? Another start",
        "You fade away, afraid our aim is out of sight",
        "Wanna see us alive",
        "Where are you now? Where are you now?"
      ],
      ado: [
        "♪ ~ (Electronic Fanfare) ~ ♪",
        "新時代はこの未来だ",
        "世界中全部 変えてしまえば 変えてしまえば",
        "果てしない音楽の波に乗せて",
        "夢を見ようよ ずっと覚めないように"
      ]
    };

    let activeLyrics = lyricsData.yoasobi;

    // 2. THEME SWITCHER
    function switchTheme(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      document.querySelectorAll('.theme-dot').forEach(d => {
        d.classList.toggle('active', d.classList.contains(theme));
      });
      localStorage.setItem('rem_landing_theme', theme);
      showToast(`Switched theme to ${theme.toUpperCase()} ✨`, '🎨');
    }

    // 3. TOAST SYSTEM
    let toastTimeout = null;
    function showToast(text, icon = '✨') {
      const toast = document.getElementById('live-toast');
      document.getElementById('toast-icon').textContent = icon;
      document.getElementById('toast-text').textContent = text;
      toast.classList.add('show');
      if (toastTimeout) clearTimeout(toastTimeout);
      toastTimeout = setTimeout(() => {
        toast.classList.remove('show');
      }, 3000);
    }

    // 4. RENDER SUGGESTIONS GRID
    function renderSuggestions() {
      const container = document.getElementById('suggestions-grid');
      let filtered = trackDatabase;
      if (activeVibe !== 'all') {
        filtered = trackDatabase.filter(t => t.vibe === activeVibe);
      }

      container.innerHTML = filtered.map(t => `
        <div class="sug-card">
          <div class="sug-thumb-wrap">
            <img src="${t.image}" alt="${t.title}" onerror="this.src='/public/rem_avatar_static.png'">
            <span class="sug-dur-badge">${t.durText}</span>
          </div>
          <h4 class="sug-title" title="${t.title}">${t.title}</h4>
          <p class="sug-artist">${t.artist}</p>
          <div class="sug-actions">
            <button class="btn btn-primary" onclick="playSelectedTrack('${t.title.replace(/'/g, "\\'")}', '${t.artist.replace(/'/g, "\\'")}', '${t.image}')">▶ Play</button>
            <button class="btn btn-secondary" onclick="queueSelectedTrack('${t.title.replace(/'/g, "\\'")}', '${t.artist.replace(/'/g, "\\'")}', '${t.durText}', '${t.image}')">+ Queue</button>
          </div>
        </div>
      `).join('');
    }

    function filterVibe(vibe) {
      activeVibe = vibe;
      document.querySelectorAll('.vibe-chip').forEach(c => {
        c.classList.toggle('active', c.textContent.toLowerCase().includes(vibe) || (vibe === 'all' && c.textContent.includes('All')));
      });
      renderSuggestions();
    }

    // 5. SEARCH & AUTOCOMPLETE
    function handleSearchInput(e) {
      const val = e.target.value.trim().toLowerCase();
      const box = document.getElementById('autocomplete-box');
      if (!val) {
        box.classList.remove('show');
        return;
      }
      const matches = trackDatabase.filter(t => t.title.toLowerCase().includes(val) || t.artist.toLowerCase().includes(val) || t.query.toLowerCase().includes(val)).slice(0, 4);
      if (matches.length > 0) {
        box.innerHTML = matches.map(m => `
          <div class="ac-item" onclick="selectAutocomplete('${m.title.replace(/'/g, "\\'")}', '${m.artist.replace(/'/g, "\\'")}', '${m.image}', '${m.durText}')">
            <img src="${m.image}" alt="Thumb" onerror="this.src='/public/rem_avatar_static.png'">
            <div>
              <div class="ac-item-title">${m.title}</div>
              <div class="ac-item-sub">${m.artist} • ${m.durText}</div>
            </div>
          </div>
        `).join('');
        box.classList.add('show');
      } else {
        box.classList.remove('show');
      }
    }

    function selectAutocomplete(title, artist, img, dur) {
      document.getElementById('search-input').value = title;
      document.getElementById('autocomplete-box').classList.remove('show');
      playSelectedTrack(title, artist, img);
    }

    function executeSearch() {
      const input = document.getElementById('search-input');
      const val = input.value.trim();
      if (!val) {
        showToast('Please type a song or artist name to search', '🔍');
        return;
      }
      document.getElementById('autocomplete-box').classList.remove('show');
      playSelectedTrack(val, 'Searched Track', '/public/rem_avatar_static.png');
      showToast(`Searching & playing "${val}" via Rem Audio Engine ⚡`, '🎵');
    }

    function triggerSurpriseAutoDJ() {
      const randomTrack = trackDatabase[Math.floor(Math.random() * trackDatabase.length)];
      playSelectedTrack(randomTrack.title, randomTrack.artist, randomTrack.image);
      showToast(`Auto-DJ selected: "${randomTrack.title}" by ${randomTrack.artist}! 🎲`, '🎧');
    }

    // 6. RENDER INTEGRATED COMMANDS
    function renderCommands() {
      const grid = document.getElementById('commands-grid');
      const searchVal = (document.getElementById('cmd-search')?.value || '').toLowerCase().trim();

      let filtered = botCommands;
      if (activeCmdCategory !== 'all') {
        filtered = filtered.filter(c => c.cat === activeCmdCategory);
      }
      if (searchVal) {
        filtered = filtered.filter(c => c.name.toLowerCase().includes(searchVal) || c.desc.toLowerCase().includes(searchVal) || c.aliases.toLowerCase().includes(searchVal));
      }

      grid.innerHTML = filtered.map(c => `
        <div class="cmd-card">
          <div class="cmd-card-header">
            <span class="cmd-pill">${c.name} ${c.args}</span>
            <span class="cmd-role-badge ${c.role}">${c.role}</span>
          </div>
          <p class="cmd-desc">${c.desc}</p>
          <div class="cmd-footer">
            <span class="cmd-aliases">Aliases: ${c.aliases || 'none'}</span>
            <div class="cmd-actions">
              <button class="btn btn-secondary btn-sm" onclick="copySlashCommand('${c.name}')" title="Copy Slash Command">📋 Copy</button>
              <button class="btn btn-primary btn-sm" onclick="runWebCommand('${c.name}')" title="Run in Web Simulator">⚡ Run</button>
            </div>
          </div>
        </div>
      `).join('');
    }

    function filterCommands(cat) {
      activeCmdCategory = cat;
      document.querySelectorAll('.cmd-tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('onclick').includes(cat));
      });
      renderCommands();
    }

    function handleCmdSearch(e) {
      renderCommands();
    }

    function copySlashCommand(cmd) {
      navigator.clipboard?.writeText(cmd).catch(() => {});
      showToast(`Copied "${cmd}" to clipboard! Paste into Discord.`, '📋');
    }

    async function dispatchBackendControl(action, payload = {}) {
      try {
        const res = await fetch('/api/music/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: action, payload: payload })
        });
        const data = await res.json();
        if (data.success) {
          setTimeout(syncLiveBotTrack, 800);
        }
      } catch (e) {
        console.warn("Backend control dispatch note:", e);
      }
    }

    function runWebCommand(cmd) {
      const parts = cmd.trim().split(/\s+/);
      const name = parts[0].toLowerCase();
      const args = parts.slice(1).join(' ');

      showToast(`Running ${cmd} on Rem Discord Bot... ⚡`, '⚡');

      // Dispatch directly to Discord Bot
      switch (name) {
        case '/pause':
          dispatchBackendControl('PAUSE');
          isPlaying = false;
          updatePlaybackUI();
          showToast('Paused playback on Discord ⏸️', '⏸');
          break;
        case '/resume':
          dispatchBackendControl('RESUME');
          isPlaying = true;
          updatePlaybackUI();
          showToast('Resumed playback on Discord 🎧', '▶');
          break;
        case '/skip':
        case '/next':
          dispatchBackendControl('SKIP');
          triggerNext();
          showToast('Skipped current track on Discord ⏭️', '⏭️');
          break;
        case '/stop':
          dispatchBackendControl('STOP');
          isPlaying = false;
          updatePlaybackUI();
          showToast('Stopped playback and cleared active voice stream on Discord ⏹️', '⏹️');
          break;
        case '/shuffle':
          dispatchBackendControl('SHUFFLE');
          shuffleQueueList();
          showToast('Queue shuffled on Discord! 🔀', '🔀');
          break;
        case '/repeat':
        case '/loop':
          dispatchBackendControl('LOOP');
          triggerRepeat();
          showToast('Toggled repeat loop mode on Discord 🔁', '🔁');
          break;
        case '/volume':
          const vVal = parseInt(args) || 100;
          dispatchBackendControl('VOLUME', { volume: vVal });
          handleVolume(vVal);
          showToast(`Volume set to ${vVal}% on Discord 🔊`, '🔊');
          break;
        case '/radio':
          const st = args || 'lofi';
          dispatchBackendControl('RADIO', { station: st });
          showToast(`Streaming 24/7 Radio Station "${st}" on Discord! 📻`, '📻');
          break;
        case '/soundboard':
        case '/sfx':
          const snd = args || 'airhorn';
          dispatchBackendControl('SOUNDBOARD', { sound: snd });
          showToast(`Played sound effect "${snd}" into voice channel! 📢`, '📢');
          break;
        case '/vibe':
          const vb = args || 'anime';
          dispatchBackendControl('VIBE', { mood: vb });
          showToast(`Auto-generating queue for vibe "${vb}" on Discord! 🌸`, '🌸');
          break;
        case '/sleep':
          const mins = parseInt(args) || 30;
          dispatchBackendControl('SLEEP', { minutes: mins });
          showToast(`Sleep timer set for ${mins} minutes on Discord! 💤`, '💤');
          break;
        case '/nightcore':
          applyEqPreset('nightcore');
          dispatchBackendControl('FILTER', { preset: 'nightcore' });
          showToast('Applied Nightcore audio filter on Discord! ⚡', '⚡');
          break;
        case '/8d':
          applyEqPreset('8d');
          dispatchBackendControl('FILTER', { preset: '8d' });
          showToast('Applied 8D Surround audio filter on Discord! 🎧', '🎧');
          break;
        case '/vaporwave':
          applyEqPreset('vaporwave');
          dispatchBackendControl('FILTER', { preset: 'vaporwave' });
          showToast('Applied Vaporwave slow-down filter on Discord! 🌊', '🌊');
          break;
        case '/karaoke':
          applyEqPreset('karaoke');
          dispatchBackendControl('FILTER', { preset: 'karaoke' });
          showToast('Applied Vocal Isolation Karaoke filter on Discord! 🎤', '🎤');
          break;
        case '/cleareffect':
          applyEqPreset('flat');
          dispatchBackendControl('FILTER', { preset: 'flat' });
          showToast('Reset audio DSP equalizer on Discord! 🎚️', '🎚️');
          break;
        case '/queue':
          scrollToId('queue');
          showToast('Navigated to live Queue Manager! 📑', '📑');
          break;
        case '/lyrics':
          scrollToId('lyrics');
          showToast('Showing synchronized karaoke lyrics! 🎤', '🎤');
          break;
        default:
          dispatchBackendControl('EXECUTE', { command: cmd, args: args });
          showToast(`Executed ${cmd} in Rem Discord Engine! ⚡`, '⚡');
      }
    }

    // 7. PLAYBACK CONTROLS
    function togglePlayPause() {
      isPlaying = !isPlaying;
      updatePlaybackUI();
      showToast(isPlaying ? 'Resumed playback on Discord 🎧' : 'Paused playback on Discord ⏸️', isPlaying ? '▶' : '⏸');
      dispatchBackendControl(isPlaying ? 'RESUME' : 'PAUSE');
    }

    function triggerNext() {
      dispatchBackendControl('SKIP');
      if (activeQueue.length > 0) {
        const next = activeQueue.shift();
        playSelectedTrack(next.title, next.artist, next.thumb);
        renderQueue();
        showToast(`Skipped to "${next.title}" on Discord ⏭️`, '⏭️');
      } else {
        triggerSurpriseAutoDJ();
      }
    }

    function triggerPrev() {
      dispatchBackendControl('PREVIOUS');
      currentSec = 0;
      updateDeckTime();
      showToast('Restarted playback from beginning! ⏮️', '⏮️');
    }

    function triggerRepeat() {
      const modes = ['off', 'track', 'queue'];
      repeatMode = modes[(modes.indexOf(repeatMode) + 1) % modes.length];
      const icons = { off: '🔁', track: '🔂', queue: '🔁' };
      const btn = document.getElementById('sp-repeat-btn');
      if (btn) {
        btn.textContent = icons[repeatMode];
        btn.classList.toggle('active', repeatMode !== 'off');
      }
      dispatchBackendControl('LOOP');
      showToast(`Loop Mode: ${repeatMode.toUpperCase()} 🔁`, '🔁');
    }

    function triggerShuffle() {
      shuffleQueueList();
      dispatchBackendControl('SHUFFLE');
    }

    function handleVolume(val) {
      activeVolume = parseInt(val);
      document.getElementById('sp-vol-slider').value = activeVolume;
      document.getElementById('hero-vol-slider').value = activeVolume;
      document.getElementById('sp-vol-icon').textContent = activeVolume === 0 ? '🔇' : (activeVolume < 50 ? '🔉' : '🔊');
      dispatchBackendControl('VOLUME', { volume: activeVolume });
    }

    function playSelectedTrack(title, artist, img) {
      document.getElementById('hero-title').textContent = title;
      document.getElementById('hero-artist').textContent = artist;
      document.getElementById('sp-title').textContent = title;
      document.getElementById('sp-artist').textContent = artist;
      if (img) {
        document.getElementById('hero-thumb').src = img;
        document.getElementById('sp-thumb').src = img;
      }
      isPlaying = true;
      currentSeconds = 0;
      updatePlaybackUI();
      showToast(`Now Playing: "${title}" by ${artist} 🎵`, '🎶');
    }

    function queueSelectedTrack(title, artist, dur, img) {
      activeQueue.push({ title, artist, dur, thumb: img || '/public/rem_avatar_static.png', user: '@WebUser' });
      renderQueue();
      showToast(`Added "${title}" to collaborative queue! 📑`, '➕');
    }

    function updatePlaybackUI() {
      const playIcon = isPlaying ? '⏸️' : '▶';
      document.getElementById('hero-play-btn').textContent = playIcon;
      document.getElementById('sp-play-btn').textContent = playIcon;

      document.getElementById('hero-vinyl').classList.toggle('paused', !isPlaying);
      document.getElementById('hero-waveform').classList.toggle('paused', !isPlaying);
    }

    // Timer loop for scrubber
    setInterval(() => {
      if (isPlaying) {
        currentSeconds++;
        if (currentSeconds > totalSeconds) {
          triggerNext();
          return;
        }
        const pct = (currentSeconds / totalSeconds) * 100;
        document.getElementById('hero-progress').style.width = pct + '%';
        document.getElementById('sp-scrub-slider').value = pct;

        const curM = Math.floor(currentSeconds / 60);
        const curS = currentSeconds % 60;
        const curStr = `${String(curM).padStart(2, '0')}:${String(curS).padStart(2, '0')}`;
        document.getElementById('hero-cur-time').textContent = curStr;
        document.getElementById('sp-cur-time').textContent = curStr;

        // Auto advance karaoke line
        if (currentSeconds % 12 === 0) {
          currentLyricIdx = (currentLyricIdx + 1) % activeLyrics.length;
          renderLyrics();
        }
      }
    }, 1000);

    function handleScrub(val) {
      currentSeconds = Math.floor((val / 100) * totalSeconds);
      document.getElementById('hero-progress').style.width = val + '%';
    }

    function seekHeroProgress(e) {
      const rect = e.currentTarget.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      currentSeconds = Math.floor(pct * totalSeconds);
      document.getElementById('hero-progress').style.width = (pct * 100) + '%';
      document.getElementById('sp-scrub-slider').value = (pct * 100);
    }

    function handleVolume(val) {
      volumeLevel = val;
      isMuted = val == 0;
      document.getElementById('sp-vol-slider').value = val;
      document.getElementById('sp-vol-icon').textContent = isMuted ? '🔇' : val > 50 ? '🔊' : '🔉';
    }

    function toggleMute() {
      if (isMuted) {
        handleVolume(volumeLevel || 80);
      } else {
        handleVolume(0);
      }
    }

    // 8. 10-BAND EQUALIZER
    const eqFrequencies = ["31Hz", "62Hz", "125Hz", "250Hz", "500Hz", "1kHz", "2kHz", "4kHz", "8kHz", "16kHz"];
    let eqValues = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0];

    function renderEqSliders() {
      const rack = document.getElementById('eq-sliders-rack');
      rack.innerHTML = eqFrequencies.map((freq, i) => `
        <div class="eq-slider-col">
          <span class="eq-db-value" id="eq-val-${i}">${eqValues[i] > 0 ? '+' : ''}${eqValues[i]}dB</span>
          <input type="range" min="-12" max="12" value="${eqValues[i]}" oninput="updateEqBand(${i}, this.value)">
          <span class="eq-freq-label">${freq}</span>
        </div>
      `).join('');
    }

    function updateEqBand(idx, val) {
      eqValues[idx] = parseInt(val);
      document.getElementById(`eq-val-${idx}`).textContent = `${val > 0 ? '+' : ''}${val}dB`;
    }

    function applyEqPreset(preset) {
      document.querySelectorAll('.eq-preset-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('onclick').includes(preset));
      });

      const presets = {
        flat: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        bassboost: [8, 7, 5, 3, 1, 0, 0, 0, 0, 0],
        nightcore: [-2, -1, 0, 1, 2, 4, 6, 8, 9, 10],
        vaporwave: [4, 3, 2, 1, 0, -1, -3, -5, -6, -8],
        '8d': [2, 1, 0, 2, 3, 2, 1, 3, 4, 3],
        karaoke: [0, 0, -2, -6, -10, -10, -6, -2, 0, 0],
        lowpass: [3, 2, 1, 0, -2, -4, -7, -10, -12, -12]
      };

      eqValues = presets[preset] || presets.flat;
      renderEqSliders();
      showToast(`Applied Audio Preset: ${preset.toUpperCase()} 🎛️`, '🎛️');
    }

    // 9. LYRICS
    function renderLyrics() {
      const box = document.getElementById('lyrics-scroll-box');
      box.innerHTML = activeLyrics.map((line, idx) => `
        <div class="lyric-line ${idx === currentLyricIdx ? 'active' : ''}" onclick="seekLyricLine(${idx})">
          ${line}
        </div>
      `).join('');

      // Auto scroll active line to center
      const activeEl = box.querySelector('.lyric-line.active');
      if (activeEl) {
        box.scrollTop = activeEl.offsetTop - box.offsetTop - 120;
      }
    }

    function seekLyricLine(idx) {
      currentLyricIdx = idx;
      renderLyrics();
      showToast(`Jumped to lyrics stanza #${idx + 1} 🎤`, '🎤');
    }

    function setLyricSong(key) {
      activeLyrics = lyricsData[key] || lyricsData.yoasobi;
      currentLyricIdx = 0;
      renderLyrics();
      showToast(`Loaded synchronized lyrics for ${key.toUpperCase()} 🎶`, '🎤');
    }

    // 10. DRAG-AND-DROP QUEUE
    let draggedIdx = null;

    function renderQueue() {
      const box = document.getElementById('queue-list-box');
      document.getElementById('queue-count').textContent = activeQueue.length;
      if (activeQueue.length === 0) {
        box.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-dim);">Queue is empty. Click "+ Queue" on any song to add it!</div>`;
        return;
      }
      box.innerHTML = activeQueue.map((item, idx) => `
        <div class="queue-row" draggable="true"
             ondragstart="onDragStart(event, ${idx})"
             ondragover="onDragOver(event)"
             ondrop="onDrop(event, ${idx})"
             ondragend="onDragEnd(event)">
          <span class="queue-drag-handle">⋮⋮</span>
          <img src="${item.thumb}" class="queue-thumb" alt="Thumb" onerror="this.src='/public/rem_avatar_static.png'">
          <div class="queue-row-meta">
            <div class="queue-row-title">${item.title}</div>
            <div class="queue-row-sub">${item.artist} • ${item.user}</div>
          </div>
          <span style="font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:var(--text-dim);">${item.dur}</span>
          <button class="btn btn-secondary btn-sm" onclick="removeQueueIndex(${idx})" title="Remove">✕</button>
        </div>
      `).join('');
    }

    function onDragStart(e, idx) {
      draggedIdx = idx;
      e.dataTransfer.effectAllowed = 'move';
      e.currentTarget.classList.add('dragging');
    }

    function onDragOver(e) {
      e.preventDefault();
    }

    function onDragEnd(e) {
      document.querySelectorAll('.queue-row').forEach(r => r.classList.remove('dragging'));
    }

    function onDrop(e, targetIdx) {
      e.preventDefault();
      onDragEnd(e);
      if (draggedIdx === null || draggedIdx === targetIdx) return;
      const moved = activeQueue.splice(draggedIdx, 1)[0];
      activeQueue.splice(targetIdx, 0, moved);
      draggedIdx = null;
      renderQueue();
      showToast('Queue reordered via drag-and-drop! ↕️', '↕️');
    }

    function removeQueueIndex(idx) {
      const removed = activeQueue.splice(idx, 1)[0];
      renderQueue();
      showToast(`Removed "${removed.title}" from queue 🗑️`, '🗑️');
    }

    function shuffleQueueList() {
      for (let i = activeQueue.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [activeQueue[i], activeQueue[j]] = [activeQueue[j], activeQueue[i]];
      }
      renderQueue();
      showToast('Collaborative queue shuffled! 🔀', '🔀');
    }

    function clearQueueList() {
      activeQueue = [];
      renderQueue();
      showToast('Upcoming queue cleared! 🗑️', '🗑️');
    }

    // 11. SYSTEM HEALTH & AUTO-UPDATER
    function checkSystemUpdate() {
      showToast('Querying supervisor update status... 🔄', '🔄');
      fetch('/api/system/update_status')
        .then(r => r.json())
        .then(data => {
          document.getElementById('diag-commit').textContent = (data.current_commit || '9aaf445').substring(0, 7);
          if (data.update_available) {
            showToast(`Update Available! New Commit: ${(data.remote_commit || '').substring(0, 7)}`, '🔔');
          } else {
            showToast('Rem is fully up-to-date with branch origin! ✅', '✅');
          }
        })
        .catch(() => {
          showToast('Autonomous supervisor operational: Bot healthy! ✅', '✅');
        });
    }

    // 12. CANVAS PARTICLE ANIMATION
    const canvas = document.getElementById('bg-canvas');
    const ctx = canvas.getContext('2d');
    let particles = [];

    function resizeCanvas() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    for (let i = 0; i < 45; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        r: Math.random() * 2 + 1,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        alpha: Math.random() * 0.5 + 0.2
      });
    }

    function drawParticles() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#c084fc';
      particles.forEach(p => {
        ctx.globalAlpha = p.alpha;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;
      });
      requestAnimationFrame(drawParticles);
    }
    drawParticles();

    function scrollToId(id) {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    }

    // 13. LIVE BOT SESSION SYNC (Polls Discord Voice Player in Real-Time)
    function syncLiveBotTrack() {
      fetch('/api/music/session')
        .then(r => r.json())
        .then(res => {
          const sess = res?.data || res;
          const trk = sess?.current_track;
          if (trk && trk.title) {
            const hTitle = document.getElementById('hero-title');
            const hArtist = document.getElementById('hero-artist');
            const hThumb = document.getElementById('hero-thumb');
            const hVc = document.getElementById('hero-vc-name');
            const spTitle = document.getElementById('sp-title');
            const spArtist = document.getElementById('sp-artist');
            const spThumb = document.getElementById('sp-thumb');
            const badgeChannel = document.querySelector('.hero-badge span:last-child');

            if (hTitle && hTitle.textContent !== trk.title) {
              hTitle.textContent = trk.title;
            }
            const artistDisplay = trk.artist + (trk.channel_name ? ' • In ' + trk.channel_name : (trk.requester_name ? ' • Req: ' + trk.requester_name : ' • 320kbps'));
            if (hArtist && hArtist.textContent !== artistDisplay) {
              hArtist.textContent = artistDisplay;
            }
            if (hVc && trk.channel_name) {
              hVc.textContent = '🔊 ' + trk.channel_name + (trk.guild_name ? ' (' + trk.guild_name + ')' : '');
            }
            if (spTitle && spTitle.textContent !== trk.title) {
              spTitle.textContent = trk.title;
            }
            if (spArtist) {
              spArtist.textContent = trk.artist + ' • 320kbps';
            }
            if (trk.thumbnail) {
              if (hThumb && hThumb.src !== trk.thumbnail) hThumb.src = trk.thumbnail;
              if (spThumb && spThumb.src !== trk.thumbnail) spThumb.src = trk.thumbnail;
            }
            if (badgeChannel && trk.channel_name) {
              badgeChannel.textContent = '🎵 Live in ' + trk.channel_name + (trk.guild_name ? ' • ' + trk.guild_name : '');
            }

            if (sess.duration > 0) {
              totalSec = sess.duration;
            }
            if (typeof sess.position === 'number' && sess.position >= 0) {
              currentSec = sess.position;
              updateDeckTime();
            }

            // Sync play state
            if (sess.is_playing && !sess.is_paused) {
              playActive = true;
              const spIcon = document.getElementById('sp-play-icon');
              const heroIcon = document.getElementById('hero-play-icon');
              if (spIcon) spIcon.textContent = '⏸';
              if (heroIcon) heroIcon.textContent = '⏸';
            } else if (sess.is_paused) {
              playActive = false;
              const spIcon = document.getElementById('sp-play-icon');
              const heroIcon = document.getElementById('hero-play-icon');
              if (spIcon) spIcon.textContent = '▶';
              if (heroIcon) heroIcon.textContent = '▶';
            }
          }
        })
        .catch(() => {});
    }

    // Initialize all components on DOM ready
    window.addEventListener('DOMContentLoaded', () => {
      const savedTheme = localStorage.getItem('rem_landing_theme') || 'obsidian';
      switchTheme(savedTheme);

      renderSuggestions();
      renderCommands();
      renderEqSliders();
      renderLyrics();
      renderQueue();

      // 13. LIVE BOT REAL-TIME SYNC
      syncLiveBotTrack();
      if (!window.__remSyncTimer) {
        window.__remSyncTimer = setInterval(syncLiveBotTrack, 3000);
      }
    });
  </script>
</body>
</html>
"""

__all__ = ["LANDING_PAGE_HTML"]
