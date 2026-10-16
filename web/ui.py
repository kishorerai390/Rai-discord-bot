"""
MusicMaid — Discord Music Bot Master Control Panel & Web Platform UI.
Dedicated 24/7 Hi-Fi Lossless Music Engine with Smart Auto-DJ, DSP Equalizer,
Queue Synchronization, Multi-Lingual Search, and Discord OAuth2 Integration.
"""

from __future__ import annotations

UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MusicMaid ✦ Discord Music Engine & Master Control Panel</title>
  <meta name="description" content="Dedicated 24/7 Lossless 320kbps Discord Music Bot Control Panel. Control queues, DSP equalizer, Smart Auto-DJ, and synchronized playback.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #07090e;
      --bg-sidebar: #0b0e17;
      --bg-surface: #0f1422;
      --bg-card: rgba(18, 23, 37, 0.78);
      --bg-card-hover: rgba(28, 35, 56, 0.88);
      --card-border: rgba(147, 51, 234, 0.22);
      --card-border-hover: rgba(168, 85, 247, 0.55);
      --primary: #9333ea;
      --primary-hover: #a855f7;
      --primary-glow: rgba(147, 51, 234, 0.45);
      --cyan: #00e5ff;
      --cyan-hover: #38bdf8;
      --cyan-glow: rgba(0, 229, 255, 0.35);
      --neon-blue: #00b0ff;
      --pink: #ec4899;
      --emerald: #10b981;
      --amber: #f59e0b;
      --danger: #ef4444;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --blurple: #5865F2;
      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 20px;
      --radius-full: 9999px;
      --player-height: 88px;
      --sidebar-width: 260px;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      background-color: var(--bg-dark);
      background-image:
        radial-gradient(at 0% 0%, rgba(147, 51, 234, 0.16) 0px, transparent 55%),
        radial-gradient(at 100% 100%, rgba(0, 229, 255, 0.12) 0px, transparent 55%),
        radial-gradient(at 50% 50%, rgba(236, 72, 153, 0.05) 0px, transparent 65%);
      color: var(--text);
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      overflow-x: hidden;
    }

    /* APP LAYOUT SHELL */
    .app-layout {
      display: flex;
      min-height: 100vh;
      padding-bottom: calc(var(--player-height) + 12px);
    }

    /* LEFT SIDEBAR */
    aside.sidebar {
      width: var(--sidebar-width);
      background: var(--bg-sidebar);
      border-right: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      flex-direction: column;
      position: fixed;
      top: 0;
      left: 0;
      bottom: var(--player-height);
      z-index: 50;
      padding: 1.25rem 1rem;
      gap: 1.2rem;
      backdrop-filter: blur(20px);
    }

    .brand-box {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      padding: 0.5rem 0.6rem;
      cursor: pointer;
      text-decoration: none;
    }
    .brand-avatar {
      width: 42px;
      height: 42px;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--primary) 0%, var(--cyan) 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.4rem;
      box-shadow: 0 0 16px var(--primary-glow);
    }
    .brand-title-wrap h1 {
      font-size: 1.18rem;
      font-weight: 800;
      letter-spacing: -0.3px;
      background: linear-gradient(90deg, #fff, #cbd5e1);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .brand-title-wrap p {
      font-size: 0.72rem;
      color: var(--cyan);
      font-weight: 600;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }

    /* SERVER SELECTOR DROPDOWN */
    .server-switcher {
      position: relative;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(147, 51, 234, 0.3);
      border-radius: var(--radius-md);
      padding: 0.65rem 0.85rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .server-switcher:hover {
      background: rgba(147, 51, 234, 0.15);
      border-color: var(--primary);
    }
    .server-active-info {
      display: flex;
      align-items: center;
      gap: 0.7rem;
      overflow: hidden;
    }
    .server-icon {
      width: 28px;
      height: 28px;
      border-radius: 8px;
      background: #1e2438;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--cyan);
      flex-shrink: 0;
    }
    .server-names {
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .server-name-text {
      font-size: 0.85rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .server-status-sub {
      font-size: 0.7rem;
      color: var(--emerald);
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }
    .pulse-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--emerald);
      box-shadow: 0 0 8px var(--emerald);
      animation: pulseAnim 2s infinite;
    }
    @keyframes pulseAnim {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.8); }
    }
    .server-dropdown-menu {
      position: absolute;
      top: 105%;
      left: 0;
      right: 0;
      background: #0f1322;
      border: 1px solid rgba(147, 51, 234, 0.4);
      border-radius: var(--radius-md);
      box-shadow: 0 15px 35px rgba(0, 0, 0, 0.8);
      display: none;
      flex-direction: column;
      max-height: 280px;
      overflow-y: auto;
      z-index: 100;
      padding: 0.4rem;
      gap: 0.2rem;
    }
    .server-dropdown-menu.open { display: flex; }
    .server-opt {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      padding: 0.5rem 0.6rem;
      border-radius: var(--radius-sm);
      cursor: pointer;
      font-size: 0.82rem;
      font-weight: 600;
      transition: background 0.15s;
    }
    .server-opt:hover {
      background: rgba(147, 51, 234, 0.25);
      color: #fff;
    }
    .server-opt.selected {
      background: rgba(0, 229, 255, 0.18);
      color: var(--cyan);
    }

    /* NAV LINKS LIST */
    .nav-group-title {
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-dim);
      padding-left: 0.6rem;
      margin-top: 0.4rem;
    }
    .nav-list {
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
      list-style: none;
    }
    .nav-link {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      padding: 0.7rem 0.85rem;
      border-radius: var(--radius-md);
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.92rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .nav-link:hover {
      color: #fff;
      background: rgba(255, 255, 255, 0.05);
      transform: translateX(3px);
    }
    .nav-link.active {
      color: #fff;
      background: linear-gradient(90deg, rgba(147, 51, 234, 0.3) 0%, rgba(0, 229, 255, 0.15) 100%);
      border: 1px solid rgba(147, 51, 234, 0.45);
      box-shadow: 0 4px 15px rgba(147, 51, 234, 0.15);
    }
    .nav-icon {
      font-size: 1.15rem;
      width: 22px;
      display: flex;
      justify-content: center;
    }

    /* SIDEBAR FOOTER (VOICE BADGE & AUTH) */
    .sidebar-footer {
      margin-top: auto;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }
    .voice-badge-card {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.35);
      border-radius: var(--radius-md);
      padding: 0.6rem 0.75rem;
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-size: 0.78rem;
      color: #34d399;
      font-weight: 600;
    }
    .user-pill {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: var(--radius-md);
      padding: 0.55rem 0.75rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .user-meta {
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }
    .user-avatar {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: var(--primary);
      object-fit: cover;
    }
    .user-name {
      font-size: 0.82rem;
      font-weight: 700;
      color: #fff;
    }
    .btn-logout {
      background: transparent;
      border: none;
      color: var(--text-dim);
      cursor: pointer;
      font-size: 0.9rem;
      transition: color 0.15s;
    }
    .btn-logout:hover { color: var(--danger); }
    .btn-login-discord {
      background: var(--blurple);
      border: none;
      color: #fff;
      padding: 0.65rem 0.9rem;
      border-radius: var(--radius-md);
      font-weight: 700;
      font-size: 0.85rem;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      cursor: pointer;
      text-decoration: none;
      transition: transform 0.15s, box-shadow 0.15s;
    }
    .btn-login-discord:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(88, 101, 242, 0.4);
    }

    /* MAIN CONTENT VIEW */
    main.content-area {
      margin-left: var(--sidebar-width);
      flex: 1;
      padding: 1.8rem 2.2rem;
      max-width: 1400px;
      width: calc(100vw - var(--sidebar-width));
    }
    @media (max-width: 900px) {
      aside.sidebar {
        transform: translateX(-100%);
        transition: transform 0.3s ease;
      }
      aside.sidebar.mobile-open {
        transform: translateX(0);
      }
      main.content-area {
        margin-left: 0;
        width: 100vw;
        padding: 1rem;
      }
      .mobile-top-bar {
        display: flex !important;
      }
    }

    .mobile-top-bar {
      display: none;
      justify-content: space-between;
      align-items: center;
      background: var(--bg-surface);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: var(--radius-md);
      padding: 0.75rem 1rem;
      margin-bottom: 1.2rem;
    }
    .mobile-btn {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #fff;
      width: 36px;
      height: 36px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 1.2rem;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    /* CARD & COMPONENT STYLING */
    .glass-card {
      background: var(--bg-card);
      border: 1px solid var(--card-border);
      backdrop-filter: blur(20px);
      border-radius: var(--radius-lg);
      padding: 1.6rem;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
      position: relative;
      overflow: hidden;
      transition: border-color 0.25s, box-shadow 0.25s;
    }
    .glass-card:hover {
      border-color: var(--card-border-hover);
    }
    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.2rem;
      flex-wrap: wrap;
      gap: 0.8rem;
    }
    .section-title {
      font-size: 1.35rem;
      font-weight: 800;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 0.6rem;
      letter-spacing: -0.3px;
    }

    /* PERSISTENT BOTTOM PLAYBACK BAR */
    footer.player-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      height: var(--player-height);
      background: rgba(10, 13, 22, 0.94);
      backdrop-filter: blur(28px);
      -webkit-backdrop-filter: blur(28px);
      border-top: 1px solid rgba(147, 51, 234, 0.28);
      box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.8), 0 0 25px rgba(147, 51, 234, 0.12);
      z-index: 999;
      display: grid;
      grid-template-columns: 320px 1fr 300px;
      align-items: center;
      padding: 0 1.8rem;
      gap: 1.5rem;
    }
    @media (max-width: 1024px) {
      footer.player-bar {
        grid-template-columns: 240px 1fr 200px;
        padding: 0 1rem;
      }
    }
    @media (max-width: 768px) {
      footer.player-bar {
        grid-template-columns: 1fr auto;
        padding: 0.5rem 0.8rem;
        height: auto;
        min-height: 76px;
      }
      .player-bar-right { display: none !important; }
      .player-bar-center { width: 100%; }
    }

    /* PLAYER BAR LEFT: TRACK META */
    .player-bar-left {
      display: flex;
      align-items: center;
      gap: 0.9rem;
      min-width: 0;
    }
    .bar-thumb {
      width: 52px;
      height: 52px;
      border-radius: 10px;
      object-fit: cover;
      background: #181d2e;
      border: 1px solid rgba(255, 255, 255, 0.1);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
      flex-shrink: 0;
    }
    .bar-meta {
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .bar-title {
      font-size: 0.92rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      cursor: pointer;
    }
    .bar-title:hover { color: var(--cyan); }
    .bar-artist {
      font-size: 0.78rem;
      color: var(--text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .btn-fav {
      background: transparent;
      border: none;
      color: var(--text-dim);
      font-size: 1.2rem;
      cursor: pointer;
      transition: transform 0.15s, color 0.15s;
      flex-shrink: 0;
    }
    .btn-fav:hover, .btn-fav.active {
      color: var(--pink);
      transform: scale(1.15);
    }

    /* PLAYER BAR CENTER: CONTROLS & SCRUBBER */
    .player-bar-center {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.35rem;
      width: 100%;
      max-width: 620px;
      margin: 0 auto;
    }
    .player-buttons-row {
      display: flex;
      align-items: center;
      gap: 1.1rem;
    }
    .p-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 1.15rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.15s ease;
      width: 32px;
      height: 32px;
      border-radius: 50%;
    }
    .p-btn:hover {
      color: #fff;
      background: rgba(255, 255, 255, 0.08);
      transform: scale(1.1);
    }
    .p-btn.active {
      color: var(--cyan);
    }
    .p-btn-play {
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, var(--primary) 0%, var(--cyan) 100%);
      color: #fff;
      border-radius: 50%;
      box-shadow: 0 0 16px var(--primary-glow);
      font-size: 1.3rem;
    }
    .p-btn-play:hover {
      transform: scale(1.08);
      box-shadow: 0 0 24px var(--cyan-glow);
      color: #fff;
      background: linear-gradient(135deg, var(--primary-hover) 0%, var(--cyan-hover) 100%);
    }

    .scrub-row {
      display: flex;
      align-items: center;
      gap: 0.8rem;
      width: 100%;
    }
    .scrub-time {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: var(--text-muted);
      min-width: 42px;
      text-align: center;
    }
    .slider-track {
      -webkit-appearance: none;
      appearance: none;
      width: 100%;
      height: 5px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.14);
      outline: none;
      cursor: pointer;
      transition: height 0.15s;
    }
    .slider-track:hover { height: 7px; }
    .slider-track::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 13px;
      height: 13px;
      border-radius: 50%;
      background: var(--cyan);
      box-shadow: 0 0 10px var(--cyan);
      cursor: pointer;
    }

    /* PLAYER BAR RIGHT: VOLUME & SHORTCUTS */
    .player-bar-right {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 0.9rem;
    }
    .vol-wrapper {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      width: 130px;
    }
    .chip-pill {
      background: rgba(255, 255, 255, 0.07);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-full);
      padding: 0.25rem 0.65rem;
      font-size: 0.72rem;
      font-weight: 700;
      color: var(--cyan);
      letter-spacing: 0.3px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .chip-pill:hover, .chip-pill.active {
      background: var(--primary);
      border-color: var(--primary);
      color: #fff;
    }

    /* TOAST NOTIFICATION */
    #toast-container {
      position: fixed;
      bottom: calc(var(--player-height) + 16px);
      right: 24px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      z-index: 10000;
      pointer-events: none;
    }
    .toast-msg {
      background: #0f1422;
      border: 1px solid var(--primary);
      box-shadow: 0 10px 30px rgba(0,0,0,0.8);
      border-radius: var(--radius-md);
      padding: 0.75rem 1.1rem;
      font-size: 0.86rem;
      font-weight: 600;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 0.6rem;
      animation: toastIn 0.25s ease-out;
      pointer-events: auto;
    }
    @keyframes toastIn {
      from { opacity: 0; transform: translateY(12px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* BUTTONS & FORMS */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      font-family: inherit;
      font-weight: 700;
      border-radius: var(--radius-md);
      padding: 0.65rem 1.25rem;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      border: none;
      font-size: 0.9rem;
    }
    .btn-primary {
      background: linear-gradient(135deg, var(--primary) 0%, var(--cyan) 100%);
      color: #fff;
      box-shadow: 0 4px 15px rgba(147, 51, 234, 0.35);
    }
    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 25px rgba(0, 229, 255, 0.45);
    }
    .btn-secondary {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #fff;
    }
    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.15);
      transform: translateY(-2px);
    }
    .btn-danger {
      background: rgba(239, 68, 68, 0.2);
      border: 1px solid rgba(239, 68, 68, 0.5);
      color: #ef4444;
    }
    .btn-danger:hover {
      background: rgba(239, 68, 68, 0.4);
      color: #fff;
    }
    .btn-sm { padding: 0.45rem 0.85rem; font-size: 0.8rem; }

    /* SEARCH INPUT */
    .search-hero-box {
      display: flex;
      align-items: center;
      background: rgba(15, 20, 34, 0.8);
      border: 1px solid rgba(147, 51, 234, 0.4);
      border-radius: var(--radius-lg);
      padding: 0.75rem 1.2rem;
      gap: 0.8rem;
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
      width: 100%;
    }
    .search-hero-box:focus-within {
      border-color: var(--cyan);
      box-shadow: 0 0 25px var(--cyan-glow);
    }
    .search-input {
      background: transparent;
      border: none;
      outline: none;
      color: #fff;
      font-size: 1.05rem;
      font-family: inherit;
      width: 100%;
    }
    .search-input::placeholder { color: var(--text-dim); }

    /* RESULTS GRID */
    .tracks-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1.1rem;
      margin-top: 1.2rem;
    }
    .track-card {
      background: rgba(20, 26, 42, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: var(--radius-md);
      padding: 0.85rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      transition: all 0.2s;
    }
    .track-card:hover {
      background: rgba(30, 38, 62, 0.9);
      border-color: rgba(147, 51, 234, 0.5);
      transform: translateY(-3px);
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
    }
    .track-card-top {
      display: flex;
      gap: 0.85rem;
    }
    .track-card-thumb {
      width: 68px;
      height: 68px;
      border-radius: 10px;
      object-fit: cover;
      background: #141724;
      flex-shrink: 0;
    }
    .track-card-info {
      display: flex;
      flex-direction: column;
      justify-content: center;
      min-width: 0;
    }
    .track-card-title {
      font-size: 0.92rem;
      font-weight: 700;
      color: #fff;
      line-height: 1.3;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .track-card-artist {
      font-size: 0.78rem;
      color: var(--cyan);
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .track-card-dur {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: var(--text-dim);
      margin-top: 0.2rem;
    }
    .track-card-actions {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 0.4rem;
      margin-top: auto;
    }

    /* VINYL HERO CARD */
    .hero-now-playing {
      display: grid;
      grid-template-columns: 210px 1fr;
      gap: 2.2rem;
      align-items: center;
      background: linear-gradient(135deg, rgba(22, 16, 40, 0.92) 0%, rgba(12, 17, 30, 0.95) 100%);
      border: 1px solid rgba(147, 51, 234, 0.38);
      border-radius: var(--radius-lg);
      padding: 2.2rem;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7), 0 0 35px rgba(147, 51, 234, 0.15);
      position: relative;
      overflow: hidden;
    }
    @media (max-width: 768px) {
      .hero-now-playing {
        grid-template-columns: 1fr;
        justify-items: center;
        text-align: center;
        padding: 1.5rem;
      }
    }
    .vinyl-wrapper {
      position: relative;
      width: 190px;
      height: 190px;
      border-radius: 50%;
      padding: 6px;
      background: radial-gradient(circle, rgba(147, 51, 234, 0.4) 0%, rgba(0, 229, 255, 0.2) 65%, transparent 100%);
      box-shadow: 0 10px 30px rgba(0,0,0,0.8), 0 0 25px rgba(147, 51, 234, 0.35);
    }
    .vinyl-disc {
      width: 100%;
      height: 100%;
      border-radius: 50%;
      object-fit: cover;
      border: 3px solid rgba(255, 255, 255, 0.15);
    }
    .vinyl-disc.spin {
      animation: spinVinyl 14s linear infinite;
    }
    @keyframes spinVinyl {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }

    /* QUEUE TABLE */
    .queue-table {
      width: 100%;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      margin-top: 1rem;
    }
    .queue-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(18, 23, 37, 0.65);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: var(--radius-md);
      padding: 0.75rem 1rem;
      gap: 1rem;
      transition: all 0.15s ease;
    }
    .queue-row:hover {
      border-color: rgba(147, 51, 234, 0.4);
      background: rgba(147, 51, 234, 0.1);
      transform: translateX(4px);
    }
    .queue-row-left {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      min-width: 0;
    }
    .queue-num {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      color: var(--text-dim);
      width: 24px;
      text-align: center;
    }
    .queue-thumb {
      width: 44px;
      height: 44px;
      border-radius: 8px;
      object-fit: cover;
      background: #141724;
      flex-shrink: 0;
    }
    .queue-meta {
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .queue-title {
      font-size: 0.9rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .queue-artist {
      font-size: 0.76rem;
      color: var(--text-muted);
    }
    .queue-row-right {
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }

    /* EQUALIZER PRESET GRID */
    .eq-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 0.85rem;
      margin-top: 1rem;
    }
    .eq-chip {
      background: rgba(22, 28, 46, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: var(--radius-md);
      padding: 0.9rem 0.6rem;
      text-align: center;
      cursor: pointer;
      font-weight: 700;
      font-size: 0.85rem;
      color: var(--text-muted);
      transition: all 0.2s;
    }
    .eq-chip:hover {
      background: rgba(147, 51, 234, 0.25);
      border-color: var(--primary);
      color: #fff;
      transform: translateY(-2px);
    }
    .eq-chip.active {
      background: linear-gradient(135deg, rgba(147, 51, 234, 0.5) 0%, rgba(0, 229, 255, 0.3) 100%);
      border-color: var(--cyan);
      color: #fff;
      box-shadow: 0 0 15px var(--cyan-glow);
    }

    /* MODAL */
    .modal-backdrop {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(12px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 10000;
      padding: 1rem;
    }
    .modal-backdrop.open { display: flex; }
    .modal-content {
      background: #0f1424;
      border: 1px solid rgba(147, 51, 234, 0.4);
      border-radius: var(--radius-lg);
      padding: 1.8rem;
      width: 100%;
      max-width: 480px;
      box-shadow: 0 25px 60px rgba(0, 0, 0, 0.8);
    }
  </style>
</head>
<body>

  <div class="app-layout">

    <!-- DESKTOP / MOBILE SIDEBAR -->
    <aside class="sidebar" id="sidebar">
      <a class="brand-box" onclick="navigate('/')">
        <div class="brand-avatar">🎵</div>
        <div class="brand-title-wrap">
          <h1>MusicMaid</h1>
          <p>320kbps Lossless</p>
        </div>
      </a>

      <!-- ACTIVE DISCORD GUILD SWITCHER -->
      <div class="server-switcher" onclick="toggleServerMenu(event)">
        <div class="server-active-info">
          <div class="server-icon" id="server-icon-badge">⚡</div>
          <div class="server-names">
            <span class="server-name-text" id="active-server-name">Loading Server...</span>
            <span class="server-status-sub"><span class="pulse-dot"></span> <span id="active-server-vc">Checking Voice</span></span>
          </div>
        </div>
        <span style="font-size:0.75rem; color:var(--text-dim);">▼</span>
        <div class="server-dropdown-menu" id="server-dropdown-menu">
          <!-- Populated dynamically -->
        </div>
      </div>

      <!-- MAIN NAVIGATION -->
      <span class="nav-group-title">Music Engine</span>
      <ul class="nav-list">
        <li><a class="nav-link active" id="nav-dashboard" onclick="navigate('/')"><span class="nav-icon">🏠</span> Dashboard</a></li>
        <li><a class="nav-link" id="nav-search" onclick="navigate('/search')"><span class="nav-icon">🔍</span> Search & Discover</a></li>
        <li><a class="nav-link" id="nav-queue" onclick="navigate('/queue')"><span class="nav-icon">🎵</span> Queue & Live Player</a></li>
        <li><a class="nav-link" id="nav-autodj" onclick="navigate('/autodj')"><span class="nav-icon">🤖</span> Smart Auto-DJ</a></li>
        <li><a class="nav-link" id="nav-library" onclick="navigate('/library')"><span class="nav-icon">📚</span> Playlists & Library</a></li>
        <li><a class="nav-link" id="nav-audio" onclick="navigate('/audio')"><span class="nav-icon">🎛️</span> Equalizer & DSP</a></li>
        <li><a class="nav-link" id="nav-stats" onclick="navigate('/stats')"><span class="nav-icon">📊</span> Telemetry & Health</a></li>
      </ul>

      <!-- SIDEBAR FOOTER -->
      <div class="sidebar-footer">
        <div class="voice-badge-card" id="sidebar-voice-pill">
          <span>🔊</span> <span id="sidebar-vc-text">Connecting to Voice Engine...</span>
        </div>
        <div id="auth-box-sidebar">
          <a class="btn-login-discord" id="btn-login-link" href="/api/auth/url">
            <span>👾 Sign in with Discord</span>
          </a>
        </div>
      </div>
    </aside>

    <!-- MAIN WORKSPACE -->
    <main class="content-area">
      <!-- MOBILE TOP BAR -->
      <div class="mobile-top-bar">
        <div style="display:flex; align-items:center; gap:0.6rem;">
          <button class="mobile-btn" onclick="toggleMobileSidebar()">☰</button>
          <span style="font-weight:800; font-size:1.1rem; color:#fff;">MusicMaid</span>
        </div>
        <div id="mobile-voice-status" style="font-size:0.78rem; color:var(--cyan); font-weight:700;">320kbps Online</div>
      </div>

      <!-- DYNAMIC VIEW CONTAINER -->
      <div id="view-container">
        <!-- Rendered via JavaScript -->
      </div>
    </main>

  </div>

  <!-- PERSISTENT BOTTOM PLAYBACK BAR -->
  <footer class="player-bar">
    <!-- LEFT: TRACK METADATA -->
    <div class="player-bar-left">
      <img id="bar-art" class="bar-thumb" src="https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=120" alt="Album Cover">
      <div class="bar-meta">
        <span class="bar-title" id="bar-title" onclick="navigate('/queue')">No Track Playing</span>
        <span class="bar-artist" id="bar-artist">Join a voice channel and play a song</span>
      </div>
      <button class="btn-fav" id="bar-fav-btn" onclick="toggleCurrentFavorite()" title="Save to Favorites">♡</button>
    </div>

    <!-- CENTER: CONTROLS & SCRUBBER -->
    <div class="player-bar-center">
      <div class="player-buttons-row">
        <button class="p-btn" id="btn-shuffle" onclick="dispatchCmd('SHUFFLE')" title="Shuffle Queue">🔀</button>
        <button class="p-btn" onclick="dispatchCmd('PREVIOUS')" title="Previous Track">⏮</button>
        <button class="p-btn p-btn-play" id="btn-master-play" onclick="togglePlayPause()" title="Play / Pause">▶</button>
        <button class="p-btn" onclick="dispatchCmd('SKIP')" title="Skip Track">⏭</button>
        <button class="p-btn" id="btn-loop" onclick="cycleLoopMode()" title="Toggle Loop (Off / Track / Queue)">🔁</button>
      </div>
      <div class="scrub-row">
        <span class="scrub-time" id="scrub-current">00:00</span>
        <input type="range" class="slider-track" id="scrub-slider" min="0" max="100" value="0" oninput="onScrubInput(this.value)" onchange="onScrubChange(this.value)">
        <span class="scrub-time" id="scrub-total">00:00</span>
      </div>
    </div>

    <!-- RIGHT: VOLUME & QUICK TOGGLES -->
    <div class="player-bar-right">
      <button class="chip-pill" id="btn-247-pill" onclick="dispatchCmd('247_TOGGLE')" title="Toggle 24/7 Voice Persistence">24/7 OFF</button>
      <div class="vol-wrapper">
        <span style="font-size:0.9rem; color:var(--text-dim);" id="vol-icon" onclick="quickMute()">🔊</span>
        <input type="range" class="slider-track" id="vol-slider" min="0" max="150" value="80" onchange="onVolumeChange(this.value)" title="Volume Slider">
      </div>
      <button class="p-btn" onclick="navigate('/queue')" title="Open Queue">📜</button>
    </div>
  </footer>

  <!-- TOAST CONTAINER -->
  <div id="toast-container"></div>

  <!-- PLAYLIST SAVE MODAL -->
  <div class="modal-backdrop" id="playlist-modal">
    <div class="modal-content">
      <div class="section-title" style="margin-bottom:0.8rem;">💾 Save Current Queue to Playlist</div>
      <p style="font-size:0.82rem; color:var(--text-muted); margin-bottom:1rem;">Enter a playlist name to snapshot the current queue into your server library.</p>
      <input type="text" id="playlist-name-input" class="search-input" placeholder="e.g. Midnight Vibe 2026" style="background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.15); border-radius:var(--radius-md); padding:0.75rem 1rem; width:100%; margin-bottom:1.2rem;">
      <div style="display:flex; justify-content:flex-end; gap:0.6rem;">
        <button class="btn btn-secondary btn-sm" onclick="closePlaylistModal()">Cancel</button>
        <button class="btn btn-primary btn-sm" onclick="confirmSavePlaylist()">Save Playlist</button>
      </div>
    </div>
  </div>

  <script>
    // =========================================================================
    // GLOBAL STATE & DISCORD BOT SYNCHRONIZATION ENGINE
    // =========================================================================
    let currentGuildId = "1525030316845301781";
    let activeGuilds = [];
    let currentSession = null;
    let currentQueue = [];
    let playbackSeconds = 0;
    let trackDurationSeconds = 0;
    let isPlaying = false;
    let isPaused = false;
    let pollTimer = null;
    let progressTimer = null;
    let isScrubbing = false;
    let currentUser = null;
    let ws = null;

    // =========================================================================
    // INITIALIZATION & REAL-TIME WEBSOCKET
    // =========================================================================
    document.addEventListener("DOMContentLoaded", async () => {
      setupRealtimeWebSocket();
      await fetchAuthStatus();
      await fetchGuilds();
      await syncAll();

      // Start synchronized progress timer (1-second tick)
      progressTimer = setInterval(tickProgress, 1000);
      // Fast polling fallback (every 3 seconds)
      pollTimer = setInterval(syncAll, 3000);

      // Handle Route
      handleRoute();
      window.addEventListener('popstate', handleRoute);

      // Spacebar Play/Pause Shortcut
      window.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.code === 'Space') {
          e.preventDefault();
          togglePlayPause();
        }
      });
    });

    function setupRealtimeWebSocket() {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${proto}//${location.host}/api/realtime/ws`;
      try {
        ws = new WebSocket(wsUrl);
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.event === "MUSIC_UPDATED" || data.event === "PULSE_UPDATED") {
              syncAll();
            }
          } catch(e){}
        };
        ws.onclose = () => { setTimeout(setupRealtimeWebSocket, 5000); };
      } catch(e) {
        console.warn("WebSocket fallback to polling:", e);
      }
    }

    async function fetchAuthStatus() {
      try {
        const res = await fetch('/api/auth/me');
        const json = await res.json();
        if (json.success && json.data && json.data.authenticated) {
          currentUser = json.data.user;
          renderAuthBox(currentUser);
        } else {
          renderAuthBox(null);
        }
      } catch(e) {
        renderAuthBox(null);
      }
    }

    function renderAuthBox(user) {
      const el = document.getElementById('auth-box-sidebar');
      if (user) {
        el.innerHTML = `
          <div class="user-pill">
            <div class="user-meta">
              <img src="${user.avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png'}" class="user-avatar" alt="Avatar">
              <span class="user-name">${user.display_name || user.username}</span>
            </div>
            <button class="btn-logout" onclick="logoutUser()" title="Logout">🚪</button>
          </div>
        `;
      } else {
        el.innerHTML = `
          <a class="btn-login-discord" href="/api/auth/url">
            <span>👾 Sign in with Discord</span>
          </a>
        `;
      }
    }

    async function logoutUser() {
      await fetch('/api/auth/logout', { method: 'POST' });
      currentUser = null;
      renderAuthBox(null);
      showToast("Logged out successfully");
    }

    // =========================================================================
    // GUILD SELECTOR & ACTIVE AUDIO SESSION
    // =========================================================================
    async function fetchGuilds() {
      try {
        const res = await fetch('/api/music/guilds');
        const json = await res.json();
        if (json.success && json.data.guilds) {
          activeGuilds = json.data.guilds;
          if (activeGuilds.length > 0 && !activeGuilds.some(g => g.id === currentGuildId)) {
            currentGuildId = activeGuilds[0].id;
          }
          renderGuildDropdown();
        }
      } catch(e) {}
    }

    function renderGuildDropdown() {
      const active = activeGuilds.find(g => g.id === currentGuildId) || { name: "MusicMaid Server", id: currentGuildId };
      document.getElementById('active-server-name').innerText = active.name;
      document.getElementById('server-icon-badge').innerText = active.name.charAt(0);

      const menu = document.getElementById('server-dropdown-menu');
      menu.innerHTML = activeGuilds.map(g => `
        <div class="server-opt ${g.id === currentGuildId ? 'selected' : ''}" onclick="selectServer('${g.id}')">
          <div class="server-icon" style="width:24px; height:24px; font-size:0.75rem;">${g.name.charAt(0)}</div>
          <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${g.name}</span>
          ${g.has_active_playback ? '<span style="color:var(--emerald); margin-left:auto;">▶</span>' : ''}
        </div>
      `).join('');
    }

    function toggleServerMenu(e) {
      e.stopPropagation();
      document.getElementById('server-dropdown-menu').classList.toggle('open');
    }
    document.addEventListener('click', () => {
      document.getElementById('server-dropdown-menu')?.classList.remove('open');
    });

    async function selectServer(guildId) {
      currentGuildId = guildId;
      renderGuildDropdown();
      showToast(`Switched active server`);
      await syncAll();
    }

    // =========================================================================
    // CORE SYNC & DATA FETCHING
    // =========================================================================
    async function syncAll() {
      await Promise.all([syncSession(), syncQueue()]);
      updateActiveView();
    }

    async function syncSession() {
      try {
        const res = await fetch(`/api/music/session?guild_id=${currentGuildId}`);
        const json = await res.json();
        if (json.success && json.data) {
          currentSession = json.data;
          isPlaying = currentSession.is_playing;
          isPaused = currentSession.is_paused;
          trackDurationSeconds = currentSession.duration_seconds || 0;
          if (!isScrubbing) {
            playbackSeconds = currentSession.position_seconds || 0;
          }
          updatePlaybackBarUI();
        }
      } catch(e) {}
    }

    async function syncQueue() {
      try {
        const res = await fetch(`/api/music/queue?guild_id=${currentGuildId}`);
        const json = await res.json();
        if (json.success && json.data) {
          currentQueue = json.data.tracks || [];
        }
      } catch(e) {}
    }

    function tickProgress() {
      if (isPlaying && !isPaused && trackDurationSeconds > 0) {
        if (!isScrubbing) {
          playbackSeconds = Math.min(trackDurationSeconds, playbackSeconds + 1);
          updateScrubberTimes();
        }
      }
    }

    function updatePlaybackBarUI() {
      if (!currentSession) return;
      const t = currentSession.current_track;
      const titleEl = document.getElementById('bar-title');
      const artistEl = document.getElementById('bar-artist');
      const artEl = document.getElementById('bar-art');
      const playBtn = document.getElementById('btn-master-play');
      const loopBtn = document.getElementById('btn-loop');
      const pill247 = document.getElementById('btn-247-pill');
      const vcText = document.getElementById('sidebar-vc-text');
      const activeVcEl = document.getElementById('active-server-vc');

      if (t) {
        titleEl.innerText = t.title;
        artistEl.innerText = t.artist || "Unknown Artist";
        if (t.thumbnail) artEl.src = t.thumbnail;
      } else {
        titleEl.innerText = "Queue is Empty";
        artistEl.innerText = "Ready for songs — type a query or play from search";
      }

      playBtn.innerText = isPlaying && !isPaused ? "⏸" : "▶";

      // Loop Icon State
      const loop = currentSession.loop_mode || "off";
      loopBtn.className = "p-btn " + (loop !== "off" ? "active" : "");
      loopBtn.innerText = loop === "track" ? "🔂" : "🔁";

      // 24/7 pill
      pill247.innerText = currentSession.twenty_four_seven ? "24/7 ON" : "24/7 OFF";
      pill247.className = "chip-pill " + (currentSession.twenty_four_seven ? "active" : "");

      // Voice channel pill
      const vc = currentSession.voice_channel_name || "#Voice Channel";
      vcText.innerText = vc;
      activeVcEl.innerText = vc;

      // Volume
      document.getElementById('vol-slider').value = currentSession.volume || 80;

      updateScrubberTimes();
    }

    function updateScrubberTimes() {
      document.getElementById('scrub-current').innerText = formatTime(playbackSeconds);
      document.getElementById('scrub-total').innerText = formatTime(trackDurationSeconds);
      if (!isScrubbing && trackDurationSeconds > 0) {
        document.getElementById('scrub-slider').value = Math.floor((playbackSeconds / trackDurationSeconds) * 100);
      }
    }

    function formatTime(sec) {
      if (!sec || isNaN(sec) || sec <= 0) return "00:00";
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
    }

    // =========================================================================
    // DISPATCH ACTIONS
    // =========================================================================
    async function dispatchCmd(action, payload = {}) {
      try {
        const res = await fetch('/api/music/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            guild_id: currentGuildId,
            action: action,
            payload: payload
          })
        });
        const json = await res.json();
        if (json.success) {
          showToast(`Executed: ${action}`);
          await syncAll();
        } else {
          showToast(json.error?.message || "Command failed", "danger");
        }
      } catch(e) {
        showToast("Network error executing command", "danger");
      }
    }

    async function togglePlayPause() {
      if (isPlaying && !isPaused) {
        await dispatchCmd('PAUSE');
      } else {
        await dispatchCmd('RESUME');
      }
    }

    async function cycleLoopMode() {
      await dispatchCmd('LOOP');
    }

    function onScrubInput(val) {
      isScrubbing = true;
      if (trackDurationSeconds > 0) {
        playbackSeconds = Math.floor((val / 100) * trackDurationSeconds);
        document.getElementById('scrub-current').innerText = formatTime(playbackSeconds);
      }
    }

    async function onScrubChange(val) {
      isScrubbing = false;
      if (trackDurationSeconds > 0) {
        const targetSec = Math.floor((val / 100) * trackDurationSeconds);
        await dispatchCmd('SEEK', { seconds: targetSec });
      }
    }

    async function onVolumeChange(val) {
      await dispatchCmd('VOLUME', { volume: parseInt(val) });
    }

    function quickMute() {
      const slider = document.getElementById('vol-slider');
      if (parseInt(slider.value) > 0) {
        slider.value = 0;
        onVolumeChange(0);
      } else {
        slider.value = 80;
        onVolumeChange(80);
      }
    }

    async function toggleCurrentFavorite() {
      if (!currentSession || !currentSession.current_track) {
        showToast("No active song to favorite", "danger");
        return;
      }
      const t = currentSession.current_track;
      try {
        const res = await fetch('/api/music/favorites/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(t)
        });
        const json = await res.json();
        if (json.success) {
          showToast(json.data.message || "Updated Favorites ❤️");
          document.getElementById('bar-fav-btn').classList.toggle('active', json.data.favorited);
        }
      } catch(e){}
    }

    function showToast(msg, type = "success") {
      const container = document.getElementById('toast-container');
      const toast = document.createElement('div');
      toast.className = 'toast-msg';
      if (type === "danger") toast.style.borderColor = "var(--danger)";
      toast.innerHTML = `<span>${type === 'danger' ? '⚠️' : '✦'}</span> <span>${msg}</span>`;
      container.appendChild(toast);
      setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
      }, 3000);
    }

    function toggleMobileSidebar() {
      document.getElementById('sidebar').classList.toggle('mobile-open');
    }

    // =========================================================================
    // CLIENT-SIDE ROUTER & VIEW RENDERING
    // =========================================================================
    function navigate(route) {
      window.history.pushState({}, '', route);
      handleRoute();
      document.getElementById('sidebar')?.classList.remove('mobile-open');
    }

    function handleRoute() {
      const path = location.pathname;
      document.querySelectorAll('.nav-link').forEach(el => el.classList.remove('active'));

      if (path === '/' || path === '/dashboard') {
        document.getElementById('nav-dashboard')?.classList.add('active');
        renderDashboard();
      } else if (path === '/search') {
        document.getElementById('nav-search')?.classList.add('active');
        renderSearch();
      } else if (path === '/queue') {
        document.getElementById('nav-queue')?.classList.add('active');
        renderQueue();
      } else if (path === '/autodj') {
        document.getElementById('nav-autodj')?.classList.add('active');
        renderAutoDJ();
      } else if (path === '/library') {
        document.getElementById('nav-library')?.classList.add('active');
        renderLibrary();
      } else if (path === '/audio') {
        document.getElementById('nav-audio')?.classList.add('active');
        renderAudioDSP();
      } else if (path === '/stats') {
        document.getElementById('nav-stats')?.classList.add('active');
        renderStats();
      } else {
        renderDashboard();
      }
    }

    function updateActiveView() {
      const path = location.pathname;
      if (path === '/' || path === '/dashboard') {
        updateDashboardDynamicElements();
      } else if (path === '/queue') {
        updateQueueList();
      }
    }

    // =========================================================================
    // VIEW 1: DASHBOARD OVERVIEW
    // =========================================================================
    function renderDashboard() {
      const container = document.getElementById('view-container');
      const t = currentSession?.current_track;

      container.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:1.8rem;">

          <!-- HERO NOW PLAYING VINYL CARD -->
          <div class="hero-now-playing">
            <div class="vinyl-wrapper">
              <img id="hero-vinyl-art" class="vinyl-disc ${isPlaying && !isPaused ? 'spin' : ''}" src="${t?.thumbnail || 'https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=350'}" alt="Vinyl Art">
            </div>
            <div style="display:flex; flex-direction:column; gap:0.9rem; min-width:0;">
              <div style="display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap;">
                <span class="chip-pill" style="color:var(--emerald); background:rgba(16, 185, 129, 0.15);">● 320kbps Lossless Opus</span>
                <span class="chip-pill" id="hero-state-pill">${currentSession?.state || 'IDLE'}</span>
                <span class="chip-pill" id="hero-vc-pill">🔊 ${currentSession?.voice_channel_name || 'No Voice Room'}</span>
              </div>
              <h2 id="hero-track-title" style="font-size:1.85rem; font-weight:800; color:#fff; line-height:1.2; word-break:break-word;">
                ${t ? t.title : 'Ready for Music — The Queue is Empty'}
              </h2>
              <p id="hero-track-artist" style="font-size:1.05rem; color:var(--cyan); font-weight:600;">
                ${t ? (t.artist || 'Unknown Artist') : 'Use /play <query> in Discord or search songs below'}
              </p>

              <!-- HERO SCRUBBER -->
              <div style="display:flex; flex-direction:column; gap:0.35rem; width:100%; max-width:540px; margin-top:0.3rem;">
                <input type="range" class="slider-track" id="hero-scrub-slider" min="0" max="100" value="0" oninput="onScrubInput(this.value)" onchange="onScrubChange(this.value)">
                <div style="display:flex; justify-content:space-between; font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:var(--text-muted);">
                  <span id="hero-time-curr">${formatTime(playbackSeconds)}</span>
                  <span id="hero-time-total">${formatTime(trackDurationSeconds)}</span>
                </div>
              </div>

              <!-- QUICK ACTION BUTTONS CLUSTER -->
              <div style="display:flex; align-items:center; gap:0.75rem; flex-wrap:wrap; margin-top:0.4rem;">
                <button class="btn btn-primary btn-sm" onclick="togglePlayPause()" id="hero-play-btn">
                  <span>${isPlaying && !isPaused ? '⏸ Pause' : '▶ Play'}</span>
                </button>
                <button class="btn btn-secondary btn-sm" onclick="dispatchCmd('SKIP')">
                  <span>⏭ Skip</span>
                </button>
                <button class="btn btn-secondary btn-sm" onclick="dispatchCmd('SHUFFLE')">
                  <span>🔀 Shuffle</span>
                </button>
                <button class="btn btn-secondary btn-sm" onclick="navigate('/search')">
                  <span>🔍 Add Song</span>
                </button>
                <button class="btn btn-secondary btn-sm" onclick="openPlaylistModal()">
                  <span>💾 Save Playlist</span>
                </button>
              </div>
            </div>
          </div>

          <!-- METRICS & QUEUE PREVIEW ROW -->
          <div style="display:grid; grid-template-columns:2fr 1fr; gap:1.5rem;">

            <!-- QUEUE PREVIEW CARD -->
            <div class="glass-card">
              <div class="section-header">
                <span class="section-title"><span>📜</span> Upcoming Queue (${currentQueue.length})</span>
                <button class="btn btn-secondary btn-sm" onclick="navigate('/queue')">Full Queue ↗</button>
              </div>
              <div id="dash-queue-list" class="queue-table">
                ${renderQueuePreviewHtml()}
              </div>
            </div>

            <!-- SMART AUTO-DJ & EQUALIZER QUICK WIDGET -->
            <div style="display:flex; flex-direction:column; gap:1.4rem;">
              <div class="glass-card" style="padding:1.3rem;">
                <div class="section-header" style="margin-bottom:0.8rem;">
                  <span class="section-title" style="font-size:1.1rem;"><span>🤖</span> Smart Auto-DJ</span>
                  <button class="btn btn-sm ${currentSession?.auto_dj ? 'btn-primary' : 'btn-secondary'}" onclick="dispatchCmd('AUTODJ_TOGGLE')">
                    ${currentSession?.auto_dj ? 'ACTIVE ✅' : 'ENABLE'}
                  </button>
                </div>
                <p style="font-size:0.82rem; color:var(--text-muted); line-height:1.5;">
                  Continuous non-stop playback. When queue is empty, MusicMaid intelligently selects tracks matching your current mood.
                </p>
                <div style="margin-top:0.8rem; display:flex; gap:0.4rem; flex-wrap:wrap;">
                  <span class="chip-pill ${currentSession?.dj_mood === 'balanced' ? 'active' : ''}" onclick="dispatchCmd('AUTODJ_MOOD', {mood:'balanced'})">Balanced</span>
                  <span class="chip-pill ${currentSession?.dj_mood === 'energetic' ? 'active' : ''}" onclick="dispatchCmd('AUTODJ_MOOD', {mood:'energetic'})">Energetic</span>
                  <span class="chip-pill ${currentSession?.dj_mood === 'chill' ? 'active' : ''}" onclick="dispatchCmd('AUTODJ_MOOD', {mood:'chill'})">Chill</span>
                </div>
              </div>

              <!-- EQUALIZER PRESETS CARD -->
              <div class="glass-card" style="padding:1.3rem;">
                <div class="section-header" style="margin-bottom:0.6rem;">
                  <span class="section-title" style="font-size:1.1rem;"><span>🎛️</span> DSP Audio Preset</span>
                  <span class="chip-pill active" id="dash-eq-badge">${currentSession?.eq_preset || 'Flat'}</span>
                </div>
                <div class="eq-grid" style="grid-template-columns: repeat(2, 1fr); margin-top:0.5rem;">
                  <div class="eq-chip" onclick="dispatchCmd('FILTER', {preset:'bassboost', name:'Bass Boost'})">🔥 Bass Boost</div>
                  <div class="eq-chip" onclick="dispatchCmd('FILTER', {preset:'nightcore', name:'Nightcore'})">⚡ Nightcore</div>
                  <div class="eq-chip" onclick="dispatchCmd('FILTER', {preset:'8d', name:'8D Audio'})">🎧 8D Spatial</div>
                  <div class="eq-chip" onclick="dispatchCmd('FILTER', {preset:'flat', name:'Flat Studio'})">🎵 Flat Pure</div>
                </div>
              </div>
            </div>

          </div>

        </div>
      `;
    }

    function renderQueuePreviewHtml() {
      if (!currentQueue || currentQueue.length === 0) {
        return `
          <div style="text-align:center; padding:2rem; color:var(--text-muted); font-size:0.88rem;">
            🐾 The upcoming queue is currently empty.<br>
            Search songs in the <b style="color:var(--cyan); cursor:pointer;" onclick="navigate('/search')">Search & Discover</b> tab to queue tracks!
          </div>
        `;
      }
      return currentQueue.slice(0, 5).map((q, i) => `
        <div class="queue-row">
          <div class="queue-row-left">
            <span class="queue-num">${i + 1}</span>
            <img class="queue-thumb" src="${q.thumbnail || 'https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=100'}" alt="Thumb">
            <div class="queue-meta">
              <span class="queue-title">${q.title}</span>
              <span class="queue-artist">${q.artist || 'Unknown'} • Req by ${q.requester_name || 'User'}</span>
            </div>
          </div>
          <div class="queue-row-right">
            <span style="font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:var(--text-muted);">${formatTime(q.duration)}</span>
            <button class="btn btn-secondary btn-sm" onclick="dispatchCmd('REMOVE', {index:${i}})" title="Remove Track">✕</button>
          </div>
        </div>
      `).join('');
    }

    function updateDashboardDynamicElements() {
      const heroArt = document.getElementById('hero-vinyl-art');
      if (heroArt) {
        heroArt.className = `vinyl-disc ${isPlaying && !isPaused ? 'spin' : ''}`;
        if (currentSession?.current_track?.thumbnail) {
          heroArt.src = currentSession.current_track.thumbnail;
        }
      }
      const heroPlayBtn = document.getElementById('hero-play-btn');
      if (heroPlayBtn) {
        heroPlayBtn.innerHTML = `<span>${isPlaying && !isPaused ? '⏸ Pause' : '▶ Play'}</span>`;
      }
      const queueList = document.getElementById('dash-queue-list');
      if (queueList) {
        queueList.innerHTML = renderQueuePreviewHtml();
      }
      const heroCurr = document.getElementById('hero-time-curr');
      const heroTotal = document.getElementById('hero-time-total');
      const heroSlider = document.getElementById('hero-scrub-slider');
      if (heroCurr && heroTotal && heroSlider) {
        heroCurr.innerText = formatTime(playbackSeconds);
        heroTotal.innerText = formatTime(trackDurationSeconds);
        if (!isScrubbing && trackDurationSeconds > 0) {
          heroSlider.value = Math.floor((playbackSeconds / trackDurationSeconds) * 100);
        }
      }
    }

    // =========================================================================
    // VIEW 2: SEARCH & DISCOVER (MULTI-LINGUAL / YOUTUBE / SPOTIFY)
    // =========================================================================
    let searchDebounce = null;
    function renderSearch() {
      const container = document.getElementById('view-container');
      container.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:1.6rem;">
          <div class="glass-card" style="padding:2rem;">
            <div class="section-title" style="margin-bottom:0.6rem;">
              <span>🔍</span> Search & Discover Music
            </div>
            <p style="font-size:0.86rem; color:var(--text-muted); margin-bottom:1.2rem;">
              High-speed YouTube & Spotify search with Tamil, Hindi, Telugu, and English multi-lingual recognition.
            </p>

            <!-- SEARCH BAR -->
            <div class="search-hero-box">
              <span style="font-size:1.2rem; color:var(--cyan);">🔍</span>
              <input type="text" id="live-search-input" class="search-input" placeholder="Type song name, artist, YouTube URL, or Spotify link..." oninput="onSearchInput(this.value)" autocomplete="off">
              <button class="btn btn-primary btn-sm" onclick="triggerSearch()">Search</button>
            </div>

            <!-- MULTI-LINGUAL QUICK SUGGESTIONS -->
            <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-top:1rem; align-items:center;">
              <span style="font-size:0.75rem; color:var(--text-dim); font-weight:700;">POPULAR:</span>
              <span class="chip-pill" onclick="quickFillSearch('Anirudh Ravichander hits')">🎵 Anirudh</span>
              <span class="chip-pill" onclick="quickFillSearch('A.R. Rahman Tamil classics')">✨ A.R. Rahman</span>
              <span class="chip-pill" onclick="quickFillSearch('Yuvan Shankar Raja vibes')">⚡ Yuvan</span>
              <span class="chip-pill" onclick="quickFillSearch('Arijit Singh Hindi melodies')">🎻 Arijit Singh</span>
              <span class="chip-pill" onclick="quickFillSearch('Lofi Hip Hop Chill Beats')">☕ Lo-Fi Chill</span>
              <span class="chip-pill" onclick="quickFillSearch('Synthwave Gaming 2026')">🕹️ Synthwave</span>
            </div>
          </div>

          <!-- RESULTS CONTAINER -->
          <div class="glass-card">
            <div class="section-header">
              <span class="section-title"><span>🎧</span> Search Results</span>
              <span id="search-status-label" style="font-size:0.82rem; color:var(--text-muted);">Ready to search</span>
            </div>
            <div id="search-results-grid" class="tracks-grid">
              <div style="grid-column: 1 / -1; text-align:center; padding:3rem; color:var(--text-muted);">
                Type a song or click any suggestion tag above to resolve tracks.
              </div>
            </div>
          </div>
        </div>
      `;
    }

    function quickFillSearch(query) {
      const input = document.getElementById('live-search-input');
      if (input) {
        input.value = query;
        triggerSearch();
      }
    }

    function onSearchInput(val) {
      if (searchDebounce) clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => {
        if (val.trim().length >= 2) triggerSearch();
      }, 450);
    }

    async function triggerSearch() {
      const q = document.getElementById('live-search-input')?.value.trim();
      if (!q) return;

      const grid = document.getElementById('search-results-grid');
      const label = document.getElementById('search-status-label');
      grid.innerHTML = `<div style="grid-column:1 / -1; text-align:center; padding:3rem; color:var(--cyan);">Resolving audio tracks from engine... ⏳</div>`;
      label.innerText = `Searching for "${q}"...`;

      try {
        const res = await fetch(`/api/music/search?q=${encodeURIComponent(q)}`);
        const json = await res.json();
        if (json.success && json.data && json.data.length > 0) {
          label.innerText = `Found ${json.data.length} matches`;
          grid.innerHTML = json.data.map(track => `
            <div class="track-card">
              <div class="track-card-top">
                <img class="track-card-thumb" src="${track.thumbnail || 'https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=150'}" alt="Art">
                <div class="track-card-info">
                  <span class="track-card-title" title="${track.title}">${track.title}</span>
                  <span class="track-card-artist">${track.artist || 'YouTube / Spotify'}</span>
                  <span class="track-card-dur">${formatTime(track.duration)}</span>
                </div>
              </div>
              <div class="track-card-actions">
                <button class="btn btn-primary btn-sm" onclick="actionPlayNow('${encodeURIComponent(track.url || track.title)}')" title="Play Immediately">⚡ Play Now</button>
                <button class="btn btn-secondary btn-sm" onclick="actionPlayNext('${encodeURIComponent(track.url || track.title)}')" title="Play Next in Queue">⏭ Next</button>
                <button class="btn btn-secondary btn-sm" onclick="actionEnqueue('${encodeURIComponent(track.url || track.title)}')" title="Add to End of Queue">➕ Queue</button>
              </div>
            </div>
          `).join('');
        } else {
          label.innerText = "No results found";
          grid.innerHTML = `<div style="grid-column:1 / -1; text-align:center; padding:3rem; color:var(--danger);">No playable tracks found. Please try another query or direct URL.</div>`;
        }
      } catch(e) {
        label.innerText = "Search failed";
        grid.innerHTML = `<div style="grid-column:1 / -1; text-align:center; padding:3rem; color:var(--danger);">Error communicating with resolver: ${e.message}</div>`;
      }
    }

    async function actionPlayNow(enc) {
      const q = decodeURIComponent(enc);
      showToast(`Playing "${q}" immediately...`);
      await dispatchCmd('PLAY_NOW', { query: q });
    }

    async function actionPlayNext(enc) {
      const q = decodeURIComponent(enc);
      showToast(`Added "${q}" as next song`);
      await dispatchCmd('PLAY_NEXT', { query: q });
    }

    async function actionEnqueue(enc) {
      const q = decodeURIComponent(enc);
      showToast(`Added "${q}" to queue`);
      await dispatchCmd('ENQUEUE', { query: q });
    }

    // =========================================================================
    // VIEW 3: LIVE PLAYER & QUEUE MANAGER
    // =========================================================================
    function renderQueue() {
      const container = document.getElementById('view-container');
      const t = currentSession?.current_track;

      container.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:1.6rem;">
          <!-- CURRENT TRACK BANNER -->
          <div class="glass-card" style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:1rem;">
            <div style="display:flex; align-items:center; gap:1.2rem;">
              <img src="${t?.thumbnail || 'https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=150'}" style="width:68px; height:68px; border-radius:12px; object-fit:cover;">
              <div>
                <span class="chip-pill" style="color:var(--emerald);">NOW STREAMING</span>
                <h3 style="font-size:1.25rem; font-weight:800; color:#fff; margin-top:0.3rem;">${t ? t.title : 'No Song Currently Playing'}</h3>
                <span style="font-size:0.85rem; color:var(--cyan);">${t ? (t.artist || 'Unknown Artist') : 'Queue tracks to start'}</span>
              </div>
            </div>
            <div style="display:flex; align-items:center; gap:0.6rem;">
              <button class="btn btn-secondary btn-sm" onclick="dispatchCmd('SHUFFLE')">🔀 Shuffle</button>
              <button class="btn btn-danger btn-sm" onclick="confirmClearQueue()">🗑 Clear Queue</button>
              <button class="btn btn-primary btn-sm" onclick="openPlaylistModal()">💾 Save as Playlist</button>
            </div>
          </div>

          <!-- FULL QUEUE LIST -->
          <div class="glass-card">
            <div class="section-header">
              <span class="section-title"><span>📜</span> Track Queue (<span id="queue-count-badge">${currentQueue.length}</span> tracks)</span>
              <span style="font-family:'JetBrains Mono',monospace; font-size:0.82rem; color:var(--text-muted);" id="queue-total-dur">Calculating Duration...</span>
            </div>
            <div class="queue-table" id="full-queue-container">
              ${renderFullQueueRows()}
            </div>
          </div>
        </div>
      `;
    }

    function renderFullQueueRows() {
      if (!currentQueue || currentQueue.length === 0) {
        return `<div style="text-align:center; padding:3.5rem; color:var(--text-muted);">🐾 The queue is empty! Add tracks from Search & Discover.</div>`;
      }
      return currentQueue.map((q, i) => `
        <div class="queue-row">
          <div class="queue-row-left">
            <span class="queue-num">${i + 1}</span>
            <img class="queue-thumb" src="${q.thumbnail || 'https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=100'}">
            <div class="queue-meta">
              <span class="queue-title">${q.title}</span>
              <span class="queue-artist">${q.artist || 'Unknown'} • Req by ${q.requester_name || 'Web'}</span>
            </div>
          </div>
          <div class="queue-row-right">
            <span style="font-family:'JetBrains Mono',monospace; font-size:0.8rem; color:var(--text-muted);">${formatTime(q.duration)}</span>
            ${i > 0 ? `<button class="btn btn-secondary btn-sm" onclick="moveTrack(${i}, ${i - 1})" title="Move Up">▲</button>` : ''}
            ${i < currentQueue.length - 1 ? `<button class="btn btn-secondary btn-sm" onclick="moveTrack(${i}, ${i + 1})" title="Move Down">▼</button>` : ''}
            <button class="btn btn-secondary btn-sm" onclick="dispatchCmd('REMOVE', {index:${i}})" title="Remove Track">✕</button>
          </div>
        </div>
      `).join('');
    }

    function updateQueueList() {
      const container = document.getElementById('full-queue-container');
      const badge = document.getElementById('queue-count-badge');
      if (container && badge) {
        badge.innerText = currentQueue.length;
        container.innerHTML = renderFullQueueRows();
      }
    }

    async function moveTrack(fromIdx, toIdx) {
      await dispatchCmd('MOVE', { from_index: fromIdx, to_index: toIdx });
    }

    async function confirmClearQueue() {
      if (confirm("Are you sure you want to clear the entire queue?")) {
        await dispatchCmd('CLEAR');
      }
    }

    // =========================================================================
    // VIEW 4: SMART AUTO-DJ & RADIO MODES
    // =========================================================================
    async function renderAutoDJ() {
      const container = document.getElementById('view-container');
      container.innerHTML = `<div style="text-align:center; padding:4rem; color:var(--cyan);">Loading Auto-DJ state...</div>`;

      try {
        const [statusRes, recsRes] = await Promise.all([
          fetch(`/api/music/autodj?guild_id=${currentGuildId}`),
          fetch(`/api/music/autodj/recommendations?guild_id=${currentGuildId}`)
        ]);
        const statusJson = await statusRes.json();
        const recsJson = await recsRes.json();
        const status = statusJson.data || {};
        const recs = recsJson.data || [];

        container.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:1.6rem;">
            <!-- MASTER SWITCH & MOOD CONTROLS -->
            <div class="glass-card" style="padding:2rem;">
              <div class="section-header">
                <div>
                  <div class="section-title"><span>🤖</span> Smart Auto-DJ 2.0</div>
                  <p style="font-size:0.86rem; color:var(--text-muted); margin-top:0.3rem;">
                    Proactive queue generation based on song features, artist discography, and genre affinity.
                  </p>
                </div>
                <button class="btn ${status.enabled ? 'btn-primary' : 'btn-secondary'}" onclick="toggleAutoDJStatus(!${status.enabled})">
                  ${status.enabled ? 'ACTIVE ✅' : 'DISABLED ❌'}
                </button>
              </div>

              <!-- MOOD SELECTION GRID -->
              <span class="nav-group-title" style="padding:0; margin-top:1.2rem; display:block;">Select Auto-DJ Vibe & Mood</span>
              <div class="eq-grid" style="grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); margin-top:0.6rem;">
                <div class="eq-chip ${status.mood === 'balanced' ? 'active' : ''}" onclick="setAutoDJMood('balanced')">⚖️ Balanced Mix</div>
                <div class="eq-chip ${status.mood === 'energetic' ? 'active' : ''}" onclick="setAutoDJMood('energetic')">🔥 High Energy</div>
                <div class="eq-chip ${status.mood === 'chill' ? 'active' : ''}" onclick="setAutoDJMood('chill')">🍃 Chill & Acoustic</div>
                <div class="eq-chip ${status.mood === 'gaming' ? 'active' : ''}" onclick="setAutoDJMood('gaming')">🕹️ Gaming Focus</div>
                <div class="eq-chip ${status.mood === 'party' ? 'active' : ''}" onclick="setAutoDJMood('party')">🎉 Party Anthem</div>
                <div class="eq-chip ${status.mood === 'lofi' ? 'active' : ''}" onclick="setAutoDJMood('lofi')">☕ Lo-Fi Beats</div>
              </div>
            </div>

            <!-- LIVE RECOMMENDATION CARDS -->
            <div class="glass-card">
              <div class="section-header">
                <span class="section-title"><span>✨</span> Dynamic Recommendations for You</span>
                <span style="font-size:0.82rem; color:var(--cyan);">${recs.length} matches analyzed</span>
              </div>
              <div class="tracks-grid">
                ${recs.length === 0 ? '<div style="grid-column:1 / -1; text-align:center; padding:2rem; color:var(--text-muted);">Play a track to generate contextual recommendations!</div>' :
                  recs.map(r => `
                    <div class="track-card">
                      <div class="track-card-top">
                        <img class="track-card-thumb" src="${r.thumbnail || 'https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=120'}">
                        <div class="track-card-info">
                          <span class="track-card-title">${r.title}</span>
                          <span class="track-card-artist">${r.artist}</span>
                          <span style="font-size:0.7rem; color:var(--text-dim); margin-top:0.2rem;">💡 ${r.reason}</span>
                        </div>
                      </div>
                      <div class="track-card-actions">
                        <button class="btn btn-primary btn-sm" onclick="actionPlayNow('${encodeURIComponent(r.url || r.title)}')">⚡ Play</button>
                        <button class="btn btn-secondary btn-sm" onclick="actionPlayNext('${encodeURIComponent(r.url || r.title)}')">⏭ Next</button>
                        <button class="btn btn-secondary btn-sm" onclick="actionEnqueue('${encodeURIComponent(r.url || r.title)}')">➕ Queue</button>
                      </div>
                    </div>
                  `).join('')
                }
              </div>
            </div>
          </div>
        `;
      } catch(e) {
        container.innerHTML = `<div class="glass-card" style="color:var(--danger); text-align:center;">Failed to load Auto-DJ settings: ${e.message}</div>`;
      }
    }

    async function toggleAutoDJStatus(enabled) {
      await fetch('/api/music/autodj/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: currentGuildId, enabled: enabled })
      });
      showToast(`Auto-DJ ${enabled ? 'Enabled' : 'Disabled'}`);
      renderAutoDJ();
    }

    async function setAutoDJMood(mood) {
      await fetch('/api/music/autodj/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: currentGuildId, mood: mood })
      });
      showToast(`Auto-DJ mood set to ${mood}`);
      renderAutoDJ();
    }

    // =========================================================================
    // VIEW 5: MUSIC LIBRARY & PLAYLISTS
    // =========================================================================
    let libraryTab = 'favs';
    async function renderLibrary() {
      const container = document.getElementById('view-container');
      container.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:1.6rem;">
          <div class="glass-card" style="padding:1.4rem 2rem;">
            <div class="section-header" style="margin-bottom:0.5rem;">
              <span class="section-title"><span>📚</span> Music Library & Playlists</span>
              <button class="btn btn-primary btn-sm" onclick="openPlaylistModal()">+ Save Current Queue</button>
            </div>
            <div style="display:flex; gap:0.6rem; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:0.6rem; margin-top:1rem;">
              <button class="chip-pill ${libraryTab === 'favs' ? 'active' : ''}" onclick="switchLibraryTab('favs')">❤️ Favorites</button>
              <button class="chip-pill ${libraryTab === 'playlists' ? 'active' : ''}" onclick="switchLibraryTab('playlists')">📁 Saved Playlists</button>
              <button class="chip-pill ${libraryTab === 'history' ? 'active' : ''}" onclick="switchLibraryTab('history')">🕒 Recent History</button>
            </div>
          </div>

          <div class="glass-card" id="library-content-container">
            <div style="text-align:center; padding:3rem; color:var(--cyan);">Loading library items...</div>
          </div>
        </div>
      `;
      loadLibraryTabContent();
    }

    function switchLibraryTab(tab) {
      libraryTab = tab;
      renderLibrary();
    }

    async function loadLibraryTabContent() {
      const container = document.getElementById('library-content-container');
      if (!container) return;

      if (libraryTab === 'favs') {
        try {
          const res = await fetch('/api/music/favorites');
          const json = await res.json();
          const favs = json.data || [];
          if (favs.length === 0) {
            container.innerHTML = `<div style="text-align:center; padding:3rem; color:var(--text-muted);">No favorite songs saved yet! Click the heart icon on any playing song to add it here.</div>`;
            return;
          }
          container.innerHTML = `
            <div class="tracks-grid">
              ${favs.map(f => `
                <div class="track-card">
                  <div class="track-card-top">
                    <img class="track-card-thumb" src="${f.thumbnail || 'https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=100'}">
                    <div class="track-card-info">
                      <span class="track-card-title">${f.title}</span>
                      <span class="track-card-artist">${f.artist || 'Favorite'}</span>
                      <span class="track-card-dur">${formatTime(f.duration)}</span>
                    </div>
                  </div>
                  <div class="track-card-actions">
                    <button class="btn btn-primary btn-sm" onclick="actionPlayNow('${encodeURIComponent(f.url)}')">⚡ Play</button>
                    <button class="btn btn-secondary btn-sm" onclick="actionEnqueue('${encodeURIComponent(f.url)}')">➕ Queue</button>
                    <button class="btn btn-danger btn-sm" onclick="removeFavorite('${encodeURIComponent(f.url)}')">✕ Remove</button>
                  </div>
                </div>
              `).join('')}
            </div>
          `;
        } catch(e) {
          container.innerHTML = `<div style="color:var(--danger); text-align:center;">Failed to load favorites: ${e.message}</div>`;
        }
      } else if (libraryTab === 'playlists') {
        try {
          const res = await fetch(`/api/music/playlists?guild_id=${currentGuildId}`);
          const json = await res.json();
          const playlists = json.data?.playlists || [];
          if (playlists.length === 0) {
            container.innerHTML = `<div style="text-align:center; padding:3rem; color:var(--text-muted);">No playlists created yet. Click "+ Save Current Queue" above to create your first playlist!</div>`;
            return;
          }
          container.innerHTML = `
            <div class="tracks-grid">
              ${playlists.map(p => `
                <div class="track-card" style="padding:1.2rem;">
                  <span style="font-size:1.1rem; font-weight:800; color:#fff;">📁 ${p.name}</span>
                  <span style="font-size:0.8rem; color:var(--cyan); font-weight:600;">${p.track_count} Tracks • ${p.is_server ? 'Server Playlist' : 'Personal Playlist'}</span>
                  <div style="display:flex; gap:0.5rem; margin-top:0.8rem;">
                    <button class="btn btn-primary btn-sm" style="flex:1;" onclick="loadPlaylist('${encodeURIComponent(p.name)}')">▶ Load Queue</button>
                    <button class="btn btn-danger btn-sm" onclick="deletePlaylist('${encodeURIComponent(p.name)}')">✕</button>
                  </div>
                </div>
              `).join('')}
            </div>
          `;
        } catch(e) {
          container.innerHTML = `<div style="color:var(--danger); text-align:center;">Failed to load playlists: ${e.message}</div>`;
        }
      } else if (libraryTab === 'history') {
        try {
          const res = await fetch(`/api/music/history?guild_id=${currentGuildId}`);
          const json = await res.json();
          const history = json.data?.history || [];
          if (history.length === 0) {
            container.innerHTML = `<div style="text-align:center; padding:3rem; color:var(--text-muted);">No playback history recorded for this server yet.</div>`;
            return;
          }
          container.innerHTML = `
            <div class="queue-table">
              ${history.map((h, i) => `
                <div class="queue-row">
                  <div class="queue-row-left">
                    <span class="queue-num">${i + 1}</span>
                    <img class="queue-thumb" src="${h.thumbnail || 'https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=100'}">
                    <div class="queue-meta">
                      <span class="queue-title">${h.title}</span>
                      <span class="queue-artist">${h.artist || 'Unknown'} • Req by ${h.requester_name || 'User'}</span>
                    </div>
                  </div>
                  <div class="queue-row-right">
                    <span style="font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:var(--text-muted);">${formatTime(h.duration)}</span>
                    <button class="btn btn-primary btn-sm" onclick="actionPlayNow('${encodeURIComponent(h.url)}')">Replay</button>
                  </div>
                </div>
              `).join('')}
            </div>
          `;
        } catch(e) {
          container.innerHTML = `<div style="color:var(--danger); text-align:center;">Failed to load history: ${e.message}</div>`;
        }
      }
    }

    async function removeFavorite(urlEnc) {
      const url = decodeURIComponent(urlEnc);
      await fetch('/api/music/favorites/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url })
      });
      showToast("Removed from Favorites");
      loadLibraryTabContent();
    }

    function openPlaylistModal() {
      document.getElementById('playlist-modal').classList.add('open');
      document.getElementById('playlist-name-input').focus();
    }
    function closePlaylistModal() {
      document.getElementById('playlist-modal').classList.remove('open');
    }
    async function confirmSavePlaylist() {
      const name = document.getElementById('playlist-name-input').value.trim();
      if (!name) return;
      try {
        const res = await fetch('/api/music/playlists/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ guild_id: currentGuildId, name: name })
        });
        const json = await res.json();
        if (json.success) {
          showToast(`Saved playlist "${name}" (${json.data.track_count} tracks)`);
          closePlaylistModal();
          if (libraryTab === 'playlists') loadLibraryTabContent();
        } else {
          showToast(json.error?.message || "Failed to save playlist", "danger");
        }
      } catch(e) {
        showToast("Error saving playlist", "danger");
      }
    }

    async function loadPlaylist(nameEnc) {
      const name = decodeURIComponent(nameEnc);
      const res = await fetch('/api/music/playlists/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: currentGuildId, name: name })
      });
      const json = await res.json();
      if (json.success) {
        showToast(`Loaded ${json.data.tracks_loaded} tracks into queue!`);
        syncAll();
      } else {
        showToast(json.error?.message || "Could not load playlist", "danger");
      }
    }

    async function deletePlaylist(nameEnc) {
      const name = decodeURIComponent(nameEnc);
      if (confirm(`Delete playlist "${name}"?`)) {
        await fetch('/api/music/playlists/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ guild_id: currentGuildId, name: name })
        });
        showToast(`Deleted playlist "${name}"`);
        loadLibraryTabContent();
      }
    }

    // =========================================================================
    // VIEW 6: EQUALIZER & DSP AUDIO TOOLS
    // =========================================================================
    async function renderAudioDSP() {
      const container = document.getElementById('view-container');
      const t = currentSession?.current_track;

      container.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:1.6rem;">
          <div class="glass-card" style="padding:2rem;">
            <div class="section-title" style="margin-bottom:0.5rem;">
              <span>🎛️</span> 10-Band Equalizer & Audio DSP Presets
            </div>
            <p style="font-size:0.86rem; color:var(--text-muted); margin-bottom:1.4rem;">
              Real-time FFmpeg dynamic audio filtration applied live to Discord voice output at 320kbps Opus.
            </p>

            <div class="eq-grid">
              <div class="eq-chip ${currentSession?.eq_preset === 'Flat' ? 'active' : ''}" onclick="dispatchCmd('FILTER', {preset:'flat', name:'Flat Pure'})">🎵 Flat / Bypass</div>
              <div class="eq-chip ${currentSession?.eq_preset === 'Bass Boost' ? 'active' : ''}" onclick="dispatchCmd('FILTER', {preset:'bassboost', name:'Bass Boost'})">🔥 Bass Boost</div>
              <div class="eq-chip ${currentSession?.eq_preset === 'Nightcore' ? 'active' : ''}" onclick="dispatchCmd('FILTER', {preset:'nightcore', name:'Nightcore'})">⚡ Nightcore</div>
              <div class="eq-chip ${currentSession?.eq_preset === '8D Audio' ? 'active' : ''}" onclick="dispatchCmd('FILTER', {preset:'8d', name:'8D Audio'})">🎧 8D Spatial</div>
              <div class="eq-chip ${currentSession?.eq_preset === 'Vaporwave' ? 'active' : ''}" onclick="dispatchCmd('FILTER', {preset:'vaporwave', name:'Vaporwave'})">📼 Vaporwave</div>
              <div class="eq-chip ${currentSession?.eq_preset === 'Vocal' ? 'active' : ''}" onclick="dispatchCmd('FILTER', {preset:'vocal', name:'Vocal Boost'})">🎤 Vocal Boost</div>
              <div class="eq-chip ${currentSession?.eq_preset === 'Treble' ? 'active' : ''}" onclick="dispatchCmd('FILTER', {preset:'treble', name:'Treble Boost'})">✨ Treble Boost</div>
              <div class="eq-chip ${currentSession?.eq_preset === 'Lofi' ? 'active' : ''}" onclick="dispatchCmd('FILTER', {preset:'lofi', name:'Lofi Radio'})">📻 Lofi Radio</div>
            </div>
          </div>

          <!-- SYNCHRONIZED LYRICS VIEWER -->
          <div class="glass-card">
            <div class="section-header">
              <span class="section-title"><span>🎤</span> Synchronized Real-time Lyrics</span>
              <button class="btn btn-secondary btn-sm" onclick="fetchLiveLyrics()">Refresh Lyrics ↻</button>
            </div>
            <div id="lyrics-display-area" style="white-space:pre-wrap; font-size:1.05rem; line-height:2.2; color:var(--text); text-align:center; padding:2rem; max-height:420px; overflow-y:auto; font-weight:500;">
              ${t ? `Fetching lyrics for "${t.title}"...` : 'Play a song to view real-time synchronized lyrics.'}
            </div>
          </div>
        </div>
      `;

      if (t) fetchLiveLyrics();
    }

    async function fetchLiveLyrics() {
      const area = document.getElementById('lyrics-display-area');
      if (!area || !currentSession?.current_track) return;
      const t = currentSession.current_track;
      area.innerText = `Fetching lyrics for "${t.title}"... ⏳`;
      try {
        const res = await fetch(`/api/music/lyrics?title=${encodeURIComponent(t.title)}&artist=${encodeURIComponent(t.artist || '')}`);
        const json = await res.json();
        area.innerText = json.data?.lyrics || "No lyrics found for this track.";
      } catch(e) {
        area.innerText = "Could not connect to lyrics provider.";
      }
    }

    // =========================================================================
    // VIEW 7: TELEMETRY & HEALTH STATISTICS
    // =========================================================================
    async function renderStats() {
      const container = document.getElementById('view-container');
      container.innerHTML = `<div style="text-align:center; padding:4rem; color:var(--cyan);">Collecting audio telemetry...</div>`;

      try {
        const res = await fetch('/api/music/stats');
        const json = await res.json();
        const s = json.data || {};

        container.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:1.6rem;">
            <div class="glass-card" style="padding:2rem;">
              <div class="section-title" style="margin-bottom:0.5rem;"><span>📊</span> Audio Subsystem & Telemetry</div>
              <p style="font-size:0.86rem; color:var(--text-muted);">Real-time monitoring of Discord Gateway voice connection, encoder status, and memory performance.</p>

              <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:1.2rem; margin-top:1.5rem;">
                <div class="glass-card" style="padding:1.2rem; background:rgba(255,255,255,0.03);">
                  <span style="font-size:0.75rem; color:var(--text-dim); font-weight:700;">BOT STATUS</span>
                  <div style="font-size:1.4rem; font-weight:800; color:var(--emerald); margin-top:0.3rem;">${s.status || 'ONLINE'}</div>
                  <span style="font-size:0.75rem; color:var(--text-muted);">${s.bot_name || 'MusicMaid'}</span>
                </div>
                <div class="glass-card" style="padding:1.2rem; background:rgba(255,255,255,0.03);">
                  <span style="font-size:0.75rem; color:var(--text-dim); font-weight:700;">ACTIVE AUDIO SESSIONS</span>
                  <div style="font-size:1.4rem; font-weight:800; color:var(--cyan); margin-top:0.3rem;">${s.active_sessions || 1} Guilds</div>
                  <span style="font-size:0.75rem; color:var(--text-muted);">${s.playing_sessions || 1} Actively Playing</span>
                </div>
                <div class="glass-card" style="padding:1.2rem; background:rgba(255,255,255,0.03);">
                  <span style="font-size:0.75rem; color:var(--text-dim); font-weight:700;">GATEWAY VOICE LATENCY</span>
                  <div style="font-size:1.4rem; font-weight:800; color:#fff; margin-top:0.3rem;">${s.gateway_latency_ms || 18} ms</div>
                  <span style="font-size:0.75rem; color:var(--emerald);">DAVE E2EE Active ✅</span>
                </div>
                <div class="glass-card" style="padding:1.2rem; background:rgba(255,255,255,0.03);">
                  <span style="font-size:0.75rem; color:var(--text-dim); font-weight:700;">RESOLVER ENGINE</span>
                  <div style="font-size:1.4rem; font-weight:800; color:var(--primary); margin-top:0.3rem;">yt-dlp + PyNaCl</div>
                  <span style="font-size:0.75rem; color:var(--text-muted);">${s.audio_backend || '320kbps Opus'}</span>
                </div>
              </div>
            </div>
          </div>
        `;
      } catch(e) {
        container.innerHTML = `<div class="glass-card" style="color:var(--danger); text-align:center;">Failed to load statistics: ${e.message}</div>`;
      }
    }
  </script>
</body>
</html>
"""
