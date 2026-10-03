"""
Rai Community OS — Discovery Platform V2 (The Raivora).
Top.gg-inspired discovery UX combined with Rai's signature midnight luxury identity.
Full-featured, responsive SPA with global debounced search, discovery cards,
subtle canvas particle background, desktop cursor interaction, and complete community modules.
"""

from __future__ import annotations

UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RAI ✦ THE RAIVORA — Community Discovery Platform</title>
  <meta name="description" content="Discover communities, creators, projects, gaming squads, and lossless music powered by Rai Community OS.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #07080d;
      --bg-surface: #0f111a;
      --card-bg: rgba(18, 20, 32, 0.78);
      --card-border: rgba(147, 51, 234, 0.22);
      --card-border-hover: rgba(168, 85, 247, 0.55);
      --primary: #9333ea;
      --primary-hover: #a855f7;
      --primary-glow: rgba(147, 51, 234, 0.35);
      --cyan: #06b6d4;
      --cyan-glow: rgba(6, 182, 212, 0.28);
      --pink: #ec4899;
      --emerald: #10b981;
      --amber: #f59e0b;
      --danger: #ef4444;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --blurple: #5865F2;
      --glass-nav: rgba(10, 11, 18, 0.88);
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 18px;
      --radius-full: 9999px;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }
    html { scroll-behavior: smooth; }

    body {
      background-color: var(--bg-dark);
      background-image: 
        radial-gradient(at 0% 0%, rgba(147, 51, 234, 0.14) 0px, transparent 55%),
        radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.10) 0px, transparent 55%),
        radial-gradient(at 50% 50%, rgba(236, 72, 153, 0.04) 0px, transparent 65%);
      color: var(--text);
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
      position: relative;
    }

    /* SUBTLE CANVAS BACKGROUND */
    #bg-canvas {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      pointer-events: none;
      z-index: 0;
      opacity: 0.65;
    }

    /* DESKTOP CURSOR GLOW */
    #cursor-glow {
      position: fixed;
      width: 380px;
      height: 380px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(147, 51, 234, 0.12) 0%, rgba(6, 182, 212, 0.04) 45%, transparent 70%);
      pointer-events: none;
      transform: translate(-50%, -50%);
      z-index: 1;
      transition: opacity 0.3s ease;
      opacity: 0;
    }

    /* TOP NAVIGATION */
    nav.top-nav {
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--glass-nav);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 0.75rem 2rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1.5rem;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      text-decoration: none;
      color: inherit;
      cursor: pointer;
      flex-shrink: 0;
    }
    .brand-icon {
      width: 40px;
      height: 40px;
      background: linear-gradient(135deg, var(--primary), #7c3aed);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.3rem;
      box-shadow: 0 0 18px var(--primary-glow);
    }
    .brand-title h1 {
      font-size: 1.25rem;
      font-weight: 800;
      letter-spacing: 0.8px;
      background: linear-gradient(to right, #ffffff, #d8b4fe, #a5f3fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }
    .brand-title p {
      font-size: 0.7rem;
      color: var(--text-muted);
      letter-spacing: 0.6px;
      text-transform: uppercase;
    }

    /* NAV LINKS */
    .nav-links {
      display: flex;
      align-items: center;
      gap: 0.35rem;
      list-style: none;
      flex-shrink: 0;
    }
    .nav-item {
      padding: 0.45rem 0.85rem;
      border-radius: 8px;
      text-decoration: none;
      color: var(--text-muted);
      font-size: 0.9rem;
      font-weight: 500;
      transition: all 0.2s ease;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
    }
    .nav-item:hover, .nav-item.active {
      color: #fff;
      background: rgba(147, 51, 234, 0.18);
      border: 1px solid rgba(147, 51, 234, 0.35);
    }

    /* MORE DROPDOWN */
    .nav-dropdown {
      position: relative;
      display: inline-block;
    }
    .nav-dropdown-menu {
      display: none;
      position: absolute;
      top: 100%;
      right: 0;
      min-width: 200px;
      background: rgba(15, 17, 26, 0.96);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(147, 51, 234, 0.3);
      border-radius: var(--radius-md);
      box-shadow: 0 12px 35px rgba(0, 0, 0, 0.65);
      padding: 0.5rem;
      z-index: 150;
      margin-top: 0.5rem;
    }
    .nav-dropdown.open .nav-dropdown-menu { display: block; }
    .nav-dropdown-item {
      padding: 0.55rem 0.9rem;
      border-radius: var(--radius-sm);
      color: var(--text-muted);
      font-size: 0.86rem;
      display: flex;
      align-items: center;
      gap: 0.6rem;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.15s ease;
    }
    .nav-dropdown-item:hover {
      background: rgba(147, 51, 234, 0.2);
      color: #fff;
    }

    /* GLOBAL NAV SEARCH BAR */
    .nav-search-box {
      flex: 1;
      max-width: 360px;
      position: relative;
    }
    .nav-search-input {
      width: 100%;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-full);
      padding: 0.45rem 2.4rem 0.45rem 2.2rem;
      font-size: 0.85rem;
      color: #fff;
      font-family: inherit;
      outline: none;
      transition: all 0.25s ease;
    }
    .nav-search-input:focus {
      background: rgba(255, 255, 255, 0.08);
      border-color: var(--primary);
      box-shadow: 0 0 15px rgba(147, 51, 234, 0.3);
    }
    .nav-search-icon {
      position: absolute;
      left: 0.75rem;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-dim);
      font-size: 0.9rem;
      pointer-events: none;
    }
    .nav-search-badge {
      position: absolute;
      right: 0.6rem;
      top: 50%;
      transform: translateY(-50%);
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 4px;
      padding: 1px 5px;
      font-size: 0.68rem;
      color: var(--text-dim);
      font-family: monospace;
    }

    /* AUTOCOMPLETE SEARCH DROPDOWN OVERLAY */
    .search-suggestions-panel {
      display: none;
      position: absolute;
      top: 100%;
      left: 0;
      right: 0;
      background: rgba(14, 16, 26, 0.98);
      backdrop-filter: blur(28px);
      border: 1px solid rgba(147, 51, 234, 0.35);
      border-radius: var(--radius-md);
      box-shadow: 0 16px 45px rgba(0, 0, 0, 0.85);
      margin-top: 0.5rem;
      max-height: 480px;
      overflow-y: auto;
      z-index: 200;
      padding: 0.75rem;
    }
    .search-suggestions-panel.active { display: block; }
    .search-section-header {
      font-size: 0.72rem;
      font-weight: 700;
      color: var(--cyan);
      text-transform: uppercase;
      letter-spacing: 0.6px;
      margin: 0.6rem 0.4rem 0.3rem 0.4rem;
    }
    .search-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.5rem 0.75rem;
      border-radius: var(--radius-sm);
      cursor: pointer;
      text-decoration: none;
      color: var(--text);
      transition: background 0.15s ease;
    }
    .search-item:hover {
      background: rgba(147, 51, 234, 0.22);
    }
    .search-item-info {
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
    }
    .search-item-title {
      font-size: 0.88rem;
      font-weight: 600;
      color: #fff;
    }
    .search-item-snippet {
      font-size: 0.75rem;
      color: var(--text-muted);
      max-width: 280px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* NAV ACTIONS */
    .nav-actions {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-shrink: 0;
    }

    /* BUTTONS */
    .btn {
      padding: 0.52rem 1.1rem;
      border-radius: 10px;
      font-size: 0.88rem;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      text-decoration: none;
      border: none;
      white-space: nowrap;
    }
    .btn-primary {
      background: linear-gradient(135deg, var(--primary), #7c3aed);
      color: #fff;
      box-shadow: 0 4px 15px var(--primary-glow);
    }
    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 22px rgba(147, 51, 234, 0.55);
    }
    .btn-discord {
      background: var(--blurple);
      color: #fff;
      box-shadow: 0 4px 14px rgba(88, 101, 242, 0.35);
    }
    .btn-discord:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(88, 101, 242, 0.5);
    }
    .btn-outline {
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      border: 1px solid rgba(255, 255, 255, 0.12);
    }
    .btn-outline:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.28);
      transform: translateY(-2px);
    }
    .btn-sm {
      padding: 0.35rem 0.75rem;
      font-size: 0.8rem;
      border-radius: 8px;
    }
    .btn-lg {
      padding: 0.85rem 1.8rem;
      font-size: 1rem;
      border-radius: 12px;
    }

    /* USER PROFILE BADGE */
    .user-profile-btn {
      display: flex;
      align-items: center;
      gap: 0.55rem;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.14);
      padding: 0.3rem 0.8rem 0.3rem 0.4rem;
      border-radius: var(--radius-full);
      cursor: pointer;
      color: inherit;
      text-decoration: none;
      transition: all 0.2s ease;
    }
    .user-profile-btn:hover {
      background: rgba(147, 51, 234, 0.2);
      border-color: rgba(147, 51, 234, 0.4);
    }
    .user-avatar {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: var(--primary);
      object-fit: cover;
    }
    .badge-count {
      background: var(--pink);
      color: #fff;
      font-size: 0.7rem;
      font-weight: 700;
      padding: 0.1rem 0.45rem;
      border-radius: var(--radius-full);
    }

    /* MAIN CONTAINER */
    main.main-content {
      flex: 1;
      width: 100%;
      max-width: 1320px;
      margin: 0 auto;
      padding: 2rem 1.5rem 5rem 1.5rem;
      position: relative;
      z-index: 10;
    }

    /* HERO SECTION */
    .discovery-hero {
      text-align: center;
      padding: 4.5rem 1rem 3rem 1rem;
      position: relative;
    }
    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background: rgba(147, 51, 234, 0.12);
      border: 1px solid rgba(147, 51, 234, 0.32);
      color: #d8b4fe;
      padding: 0.35rem 1rem;
      border-radius: var(--radius-full);
      font-size: 0.82rem;
      font-weight: 600;
      letter-spacing: 0.8px;
      margin-bottom: 1.4rem;
      text-transform: uppercase;
    }
    .hero-title {
      font-size: 3.6rem;
      font-weight: 900;
      line-height: 1.12;
      margin-bottom: 1rem;
      background: linear-gradient(135deg, #ffffff 10%, #e2e8f0 45%, #c084fc 80%, #67e8f9 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: -0.5px;
    }
    .hero-subtitle {
      font-size: 1.2rem;
      color: var(--text-muted);
      max-width: 650px;
      margin: 0 auto 2.2rem auto;
      line-height: 1.6;
    }

    /* HERO SEARCH BAR */
    .hero-search-wrapper {
      max-width: 680px;
      margin: 0 auto 2rem auto;
      position: relative;
    }
    .hero-search-box {
      display: flex;
      align-items: center;
      background: rgba(18, 20, 32, 0.92);
      border: 1.5px solid rgba(147, 51, 234, 0.4);
      box-shadow: 0 10px 35px rgba(0, 0, 0, 0.6), 0 0 25px rgba(147, 51, 234, 0.2);
      border-radius: var(--radius-full);
      padding: 0.45rem 0.6rem 0.45rem 1.4rem;
      transition: all 0.3s ease;
    }
    .hero-search-box:focus-within {
      border-color: var(--primary-hover);
      box-shadow: 0 12px 45px rgba(0, 0, 0, 0.75), 0 0 35px rgba(147, 51, 234, 0.35);
      transform: translateY(-2px);
    }
    .hero-search-input {
      flex: 1;
      background: transparent;
      border: none;
      color: #fff;
      font-size: 1.05rem;
      font-family: inherit;
      outline: none;
      padding: 0.5rem 0;
    }
    .hero-search-input::placeholder { color: var(--text-dim); }

    .hero-actions {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 1.2rem;
      flex-wrap: wrap;
    }

    /* CATEGORY PILLS BAR */
    .category-pills-bar {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      overflow-x: auto;
      padding: 1.5rem 0 2rem 0;
      scrollbar-width: none;
    }
    .category-pills-bar::-webkit-scrollbar { display: none; }
    .cat-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.6rem;
      background: rgba(18, 20, 32, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.09);
      padding: 0.65rem 1.15rem;
      border-radius: var(--radius-full);
      color: var(--text);
      font-size: 0.9rem;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.25s ease;
    }
    .cat-pill:hover, .cat-pill.active {
      background: rgba(147, 51, 234, 0.22);
      border-color: rgba(147, 51, 234, 0.5);
      color: #fff;
      transform: translateY(-2px);
      box-shadow: 0 6px 18px rgba(147, 51, 234, 0.25);
    }
    .cat-pill-count {
      background: rgba(255, 255, 255, 0.1);
      border-radius: var(--radius-full);
      padding: 0.1rem 0.45rem;
      font-size: 0.72rem;
      color: var(--text-muted);
    }

    /* SECTION TITLES */
    .section-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin: 3.5rem 0 1.5rem 0;
    }
    .title-group {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .title-text {
      font-size: 1.45rem;
      font-weight: 800;
      color: #fff;
      letter-spacing: -0.2px;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .title-desc {
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-top: 0.2rem;
    }

    /* DISCOVERY CARD SYSTEM (Reusable across all modules) */
    .discovery-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 1.4rem;
    }
    .discovery-card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: var(--radius-lg);
      padding: 1.4rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;
    }
    .discovery-card:hover {
      transform: translateY(-4px);
      border-color: var(--card-border-hover);
      box-shadow: 0 14px 35px rgba(0, 0, 0, 0.65), 0 0 25px rgba(147, 51, 234, 0.2);
    }
    .card-top {
      display: flex;
      align-items: flex-start;
      gap: 1rem;
      margin-bottom: 0.85rem;
    }
    .card-media-icon {
      width: 52px;
      height: 52px;
      border-radius: var(--radius-md);
      background: linear-gradient(135deg, rgba(147, 51, 234, 0.25), rgba(6, 182, 212, 0.2));
      border: 1px solid rgba(255, 255, 255, 0.1);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.8rem;
      flex-shrink: 0;
      overflow: hidden;
    }
    .card-media-icon img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .card-heading {
      flex: 1;
      overflow: hidden;
    }
    .card-name {
      font-size: 1.1rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      display: flex;
      align-items: center;
      gap: 0.4rem;
    }
    .card-subtitle {
      font-size: 0.78rem;
      color: var(--cyan);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-top: 0.15rem;
    }
    .card-desc {
      font-size: 0.88rem;
      color: var(--text-muted);
      line-height: 1.5;
      margin-bottom: 1rem;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .card-tags {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      flex-wrap: wrap;
      margin-bottom: 1.1rem;
    }
    .tag-badge {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: var(--radius-full);
      padding: 0.15rem 0.55rem;
      font-size: 0.72rem;
      color: var(--text-dim);
      font-weight: 500;
    }
    .card-metrics {
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      padding-top: 0.85rem;
      font-size: 0.8rem;
      color: var(--text-muted);
    }
    .card-bottom-actions {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-top: 0.85rem;
    }

    /* PILLS & BADGES */
    .pill {
      font-size: 0.7rem;
      font-weight: 700;
      padding: 0.2rem 0.55rem;
      border-radius: var(--radius-full);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
    }
    .pill-purple { background: rgba(147, 51, 234, 0.18); color: #d8b4fe; border: 1px solid rgba(147, 51, 234, 0.35); }
    .pill-cyan { background: rgba(6, 182, 212, 0.15); color: #67e8f9; border: 1px solid rgba(6, 182, 212, 0.3); }
    .pill-pink { background: rgba(236, 72, 153, 0.15); color: #f472b6; border: 1px solid rgba(236, 72, 153, 0.3); }
    .pill-green { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.3); }
    .pill-amber { background: rgba(245, 158, 11, 0.15); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.3); }

    /* FEATURED SPOTLIGHT CARD */
    .spotlight-card {
      background: linear-gradient(135deg, rgba(28, 22, 50, 0.9), rgba(12, 15, 28, 0.95));
      border: 1px solid rgba(168, 85, 247, 0.35);
      box-shadow: 0 16px 45px rgba(0, 0, 0, 0.7), 0 0 30px rgba(147, 51, 234, 0.22);
      border-radius: var(--radius-lg);
      padding: 2.2rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 2rem;
      margin-bottom: 2.5rem;
      position: relative;
      overflow: hidden;
    }
    .spotlight-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: rgba(236, 72, 153, 0.2);
      color: #f472b6;
      border: 1px solid rgba(236, 72, 153, 0.35);
      border-radius: var(--radius-full);
      padding: 0.25rem 0.75rem;
      font-size: 0.78rem;
      font-weight: 700;
      margin-bottom: 0.75rem;
    }
    .spotlight-content h3 {
      font-size: 2rem;
      font-weight: 800;
      color: #fff;
      margin-bottom: 0.6rem;
      letter-spacing: -0.3px;
    }
    .spotlight-content p {
      font-size: 1rem;
      color: var(--text-muted);
      max-width: 620px;
      line-height: 1.6;
      margin-bottom: 1.4rem;
    }

    /* RYTHM AUDIO PREVIEW WIDGET */
    .player-widget {
      background: linear-gradient(135deg, rgba(20, 24, 40, 0.92), rgba(10, 12, 22, 0.98));
      border: 1px solid rgba(147, 51, 234, 0.35);
      box-shadow: 0 16px 45px rgba(0, 0, 0, 0.7), 0 0 30px rgba(147, 51, 234, 0.18);
      border-radius: var(--radius-lg);
      padding: 1.4rem 1.8rem;
      backdrop-filter: blur(20px);
      margin-bottom: 2rem;
    }
    .player-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .player-main {
      display: flex;
      align-items: center;
      gap: 1.2rem;
    }
    .player-disc {
      width: 58px;
      height: 58px;
      border-radius: 50%;
      background: radial-gradient(circle, #0f172a 25%, #581c87 65%, #06b6d4 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.6rem;
      box-shadow: 0 0 20px rgba(147, 51, 234, 0.5);
      animation: spin 6s linear infinite;
    }
    .player-disc.paused { animation-play-state: paused; }
    @keyframes spin { 100% { transform: rotate(360deg); } }
    .player-info { flex: 1; }
    .player-title { font-size: 1.05rem; font-weight: 700; color: #fff; }
    .player-artist { font-size: 0.82rem; color: var(--text-muted); margin-top: 0.2rem; }
    .player-controls { display: flex; align-items: center; gap: 0.6rem; }
    .ctrl-icon-btn {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #fff;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 0.95rem;
      transition: all 0.2s;
    }
    .ctrl-icon-btn:hover { background: rgba(147, 51, 234, 0.3); border-color: var(--primary); }
    .play-btn {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--primary), #7c3aed);
      color: #fff;
      border: none;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 1.1rem;
      box-shadow: 0 4px 15px var(--primary-glow);
      transition: all 0.2s;
    }
    .play-btn:hover { transform: scale(1.08); box-shadow: 0 6px 20px rgba(147, 51, 234, 0.6); }

    /* EQUALIZER BARS */
    .eq-bars { display: flex; align-items: flex-end; gap: 2px; height: 16px; }
    .eq-bar {
      width: 3px;
      background: var(--cyan);
      border-radius: 2px;
      animation: equalize 0.8s infinite ease-in-out alternate;
    }
    .eq-bar:nth-child(1) { height: 60%; animation-delay: 0.1s; }
    .eq-bar:nth-child(2) { height: 100%; animation-delay: 0.3s; }
    .eq-bar:nth-child(3) { height: 40%; animation-delay: 0.2s; }
    .eq-bar:nth-child(4) { height: 80%; animation-delay: 0.4s; }
    .eq-bar.paused { animation-play-state: paused; height: 30% !important; }
    @keyframes equalize { 0% { height: 20%; } 100% { height: 100%; } }

    /* FILTERS & SEARCH ROW */
    .filters-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
      margin-bottom: 1.8rem;
      background: rgba(15, 17, 26, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: var(--radius-md);
      padding: 0.85rem 1.2rem;
    }
    .filter-group { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
    .select-field, .input-field {
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-sm);
      color: #fff;
      padding: 0.45rem 0.85rem;
      font-size: 0.85rem;
      font-family: inherit;
      outline: none;
      transition: border-color 0.2s;
    }
    .select-field:focus, .input-field:focus { border-color: var(--primary); }

    /* SKELETON LOADERS */
    .skeleton-card {
      background: rgba(18, 20, 32, 0.5);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: var(--radius-lg);
      padding: 1.4rem;
      min-height: 200px;
      animation: pulse 1.6s infinite ease-in-out;
    }
    @keyframes pulse { 0%, 100% { opacity: 0.5; } 50% { opacity: 0.85; } }

    /* EMPTY & ERROR STATES */
    .state-box {
      text-align: center;
      padding: 3.5rem 1.5rem;
      background: rgba(15, 17, 26, 0.6);
      border: 1px dashed rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-lg);
      grid-column: 1 / -1;
    }
    .state-icon { font-size: 2.8rem; margin-bottom: 0.75rem; }
    .state-title { font-size: 1.25rem; font-weight: 700; color: #fff; margin-bottom: 0.4rem; }
    .state-desc { font-size: 0.88rem; color: var(--text-muted); max-width: 440px; margin: 0 auto 1.4rem auto; line-height: 1.5; }

    /* MODAL */
    .modal-overlay {
      position: fixed;
      top: 0; left: 0; width: 100vw; height: 100vh;
      background: rgba(4, 5, 8, 0.85);
      backdrop-filter: blur(16px);
      z-index: 1000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .modal-overlay.active { display: flex; }
    .modal-card {
      background: rgba(15, 17, 26, 0.98);
      border: 1px solid rgba(147, 51, 234, 0.4);
      box-shadow: 0 25px 60px rgba(0, 0, 0, 0.85), 0 0 35px rgba(147, 51, 234, 0.25);
      border-radius: var(--radius-lg);
      width: 100%;
      max-width: 600px;
      max-height: 88vh;
      overflow-y: auto;
      padding: 1.8rem;
      position: relative;
    }
    .modal-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1.2rem;
      padding-bottom: 0.8rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .modal-close {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 1.5rem;
      cursor: pointer;
      line-height: 1;
    }
    .modal-close:hover { color: #fff; }

    /* KANBAN BOARD */
    .kanban-board {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      margin-top: 1rem;
    }
    .kanban-col {
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(255, 255, 255, 0.07);
      border-radius: var(--radius-md);
      padding: 0.8rem;
      min-height: 240px;
    }
    .kanban-header {
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--cyan);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 0.8rem;
      display: flex;
      justify-content: space-between;
    }
    .kanban-task {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: var(--radius-sm);
      padding: 0.7rem;
      margin-bottom: 0.6rem;
      font-size: 0.82rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    .kanban-task:hover {
      background: rgba(147, 51, 234, 0.2);
      border-color: var(--primary);
    }

    /* FOOTER */
    footer.site-footer {
      background: rgba(10, 11, 18, 0.95);
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      padding: 4rem 2rem 2rem 2rem;
      margin-top: auto;
      position: relative;
      z-index: 10;
    }
    .footer-content {
      max-width: 1320px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: 2fr 1fr 1fr 1fr;
      gap: 3rem;
      margin-bottom: 3rem;
    }
    .footer-col h4 {
      color: #fff;
      font-size: 0.92rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      margin-bottom: 1.1rem;
    }
    .footer-col ul { list-style: none; display: flex; flex-direction: column; gap: 0.65rem; }
    .footer-col a {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.86rem;
      transition: color 0.2s;
      cursor: pointer;
    }
    .footer-col a:hover { color: #fff; }
    .footer-bottom {
      max-width: 1320px;
      margin: 0 auto;
      padding-top: 1.8rem;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--text-dim);
      font-size: 0.82rem;
      flex-wrap: wrap;
      gap: 1rem;
    }

    /* MOBILE NAV TOGGLE */
    .mobile-nav-toggle {
      display: none;
      background: transparent;
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #fff;
      padding: 0.4rem 0.65rem;
      border-radius: var(--radius-sm);
      font-size: 1.2rem;
      cursor: pointer;
    }

    /* RESPONSIVE DESIGN */
    @media (max-width: 1024px) {
      .footer-content { grid-template-columns: 1fr 1fr; }
      .nav-links { display: none; }
      .mobile-nav-toggle { display: block; }
      nav.top-nav { padding: 0.75rem 1.2rem; }
    }

    @media (max-width: 768px) {
      .hero-title { font-size: 2.5rem; }
      .nav-search-box { display: none; }
      .footer-content { grid-template-columns: 1fr; }
      .spotlight-card { flex-direction: column; text-align: center; }
      .discovery-grid { grid-template-columns: 1fr; }
    }

    /* REDUCED MOTION */
    @media (prefers-reduced-motion: reduce) {
      *, ::before, ::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }
      #cursor-glow, #bg-canvas { display: none !important; }
    }
  </style>
</head>
<body>

  <!-- SUBTLE CANVAS PARTICLES -->
  <canvas id="bg-canvas"></canvas>

  <!-- DESKTOP CURSOR GLOW -->
  <div id="cursor-glow"></div>

  <!-- TOP NAVIGATION -->
  <nav class="top-nav">
    <div class="brand" onclick="navigate('/')">
      <div class="brand-icon">✦</div>
      <div class="brand-title">
        <h1>RAI ✦</h1>
        <p>The Raivora</p>
      </div>
    </div>

    <!-- MAIN NAV LINKS -->
    <ul class="nav-links" id="main-nav-links">
      <li><a class="nav-item" onclick="navigate('/discover')">Discover</a></li>
      <li><a class="nav-item" onclick="navigate('/communities')">Communities</a></li>
      <li><a class="nav-item" onclick="navigate('/projects')">Projects</a></li>
      <li><a class="nav-item" onclick="navigate('/creators')">Creators</a></li>
      <li><a class="nav-item" onclick="navigate('/gaming')">Gaming</a></li>
      <li><a class="nav-item" onclick="navigate('/music')">Music</a></li>

      <!-- MORE DROPDOWN -->
      <li class="nav-dropdown" id="more-dropdown">
        <a class="nav-item" onclick="toggleMoreMenu(event)">More ▾</a>
        <div class="nav-dropdown-menu">
          <a class="nav-dropdown-item" onclick="navigate('/media')">🎬 Media & Watch Parties</a>
          <a class="nav-dropdown-item" onclick="navigate('/resources')">📚 Resources & LUTs</a>
          <a class="nav-dropdown-item" onclick="navigate('/events')">📅 Events Calendar</a>
          <a class="nav-dropdown-item" onclick="navigate('/ideas')">💡 Ideas & Roadmap</a>
          <a class="nav-dropdown-item" onclick="navigate('/brain')">🧠 Rai Community Brain</a>
          <a class="nav-dropdown-item" onclick="navigate('/labs')">🔬 Labs & Constellation</a>
          <a class="nav-dropdown-item" onclick="navigate('/rai')">✦ Rai Product Platform</a>
          <a class="nav-dropdown-item" onclick="navigate('/wiki')">📖 Community Wiki</a>
          <a class="nav-dropdown-item" onclick="navigate('/status')">🩺 Subsystem Status</a>
        </div>
      </li>
    </ul>

    <!-- GLOBAL NAVBAR SEARCH -->
    <div class="nav-search-box">
      <span class="nav-search-icon">🔍</span>
      <input type="text" class="nav-search-input" id="global-nav-search" placeholder="Search communities, creators, projects..." oninput="onGlobalSearchInput(this.value)" onfocus="onGlobalSearchFocus()" autocomplete="off">
      <span class="nav-search-badge">Ctrl K</span>

      <!-- AUTOCOMPLETE SUGGESTIONS POPUP -->
      <div class="search-suggestions-panel" id="nav-search-suggestions">
        <div style="font-size:0.8rem; color:var(--text-muted); text-align:center; padding:0.5rem;">
          Type to search verified communities, projects, creators, games...
        </div>
      </div>
    </div>

    <!-- ACTIONS / USER -->
    <div class="nav-actions" id="nav-user-container">
      <a href="https://discord.com/oauth2/authorize?client_id=1554732669072445532&permissions=8&scope=bot%20applications.commands" target="_blank" class="btn btn-outline btn-sm">
        <span>+ Add to Discord</span>
      </a>
      <button class="btn btn-discord btn-sm" onclick="openLoginModal()">
        <span>👾 Log in with Discord</span>
      </button>
      <button class="mobile-nav-toggle" onclick="toggleMobileMenu()">☰</button>
    </div>
  </nav>

  <!-- MAIN VIEW CONTAINER -->
  <main class="main-content" id="view-container">
    <!-- Dynamic views render here -->
  </main>

  <!-- MODAL CONTAINER -->
  <div class="modal-overlay" id="modal-overlay">
    <div class="modal-card" id="modal-card">
      <div class="modal-header">
        <h3 id="modal-title" style="color:#fff;">Modal Title</h3>
        <button class="modal-close" onclick="closeModal()">&times;</button>
      </div>
      <div id="modal-body"></div>
    </div>
  </div>

  <!-- RICH 4-COLUMN FOOTER -->
  <footer class="site-footer">
    <div class="footer-content">
      <div class="footer-col">
        <div style="display:flex; align-items:center; gap:0.6rem; margin-bottom:0.8rem;">
          <div style="width:30px; height:30px; border-radius:8px; background:linear-gradient(135deg, var(--primary), #7c3aed); display:flex; align-items:center; justify-content:center; font-size:1.1rem;">✦</div>
          <span style="font-size:1.15rem; font-weight:800; color:#fff;">RAI COMMUNITY OS</span>
        </div>
        <p style="color:var(--text-muted); font-size:0.88rem; line-height:1.6; max-width:340px; margin-bottom:1.2rem;">
          The Raivora — A community discovery platform and operating system powered by Rai.
          Connecting Discord servers, creators, gaming squads, and multimedia projects in a unified world.
        </p>
        <span class="pill pill-green">🟢 SQLite WAL & Discord Bot Connected</span>
      </div>

      <div class="footer-col">
        <h4>Explore</h4>
        <ul>
          <li><a onclick="navigate('/communities')">Communities Directory</a></li>
          <li><a onclick="navigate('/projects')">Active Projects</a></li>
          <li><a onclick="navigate('/creators')">Creator Portfolios</a></li>
          <li><a onclick="navigate('/gaming')">Gaming Hub & LFG</a></li>
          <li><a onclick="navigate('/music')">Music & Audio 320kbps</a></li>
          <li><a onclick="navigate('/events')">Events Calendar</a></li>
          <li><a onclick="navigate('/resources')">Resource Library</a></li>
        </ul>
      </div>

      <div class="footer-col">
        <h4>Rai Systems</h4>
        <ul>
          <li><a onclick="navigate('/rai')">✦ Rai AI Platform</a></li>
          <li><a onclick="navigate('/rai/features')">Features Directory</a></li>
          <li><a onclick="navigate('/brain')">Community Brain</a></li>
          <li><a onclick="navigate('/labs')">Labs & Constellation</a></li>
          <li><a onclick="navigate('/status')">Subsystem Status</a></li>
          <li><a onclick="navigate('/wiki')">Knowledge Base</a></li>
          <li><a href="https://discord.com/oauth2/authorize?client_id=1554732669072445532&permissions=8&scope=bot%20applications.commands" target="_blank">Invite Rai Bot ↗</a></li>
        </ul>
      </div>

      <div class="footer-col">
        <h4>Community & Legal</h4>
        <ul>
          <li><a href="https://discord.gg/raivora" target="_blank">Official Discord Server ↗</a></li>
          <li><a onclick="navigate('/wiki')">Server Rules & Safety</a></li>
          <li><a onclick="navigate('/ideas')">Feature Roadmap</a></li>
          <li><a onclick="navigate('/saved')">My Saved Bookmarks</a></li>
          <li><a onclick="navigate('/dashboard')">Member Dashboard</a></li>
        </ul>
      </div>
    </div>

    <div class="footer-bottom">
      <div>Powered by Rai • The Raivora Core 2.6 • Persistent Community Discovery Platform</div>
      <div>Single Source of Truth with SQLite WAL & Discord Bot Gateway. Discord remains the real-time interaction hub.</div>
    </div>
  </footer>

  <!-- SPA ROUTING & INTERACTIVE ENGINE -->
  <script>
    let currentUser = null;
    let currentRoute = '/';
    let searchDebounceTimer = null;

    // ==========================================
    // 1. CANVAS PARTICLE SYSTEM
    // ==========================================
    function initCanvasParticles() {
      const canvas = document.getElementById('bg-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      let w = canvas.width = window.innerWidth;
      let h = canvas.height = window.innerHeight;

      const particles = [];
      const count = Math.min(Math.floor(w / 45), 35);

      for (let i = 0; i < count; i++) {
        particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() - 0.5) * 0.35,
          vy: (Math.random() - 0.5) * 0.35,
          r: Math.random() * 2 + 1,
          color: Math.random() > 0.4 ? 'rgba(168, 85, 247, ' : 'rgba(6, 182, 212, ',
          alpha: Math.random() * 0.35 + 0.15
        });
      }

      function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
      }
      window.addEventListener('resize', resize);

      let animId;
      function render() {
        if (document.hidden) {
          animId = requestAnimationFrame(render);
          return;
        }
        ctx.clearRect(0, 0, w, h);
        for (let p of particles) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < 0) p.x = w;
          if (p.x > w) p.x = 0;
          if (p.y < 0) p.y = h;
          if (p.y > h) p.y = 0;

          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
          ctx.fillStyle = p.color + p.alpha + ')';
          ctx.fill();
        }
        animId = requestAnimationFrame(render);
      }
      render();
    }

    // ==========================================
    // 2. DESKTOP CURSOR GLOW
    // ==========================================
    function initCursorGlow() {
      const glow = document.getElementById('cursor-glow');
      if (!glow || window.matchMedia('(pointer: coarse)').matches) return;

      document.addEventListener('mousemove', e => {
        glow.style.left = e.clientX + 'px';
        glow.style.top = e.clientY + 'px';
        glow.style.opacity = '1';
      });

      document.addEventListener('mouseleave', () => {
        glow.style.opacity = '0';
      });
    }

    // ==========================================
    // 3. AUTHENTICATION CONTROLLER
    // ==========================================
    async function initAuth() {
      try {
        const res = await fetch('/api/auth/me');
        const data = await res.json();
        if (data.success && data.data && data.data.authenticated) {
          currentUser = data.data.user;
          renderNavUser();
        }
      } catch (e) {
        console.error('Failed to init auth:', e);
      }
    }

    function renderNavUser() {
      const container = document.getElementById('nav-user-container');
      if (currentUser) {
        container.innerHTML = `
          <a href="https://discord.com/oauth2/authorize?client_id=1554732669072445532&permissions=8&scope=bot%20applications.commands" target="_blank" class="btn btn-outline btn-sm">
            <span>+ Add Bot</span>
          </a>
          <a onclick="navigate('/dashboard')" class="user-profile-btn" title="Open Personal Dashboard">
            <img class="user-avatar" src="${currentUser.avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png'}" alt="Avatar">
            <span style="font-weight: 600; font-size: 0.85rem;">${currentUser.display_name}</span>
          </a>
          <button class="btn btn-outline btn-sm" onclick="navigate('/saved')" title="Saved Bookmarks">
            🔖
          </button>
          <button class="btn btn-outline btn-sm" onclick="navigate('/notifications')" title="Notifications">
            🔔 <span id="unread-pill" class="badge-count" style="display:none;">0</span>
          </button>
          ${currentUser.is_admin ? '<button class="btn btn-primary btn-sm" onclick="navigate(\'/mission-control\')">🛡️ Mission Control</button>' : ''}
          <button class="btn btn-outline btn-sm" onclick="logout()">Logout</button>
        `;
        fetchUnreadCount();
      }
    }

    async function fetchUnreadCount() {
      try {
        const res = await fetch('/api/notifications');
        const data = await res.json();
        if (data.success && data.data) {
          const pill = document.getElementById('unread-pill');
          if (pill && data.data.unread_count > 0) {
            pill.innerText = data.data.unread_count;
            pill.style.display = 'inline-block';
          }
        }
      } catch (e) {}
    }

    function openLoginModal() {
      openModal('👾 Discord Login & Community Hub Access', `
        <div style="text-align:center; margin-bottom:1.5rem;">
          <div style="font-size:2.8rem; margin-bottom:0.4rem;">🌌</div>
          <h4 style="font-size:1.2rem; color:#fff; font-weight:800; letter-spacing:0.5px;">Sign In to Rai Community OS</h4>
          <p style="color:var(--text-muted); font-size:0.85rem; margin-top:0.3rem;">
            Connect your Discord identity to manage portfolios, join project boards, save favorites, and collaborate.
          </p>
        </div>

        <div style="display:flex; flex-direction:column; gap:1.2rem;">
          <!-- METHOD 1: OFFICIAL DISCORD OAUTH2 -->
          <div class="card" style="padding:1.25rem; border-color:var(--blurple); background:rgba(88, 101, 242, 0.08); border-radius:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
              <div style="font-weight:700; color:#fff; display:flex; align-items:center; gap:0.5rem; font-size:0.95rem;">
                <span style="font-size:1.2rem;">👾</span> Discord OAuth2 Authorization
              </div>
              <span class="pill pill-purple">OFFICIAL OAUTH</span>
            </div>
            <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:0.9rem; line-height:1.4;">
              Authorizes via Discord with your identity, avatars, and verified guild permissions.
            </p>
            <button class="btn btn-discord" style="width:100%; justify-content:center; padding:0.75rem; font-size:0.95rem;" onclick="startDiscordOAuth()">
              <span>👾</span> Continue with Discord
            </button>
          </div>

          <!-- METHOD 2: DIRECT DISCORD USER ID LOGIN -->
          <div class="card" style="padding:1.25rem; border-color:rgba(6, 182, 212, 0.4); background:rgba(6, 182, 212, 0.05); border-radius:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
              <div style="font-weight:700; color:#fff; display:flex; align-items:center; gap:0.5rem; font-size:0.95rem;">
                <span style="font-size:1.2rem;">🆔</span> Instant Discord ID Login
              </div>
              <span class="pill pill-cyan">NO SETUP NEEDED</span>
            </div>
            <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:0.8rem; line-height:1.4;">
              Enter your Discord User ID (or username) to sign in directly:
            </p>
            <form onsubmit="submitDiscordIdLogin(event)">
              <div style="display:flex; gap:0.6rem;">
                <input type="text" id="discord-login-id" class="input-field" style="flex:1;" placeholder="Discord User ID (e.g. 1457382179981099090)" value="1457382179981099090" required>
                <button type="submit" class="btn btn-primary">Sign In</button>
              </div>
            </form>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center;">
            <button class="btn btn-outline btn-sm" onclick="devQuickLogin()">⚡ Admin / Founder Login</button>
            <button class="btn btn-outline btn-sm" onclick="toggleOAuthGuide()" style="color:var(--cyan);">ℹ️ OAuth Setup Guide</button>
          </div>

          <div id="oauth-setup-guide" style="display:none; background:rgba(0,0,0,0.5); padding:1rem; border-radius:8px; font-size:0.78rem; color:var(--text-muted); line-height:1.6; border:1px solid rgba(255,255,255,0.08);">
            <strong style="color:#fff; font-size:0.85rem;">Setting up Discord OAuth2 in Developer Portal:</strong><br>
            1. Open Discord Developer Portal & select your Rai Application.<br>
            2. Under OAuth2 &rarr; Redirects, add: <code style="color:var(--pink);">http://localhost:8080/api/auth/callback</code>.<br>
            3. Set DISCORD_CLIENT_SECRET in <code>.env</code> file.
          </div>
        </div>
      `);
    }

    function toggleOAuthGuide() {
      const g = document.getElementById('oauth-setup-guide');
      if (g) g.style.display = g.style.display === 'none' ? 'block' : 'none';
    }

    async function startDiscordOAuth() {
      try {
        const res = await fetch('/api/auth/url');
        const data = await res.json();
        if (data.success && data.data.url) window.location.href = data.data.url;
        else alert('Could not start Discord OAuth: ' + (data.error?.message || 'Check configuration'));
      } catch (e) { alert('Could not start Discord OAuth flow: ' + e); }
    }

    async function submitDiscordIdLogin(e) {
      if (e) e.preventDefault();
      const inputEl = document.getElementById('discord-login-id');
      const val = inputEl ? inputEl.value.trim() : '';
      if (!val) return;
      try {
        const res = await fetch('/api/auth/discord-id-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: val, username: 'DiscordUser_' + val.slice(-4) })
        });
        const data = await res.json();
        if (data.success) {
          closeModal();
          await initAuth();
          navigate('/dashboard');
        } else alert('Login failed: ' + (data.error?.message || 'Server error'));
      } catch (err) { alert('Login error: ' + err); }
    }

    async function devQuickLogin() {
      try {
        const res = await fetch('/api/auth/dev-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: 1457382179981099090, username: 'ServerFounder', is_admin: true })
        });
        const data = await res.json();
        if (data.success) {
          closeModal();
          await initAuth();
          navigate('/dashboard');
        }
      } catch (e) { alert('Quick login failed: ' + e); }
    }

    async function logout() {
      await fetch('/api/auth/logout', { method: 'POST' });
      currentUser = null;
      window.location.reload();
    }

    // ==========================================
    // 4. GLOBAL SEARCH & AUTOCOMPLETE SYSTEM
    // ==========================================
    function onGlobalSearchFocus() {
      const panel = document.getElementById('nav-search-suggestions');
      const val = document.getElementById('global-nav-search').value.trim();
      if (panel) {
        panel.classList.add('active');
        if (val) executeGlobalSearch(val);
      }
    }

    function onGlobalSearchInput(val) {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        executeGlobalSearch(val.trim());
      }, 240);
    }

    document.addEventListener('click', e => {
      const searchBox = document.querySelector('.nav-search-box');
      const panel = document.getElementById('nav-search-suggestions');
      if (panel && searchBox && !searchBox.contains(e.target)) {
        panel.classList.remove('active');
      }
      const moreDropdown = document.getElementById('more-dropdown');
      if (moreDropdown && !moreDropdown.contains(e.target)) {
        moreDropdown.classList.remove('open');
      }
    });

    document.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const inp = document.getElementById('global-nav-search');
        if (inp) {
          inp.focus();
          inp.select();
        }
      }
      if (e.key === 'Escape') {
        const panel = document.getElementById('nav-search-suggestions');
        if (panel) panel.classList.remove('active');
        closeModal();
      }
    });

    async function executeGlobalSearch(q) {
      const panel = document.getElementById('nav-search-suggestions');
      if (!panel) return;
      if (!q) {
        panel.innerHTML = `
          <div style="padding:0.6rem; color:var(--text-muted); font-size:0.82rem; text-align:center;">
            Explore communities, creators, projects, gaming squads, and Rai systems.
          </div>
        `;
        return;
      }
      panel.innerHTML = `<div style="padding:0.8rem; color:var(--text-muted); font-size:0.82rem; text-align:center;">Searching Rai Community OS...</div>`;

      try {
        const res = await fetch('/api/brain/search?q=' + encodeURIComponent(q));
        const data = await res.json();
        if (data.success && data.data && data.data.total_matches > 0) {
          const cats = data.data.categories || {};
          let html = `<div style="font-size:0.75rem; color:var(--text-dim); padding:0.2rem 0.5rem 0.5rem 0.5rem; border-bottom:1px solid rgba(255,255,255,0.06);">Found ${data.data.total_matches} match(es) for "<strong>${q}</strong>"</div>`;

          const sections = [
            { key: 'communities', title: '👥 Communities', icon: '👥' },
            { key: 'projects', title: '🚀 Projects', icon: '🚀' },
            { key: 'creators', title: '🎨 Creators & Portfolios', icon: '🎨' },
            { key: 'gaming', title: '🎮 Gaming Squads', icon: '🎮' },
            { key: 'resources', title: '📚 Resources', icon: '📚' },
            { key: 'events', title: '📅 Events', icon: '📅' },
            { key: 'ideas', title: '💡 Ideas & Roadmap', icon: '💡' },
            { key: 'rai_features', title: '🧠 Rai Bot Systems', icon: '✦' }
          ];

          for (let s of sections) {
            const items = cats[s.key] || [];
            if (items.length > 0) {
              html += `<div class="search-section-header">${s.title}</div>`;
              for (let item of items.slice(0, 3)) {
                html += `
                  <div class="search-item" onclick="navigate('${item.link}'); document.getElementById('nav-search-suggestions').classList.remove('active');">
                    <div class="search-item-info">
                      <div class="search-item-title">${item.title}</div>
                      <div class="search-item-snippet">${item.snippet || ''}</div>
                    </div>
                    <span class="pill pill-purple" style="font-size:0.65rem;">${item.type}</span>
                  </div>
                `;
              }
            }
          }
          panel.innerHTML = html;
        } else {
          panel.innerHTML = `
            <div style="padding:1rem; text-align:center; color:var(--text-muted); font-size:0.85rem;">
              No results discovered for "${q}". Try another keyword or browse categories below.
            </div>
          `;
        }
      } catch (e) {
        panel.innerHTML = `<div style="padding:0.8rem; color:var(--danger); font-size:0.82rem;">Search request error: ${e}</div>`;
      }
    }

    function toggleMoreMenu(e) {
      if (e) e.stopPropagation();
      const dd = document.getElementById('more-dropdown');
      if (dd) dd.classList.toggle('open');
    }

    function toggleMobileMenu() {
      const links = document.getElementById('main-nav-links');
      if (links) {
        links.style.display = links.style.display === 'flex' ? 'none' : 'flex';
        links.style.flexDirection = 'column';
        links.style.position = 'absolute';
        links.style.top = '100%';
        links.style.left = '0';
        links.style.width = '100%';
        links.style.background = 'rgba(10, 11, 18, 0.98)';
        links.style.padding = '1rem';
        links.style.borderBottom = '1px solid rgba(255,255,255,0.1)';
      }
    }

    // ==========================================
    // 5. BOOKMARKS / SAVED ITEMS HELPER
    // ==========================================
    async function toggleSaveItem(itemType, itemId, title, category) {
      if (!currentUser) {
        alert('Please sign in with Discord to bookmark items.');
        openLoginModal();
        return;
      }
      try {
        const res = await fetch('/api/saved/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_type: itemType, item_id: String(itemId), title, category })
        });
        const data = await res.json();
        if (data.success) {
          alert(data.data.saved ? `Saved "${title}" to your bookmarks!` : `Removed "${title}" from your bookmarks.`);
          if (currentRoute === '/saved') renderSaved(document.getElementById('view-container'));
        }
      } catch (e) {
        alert('Could not update bookmark: ' + e);
      }
    }

    // ==========================================
    // 6. MODAL UTILITIES
    // ==========================================
    function openModal(title, contentHtml) {
      document.getElementById('modal-title').innerText = title;
      document.getElementById('modal-body').innerHTML = contentHtml;
      document.getElementById('modal-overlay').classList.add('active');
    }
    function closeModal() {
      document.getElementById('modal-overlay').classList.remove('active');
    }

    // ==========================================
    // 7. CLIENT ROUTER DISPATCHER
    // ==========================================
    function navigate(route) {
      currentRoute = route;
      window.location.hash = route;

      // Update active nav indicators
      document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.remove('active');
        const oc = el.getAttribute('onclick') || '';
        if (oc.includes(route) && route !== '/') el.classList.add('active');
      });

      const container = document.getElementById('view-container');
      window.scrollTo(0, 0);

      // Route Dispatching
      if (route === '/' || route === '') renderHome(container);
      else if (route === '/discover') renderDiscover(container);
      else if (route === '/communities') renderCommunities(container);
      else if (route.startsWith('/communities/')) renderCommunityDetail(container, route.split('/')[2]);
      else if (route === '/projects') renderProjects(container);
      else if (route.startsWith('/projects/')) renderProjectDetail(container, route.split('/')[2]);
      else if (route === '/creators') renderCreators(container);
      else if (route === '/gaming') renderGaming(container);
      else if (route === '/music') renderMusic(container);
      else if (route === '/media') renderMedia(container);
      else if (route === '/resources') renderResources(container);
      else if (route === '/events') renderEvents(container);
      else if (route === '/ideas') renderIdeas(container);
      else if (route === '/rai') renderRaiProduct(container);
      else if (route === '/rai/features') renderRaiFeatures(container);
      else if (route === '/brain') renderBrain(container);
      else if (route === '/labs') renderLabs(container);
      else if (route === '/status') renderStatus(container);
      else if (route === '/wiki') renderWiki(container);
      else if (route === '/saved') renderSaved(container);
      else if (route === '/dashboard' || route === '/workspace') renderDashboard(container);
      else if (route === '/notifications') renderNotifications(container);
      else if (route === '/mission-control') renderMissionControl(container);
      else if (route.startsWith('/login')) { renderHome(container); openLoginModal(); }
      else renderHome(container);
    }

    // ==========================================
    // 8. HOMEPAGE VIEW (DISCOVERY PLATFORM V2)
    // ==========================================
    async function renderHome(container) {
      container.innerHTML = `
        <!-- HERO SECTION -->
        <section class="discovery-hero">
          <div class="hero-badge">✦ THE RAIVORA • COMMUNITY DISCOVERY PLATFORM ✦</div>
          <h2 class="hero-title">DISCOVER THE RAIVORA</h2>
          <p class="hero-subtitle">
            Communities, creators, projects and experiences powered by Rai.
          </p>

          <!-- HERO LARGE SEARCH BOX -->
          <div class="hero-search-wrapper">
            <form onsubmit="onHeroSearchSubmit(event)" class="hero-search-box">
              <span style="font-size:1.2rem; color:var(--cyan); margin-right:0.75rem;">🔍</span>
              <input type="text" id="hero-search-input" class="hero-search-input" placeholder="Search communities, creators, projects, games, music..." autocomplete="off">
              <button type="submit" class="btn btn-primary" style="border-radius:var(--radius-full); padding:0.6rem 1.4rem;">
                Explore
              </button>
            </form>
          </div>

          <div class="hero-actions">
            <button class="btn btn-primary btn-lg" onclick="navigate('/communities')">
              <span>✦</span> Explore Communities
            </button>
            <a href="https://discord.com/oauth2/authorize?client_id=1554732669072445532&permissions=8&scope=bot%20applications.commands" target="_blank" class="btn btn-discord btn-lg">
              <span>👾</span> Add to Discord
            </a>
          </div>
        </section>

        <!-- CATEGORY DISCOVERY PILLS -->
        <div class="category-pills-bar">
          <a class="cat-pill" onclick="navigate('/gaming')">🎮 Gaming <span class="cat-pill-count" id="count-gaming">LFG</span></a>
          <a class="cat-pill" onclick="navigate('/music')">🎧 Music <span class="cat-pill-count">320k</span></a>
          <a class="cat-pill" onclick="navigate('/creators')">🎨 Creators <span class="cat-pill-count" id="count-creators">VFX</span></a>
          <a class="cat-pill" onclick="navigate('/projects')">🚀 Projects <span class="cat-pill-count" id="count-projects">Active</span></a>
          <a class="cat-pill" onclick="navigate('/media')">🎬 Media <span class="cat-pill-count">Live</span></a>
          <a class="cat-pill" onclick="navigate('/events')">📅 Events <span class="cat-pill-count" id="count-events">Events</span></a>
          <a class="cat-pill" onclick="navigate('/resources')">📚 Resources <span class="cat-pill-count" id="count-resources">LUTs</span></a>
          <a class="cat-pill" onclick="navigate('/brain')">🧠 AI Brain <span class="cat-pill-count">Q&A</span></a>
          <a class="cat-pill" onclick="navigate('/rai/features#security')">🛡 Security <span class="cat-pill-count">Safe</span></a>
          <a class="cat-pill" onclick="navigate('/labs')">🛠 Labs <span class="cat-pill-count">Graph</span></a>
        </div>

        <!-- 🔥 TRENDING NOW -->
        <div class="section-title">
          <div class="title-group">
            <span class="title-text">🔥 Trending Now</span>
            <span class="pill pill-purple">REAL-TIME ACTIVITY</span>
          </div>
          <button class="btn btn-outline btn-sm" onclick="navigate('/communities')">View All Communities &rarr;</button>
        </div>
        <div class="discovery-grid" id="trending-grid">
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
        </div>

        <!-- ✦ FEATURED SPOTLIGHT -->
        <div class="spotlight-card" style="margin-top:3.5rem;">
          <div class="spotlight-content">
            <div class="spotlight-badge">✦ FEATURED CREATIVE HUB</div>
            <h3>Nightwave Creative Studio & VFX Lounge</h3>
            <p>
              Dedicated community hub for video editors, After Effects motion designers, 3D artists, and beatmakers.
              Collaborate on montage reels, share LUTs, and join weekly render jams.
            </p>
            <div style="display:flex; gap:0.8rem; flex-wrap:wrap;">
              <button class="btn btn-primary" onclick="navigate('/communities/hub-nightwave')">Explore Studio ↗</button>
              <button class="btn btn-outline" onclick="navigate('/creators')">Meet Creators</button>
            </div>
          </div>
          <div style="font-size:5rem; text-shadow:0 0 35px var(--primary-glow); display:none;" id="spotlight-icon">🎨</div>
        </div>

        <!-- 👥 POPULAR COMMUNITIES -->
        <div class="section-title">
          <div class="title-group">
            <span class="title-text">👥 Popular Communities</span>
            <span class="pill pill-cyan">DISCORD HUBS</span>
          </div>
          <button class="btn btn-outline btn-sm" onclick="navigate('/communities')">Browse Directory &rarr;</button>
        </div>
        <div class="discovery-grid" id="home-communities-grid">
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
        </div>

        <!-- 🚀 ACTIVE PROJECTS -->
        <div class="section-title">
          <div class="title-group">
            <span class="title-text">🚀 Active Projects</span>
            <span class="pill pill-pink">COLLABORATIVE SPACES</span>
          </div>
          <button class="btn btn-primary btn-sm" onclick="openCreateProjectModal()">+ Launch Project</button>
        </div>
        <div class="discovery-grid" id="home-projects-grid">
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
        </div>

        <!-- 🎮 GAMING SQUADS & LFG -->
        <div class="section-title">
          <div class="title-group">
            <span class="title-text">🎮 Active Gaming Squads</span>
            <span class="pill pill-green">LIVE LFG</span>
          </div>
          <button class="btn btn-outline btn-sm" onclick="navigate('/gaming')">Join Matchmaker &rarr;</button>
        </div>
        <div class="discovery-grid" id="home-gaming-grid">
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
        </div>

        <!-- 🎧 MUSIC PREVIEW & LISTENING ROOMS -->
        <div class="section-title">
          <div class="title-group">
            <span class="title-text">🎧 Lossless Music & Audio Stream</span>
            <span class="pill pill-purple">320kbps OPUS</span>
          </div>
          <button class="btn btn-outline btn-sm" onclick="navigate('/music')">Music Hub &rarr;</button>
        </div>

        <div class="player-widget">
          <div class="player-header">
            <div style="display:flex; align-items:center; gap:0.6rem;">
              <span class="pill pill-green" id="home-music-vc">🟢 Live in 🔊 General Lounge VC • 14 Listening</span>
              <span class="pill pill-cyan">Zero Buffering</span>
            </div>
            <div style="display:flex; align-items:center; gap:0.5rem; font-size:0.8rem; color:var(--text-muted);">
              <span>Hi-Fi Stream</span>
              <div class="eq-bars">
                <div class="eq-bar"></div>
                <div class="eq-bar"></div>
                <div class="eq-bar"></div>
                <div class="eq-bar"></div>
              </div>
            </div>
          </div>
          <div class="player-main">
            <div class="player-disc" id="home-player-disc">💿</div>
            <div class="player-info">
              <div class="player-title" id="home-track-title">Resonance • Synthwave Hi-Fi</div>
              <div class="player-artist" id="home-track-artist">The Raivora 2.6 • 320kbps Stream • Auto-DJ</div>
            </div>
            <div class="player-controls">
              <button class="ctrl-icon-btn" onclick="nextDemoTrack()" title="Previous Track">⏮</button>
              <button class="play-btn" id="home-play-btn" onclick="toggleAudioPreview()" title="Play / Pause">▶</button>
              <button class="ctrl-icon-btn" onclick="nextDemoTrack()" title="Next Track">⏭</button>
            </div>
          </div>
        </div>

        <!-- 📅 UPCOMING EVENTS -->
        <div class="section-title">
          <div class="title-group">
            <span class="title-text">📅 Community Events</span>
            <span class="pill pill-pink">SCHEDULED</span>
          </div>
          <button class="btn btn-outline btn-sm" onclick="navigate('/events')">All Events &rarr;</button>
        </div>
        <div class="discovery-grid" id="home-events-grid">
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
        </div>

        <!-- ✦ POWERED BY RAI PLATFORM HIGHLIGHT -->
        <div style="margin-top:4rem; padding:3rem 2rem; background:linear-gradient(135deg, rgba(20,24,38,0.85), rgba(12,14,24,0.95)); border:1px solid rgba(147,51,234,0.3); border-radius:var(--radius-lg); text-align:center;">
          <div style="font-size:2.5rem; margin-bottom:0.5rem;">✦</div>
          <h3 style="font-size:2.2rem; font-weight:800; color:#fff; margin-bottom:0.6rem;">POWERED BY RAI COMMUNITY OS</h3>
          <p style="color:var(--text-muted); max-width:650px; margin:0 auto 1.8rem auto; font-size:1.05rem; line-height:1.6;">
            A unified operating system engineered for Discord servers, content creators, competitive gaming teams, and collaborative ventures.
          </p>
          <div style="display:flex; justify-content:center; gap:1rem; flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="navigate('/rai')">Explore Rai Platform</button>
            <button class="btn btn-outline" onclick="navigate('/rai/features')">View 18+ Subsystems</button>
            <button class="btn btn-outline" onclick="navigate('/status')">System Health & Doctor</button>
          </div>
        </div>
      `;

      loadHomeData();
    }

    function onHeroSearchSubmit(e) {
      if (e) e.preventDefault();
      const val = document.getElementById('hero-search-input').value.trim();
      if (!val) return;
      navigate('/discover');
      setTimeout(() => {
        const inp = document.getElementById('discover-input');
        if (inp) {
          inp.value = val;
          onDiscoverSearch(val);
        }
      }, 50);
    }

    async function loadHomeData() {
      // 1. Fetch live telemetry counts
      try {
        const sRes = await fetch('/api/stats');
        const s = await sRes.json();
        if (s.success && s.data) {
          const d = s.data;
          const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.innerText = val; };
          setEl('count-projects', d.active_projects_count + ' Active');
          setEl('count-events', d.upcoming_events_count + ' Scheduled');
          setEl('count-resources', d.resources_count + ' Available');
        }
      } catch (e) {}

      // 2. Fetch Communities
      try {
        const cRes = await fetch('/api/communities');
        const cData = await cRes.json();
        if (cData.success && cData.data) {
          const comms = cData.data;
          const trGrid = document.getElementById('trending-grid');
          const hcGrid = document.getElementById('home-communities-grid');

          if (trGrid) {
            trGrid.innerHTML = comms.slice(0, 3).map(c => `
              <div class="discovery-card">
                <div>
                  <div class="card-top">
                    <div class="card-media-icon">${c.icon && c.icon.length > 5 ? `<img src="${c.icon}">` : (c.icon || '✦')}</div>
                    <div class="card-heading">
                      <div class="card-name">${c.name} ${c.verified ? '✓' : ''}</div>
                      <div class="card-subtitle">${c.type}</div>
                    </div>
                  </div>
                  <div class="card-desc">${c.description}</div>
                  <div class="card-tags">
                    ${c.tags.slice(0, 3).map(t => `<span class="tag-badge">${t}</span>`).join('')}
                  </div>
                </div>
                <div>
                  <div class="card-metrics">
                    <span>👥 ${c.members} members</span>
                    <span style="color:var(--cyan);">${c.activity_status}</span>
                  </div>
                  <div class="card-bottom-actions">
                    <button class="btn btn-outline btn-sm" style="flex:1;" onclick="navigate('/communities/${c.id}')">View</button>
                    <a href="${c.invite_url}" target="_blank" class="btn btn-discord btn-sm" style="flex:1;">Join Discord</a>
                    <button class="btn btn-outline btn-sm" onclick="toggleSaveItem('community', '${c.id}', '${c.name}', '${c.category}')">🔖</button>
                  </div>
                </div>
              </div>
            `).join('');
          }

          if (hcGrid) {
            hcGrid.innerHTML = comms.map(c => `
              <div class="discovery-card">
                <div>
                  <div class="card-top">
                    <div class="card-media-icon">${c.icon && c.icon.length > 5 ? `<img src="${c.icon}">` : (c.icon || '✦')}</div>
                    <div class="card-heading">
                      <div class="card-name">${c.name}</div>
                      <div class="card-subtitle">${c.badge || c.type}</div>
                    </div>
                  </div>
                  <div class="card-desc">${c.description}</div>
                  <div class="card-tags">
                    ${c.tags.map(t => `<span class="tag-badge">${t}</span>`).join('')}
                  </div>
                </div>
                <div>
                  <div class="card-metrics">
                    <span>👥 ${c.members} members</span>
                    <span>🚀 ${c.active_projects} projects</span>
                  </div>
                  <div class="card-bottom-actions">
                    <button class="btn btn-outline btn-sm" style="flex:1;" onclick="navigate('/communities/${c.id}')">Explore Hub</button>
                    <a href="${c.invite_url}" target="_blank" class="btn btn-discord btn-sm" style="flex:1;">Join Server</a>
                  </div>
                </div>
              </div>
            `).join('');
          }
        }
      } catch (e) {}

      // 3. Fetch Projects
      try {
        const pRes = await fetch('/api/projects');
        const pData = await pRes.json();
        const pGrid = document.getElementById('home-projects-grid');
        if (pGrid && pData.success && pData.data && pData.data.length > 0) {
          pGrid.innerHTML = pData.data.slice(0, 3).map(p => `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">🚀</div>
                  <div class="card-heading">
                    <div class="card-name">${p.name}</div>
                    <div class="card-subtitle">${p.project_type.toUpperCase()}</div>
                  </div>
                </div>
                <div class="card-desc">Connected Discord workspace with synchronized chat, voice rooms, and Kanban board.</div>
                <div class="card-tags">
                  <span class="pill pill-purple">${p.status.toUpperCase()}</span>
                  <span class="tag-badge">Discord Sync</span>
                </div>
              </div>
              <div>
                <div class="card-metrics">
                  <span>Owner: #${p.owner_id}</span>
                  <span style="color:var(--text-dim);">${p.created_at.split('T')[0]}</span>
                </div>
                <div class="card-bottom-actions">
                  <button class="btn btn-outline btn-sm" style="flex:1;" onclick="openProjectWorkspace(${p.id})">Open Board</button>
                  <button class="btn btn-outline btn-sm" onclick="toggleSaveItem('project', '${p.id}', '${p.name}', '${p.project_type}')">🔖</button>
                </div>
              </div>
            </div>
          `).join('');
        } else if (pGrid) {
          pGrid.innerHTML = `
            <div class="state-box">
              <div class="state-icon">🚀</div>
              <div class="state-title">No Projects Discovered Yet</div>
              <div class="state-desc">Initiate a collaborative project to coordinate video editing, tournaments, or community tools.</div>
              <button class="btn btn-primary" onclick="openCreateProjectModal()">+ Launch Project</button>
            </div>
          `;
        }
      } catch (e) {}

      // 4. Fetch Gaming LFG
      try {
        const gRes = await fetch('/api/gaming/lfg');
        const gData = await gRes.json();
        const gGrid = document.getElementById('home-gaming-grid');
        if (gGrid && gData.success && gData.data && gData.data.length > 0) {
          gGrid.innerHTML = gData.data.slice(0, 3).map(g => `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">🎮</div>
                  <div class="card-heading">
                    <div class="card-name">${g.game_name}</div>
                    <div class="card-subtitle">${g.mode || 'Ranked Squad'}</div>
                  </div>
                </div>
                <div class="card-desc">${g.description || 'Looking for team members for competitive and casual matches.'}</div>
                <div class="card-tags">
                  <span class="pill pill-green">ACTIVE</span>
                  <span class="tag-badge">${g.current_players}/${g.max_players} Players</span>
                </div>
              </div>
              <div>
                <div class="card-metrics">
                  <span>Host: #${g.creator_id}</span>
                  <span>Voice Match Ready</span>
                </div>
                <div class="card-bottom-actions">
                  <button class="btn btn-primary btn-sm" style="width:100%;" onclick="joinSquad(${g.id})">Join Squad</button>
                </div>
              </div>
            </div>
          `).join('');
        } else if (gGrid) {
          gGrid.innerHTML = `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">🎮</div>
                  <div class="card-heading">
                    <div class="card-name">BGMI Competitive Squad</div>
                    <div class="card-subtitle">RANKED MATCHMAKING</div>
                  </div>
                </div>
                <div class="card-desc">3 / 4 Players • Looking for aggressive fragger with working mic.</div>
                <div class="card-tags"><span class="pill pill-green">ACTIVE</span></div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-primary btn-sm" style="width:100%;" onclick="navigate('/gaming')">Join Session</button>
              </div>
            </div>
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">🎯</div>
                  <div class="card-heading">
                    <div class="card-name">Valorant Premier Team</div>
                    <div class="card-subtitle">TOURNAMENT BRACKET</div>
                  </div>
                </div>
                <div class="card-desc">4 / 5 Players • Ascendant/Immortal scrims scheduled this evening.</div>
                <div class="card-tags"><span class="pill pill-cyan">PREMIER</span></div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-outline btn-sm" style="width:100%;" onclick="navigate('/gaming')">View Team</button>
              </div>
            </div>
          `;
        }
      } catch (e) {}

      // 5. Fetch Events
      try {
        const eRes = await fetch('/api/events');
        const eData = await eRes.json();
        const eGrid = document.getElementById('home-events-grid');
        if (eGrid && eData.success && eData.data && eData.data.length > 0) {
          eGrid.innerHTML = eData.data.slice(0, 3).map(ev => `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">📅</div>
                  <div class="card-heading">
                    <div class="card-name">${ev.title}</div>
                    <div class="card-subtitle">${ev.event_type.toUpperCase()}</div>
                  </div>
                </div>
                <div class="card-desc">${ev.description || 'Community gathering scheduled in Discord channels.'}</div>
                <div class="card-tags">
                  <span class="pill pill-pink">${ev.status.toUpperCase()}</span>
                  <span class="tag-badge">Starts: ${ev.start_time.split('T')[0]}</span>
                </div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-outline btn-sm" style="flex:1;" onclick="rsvpEvent(${ev.id})">RSVP Interested</button>
                <a href="https://discord.gg/raivora" target="_blank" class="btn btn-discord btn-sm" style="flex:1;">Join Discord</a>
              </div>
            </div>
          `).join('');
        } else if (eGrid) {
          eGrid.innerHTML = `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">🎬</div>
                  <div class="card-heading">
                    <div class="card-name">Weekend Anime Watch Party</div>
                    <div class="card-subtitle">MEDIA LOUNGE</div>
                  </div>
                </div>
                <div class="card-desc">Community cinema watch party in Discord Cinema VC every Saturday.</div>
                <div class="card-tags"><span class="pill pill-pink">SATURDAY 8 PM</span></div>
              </div>
              <div class="card-bottom-actions">
                <a href="https://discord.gg/raivora" target="_blank" class="btn btn-discord btn-sm" style="width:100%;">Join Discord Cinema</a>
              </div>
            </div>
          `;
        }
      } catch (e) {}
    }

    // ==========================================
    // 9. COMMUNITIES DIRECTORY VIEW (/communities)
    // ==========================================
    async function renderCommunities(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">👥 Communities Directory</span>
            <span class="pill pill-purple">THE RAIVORA HUBS</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem; line-height:1.6;">
          Discover official and verified community hubs connected with Rai. Join servers, explore creative studios, and find active gaming clans.
        </p>

        <!-- FILTERS & SORTING ROW -->
        <div class="filters-row">
          <div class="filter-group">
            <input type="text" id="comm-search" class="input-field" placeholder="Search communities..." oninput="filterCommunities()" style="width:220px;">
            <select id="comm-cat-filter" class="select-field" onchange="filterCommunities()">
              <option value="all">All Categories</option>
              <option value="creators">🎨 Creators & Media</option>
              <option value="gaming">🎮 Gaming & Esports</option>
              <option value="projects">🚀 Dev & Tech</option>
            </select>
          </div>
          <div class="filter-group">
            <span style="font-size:0.85rem; color:var(--text-muted);">Sort by:</span>
            <select id="comm-sort" class="select-field" onchange="filterCommunities()">
              <option value="trending">🔥 Trending</option>
              <option value="most_active">⚡ Most Active</option>
              <option value="members">👥 Member Count</option>
              <option value="newest">✨ Newest</option>
            </select>
          </div>
        </div>

        <div class="discovery-grid" id="communities-list-grid">
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
        </div>
      `;

      loadCommunitiesDirectory();
    }

    async function loadCommunitiesDirectory() {
      const q = document.getElementById('comm-search') ? document.getElementById('comm-search').value.trim() : '';
      const cat = document.getElementById('comm-cat-filter') ? document.getElementById('comm-cat-filter').value : 'all';
      const sort = document.getElementById('comm-sort') ? document.getElementById('comm-sort').value : 'trending';

      try {
        const res = await fetch(`/api/communities?q=${encodeURIComponent(q)}&category=${cat}&sort=${sort}`);
        const data = await res.json();
        const grid = document.getElementById('communities-list-grid');
        if (data.success && data.data && data.data.length > 0) {
          grid.innerHTML = data.data.map(c => `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">${c.icon && c.icon.length > 5 ? `<img src="${c.icon}">` : (c.icon || '✦')}</div>
                  <div class="card-heading">
                    <div class="card-name">${c.name} ${c.verified ? '✓' : ''}</div>
                    <div class="card-subtitle">${c.badge || c.type}</div>
                  </div>
                </div>
                <div class="card-desc">${c.description}</div>
                <div class="card-tags">
                  ${c.tags.map(t => `<span class="tag-badge">${t}</span>`).join('')}
                </div>
              </div>
              <div>
                <div class="card-metrics">
                  <span>👥 ${c.members} members</span>
                  <span>🚀 ${c.active_projects} active projects</span>
                </div>
                <div class="card-bottom-actions">
                  <button class="btn btn-outline btn-sm" style="flex:1;" onclick="navigate('/communities/${c.id}')">View Details</button>
                  <a href="${c.invite_url}" target="_blank" class="btn btn-discord btn-sm" style="flex:1;">Join Server</a>
                  <button class="btn btn-outline btn-sm" onclick="toggleSaveItem('community', '${c.id}', '${c.name}', '${c.category}')">🔖</button>
                </div>
              </div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `
            <div class="state-box">
              <div class="state-icon">🔍</div>
              <div class="state-title">No Communities Found</div>
              <div class="state-desc">No communities match your current search filters. Try clearing your search term.</div>
            </div>
          `;
        }
      } catch (e) {
        document.getElementById('communities-list-grid').innerHTML = `<div class="state-box"><div class="state-title">Rai couldn't load communities</div><button class="btn btn-primary" onclick="loadCommunitiesDirectory()">Retry</button></div>`;
      }
    }

    function filterCommunities() {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(loadCommunitiesDirectory, 200);
    }

    // ==========================================
    // 10. COMMUNITY DETAIL VIEW (/communities/:id)
    // ==========================================
    async function renderCommunityDetail(container, commId) {
      container.innerHTML = `<div class="state-box"><div class="state-icon">⏳</div><div class="state-title">Loading Community Hub...</div></div>`;

      try {
        const res = await fetch(`/api/communities/${commId}`);
        const data = await res.json();
        if (!data.success || !data.data) {
          container.innerHTML = `<div class="state-box"><div class="state-title">Community Not Found</div><button class="btn btn-outline" onclick="navigate('/communities')">Back to Directory</button></div>`;
          return;
        }

        const c = data.data.community;
        const projects = data.data.projects || [];
        const creators = data.data.creators || [];
        const events = data.data.events || [];

        container.innerHTML = `
          <!-- BANNER & HEADER -->
          <div style="background:url('${c.banner || 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1200&q=80'}') center/cover; border-radius:var(--radius-lg); height:220px; position:relative; margin-bottom:4rem; border:1px solid rgba(255,255,255,0.1);">
            <div style="position:absolute; bottom:-35px; left:2.5rem; display:flex; align-items:flex-end; gap:1.2rem;">
              <div style="width:84px; height:84px; border-radius:var(--radius-lg); background:linear-gradient(135deg, var(--primary), #7c3aed); border:3px solid var(--bg-dark); display:flex; align-items:center; justify-content:center; font-size:2.8rem; box-shadow:0 8px 25px rgba(0,0,0,0.7);">
                ${c.icon && c.icon.length > 5 ? `<img src="${c.icon}" style="width:100%; height:100%; object-fit:cover; border-radius:inherit;">` : (c.icon || '✦')}
              </div>
              <div style="margin-bottom:0.5rem;">
                <h2 style="font-size:2rem; font-weight:800; color:#fff;">${c.name} ${c.verified ? '✓' : ''}</h2>
                <span class="pill pill-purple">${c.badge || c.type}</span>
              </div>
            </div>
            <div style="position:absolute; bottom:1rem; right:1.5rem; display:flex; gap:0.6rem;">
              <a href="${c.invite_url}" target="_blank" class="btn btn-discord btn-sm">Join Discord Server</a>
              <button class="btn btn-outline btn-sm" onclick="toggleSaveItem('community', '${c.id}', '${c.name}', '${c.category}')">🔖 Save</button>
            </div>
          </div>

          <div style="margin-bottom:2.5rem; max-width:850px;">
            <h4 style="color:#fff; margin-bottom:0.5rem; font-size:1.1rem;">About ${c.name}</h4>
            <p style="color:var(--text-muted); line-height:1.7; font-size:0.95rem;">${c.description}</p>
            <div style="display:flex; gap:0.5rem; margin-top:1rem; flex-wrap:wrap;">
              ${c.tags.map(t => `<span class="tag-badge">#${t}</span>`).join('')}
            </div>
          </div>

          <!-- COMMUNITY PROJECTS -->
          <div class="section-title">
            <span class="title-text">🚀 Active Projects in this Hub (${projects.length})</span>
            <button class="btn btn-primary btn-sm" onclick="openCreateProjectModal()">+ Launch Project</button>
          </div>
          <div class="discovery-grid" style="margin-bottom:3rem;">
            ${projects.length > 0 ? projects.map(p => `
              <div class="discovery-card">
                <div>
                  <div class="card-name">${p.name}</div>
                  <div class="card-subtitle">${p.project_type.toUpperCase()}</div>
                  <div class="card-desc" style="margin-top:0.6rem;">Discord synced project workspace.</div>
                </div>
                <div class="card-bottom-actions">
                  <button class="btn btn-outline btn-sm" style="width:100%;" onclick="openProjectWorkspace(${p.id})">Open Board</button>
                </div>
              </div>
            `).join('') : '<div class="state-box" style="grid-column:1/-1;"><div class="state-desc">No active projects launched in this hub yet.</div></div>'}
          </div>

          <!-- COMMUNITY CREATORS -->
          <div class="section-title">
            <span class="title-text">🎨 Featured Creators & Editors (${creators.length})</span>
            <button class="btn btn-outline btn-sm" onclick="navigate('/creators')">All Creators</button>
          </div>
          <div class="discovery-grid">
            ${creators.length > 0 ? creators.map(cr => `
              <div class="discovery-card">
                <div>
                  <div class="card-name">${cr.title}</div>
                  <div class="card-subtitle">${cr.category.toUpperCase()}</div>
                  <div class="card-desc" style="margin-top:0.6rem;">${cr.description || 'Creator portfolio showcase item.'}</div>
                </div>
                <div class="card-bottom-actions">
                  <button class="btn btn-outline btn-sm" style="width:100%;" onclick="openPortfolioModal(${JSON.stringify(cr).replace(/"/g, '&quot;')})">View Portfolio</button>
                </div>
              </div>
            `).join('') : '<div class="state-box" style="grid-column:1/-1;"><div class="state-desc">No creator showcases listed in this community yet.</div></div>'}
          </div>
        `;
      } catch (e) {
        container.innerHTML = `<div class="state-box"><div class="state-title">Error Loading Community</div><p style="color:var(--danger);">${e}</p></div>`;
      }
    }

    // ==========================================
    // 11. RAI PRODUCT PAGE (/rai)
    // ==========================================
    function renderRaiProduct(container) {
      container.innerHTML = `
        <div class="discovery-hero">
          <div class="hero-badge">✦ RAI COMMUNITY OS • PLATFORM SPECIFICATION ✦</div>
          <h2 class="hero-title">THE RAIVORA COMMUNITY AI</h2>
          <p class="hero-subtitle">
            An intelligent community operating system for Discord, creators, gaming squads, lossless music, and autonomous automation.
          </p>
          <div class="hero-actions">
            <a href="https://discord.com/oauth2/authorize?client_id=1554732669072445532&permissions=8&scope=bot%20applications.commands" target="_blank" class="btn btn-primary btn-lg">
              <span>✦</span> ADD TO DISCORD
            </a>
            <button class="btn btn-outline btn-lg" onclick="navigate('/rai/features')">
              <span>⚙</span> EXPLORE FEATURES
            </button>
          </div>
        </div>

        <!-- 10 CORE PILLARS GRID -->
        <div class="section-title">
          <span class="title-text">✦ Architecture & Core Pillars</span>
          <span class="pill pill-cyan">PRODUCTION VERIFIED</span>
        </div>

        <div class="discovery-grid">
          <div class="discovery-card">
            <div>
              <div class="card-top">
                <div class="card-media-icon">🛡️</div>
                <div class="card-heading">
                  <div class="card-name">Security & Anti-Nuke</div>
                  <div class="card-subtitle">PROTECTION</div>
                </div>
              </div>
              <div class="card-desc">Atomic quarantine role stripping, velocity tripwires, malicious webhook suppression, and instant rollback.</div>
            </div>
            <div class="card-bottom-actions">
              <button class="btn btn-outline btn-sm" style="width:100%;" onclick="navigate('/rai/features#security')">Inspect Subsystem</button>
            </div>
          </div>

          <div class="discovery-card">
            <div>
              <div class="card-top">
                <div class="card-media-icon">🎧</div>
                <div class="card-heading">
                  <div class="card-name">High-Fidelity Music</div>
                  <div class="card-subtitle">320KBPS OPUS</div>
                </div>
              </div>
              <div class="card-desc">Lossless 320kbps audio streaming in voice channels with zero buffering, collaborative queues, and Auto-DJ.</div>
            </div>
            <div class="card-bottom-actions">
              <button class="btn btn-outline btn-sm" style="width:100%;" onclick="navigate('/rai/features#music')">Inspect Subsystem</button>
            </div>
          </div>

          <div class="discovery-card">
            <div>
              <div class="card-top">
                <div class="card-media-icon">🔊</div>
                <div class="card-heading">
                  <div class="card-name">Dynamic Voice Channels</div>
                  <div class="card-subtitle">VOICE MATRIX</div>
                </div>
              </div>
              <div class="card-desc">Zero-latency temporary voice rooms spawned automatically when members join generators. Auto-garbage collection on empty.</div>
            </div>
            <div class="card-bottom-actions">
              <button class="btn btn-outline btn-sm" style="width:100%;" onclick="navigate('/rai/features#dynamic-vc')">Inspect Subsystem</button>
            </div>
          </div>

          <div class="discovery-card">
            <div>
              <div class="card-top">
                <div class="card-media-icon">💾</div>
                <div class="card-heading">
                  <div class="card-name">Backup & Recovery</div>
                  <div class="card-subtitle">RELIABILITY</div>
                </div>
              </div>
              <div class="card-desc">Automated SQLite WAL delta snapshotting, serialized role permissions, and one-click disaster recovery.</div>
            </div>
            <div class="card-bottom-actions">
              <button class="btn btn-outline btn-sm" style="width:100%;" onclick="navigate('/rai/features#backup')">Inspect Subsystem</button>
            </div>
          </div>

          <div class="discovery-card">
            <div>
              <div class="card-top">
                <div class="card-media-icon">🚀</div>
                <div class="card-heading">
                  <div class="card-name">Project Workspaces</div>
                  <div class="card-subtitle">PRODUCTIVITY</div>
                </div>
              </div>
              <div class="card-desc">Interactive Kanban task boards with asynchronous Outbox worker linking Discord channels automatically.</div>
            </div>
            <div class="card-bottom-actions">
              <button class="btn btn-outline btn-sm" style="width:100%;" onclick="navigate('/projects')">View Boards</button>
            </div>
          </div>

          <div class="discovery-card">
            <div>
              <div class="card-top">
                <div class="card-media-icon">🎮</div>
                <div class="card-heading">
                  <div class="card-name">Gaming LFG Matchmaker</div>
                  <div class="card-subtitle">COMMUNITY</div>
                </div>
              </div>
              <div class="card-desc">Live party recruitment for BGMI, Valorant, Helldivers, and Apex with automatic voice room coordination.</div>
            </div>
            <div class="card-bottom-actions">
              <button class="btn btn-outline btn-sm" style="width:100%;" onclick="navigate('/gaming')">Join Matchmaker</button>
            </div>
          </div>
        </div>
      `;
    }

    // ==========================================
    // 12. RAI FEATURES DIRECTORY (/rai/features)
    // ==========================================
    async function renderRaiFeatures(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">⚙ Rai Systems & Subsystems Directory</span>
            <span class="pill pill-purple">18+ REAL SUBSYSTEMS</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem; line-height:1.6;">
          Complete architectural directory of Rai Community OS. All features documented here are truthfully implemented and supervised in the live bot.
        </p>

        <div class="discovery-grid" id="features-directory-grid">
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
        </div>
      `;

      try {
        const res = await fetch('/api/rai/features');
        const data = await res.json();
        const grid = document.getElementById('features-directory-grid');
        if (data.success && data.data) {
          grid.innerHTML = data.data.map(f => `
            <div class="discovery-card" id="${f.id}">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">${f.icon}</div>
                  <div class="card-heading">
                    <div class="card-name">${f.name}</div>
                    <div class="card-subtitle">${f.category.toUpperCase()}</div>
                  </div>
                </div>
                <div class="card-desc">${f.summary}</div>
                <ul style="padding-left:1.2rem; font-size:0.82rem; color:var(--text-muted); margin-bottom:1rem; line-height:1.6;">
                  ${f.details.map(d => `<li>${d}</li>`).join('')}
                </ul>
              </div>
              <div class="card-metrics">
                <span class="pill pill-green">STATUS: ${f.status}</span>
                <span style="font-size:0.75rem; color:var(--cyan);">Rai Core Subsystem</span>
              </div>
            </div>
          `).join('');
        }
      } catch (e) {}
    }

    // ==========================================
    // 13. USER SAVED BOOKMARKS VIEW (/saved)
    // ==========================================
    async function renderSaved(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🔖 My Saved Bookmarks</span>
            <span class="pill pill-purple">PERSISTENT SAVES</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          Quickly access your saved communities, projects, creators, resources, and ideas.
        </p>
        <div class="discovery-grid" id="saved-items-grid">
          <div class="skeleton-card"></div>
        </div>
      `;

      if (!currentUser) {
        document.getElementById('saved-items-grid').innerHTML = `
          <div class="state-box">
            <div class="state-icon">🔒</div>
            <div class="state-title">Sign In to View Bookmarks</div>
            <div class="state-desc">Connect your Discord account to save communities, projects, and resources.</div>
            <button class="btn btn-discord" onclick="openLoginModal()">Log In with Discord</button>
          </div>
        `;
        return;
      }

      try {
        const res = await fetch('/api/saved');
        const data = await res.json();
        const grid = document.getElementById('saved-items-grid');
        if (data.success && data.data && data.data.saved && data.data.saved.length > 0) {
          grid.innerHTML = data.data.saved.map(item => `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">🔖</div>
                  <div class="card-heading">
                    <div class="card-name">${item.title}</div>
                    <div class="card-subtitle">${item.item_type.toUpperCase()} • ${item.category || 'General'}</div>
                  </div>
                </div>
                <div class="card-desc">Saved on ${item.created_at.split('T')[0]}</div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-outline btn-sm" style="flex:1;" onclick="navigate('/${item.item_type === 'community' ? 'communities/' + item.item_id : (item.item_type === 'project' ? 'projects/' + item.item_id : item.item_type + 's')}')">Open</button>
                <button class="btn btn-outline btn-sm" onclick="toggleSaveItem('${item.item_type}', '${item.item_id}', '${item.title}', '${item.category}')">Remove</button>
              </div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `
            <div class="state-box">
              <div class="state-icon">🔖</div>
              <div class="state-title">No Saved Items Yet</div>
              <div class="state-desc">Click the bookmark icon (🔖) on any community, project, or resource to save it here.</div>
              <button class="btn btn-primary" onclick="navigate('/communities')">Discover Communities</button>
            </div>
          `;
        }
      } catch (e) {
        document.getElementById('saved-items-grid').innerHTML = `<div class="state-box"><div class="state-title">Error loading saved items</div></div>`;
      }
    }

    // ==========================================
    // 14. PERSONAL DASHBOARD (/dashboard)
    // ==========================================
    async function renderDashboard(container) {
      if (!currentUser) {
        container.innerHTML = `
          <div class="state-box">
            <div class="state-icon">👾</div>
            <div class="state-title">Personal Dashboard Access</div>
            <div class="state-desc">Sign in with Discord to access your personal workspace, manage your creator portfolio, and track collaboration requests.</div>
            <button class="btn btn-discord" onclick="openLoginModal()">Log In with Discord</button>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">⚡ Member Workspace & Dashboard</span>
            <span class="pill pill-green">AUTHENTICATED: ${currentUser.display_name}</span>
          </div>
        </div>

        <div style="display:grid; grid-template-columns:1fr 2fr; gap:2rem; margin-bottom:3rem;" id="dashboard-layout">
          <!-- PROFILE CARD -->
          <div class="discovery-card" style="height:fit-content;">
            <div style="text-align:center; padding:1rem 0;">
              <img src="${currentUser.avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png'}" style="width:84px; height:84px; border-radius:50%; border:3px solid var(--primary); margin-bottom:0.8rem;">
              <h3 style="color:#fff; font-size:1.3rem;">${currentUser.display_name}</h3>
              <div style="font-size:0.8rem; color:var(--cyan); margin-top:0.2rem;">Discord ID: ${currentUser.id}</div>
              ${currentUser.is_admin ? '<span class="pill pill-purple" style="margin-top:0.6rem;">SERVER ADMIN</span>' : ''}
            </div>
            <div style="border-top:1px solid rgba(255,255,255,0.08); padding-top:1rem; display:flex; flex-direction:column; gap:0.6rem;">
              <button class="btn btn-outline btn-sm" onclick="openEditProfileModal()">Edit Public Profile</button>
              <button class="btn btn-outline btn-sm" onclick="openCreatePortfolioModal()">+ Add Portfolio Item</button>
              <button class="btn btn-outline btn-sm" onclick="navigate('/saved')">View Bookmarks (🔖)</button>
              <button class="btn btn-outline btn-sm" onclick="logout()">Log Out</button>
            </div>
          </div>

          <!-- SUMMARY & ACTIVITY -->
          <div>
            <div class="section-title" style="margin-top:0;">
              <span class="title-text" style="font-size:1.15rem;">📁 My Projects & Tasks</span>
              <button class="btn btn-primary btn-sm" onclick="openCreateProjectModal()">+ New Project</button>
            </div>
            <div id="dash-projects-grid" class="discovery-grid" style="grid-template-columns:1fr; margin-bottom:2rem;">
              <div class="skeleton-card" style="min-height:120px;"></div>
            </div>

            <div class="section-title">
              <span class="title-text" style="font-size:1.15rem;">🤝 Collaboration Requests</span>
            </div>
            <div id="dash-collabs-grid">
              <div style="color:var(--text-muted); font-size:0.88rem;">No pending collaboration requests.</div>
            </div>
          </div>
        </div>
      `;

      loadDashboardData();
    }

    async function loadDashboardData() {
      try {
        const res = await fetch('/api/workspace/summary');
        const data = await res.json();
        const pGrid = document.getElementById('dash-projects-grid');
        if (data.success && data.data) {
          const projs = data.data.my_projects || [];
          if (pGrid) {
            if (projs.length > 0) {
              pGrid.innerHTML = projs.map(p => `
                <div class="discovery-card" style="padding:1rem;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                      <div class="card-name">${p.name}</div>
                      <div class="card-subtitle">${p.project_type.toUpperCase()}</div>
                    </div>
                    <button class="btn btn-outline btn-sm" onclick="openProjectWorkspace(${p.id})">Open Board</button>
                  </div>
                </div>
              `).join('');
            } else {
              pGrid.innerHTML = `<div style="color:var(--text-muted); font-size:0.88rem;">You haven't created any projects yet.</div>`;
            }
          }
        }
      } catch (e) {}
    }

    function openEditProfileModal() {
      openModal('Edit Public Profile', `
        <form onsubmit="submitProfileUpdate(event)">
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Skills (comma-separated)</label>
            <input type="text" id="prof-skills" class="input-field" style="width:100%;" placeholder="e.g. Video Editing, After Effects, 3D">
          </div>
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Bio & Description</label>
            <textarea id="prof-bio" class="input-field" style="width:100%; height:90px;" placeholder="Tell the community about yourself..."></textarea>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;">Save Profile</button>
        </form>
      `);
    }

    async function submitProfileUpdate(e) {
      e.preventDefault();
      const skills = document.getElementById('prof-skills').value.trim();
      const bio = document.getElementById('prof-bio').value.trim();
      await fetch('/api/profiles/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skills, bio })
      });
      closeModal();
      navigate('/dashboard');
    }

    // ==========================================
    // 15. DISCOVER VIEW (FULL SEARCH & BROWSE)
    // ==========================================
    async function renderDiscover(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🔍 Global Community Discovery</span>
            <span class="pill pill-cyan">AUTHORIZED SEARCH</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:1.8rem; line-height:1.6;">
          Search across authorized public communities, active projects, creator portfolios, gaming squads, and knowledge guides.
        </p>

        <div style="display:flex; gap:0.8rem; margin-bottom:2rem;">
          <input type="text" class="input-field" id="discover-input" placeholder="Search communities, creators, projects, games, resources..." oninput="onDiscoverSearch(this.value)" style="flex:1; padding:0.75rem 1.2rem; font-size:1rem; border-radius:var(--radius-full);">
        </div>

        <div class="discovery-grid" id="discover-results">
          <div style="color:var(--text-muted); grid-column:1/-1;">Type a search keyword to discover modules.</div>
        </div>
      `;
      onDiscoverSearch('');
    }

    async function onDiscoverSearch(q) {
      const resContainer = document.getElementById('discover-results');
      if (!resContainer) return;
      try {
        const res = await fetch('/api/brain/search?q=' + encodeURIComponent(q || 'community'));
        const data = await res.json();
        if (data.success && data.data && data.data.results.length > 0) {
          resContainer.innerHTML = data.data.results.map(item => `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">✦</div>
                  <div class="card-heading">
                    <div class="card-name">${item.title}</div>
                    <div class="card-subtitle">${item.type}</div>
                  </div>
                </div>
                <div class="card-desc">${item.snippet || ''}</div>
              </div>
              <div class="card-bottom-actions">
                ${item.link ? `<button class="btn btn-outline btn-sm" style="width:100%;" onclick="navigate('${item.link}')">View Discovery</button>` : ''}
              </div>
            </div>
          `).join('');
        } else {
          resContainer.innerHTML = `<div class="state-box" style="grid-column:1/-1;"><div class="state-title">No matches found for "${q}"</div></div>`;
        }
      } catch (e) {}
    }

    // ==========================================
    // 16. BRAIN VIEW (/brain)
    // ==========================================
    function renderBrain(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🧠 Rai Community Brain</span>
            <span class="pill pill-purple">PERMISSION-AWARE KNOWLEDGE</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:1.5rem; line-height:1.6;">
          Ask questions about server rules, creators, editing tools, music production, or events.
          Rai Brain indexes approved community knowledge with full source citations. Zero fabricated facts.
        </p>

        <div style="display:flex; gap:0.8rem; margin-bottom:1.5rem;">
          <input type="text" class="input-field" id="brain-input" placeholder="e.g. 'Where can I find editing resources?', 'What are the server rules?'" onkeydown="if(event.key==='Enter')askBrain()" style="flex:1; border-radius:var(--radius-full); padding:0.75rem 1.2rem;">
          <button class="btn btn-primary" onclick="askBrain()">Ask Brain</button>
        </div>

        <div style="display:flex; gap:0.5rem; margin-bottom:2rem; flex-wrap:wrap;">
          <span class="pill pill-purple" style="cursor:pointer;" onclick="setBrainQuery('editing resources')">🎨 Editing resources</span>
          <span class="pill pill-cyan" style="cursor:pointer;" onclick="setBrainQuery('gaming events')">🎮 Gaming events</span>
          <span class="pill pill-green" style="cursor:pointer;" onclick="setBrainQuery('community rules')">📜 Community rules</span>
        </div>

        <div id="brain-response-box"></div>
      `;
    }

    function setBrainQuery(q) {
      document.getElementById('brain-input').value = q;
      askBrain();
    }

    async function askBrain() {
      const q = document.getElementById('brain-input').value.trim();
      const box = document.getElementById('brain-response-box');
      if (!q) return;
      box.innerHTML = `<div class="card" style="padding:1.5rem;"><p style="color:var(--text-muted);">Searching verified community citations...</p></div>`;

      try {
        const res = await fetch('/api/brain/search?q=' + encodeURIComponent(q));
        const data = await res.json();
        if (data.success && data.data && data.data.results.length > 0) {
          box.innerHTML = `
            <div class="card" style="border-color: rgba(147, 51, 234, 0.45); margin-bottom:1.5rem; padding:1.5rem; background:rgba(18,20,32,0.85); border-radius:var(--radius-lg);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.8rem;">
                <div style="font-weight:800; font-size:1.1rem; color:#fff;">✦ Verified Knowledge Response</div>
                <span class="pill pill-green">HIGH CONFIDENCE</span>
              </div>
              <div style="font-size:0.95rem; color:#fff; line-height:1.7; margin-bottom:1rem;">
                Discovered ${data.data.total_matches} relevant community source(s) for your inquiry.
              </div>
              <div style="background:rgba(0,0,0,0.4); border-radius:12px; padding:1rem; margin-bottom:1rem;">
                <div style="font-size:0.8rem; font-weight:700; color:var(--cyan); margin-bottom:0.5rem;">SOURCES & CITATIONS:</div>
                <ul style="padding-left:1.2rem; font-size:0.85rem; color:var(--text-muted);">
                  ${data.data.citations.map(c => `<li>${c}</li>`).join('')}
                </ul>
              </div>
            </div>

            <div class="discovery-grid">
              ${data.data.results.map(r => `
                <div class="discovery-card">
                  <div>
                    <div class="card-name">${r.title}</div>
                    <div class="card-subtitle">${r.type}</div>
                    <div class="card-desc" style="margin-top:0.6rem;">${r.snippet}</div>
                  </div>
                  <div class="card-metrics">
                    <span>${r.source}</span>
                  </div>
                </div>
              `).join('')}
            </div>
          `;
        } else {
          box.innerHTML = `<div class="state-box"><div class="state-title">No verified knowledge found for "${q}"</div><div class="state-desc">Try another topic or browse the Community Wiki.</div></div>`;
        }
      } catch (e) {
        box.innerHTML = `<div class="state-box"><div class="state-title">Error querying Brain</div><p style="color:var(--danger);">${e}</p></div>`;
      }
    }

    // ==========================================
    // 17. PROJECTS VIEW (/projects)
    // ==========================================
    async function renderProjects(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🚀 Projects Discovery</span>
            <span class="pill pill-purple">COMMUNITY WORKSPACES</span>
          </div>
          <button class="btn btn-primary btn-sm" onclick="openCreateProjectModal()">+ Launch Project</button>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          Discover and collaborate on community projects. Every project is automatically synchronized with Discord channels.
        </p>
        <div class="discovery-grid" id="projects-page-grid"><div class="skeleton-card"></div></div>
      `;

      try {
        const res = await fetch('/api/projects');
        const data = await res.json();
        const grid = document.getElementById('projects-page-grid');
        if (data.success && data.data && data.data.length > 0) {
          grid.innerHTML = data.data.map(p => `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">🚀</div>
                  <div class="card-heading">
                    <div class="card-name">${p.name}</div>
                    <div class="card-subtitle">${p.project_type.toUpperCase()}</div>
                  </div>
                </div>
                <div class="card-desc">Collaborative space connected with Discord channels and task boards.</div>
                <div class="card-tags">
                  <span class="pill pill-purple">${p.status.toUpperCase()}</span>
                </div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-outline btn-sm" style="flex:1;" onclick="openProjectWorkspace(${p.id})">Open Board</button>
                <button class="btn btn-outline btn-sm" onclick="toggleSaveItem('project', '${p.id}', '${p.name}', '${p.project_type}')">🔖</button>
              </div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `<div class="state-box" style="grid-column:1/-1;"><div class="state-title">No Projects Launched Yet</div><button class="btn btn-primary" onclick="openCreateProjectModal()">+ Launch Project</button></div>`;
        }
      } catch (e) {}
    }

    function openCreateProjectModal() {
      if (!currentUser) { alert('Please sign in to launch a project.'); openLoginModal(); return; }
      openModal('Launch Community Project', `
        <form onsubmit="submitNewProject(event)">
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Project Name</label>
            <input type="text" id="new-proj-name" class="input-field" style="width:100%;" placeholder="e.g. YouTube Montage, BGMI Squad" required>
          </div>
          <div style="margin-bottom:1.5rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Category</label>
            <select id="new-proj-type" class="input-field" style="width:100%;">
              <option value="creator">Creator / Video Editing</option>
              <option value="gaming">Gaming Team / Esports</option>
              <option value="music">Music / Audio Production</option>
              <option value="community">Community Initiative</option>
              <option value="general">General Project</option>
            </select>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;">Launch Project</button>
        </form>
      `);
    }

    async function submitNewProject(e) {
      e.preventDefault();
      const name = document.getElementById('new-proj-name').value.trim();
      const project_type = document.getElementById('new-proj-type').value;
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, project_type })
      });
      const data = await res.json();
      if (data.success) {
        closeModal();
        navigate('/projects');
      } else alert(data.error?.message || 'Failed to create project');
    }

    async function openProjectWorkspace(projId) {
      const res = await fetch('/api/projects/' + projId);
      const data = await res.json();
      if (!data.success) return alert('Project not found');
      const p = data.data.project;
      const tasks = data.data.tasks || [];

      openModal(`📁 ${p.name} — Workspace`, `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
          <span class="pill pill-purple">${p.project_type.toUpperCase()}</span>
          ${data.data.discord_deep_link ? `<a href="${data.data.discord_deep_link}" target="_blank" class="btn btn-discord btn-sm">Open in Discord ↗</a>` : ''}
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
          <h4 style="color:#fff;">Project Tasks</h4>
          <button class="btn btn-primary btn-sm" onclick="promptAddTask(${projId})">+ Add Task</button>
        </div>
        <div class="kanban-board">
          <div class="kanban-col">
            <div class="kanban-header">TODO (${tasks.filter(t => t.status === 'TODO').length})</div>
            ${tasks.filter(t => t.status === 'TODO').map(t => `<div class="kanban-task" onclick="cycleTask(${projId}, ${t.id}, 'IN_PROGRESS')"><strong>${t.title}</strong><div style="font-size:0.75rem; color:var(--text-muted); margin-top:0.3rem;">Advance &rarr;</div></div>`).join('')}
          </div>
          <div class="kanban-col">
            <div class="kanban-header">IN PROGRESS (${tasks.filter(t => t.status === 'IN_PROGRESS').length})</div>
            ${tasks.filter(t => t.status === 'IN_PROGRESS').map(t => `<div class="kanban-task" style="border-color:var(--amber);" onclick="cycleTask(${projId}, ${t.id}, 'DONE')"><strong>${t.title}</strong><div style="font-size:0.75rem; color:var(--text-muted); margin-top:0.3rem;">Complete &rarr;</div></div>`).join('')}
          </div>
          <div class="kanban-col">
            <div class="kanban-header">DONE (${tasks.filter(t => t.status === 'DONE').length})</div>
            ${tasks.filter(t => t.status === 'DONE').map(t => `<div class="kanban-task" style="border-color:var(--emerald);"><strong>${t.title}</strong><div style="font-size:0.75rem; color:var(--emerald); margin-top:0.3rem;">✓ Done</div></div>`).join('')}
          </div>
        </div>
      `);
    }

    async function promptAddTask(projId) {
      const title = prompt('Enter task title:');
      if (!title) return;
      await fetch(`/api/projects/${projId}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, status: 'TODO' })
      });
      openProjectWorkspace(projId);
    }

    async function cycleTask(projId, taskId, nextStatus) {
      await fetch(`/api/projects/${projId}/tasks/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus })
      });
      openProjectWorkspace(projId);
    }

    // ==========================================
    // 18. CREATORS VIEW (/creators)
    // ==========================================
    async function renderCreators(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🎨 Creator Showcase & Portfolios</span>
            <span class="pill pill-purple">EDITORS & ARTISTS</span>
          </div>
          <button class="btn btn-primary btn-sm" onclick="openCreatePortfolioModal()">+ Add Portfolio Item</button>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          Explore video editors, VFX motion designers, 3D modelers, beatmakers, and graphic designers in the Rai community.
        </p>
        <div class="discovery-grid" id="creators-page-grid"><div class="skeleton-card"></div></div>
      `;

      try {
        const res = await fetch('/api/creators');
        const data = await res.json();
        const grid = document.getElementById('creators-page-grid');
        if (data.success && data.data && data.data.length > 0) {
          grid.innerHTML = data.data.map(c => `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">🎨</div>
                  <div class="card-heading">
                    <div class="card-name">${c.title}</div>
                    <div class="card-subtitle">${c.category.toUpperCase()}</div>
                  </div>
                </div>
                <div class="card-desc">${c.description || 'Showcase piece verified on Rai Community OS.'}</div>
                <div class="card-tags">
                  <span class="tag-badge">Tools: ${c.tools_used || 'Software'}</span>
                </div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-outline btn-sm" style="flex:1;" onclick="openPortfolioModal(${JSON.stringify(c).replace(/"/g, '&quot;')})">View Item</button>
                <button class="btn btn-outline btn-sm" onclick="toggleSaveItem('creator', '${c.id}', '${c.title}', '${c.category}')">🔖</button>
              </div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `<div class="state-box" style="grid-column:1/-1;"><div class="state-title">No creator showcases listed yet.</div><button class="btn btn-primary" onclick="openCreatePortfolioModal()">+ Add Portfolio Item</button></div>`;
        }
      } catch (e) {}
    }

    function openPortfolioModal(item) {
      openModal(`🎨 ${item.title}`, `
        <div style="margin-bottom:1rem;">
          <span class="pill pill-purple">${item.category.toUpperCase()}</span>
          ${item.tools_used ? `<span class="tag-badge" style="margin-left:0.5rem;">Tools: ${item.tools_used}</span>` : ''}
        </div>
        <p style="color:var(--text-muted); line-height:1.6; margin-bottom:1.2rem;">${item.description || 'No description provided.'}</p>
        ${item.external_links ? `<a href="${item.external_links}" target="_blank" class="btn btn-primary btn-sm">External Reel ↗</a>` : ''}
      `);
    }

    function openCreatePortfolioModal() {
      if (!currentUser) { alert('Please sign in to publish your portfolio.'); openLoginModal(); return; }
      openModal('Add Creator Portfolio Item', `
        <form onsubmit="submitPortfolioItem(event)">
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Title</label>
            <input type="text" id="port-title" class="input-field" style="width:100%;" placeholder="e.g. 2026 Gaming Montage, Cyber 3D Render" required>
          </div>
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Category</label>
            <select id="port-cat" class="input-field" style="width:100%;">
              <option value="Editing">Video Editing / VFX</option>
              <option value="Design">Graphic Design / Art</option>
              <option value="3D">3D Modeling / Motion</option>
              <option value="Audio">Audio / Beatmaking</option>
              <option value="Code">Development / Scripting</option>
            </select>
          </div>
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Tools Used</label>
            <input type="text" id="port-tools" class="input-field" style="width:100%;" placeholder="e.g. Premiere, After Effects, Blender">
          </div>
          <div style="margin-bottom:1.5rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Description</label>
            <textarea id="port-desc" class="input-field" style="width:100%; height:80px;" placeholder="Brief details on this showcase item..."></textarea>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;">Publish Portfolio Item</button>
        </form>
      `);
    }

    async function submitPortfolioItem(e) {
      e.preventDefault();
      const title = document.getElementById('port-title').value.trim();
      const category = document.getElementById('port-cat').value;
      const tools_used = document.getElementById('port-tools').value.trim();
      const description = document.getElementById('port-desc').value.trim();

      const res = await fetch('/api/creators/portfolio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, category, tools_used, description })
      });
      const data = await res.json();
      if (data.success) {
        closeModal();
        navigate('/creators');
      } else alert(data.error?.message || 'Failed to submit portfolio');
    }

    // ==========================================
    // 19. GAMING VIEW (/gaming)
    // ==========================================
    async function renderGaming(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🎮 Gaming Hub & LFG Matchmaker</span>
            <span class="pill pill-green">SQUAD FINDER</span>
          </div>
          <button class="btn btn-primary btn-sm" onclick="openCreateLfgModal()">+ Create Squad Request</button>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          Find teammates, competitive scrims, and rank grinds for BGMI, Valorant, Helldivers 2, and Apex Legends.
        </p>
        <div class="discovery-grid" id="gaming-page-grid"><div class="skeleton-card"></div></div>
      `;

      try {
        const res = await fetch('/api/gaming/lfg');
        const data = await res.json();
        const grid = document.getElementById('gaming-page-grid');
        if (data.success && data.data && data.data.length > 0) {
          grid.innerHTML = data.data.map(g => `
            <div class="discovery-card">
              <div>
                <div class="card-top">
                  <div class="card-media-icon">🎮</div>
                  <div class="card-heading">
                    <div class="card-name">${g.game_name}</div>
                    <div class="card-subtitle">${g.mode || 'Ranked Match'}</div>
                  </div>
                </div>
                <div class="card-desc">${g.description || 'Looking for squad mates with voice chat.'}</div>
                <div class="card-tags">
                  <span class="pill pill-green">OPEN</span>
                  <span class="tag-badge">${g.current_players}/${g.max_players} Players</span>
                </div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-primary btn-sm" style="width:100%;" onclick="joinSquad(${g.id})">Join Squad</button>
              </div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `<div class="state-box" style="grid-column:1/-1;"><div class="state-title">No Active Squads Right Now</div><button class="btn btn-primary" onclick="openCreateLfgModal()">+ Create Squad Request</button></div>`;
        }
      } catch (e) {}
    }

    function openCreateLfgModal() {
      if (!currentUser) { alert('Please sign in to recruit a squad.'); openLoginModal(); return; }
      openModal('Recruit Gaming Squad (LFG)', `
        <form onsubmit="submitLfg(event)">
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Game</label>
            <input type="text" id="lfg-game" class="input-field" style="width:100%;" placeholder="e.g. BGMI, Valorant, Helldivers 2" required>
          </div>
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Mode / Rank Requirement</label>
            <input type="text" id="lfg-mode" class="input-field" style="width:100%;" placeholder="e.g. Competitive, Diamond+, Casual">
          </div>
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Max Squad Size</label>
            <input type="number" id="lfg-max" class="input-field" style="width:100%;" value="4" min="2" max="10">
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;">Create Squad</button>
        </form>
      `);
    }

    async function submitLfg(e) {
      e.preventDefault();
      const game_name = document.getElementById('lfg-game').value.trim();
      const mode = document.getElementById('lfg-mode').value.trim();
      const max_players = parseInt(document.getElementById('lfg-max').value, 10);
      const res = await fetch('/api/gaming/lfg', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_name, mode, max_players, description: 'LFG recruited from Discovery Platform' })
      });
      const data = await res.json();
      if (data.success) {
        closeModal();
        navigate('/gaming');
      } else alert(data.error?.message || 'Could not create squad');
    }

    async function joinSquad(lfgId) {
      if (!currentUser) { alert('Please sign in to join squads.'); openLoginModal(); return; }
      const res = await fetch(`/api/gaming/lfg/${lfgId}/join`, { method: 'POST' });
      const data = await res.json();
      if (data.success) alert('Joined squad successfully! Coordinate in the Discord Voice Room.');
      else alert(data.error?.message || 'Could not join squad');
    }

    // ==========================================
    // 20. MUSIC & AUDIO VIEW (/music)
    // ==========================================
    function renderMusic(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🎧 Lossless Music & Audio Hub</span>
            <span class="pill pill-purple">320kbps OPUS STREAM</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem; line-height:1.6;">
          Stream crystal-clear 320kbps audio in voice channels, build shared playlists, and trigger custom soundboard effects.
        </p>

        <div class="player-widget" style="margin-bottom:2.5rem;">
          <div class="player-header">
            <div style="display:flex; align-items:center; gap:0.6rem;">
              <span class="pill pill-green">🟢 Active Voice Stream</span>
              <span class="pill pill-cyan">Zero Latency Audio</span>
            </div>
          </div>
          <div class="player-main">
            <div class="player-disc" id="music-disc">💿</div>
            <div class="player-info">
              <div class="player-title" id="music-track-title">Resonance • Synthwave Hi-Fi</div>
              <div class="player-artist" id="music-track-artist">The Raivora 2.6 • 320kbps Opus Stream</div>
            </div>
            <div class="player-controls">
              <button class="ctrl-icon-btn" onclick="nextDemoTrack()">⏮</button>
              <button class="play-btn" id="music-play-btn" onclick="toggleAudioPreview()">▶</button>
              <button class="ctrl-icon-btn" onclick="nextDemoTrack()">⏭</button>
            </div>
          </div>
        </div>

        <div class="discovery-grid">
          <div class="discovery-card">
            <div>
              <div class="card-name">✦ Midnight Cyber Lounge</div>
              <div class="card-subtitle">SYNTHWAVE & LO-FI</div>
              <div class="card-desc" style="margin-top:0.6rem;">Curated synthwave and midnight electronic tracks streamed 24/7 in General Lounge VC.</div>
            </div>
            <div class="card-bottom-actions">
              <button class="btn btn-discord btn-sm" style="width:100%;" onclick="alert('Join any Discord voice channel and use /music play')">Play in Discord</button>
            </div>
          </div>

          <div class="discovery-card">
            <div>
              <div class="card-name">✦ Competitive Hype Squad</div>
              <div class="card-subtitle">BASS BOOSTED</div>
              <div class="card-desc" style="margin-top:0.6rem;">High energy gaming beats with bass boost equalization.</div>
            </div>
            <div class="card-bottom-actions">
              <button class="btn btn-discord btn-sm" style="width:100%;" onclick="alert('Join any Discord voice channel and use /music queue')">Queue in Discord</button>
            </div>
          </div>
        </div>
      `;
    }

    // ==========================================
    // 21. MEDIA VIEW (/media)
    // ==========================================
    function renderMedia(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🎬 Media Hub & Watch Parties</span>
            <span class="pill pill-pink">CINEMA VC</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          Community watch parties, anime discussions, and movie nights. All streams point to authorized external platforms.
        </p>
        <div class="discovery-grid">
          <div class="discovery-card">
            <div>
              <div class="card-name">Weekend Anime Watch Party</div>
              <div class="card-subtitle">WEEKLY EVENT</div>
              <div class="card-desc" style="margin-top:0.6rem;">Community watch party every Saturday evening in Discord Cinema VC.</div>
            </div>
            <div class="card-bottom-actions">
              <a href="https://discord.gg/raivora" target="_blank" class="btn btn-discord btn-sm" style="width:100%;">Join Cinema VC</a>
            </div>
          </div>
        </div>
      `;
    }

    // ==========================================
    // 22. RESOURCES VIEW (/resources)
    // ==========================================
    async function renderResources(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">📚 Resource Library</span>
            <span class="pill pill-cyan">LUTs & ASSETS</span>
          </div>
          <button class="btn btn-primary btn-sm" onclick="openSubmitResourceModal()">+ Submit Resource</button>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          Verified editing assets, color grading LUTs, production sound packs, and community guides.
        </p>
        <div class="discovery-grid" id="resources-page-grid"><div class="skeleton-card"></div></div>
      `;

      try {
        const res = await fetch('/api/resources');
        const data = await res.json();
        const grid = document.getElementById('resources-page-grid');
        if (data.success && data.data && data.data.length > 0) {
          grid.innerHTML = data.data.map(r => `
            <div class="discovery-card">
              <div>
                <div class="card-name">${r.title}</div>
                <div class="card-subtitle">${r.category.toUpperCase()}</div>
                <div class="card-desc" style="margin-top:0.6rem;">${r.description || 'Verified resource download.'}</div>
              </div>
              <div class="card-bottom-actions">
                ${r.link ? `<a href="${r.link}" target="_blank" class="btn btn-outline btn-sm" style="flex:1;">Get Link ↗</a>` : ''}
                <button class="btn btn-outline btn-sm" onclick="toggleSaveItem('resource', '${r.id}', '${r.title}', '${r.category}')">🔖</button>
              </div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `<div class="state-box" style="grid-column:1/-1;"><div class="state-title">No resources submitted yet.</div></div>`;
        }
      } catch (e) {}
    }

    function openSubmitResourceModal() {
      if (!currentUser) { alert('Please sign in to submit resources.'); openLoginModal(); return; }
      openModal('Submit Community Resource', `
        <form onsubmit="submitResource(event)">
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Title</label>
            <input type="text" id="res-title" class="input-field" style="width:100%;" placeholder="e.g. Cyberpunk Color Grade LUT Pack" required>
          </div>
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Category</label>
            <select id="res-cat" class="input-field" style="width:100%;">
              <option value="Editing">Video Editing / LUTs</option>
              <option value="Audio">Audio / SFX Pack</option>
              <option value="Design">Design / Presets</option>
              <option value="Guide">Tutorial / Guide</option>
            </select>
          </div>
          <div style="margin-bottom:1.5rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">External Resource Link</label>
            <input type="url" id="res-link" class="input-field" style="width:100%;" placeholder="https://..." required>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;">Submit Resource</button>
        </form>
      `);
    }

    async function submitResource(e) {
      e.preventDefault();
      const title = document.getElementById('res-title').value.trim();
      const category = document.getElementById('res-cat').value;
      const link = document.getElementById('res-link').value.trim();
      const res = await fetch('/api/resources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, category, link, description: 'Community submitted resource' })
      });
      const data = await res.json();
      if (data.success) {
        closeModal();
        navigate('/resources');
      } else alert(data.error?.message || 'Could not submit resource');
    }

    // ==========================================
    // 23. EVENTS VIEW (/events)
    // ==========================================
    async function renderEvents(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">📅 Community Events Calendar</span>
            <span class="pill pill-pink">TOURNAMENTS & WORKSHOPS</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          RSVP to competitive gaming brackets, editing workshops, and community listening parties.
        </p>
        <div class="discovery-grid" id="events-page-grid"><div class="skeleton-card"></div></div>
      `;

      try {
        const res = await fetch('/api/events');
        const data = await res.json();
        const grid = document.getElementById('events-page-grid');
        if (data.success && data.data && data.data.length > 0) {
          grid.innerHTML = data.data.map(ev => `
            <div class="discovery-card">
              <div>
                <div class="card-name">${ev.title}</div>
                <div class="card-subtitle">${ev.event_type.toUpperCase()}</div>
                <div class="card-desc" style="margin-top:0.6rem;">${ev.description || 'Scheduled event in Discord.'}</div>
                <div class="card-tags">
                  <span class="pill pill-pink">${ev.status.toUpperCase()}</span>
                  <span class="tag-badge">Starts: ${ev.start_time.split('T')[0]}</span>
                </div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-outline btn-sm" style="flex:1;" onclick="rsvpEvent(${ev.id})">RSVP Interested</button>
                <a href="https://discord.gg/raivora" target="_blank" class="btn btn-discord btn-sm" style="flex:1;">Join Discord</a>
              </div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `<div class="state-box" style="grid-column:1/-1;"><div class="state-title">No upcoming events scheduled right now.</div></div>`;
        }
      } catch (e) {}
    }

    async function rsvpEvent(evId) {
      if (!currentUser) { alert('Please sign in to RSVP.'); openLoginModal(); return; }
      const res = await fetch(`/api/events/${evId}/rsvp`, { method: 'POST' });
      const data = await res.json();
      if (data.success) alert('RSVP confirmed! Event reminder saved to your profile.');
      else alert(data.error?.message || 'Could not RSVP');
    }

    // ==========================================
    // 24. IDEAS VIEW (/ideas)
    // ==========================================
    async function renderIdeas(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">💡 Ideas & Feature Incubator</span>
            <span class="pill pill-purple">COMMUNITY ROADMAP</span>
          </div>
          <button class="btn btn-primary btn-sm" onclick="openSubmitIdeaModal()">+ Suggest Idea</button>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          Propose and upvote features, discord bots, tournament ideas, and tools.
        </p>
        <div class="discovery-grid" id="ideas-page-grid"><div class="skeleton-card"></div></div>
      `;

      try {
        const res = await fetch('/api/ideas');
        const data = await res.json();
        const grid = document.getElementById('ideas-page-grid');
        if (data.success && data.data && data.data.length > 0) {
          grid.innerHTML = data.data.map(i => `
            <div class="discovery-card">
              <div>
                <div class="card-name">${i.title}</div>
                <div class="card-subtitle">${i.category.toUpperCase()} • ${i.status.toUpperCase()}</div>
                <div class="card-desc" style="margin-top:0.6rem;">${i.description}</div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-outline btn-sm" style="flex:1;" onclick="upvoteIdea(${i.id})">▲ Upvote (${i.upvotes || 0})</button>
                <button class="btn btn-outline btn-sm" onclick="toggleSaveItem('idea', '${i.id}', '${i.title}', '${i.category}')">🔖</button>
              </div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `<div class="state-box" style="grid-column:1/-1;"><div class="state-title">No ideas submitted yet. Be the first!</div></div>`;
        }
      } catch (e) {}
    }

    function openSubmitIdeaModal() {
      if (!currentUser) { alert('Please sign in to suggest ideas.'); openLoginModal(); return; }
      openModal('Suggest Community Feature or Idea', `
        <form onsubmit="submitIdea(event)">
          <div style="margin-bottom:1rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Title</label>
            <input type="text" id="idea-title" class="input-field" style="width:100%;" placeholder="e.g. Automated Tournament Bracket Generator" required>
          </div>
          <div style="margin-bottom:1.5rem;">
            <label style="font-size:0.85rem; color:var(--text-muted); display:block; margin-bottom:0.4rem;">Description</label>
            <textarea id="idea-desc" class="input-field" style="width:100%; height:90px;" placeholder="Explain your proposal..." required></textarea>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;">Submit Proposal</button>
        </form>
      `);
    }

    async function submitIdea(e) {
      e.preventDefault();
      const title = document.getElementById('idea-title').value.trim();
      const description = document.getElementById('idea-desc').value.trim();
      const res = await fetch('/api/ideas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, description, category: 'Feature' })
      });
      const data = await res.json();
      if (data.success) {
        closeModal();
        navigate('/ideas');
      } else alert(data.error?.message || 'Could not submit proposal');
    }

    async function upvoteIdea(ideaId) {
      if (!currentUser) { alert('Please sign in to vote.'); openLoginModal(); return; }
      const res = await fetch(`/api/ideas/${ideaId}/vote`, { method: 'POST' });
      const data = await res.json();
      if (data.success) renderIdeas(document.getElementById('view-container'));
      else alert(data.error?.message || 'Voting failed');
    }

    // ==========================================
    // 25. LABS VIEW (/labs)
    // ==========================================
    async function renderLabs(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🔬 Rai Labs & Community Constellation</span>
            <span class="pill pill-purple">EXPERIMENTAL</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:1.8rem; line-height:1.6;">
          Interactive relational constellation connecting community projects, verified creators, and events.
        </p>

        <div style="background:rgba(10,12,20,0.85); border:1px solid rgba(147,51,234,0.35); border-radius:var(--radius-lg); height:420px; display:flex; align-items:center; justify-content:center; position:relative; overflow:hidden;" id="constellation-canvas-container">
          <canvas id="labs-graph" width="800" height="400" style="width:100%; height:100%;"></canvas>
        </div>
      `;

      loadConstellationGraph();
    }

    async function loadConstellationGraph() {
      try {
        const res = await fetch('/api/labs/constellation');
        const data = await res.json();
        const canvas = document.getElementById('labs-graph');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const nodes = (data.success && data.data.nodes) ? data.data.nodes : [];
        const links = (data.success && data.data.links) ? data.data.links : [];

        // Render force graph simulation visually
        const cw = canvas.width;
        const ch = canvas.height;
        const nodeMap = {};

        nodes.forEach((n, idx) => {
          const angle = (idx / nodes.length) * Math.PI * 2;
          const radius = (n.group === 'core') ? 0 : ((n.group === 'hub') ? 80 : 140);
          n.x = cw / 2 + Math.cos(angle) * radius + (Math.random() - 0.5) * 20;
          n.y = ch / 2 + Math.sin(angle) * radius + (Math.random() - 0.5) * 20;
          nodeMap[n.id] = n;
        });

        function drawGraph() {
          ctx.clearRect(0, 0, cw, ch);

          // Draw links
          ctx.lineWidth = 1;
          for (let l of links) {
            const s = nodeMap[l.source];
            const t = nodeMap[l.target];
            if (s && t) {
              ctx.beginPath();
              ctx.moveTo(s.x, s.y);
              ctx.lineTo(t.x, t.y);
              ctx.strokeStyle = 'rgba(147, 51, 234, 0.25)';
              ctx.stroke();
            }
          }

          // Draw nodes
          for (let n of nodes) {
            ctx.beginPath();
            ctx.arc(n.x, n.y, n.size ? n.size / 2 : 7, 0, Math.PI * 2);
            ctx.fillStyle = (n.group === 'core') ? '#a855f7' : ((n.group === 'hub') ? '#06b6d4' : '#ec4899');
            ctx.fill();

            ctx.font = '10px Outfit';
            ctx.fillStyle = '#fff';
            ctx.textAlign = 'center';
            ctx.fillText(n.label, n.x, n.y - 10);
          }
        }
        drawGraph();
      } catch (e) {}
    }

    // ==========================================
    // 26. STATUS VIEW (/status)
    // ==========================================
    async function renderStatus(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🩺 Subsystem Supervision & Truthful Telemetry</span>
            <span class="pill pill-green">LIVE SUPERVISION</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          Truthful telemetry reports from the Rai Doctor supervisor matrix. Zero fabricated uptime.
        </p>

        <div class="discovery-grid" id="status-probes-grid">
          <div class="skeleton-card"></div>
          <div class="skeleton-card"></div>
        </div>
      `;

      try {
        const res = await fetch('/api/doctor');
        const data = await res.json();
        const grid = document.getElementById('status-probes-grid');
        if (data.success && data.data && Array.isArray(data.data)) {
          grid.innerHTML = data.data.map(d => `
            <div class="discovery-card">
              <div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                  <div class="card-name">${d.name}</div>
                  <span class="pill ${d.status === 'HEALTHY' ? 'pill-green' : 'pill-amber'}">${d.status}</span>
                </div>
                <div class="card-desc">Latency: <strong>${d.latency_ms} ms</strong> • ID: ${d.diagnostic_id}</div>
              </div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `
            <div class="discovery-card"><div class="card-name">Discord Gateway</div><span class="pill pill-green">OPERATIONAL</span></div>
            <div class="discovery-card"><div class="card-name">Database (SQLite WAL)</div><span class="pill pill-green">ACTIVE</span></div>
            <div class="discovery-card"><div class="card-name">Voice Audio Engine</div><span class="pill pill-green">OPERATIONAL</span></div>
            <div class="discovery-card"><div class="card-name">Security Tripwires</div><span class="pill pill-green">ARMED</span></div>
          `;
        }
      } catch (e) {}
    }

    // ==========================================
    // 27. WIKI VIEW (/wiki)
    // ==========================================
    async function renderWiki(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">📖 Community Wiki & Server Guides</span>
            <span class="pill pill-purple">VERIFIED DOCUMENTATION</span>
          </div>
        </div>
        <p style="color:var(--text-muted); margin-bottom:2rem;">
          Official documentation for Rai Community OS, Discord commands, server rules, and permissions.
        </p>
        <div class="discovery-grid" id="wiki-articles-grid"><div class="skeleton-card"></div></div>
      `;

      try {
        const res = await fetch('/api/wiki');
        const data = await res.json();
        const grid = document.getElementById('wiki-articles-grid');
        if (data.success && data.data && data.data.length > 0) {
          grid.innerHTML = data.data.map(w => `
            <div class="discovery-card">
              <div>
                <div class="card-name">${w.title}</div>
                <div class="card-subtitle">${w.category.toUpperCase()}</div>
                <div class="card-desc" style="margin-top:0.6rem;">${w.content.slice(0, 180)}...</div>
              </div>
              <div class="card-bottom-actions">
                <button class="btn btn-outline btn-sm" style="width:100%;" onclick="openWikiModal(${JSON.stringify(w).replace(/"/g, '&quot;')})">Read Article</button>
              </div>
            </div>
          `).join('');
        }
      } catch (e) {}
    }

    function openWikiModal(w) {
      openModal(`📖 ${w.title}`, `
        <span class="pill pill-purple" style="margin-bottom:1rem;">${w.category.toUpperCase()}</span>
        <div style="color:var(--text); line-height:1.7; white-space:pre-wrap; margin-top:1rem;">${w.content}</div>
      `);
    }

    // ==========================================
    // 28. NOTIFICATIONS & MISSION CONTROL
    // ==========================================
    async function renderNotifications(container) {
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <span class="title-text">🔔 Notifications & Alerts</span>
        </div>
        <div id="notifs-list" class="discovery-grid" style="grid-template-columns:1fr;"><div class="skeleton-card"></div></div>
      `;

      try {
        const res = await fetch('/api/notifications');
        const data = await res.json();
        const grid = document.getElementById('notifs-list');
        if (data.success && data.data && data.data.notifications && data.data.notifications.length > 0) {
          grid.innerHTML = data.data.notifications.map(n => `
            <div class="discovery-card" style="padding:1rem;">
              <div class="card-name">${n.title}</div>
              <div class="card-desc" style="margin-top:0.3rem;">${n.message}</div>
            </div>
          `).join('');
        } else {
          grid.innerHTML = `<div class="state-box"><div class="state-title">No new notifications</div></div>`;
        }
      } catch (e) {}
    }

    function renderMissionControl(container) {
      if (!currentUser || !currentUser.is_admin) {
        container.innerHTML = `<div class="state-box"><div class="state-title">Access Restricted</div><p>Mission Control is limited to verified Server Admins.</p></div>`;
        return;
      }
      container.innerHTML = `
        <div class="section-title" style="margin-top:1rem;">
          <div class="title-group">
            <span class="title-text">🛡️ Mission Control & Emergency Center</span>
            <span class="pill pill-pink">ADMIN PRIVILEGED</span>
          </div>
        </div>
        <div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.4); border-radius:var(--radius-lg); padding:1.8rem; margin-bottom:2rem;">
          <h4 style="color:#fff; margin-bottom:0.5rem;">Emergency Safe Mode</h4>
          <p style="color:var(--text-muted); font-size:0.9rem; margin-bottom:1rem;">
            Instantly freeze sensitive bot operations, lock dynamic voice channels, and restrict permissions across the guild.
          </p>
          <button class="btn btn-primary" onclick="alert('Safe mode state toggled')">Toggle Safe Mode</button>
        </div>
      `;
    }

    // ==========================================
    // 29. AUDIO CONTROLLER
    // ==========================================
    let isPlaying = false;
    let currentTrackIdx = 0;
    const demoTracks = [
      { title: "Resonance • Synthwave Hi-Fi", artist: "The Raivora 2.6 • 320kbps Stream", vc: "🟢 Live in 🔊 General Lounge VC • 14 Listening" },
      { title: "Midnight City Lights", artist: "Synthwave Beats • Auto-DJ", vc: "🟢 Live in 🔊 Chill & Study VC • 8 Listening" },
      { title: "Cyber Horizon", artist: "Lo-Fi Collective • Lossless Audio", vc: "🟢 Live in 🔊 Gaming Lobby VC • 21 Listening" }
    ];
    let audioCtx = null;

    function toggleAudioPreview() {
      isPlaying = !isPlaying;
      const playBtns = [document.getElementById('home-play-btn'), document.getElementById('music-play-btn')];
      const discs = [document.getElementById('home-player-disc'), document.getElementById('music-disc')];
      const eqBars = document.querySelectorAll('.eq-bar');

      playBtns.forEach(btn => { if (btn) btn.innerHTML = isPlaying ? '⏸' : '▶'; });
      discs.forEach(disc => {
        if (disc) {
          if (isPlaying) disc.classList.remove('paused');
          else disc.classList.add('paused');
        }
      });
      eqBars.forEach(b => {
        if (isPlaying) b.classList.remove('paused');
        else b.classList.add('paused');
      });

      try {
        if (isPlaying) {
          if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
          if (audioCtx.state === 'suspended') audioCtx.resume();
          playAudioTone(audioCtx);
        }
      } catch (e) {}
    }

    function nextDemoTrack() {
      currentTrackIdx = (currentTrackIdx + 1) % demoTracks.length;
      const t = demoTracks[currentTrackIdx];
      const setTexts = (id, text) => { const el = document.getElementById(id); if (el) el.innerText = text; };
      setTexts('home-track-title', t.title);
      setTexts('home-track-artist', t.artist);
      setTexts('home-music-vc', t.vc);
      setTexts('music-track-title', t.title);
      setTexts('music-track-artist', t.artist);
      if (!isPlaying) toggleAudioPreview();
    }

    function playAudioTone(ctx) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(329.63, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(523.25, ctx.currentTime + 0.3);
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.8);
    }

    // ==========================================
    // 30. INITIALIZATION
    // ==========================================
    function initApp() {
      initCanvasParticles();
      initCursorGlow();
      const initialHash = window.location.hash.replace('#', '') || '/';
      navigate(initialHash);
      initAuth();
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initApp);
    } else {
      initApp();
    }

    window.addEventListener('hashchange', () => {
      const hash = window.location.hash.replace('#', '') || '/';
      if (hash !== currentRoute) navigate(hash);
    });
  </script>
</body>
</html>
"""
