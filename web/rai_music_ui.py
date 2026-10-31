"""Rai Music Official Single-Page Platform."""

RAI_MUSIC_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>Rai Music — Your Server, Your Soundtrack</title>
  <link rel="icon" type="image/png" href="/icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    :root {
      --bg: #090810;
      --panel: #11101b;
      --panel-hover: #171524;
      --line: rgba(196, 178, 255, 0.11);
      --line-hover: rgba(196, 178, 255, 0.22);
      --muted: #89859e;
      --purple: #9b72ff;
      --purple-light: #b69bff;
      --purple-glow: rgba(155, 114, 255, 0.25);
      --green: #64dfa7;
      --green-glow: rgba(100, 223, 167, 0.35);
      font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      color: #f4f0ff;
      background: #090810;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(ellipse at 70% -20%, rgba(95, 47, 170, 0.15), transparent 45%), #090810;
      color: #f4f0ff;
      min-height: 100vh;
      overflow-x: hidden;
      -webkit-font-smoothing: antialiased;
    }
    button, input, select { font: inherit; }
    button { cursor: pointer; color: inherit; background: none; border: 0; }
    button:focus-visible, input:focus-visible, select:focus-visible {
      outline: 2px solid #a889ff;
      outline-offset: 2px;
    }

    /* Shell Layout */
    .shell { display: flex; min-height: 100vh; }
    
    /* Sidebar */
    .sidebar {
      position: fixed;
      inset: 0 auto 0 0;
      width: 252px;
      background: rgba(13, 12, 22, 0.97);
      border-right: 1px solid var(--line);
      padding: 24px 16px 16px;
      display: flex;
      flex-direction: column;
      z-index: 40;
      backdrop-filter: blur(20px);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 6px 24px;
    }
    .brand-mark {
      width: 40px;
      height: 40px;
      border-radius: 12px;
      background: linear-gradient(145deg, #a67cff, #6338d0);
      display: grid;
      place-items: center;
      box-shadow: 0 7px 25px rgba(124, 76, 228, 0.33);
      color: #fff;
    }
    .brand-name {
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 700;
      font-size: 16px;
      letter-spacing: 1.5px;
    }
    .brand-name span { color: #b69bff; }
    .brand-sub {
      font-size: 8.5px;
      letter-spacing: 1.4px;
      color: #716c85;
      margin-top: 3px;
      font-weight: 600;
    }
    .server-switch {
      height: 60px;
      background: #171523;
      border: 1px solid var(--line);
      border-radius: 12px;
      display: flex;
      align-items: center;
      padding: 9px 12px;
      gap: 10px;
      cursor: pointer;
      transition: border-color 0.2s;
    }
    .server-switch:hover { border-color: var(--line-hover); }
    .server-avatar {
      width: 36px;
      height: 36px;
      border-radius: 10px;
      background: linear-gradient(145deg, #8b64ed, #4d2b9d);
      display: grid;
      place-items: center;
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 700;
      font-size: 16px;
      color: #fff;
      overflow: hidden;
    }
    .server-avatar img { width: 100%; height: 100%; object-fit: cover; }
    .server-meta { display: flex; flex: 1; flex-direction: column; gap: 2px; min-width: 0; }
    .server-meta strong { font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .server-meta span { font-size: 10px; color: var(--muted); }

    .nav-groups { padding-top: 24px; display: flex; flex-direction: column; gap: 22px; flex: 1; }
    .nav-label { font-size: 9px; font-weight: 700; letter-spacing: 1.6px; color: #827c98; padding: 0 10px 8px; }
    .nav-item {
      height: 40px;
      width: 100%;
      border-radius: 10px;
      color: #9b96ad;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 12px;
      font-size: 12.5px;
      font-weight: 500;
      transition: all 0.2s;
      margin-bottom: 2px;
    }
    .nav-item:hover { background: rgba(255, 255, 255, 0.05); color: #fff; }
    .nav-item.active {
      background: linear-gradient(90deg, rgba(116, 73, 216, 0.2), rgba(116, 73, 216, 0.05));
      color: #c5b0ff;
      box-shadow: inset 2.5px 0 #a987ff;
      font-weight: 600;
    }
    .nav-live-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--green);
      margin-left: auto;
      box-shadow: 0 0 10px var(--green);
    }
    .sidebar-bottom { margin-top: auto; display: flex; flex-direction: column; gap: 14px; }
    .rem-card {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 12px 10px;
      background: linear-gradient(120deg, #25183e, #171323);
      border: 1px solid rgba(164, 122, 255, 0.18);
      border-radius: 12px;
    }
    .rem-orb {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: rgba(155, 114, 255, 0.16);
      color: #c6aaff;
      display: grid;
      place-items: center;
    }
    .rem-card-text { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
    .rem-card-text strong { font-size: 11px; }
    .rem-card-text span { font-size: 9px; color: #a69dbb; }

    /* Main Content Area */
    .main {
      margin-left: 252px;
      flex: 1;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      padding-bottom: 80px;
    }
    .topbar {
      height: 72px;
      position: sticky;
      top: 0;
      z-index: 30;
      background: rgba(9, 8, 16, 0.85);
      backdrop-filter: blur(18px);
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 36px;
    }
    .top-left { display: flex; align-items: center; gap: 14px; }
    .breadcrumbs { display: flex; align-items: center; gap: 8px; color: #77728c; font-size: 11.5px; }
    .breadcrumbs strong { color: #e9e2fa; font-weight: 600; }
    .top-actions { display: flex; align-items: center; gap: 16px; }
    .searchbox {
      width: 230px;
      height: 36px;
      border: 1px solid var(--line);
      background: #14121e;
      border-radius: 9px;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 10px;
      color: #8b859f;
    }
    .searchbox input {
      flex: 1;
      background: none;
      border: 0;
      color: #fff;
      font-size: 11px;
    }
    .searchbox kbd {
      font-size: 9px;
      color: #77718a;
      border: 1px solid #373246;
      border-radius: 4px;
      padding: 2px 4px;
    }
    .preview-pill {
      font-size: 8.5px;
      letter-spacing: 1px;
      color: #c5aaff;
      background: rgba(155, 114, 255, 0.1);
      border: 1px solid rgba(155, 114, 255, 0.25);
      border-radius: 20px;
      padding: 6px 10px;
      display: flex;
      align-items: center;
      gap: 6px;
      font-weight: 600;
    }
    .preview-pill span {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #b38bff;
    }
    .connected-user {
      display: flex;
      align-items: center;
      gap: 10px;
      background: #151322;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 5px 10px;
    }
    .connected-user img { width: 24px; height: 24px; border-radius: 50%; object-fit: cover; }
    .connected-user span { font-size: 11px; font-weight: 600; }
    .connected-user a { font-size: 10px; color: #8e87a2; text-decoration: none; margin-left: 4px; }
    .connected-user a:hover { color: #f4f0ff; }
    .connect-button {
      background: linear-gradient(120deg, #a17aff, #784ce2);
      color: #fff;
      font-size: 11px;
      font-weight: 600;
      padding: 8px 14px;
      border-radius: 9px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
      box-shadow: 0 4px 16px rgba(117, 69, 220, 0.3);
    }

    /* Page Content */
    .page-content {
      max-width: 1460px;
      width: 100%;
      margin: 0 auto;
      padding: 30px 36px;
      flex: 1;
    }
    .page-heading {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 24px;
    }
    .eyebrow {
      font-size: 9.5px;
      font-weight: 700;
      letter-spacing: 1.6px;
      color: #827c98;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .page-heading h1 {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 28px;
      font-weight: 600;
      letter-spacing: -0.8px;
      margin: 4px 0;
    }
    .page-heading p { color: #9690a8; font-size: 11.5px; }

    /* Connection & Health Row */
    .connection-panel {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 22px;
    }
    .connection-card {
      background: linear-gradient(145deg, #13111f, #0f0e18);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px 20px;
    }
    .connection-card-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      margin-bottom: 14px;
    }
    .connection-card-top h3 {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 16px;
      font-weight: 600;
      margin-top: 2px;
    }
    .connection-state {
      font-size: 9px;
      letter-spacing: 1px;
      padding: 5px 9px;
      border-radius: 6px;
      background: rgba(100, 223, 167, 0.12);
      color: #64dfa7;
      border: 1px solid rgba(100, 223, 167, 0.28);
      font-weight: 600;
    }
    .connection-identity {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
    }
    .connection-identity img { width: 38px; height: 38px; border-radius: 50%; }
    .connection-identity strong { font-size: 13px; display: block; }
    .connection-identity span { font-size: 10px; color: var(--muted); }
    .guild-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
    .guild-chip {
      background: #191727;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 4px 8px;
      font-size: 9.5px;
      color: #c9c3dd;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .guild-chip img { width: 14px; height: 14px; border-radius: 4px; }
    .connection-footnote { font-size: 8.5px; color: #6e6881; margin-top: 8px; }
    .bot-health-line { display: flex; align-items: center; gap: 8px; margin: 12px 0; }
    .bot-health-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 10px var(--green);
    }
    .bot-health-details {
      display: grid;
      grid-template-columns: auto 1fr auto 1fr;
      gap: 8px 14px;
      font-size: 10.5px;
      padding: 10px;
      background: #161423;
      border-radius: 9px;
      margin-bottom: 8px;
    }
    .bot-health-details span { color: var(--muted); }
    .bot-health-details strong { font-family: 'Space Grotesk', sans-serif; }

    /* Hero Panel with Vinyl Animation */
    .hero-panel {
      height: 280px;
      position: relative;
      overflow: hidden;
      border-radius: 18px;
      border: 1px solid rgba(167, 131, 255, 0.2);
      background: linear-gradient(105deg, #1a1430 0%, #171127 47%, #24153d 100%);
      padding: 30px 34px;
      margin-bottom: 20px;
    }
    .hero-glow {
      position: absolute;
      width: 450px;
      height: 300px;
      right: 8%;
      top: -100px;
      background: radial-gradient(ellipse, rgba(130, 84, 215, 0.25), transparent 68%);
      pointer-events: none;
    }
    .hero-copy { position: relative; z-index: 2; }
    .hero-tag {
      font-size: 8.5px;
      letter-spacing: 1.8px;
      color: #c5b1f9;
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
    }
    .pulse-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 9px var(--green);
    }
    .hero-copy h2 {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 34px;
      line-height: 1.15;
      font-weight: 600;
      letter-spacing: -1.2px;
      margin: 16px 0 10px;
    }
    .hero-copy h2 em { color: #b89cff; font-style: normal; }
    .hero-copy p { font-size: 11.5px; line-height: 1.6; color: #b0a7c6; max-width: 340px; }
    .hero-actions { display: flex; align-items: center; gap: 16px; margin-top: 20px; }
    .primary-button {
      background: linear-gradient(120deg, #a17aff, #784ce2);
      color: white;
      font-size: 11px;
      font-weight: 700;
      padding: 10px 16px;
      border-radius: 9px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 6px 20px rgba(117, 69, 220, 0.35);
    }
    .primary-button:hover { filter: brightness(1.1); }
    .text-button {
      color: #c4afff;
      font-size: 11px;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .text-button:hover { color: #fff; }

    /* Hero Vinyl Graphic */
    .hero-art {
      position: absolute;
      right: 6%;
      top: 10px;
      width: 300px;
      height: 250px;
      display: grid;
      place-items: center;
    }
    .hero-disc {
      width: 185px;
      height: 185px;
      border-radius: 50%;
      background: repeating-radial-gradient(circle at center, #171321 0 2px, #252039 3px 4px, #100f19 5px 7px);
      box-shadow: 0 12px 50px rgba(8, 6, 17, 0.7), 0 0 55px rgba(150, 106, 255, 0.22);
      display: grid;
      place-items: center;
      transform: rotate(-17deg);
      animation: vinylSpin 24s linear infinite;
      z-index: 2;
    }
    @keyframes vinylSpin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    .disc-inner {
      width: 76px;
      height: 76px;
      border-radius: 50%;
      background: linear-gradient(145deg, #a27cff, #5837a8);
      display: grid;
      place-items: center;
      border: 5px solid #1a1527;
    }
    .disc-face {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 34px;
      color: #eee3ff;
      text-shadow: 0 0 17px #fff;
    }
    .orbit {
      position: absolute;
      border: 1px solid rgba(189, 164, 255, 0.2);
      border-radius: 50%;
    }
    .orbit-one { width: 260px; height: 95px; transform: rotate(-24deg); }
    .orbit-two { width: 290px; height: 130px; transform: rotate(37deg); }
    .floating-note { position: absolute; color: #d2baff; font-size: 24px; z-index: 3; }
    .note-one { top: 35px; right: 40px; animation: floatNote 3s ease-in-out infinite; }
    .note-two { bottom: 45px; left: 40px; animation: floatNote 3.5s ease-in-out infinite reverse; }
    @keyframes floatNote {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-8px); }
    }
    .art-caption {
      position: absolute;
      right: -6px;
      bottom: 12px;
      display: flex;
      flex-direction: column;
      gap: 3px;
      text-align: right;
    }
    .art-caption span { font-size: 7.5px; letter-spacing: 1.4px; color: #a28acb; font-weight: 700; }
    .art-caption strong { font-family: 'Space Grotesk', sans-serif; font-size: 11px; }

    /* Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 20px;
    }
    .stat-card {
      background: linear-gradient(145deg, #14121f, #100f19);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px 18px;
      min-height: 115px;
    }
    .stat-icon {
      width: 32px;
      height: 32px;
      border-radius: 9px;
      display: grid;
      place-items: center;
      margin-bottom: 10px;
    }
    .stat-icon.purple { background: rgba(149, 104, 255, 0.15); color: #b99aff; }
    .stat-icon.blue { background: rgba(95, 158, 255, 0.15); color: #83baff; }
    .stat-icon.pink { background: rgba(236, 121, 179, 0.15); color: #f39bc3; }
    .stat-icon.orange { background: rgba(244, 165, 91, 0.15); color: #f4b77c; }
    .stat-label { font-size: 9.5px; color: #9992a9; }
    .stat-value { font-family: 'Space Grotesk', sans-serif; font-size: 22px; font-weight: 600; margin-top: 4px; }
    .stat-note { font-size: 8.5px; color: #777187; margin-top: 3px; }

    /* Content Grid */
    .content-grid {
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 16px;
      margin-bottom: 20px;
    }
    .panel {
      background: linear-gradient(145deg, #14121f, #100f19);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 20px;
    }
    .section-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
    .section-top h3 { font-family: 'Space Grotesk', sans-serif; font-size: 15px; font-weight: 600; }
    .demo-tag {
      font-size: 8px;
      letter-spacing: 1px;
      color: #b49aff;
      background: rgba(155, 114, 255, 0.1);
      border: 1px solid rgba(155, 114, 255, 0.25);
      padding: 4px 8px;
      border-radius: 6px;
      font-weight: 600;
    }
    .demo-tag.bridge-online {
      color: var(--green);
      background: rgba(100, 223, 167, 0.1);
      border-color: rgba(100, 223, 167, 0.25);
    }

    /* Live Studio Server & VC Control Bar */
    .live-controls-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      background: #161324;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
      margin-bottom: 18px;
    }
    .field-select {
      background: #1f1b32;
      border: 1px solid rgba(196, 178, 255, 0.18);
      border-radius: 8px;
      color: #fff;
      font-size: 11px;
      padding: 8px 12px;
      cursor: pointer;
    }
    .field-select option { background: #161324; color: #fff; }
    .quick-search-input {
      flex: 1;
      min-width: 220px;
      background: #1f1b32;
      border: 1px solid rgba(196, 178, 255, 0.18);
      border-radius: 8px;
      color: #fff;
      font-size: 11px;
      padding: 8px 12px;
    }
    .quick-search-input::placeholder { color: #847d9a; }
    .action-btn-pill {
      background: linear-gradient(120deg, #a17aff, #784ce2);
      color: #fff;
      font-size: 10.5px;
      font-weight: 700;
      padding: 8px 14px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .action-btn-pill:hover { filter: brightness(1.1); }
    .action-btn-pill.secondary {
      background: #25213b;
      border: 1px solid rgba(196, 178, 255, 0.15);
      color: #d1c5ee;
    }

    /* Player Panel */
    .player-panel { display: flex; flex-direction: column; }
    .album-art.player-art {
      width: 100%;
      height: 180px;
      border-radius: 12px;
      background: radial-gradient(circle at 75% 25%, rgba(229, 163, 255, 0.3), transparent 30%),
                  linear-gradient(140deg, #633ba5, #1d1834 65%, #161222);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 8px;
      position: relative;
      overflow: hidden;
      margin-bottom: 16px;
    }
    .album-art.player-art span { font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 13px; letter-spacing: 2px; }
    .album-art.player-art small { font-size: 9px; color: #b7a4db; }
    .player-track {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .player-track h2 { font-family: 'Space Grotesk', sans-serif; font-size: 18px; font-weight: 600; }
    .player-track p { color: #a49bb4; font-size: 11px; margin-top: 2px; }
    .track-progress { margin-bottom: 16px; }
    .progress-times { display: flex; justify-content: space-between; font-size: 9px; color: #8f879f; margin-bottom: 6px; }
    .progress-line {
      height: 5px;
      background: #211c33;
      border-radius: 10px;
      overflow: hidden;
      cursor: pointer;
    }
    .progress-line i {
      display: block;
      height: 100%;
      background: linear-gradient(90deg, #7449d8, #a887ff);
      border-radius: 10px;
      transition: width 0.3s;
    }
    .player-controls {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 18px;
      margin-bottom: 16px;
    }
    .player-controls button {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: #1d192f;
      color: #d1c5ee;
      transition: all 0.2s;
    }
    .player-controls button:hover { background: #2b2546; color: #fff; }
    .player-controls .main-play {
      width: 48px;
      height: 48px;
      background: linear-gradient(135deg, #a17aff, #784ce2);
      color: #fff;
      box-shadow: 0 4px 18px rgba(117, 69, 220, 0.4);
    }
    .player-controls .main-play:hover { filter: brightness(1.15); transform: scale(1.04); }
    .volume-control {
      display: flex;
      align-items: center;
      gap: 10px;
      background: #151322;
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 10px;
      color: #a49bb4;
    }
    .volume-control input[type="range"] {
      flex: 1;
      accent-color: #a17aff;
      cursor: pointer;
    }

    /* Queue Panel */
    .queue-panel { display: flex; flex-direction: column; }
    .queue-list { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
    .queue-item {
      display: flex;
      align-items: center;
      gap: 10px;
      background: #151322;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 8px 10px;
    }
    .queue-cover {
      width: 34px;
      height: 34px;
      border-radius: 7px;
      background: linear-gradient(140deg, #9865df, #332052);
      display: grid;
      place-items: center;
      color: #fff;
    }
    .queue-text { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
    .queue-text strong { font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .queue-text span { font-size: 9px; color: var(--muted); }

    /* Commands Page */
    .command-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 16px; }
    .command-card {
      background: #14121f;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px 16px;
    }
    .command-card strong { font-family: 'Space Grotesk', sans-serif; font-size: 13px; color: #c4afff; }
    .command-card p { font-size: 10.5px; color: #a49bb4; margin: 4px 0 8px; }
    .command-card code {
      font-size: 9.5px;
      background: #1f1b30;
      padding: 3px 6px;
      border-radius: 5px;
      color: #e2d7f8;
    }

    /* Bottom Mini Player */
    .mini-player {
      height: 68px;
      position: fixed;
      bottom: 0;
      left: 252px;
      right: 0;
      background: rgba(17, 15, 26, 0.96);
      border-top: 1px solid rgba(176, 139, 255, 0.18);
      backdrop-filter: blur(18px);
      z-index: 50;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 32px;
    }
    .mini-track { display: flex; align-items: center; gap: 12px; }
    .mini-info strong { font-size: 11.5px; display: block; }
    .mini-info span { font-size: 9.5px; color: var(--muted); }
    .mini-controls { display: flex; align-items: center; gap: 12px; }
    .mini-play-btn {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: #a17aff;
      color: #fff;
      display: grid;
      place-items: center;
    }

    /* Toast Notification */
    .toast {
      position: fixed;
      bottom: 84px;
      right: 32px;
      background: #1f1b33;
      border: 1px solid rgba(161, 122, 255, 0.4);
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
      border-radius: 10px;
      padding: 10px 16px;
      font-size: 11px;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
      z-index: 100;
      animation: fadeIn 0.3s;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

    /* Page Visibility */
    .page-pane { display: none; }
    .page-pane.active { display: block; }
  </style>
</head>
<body>
  <div class="shell">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><i data-lucide="headphones"></i></div>
        <div>
          <div class="brand-name">RAI<span> MUSIC</span></div>
          <div class="brand-sub">THE SOUND OF YOUR SERVER</div>
        </div>
      </div>

      <div class="server-switch" onclick="switchPage('servers')">
        <div class="server-avatar" id="sidebar-server-avatar">R</div>
        <div class="server-meta">
          <strong id="sidebar-server-name">Loading servers…</strong>
          <span>Live Workspace</span>
        </div>
        <i data-lucide="chevron-down" style="width: 15px; color: #77728c;"></i>
      </div>

      <nav class="nav-groups">
        <div>
          <div class="nav-label">WORKSPACE</div>
          <button class="nav-item active" onclick="switchPage('overview')" id="nav-overview">
            <i data-lucide="home"></i> <span>Overview</span>
          </button>
          <button class="nav-item" onclick="switchPage('live')" id="nav-live">
            <i data-lucide="audio-lines"></i> <span>Live music</span>
            <i class="nav-live-dot"></i>
          </button>
          <button class="nav-item" onclick="switchPage('servers')" id="nav-servers">
            <i data-lucide="disc-3"></i> <span>Servers</span>
          </button>
          <button class="nav-item" onclick="switchPage('members')" id="nav-members">
            <i data-lucide="users"></i> <span>Members</span>
          </button>
        </div>
        <div>
          <div class="nav-label">DISCOVER</div>
          <button class="nav-item" onclick="switchPage('rem')" id="nav-rem">
            <i data-lucide="sparkles"></i> <span>Rem AI</span>
          </button>
          <button class="nav-item" onclick="switchPage('commands')" id="nav-commands">
            <i data-lucide="command"></i> <span>Commands</span>
          </button>
        </div>
      </nav>

      <div class="sidebar-bottom">
        <div class="rem-card">
          <div class="rem-orb"><i data-lucide="sparkles"></i></div>
          <div class="rem-card-text">
            <strong>Rem is ready</strong>
            <span>Active in Discord</span>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main Section -->
    <main class="main">
      <header class="topbar">
        <div class="top-left">
          <div class="breadcrumbs">
            <span>Workspace</span>
            <i data-lucide="chevron-right" style="width: 14px;"></i>
            <strong id="topbar-title">Overview</strong>
          </div>
        </div>
        <div class="top-actions">
          <label class="searchbox">
            <i data-lucide="search" style="width: 15px;"></i>
            <input id="global-search" placeholder="Search songs or commands..." onkeydown="handleGlobalSearch(event)">
            <kbd>⌘ K</kbd>
          </label>
          <div class="preview-pill" id="discord-status-pill">
            <span></span> DISCORD LINKED
          </div>
          <div id="user-profile-zone">
            <a href="/api/auth/login" class="connect-button" id="btn-login">
              Connect Discord <i data-lucide="chevron-right" style="width: 14px;"></i>
            </a>
          </div>
        </div>
      </header>

      <div class="page-content">
        <!-- OVERVIEW PAGE -->
        <div class="page-pane active" id="pane-overview">
          <div class="page-heading">
            <div>
              <div class="eyebrow">YOUR MUSIC COMMAND CENTER</div>
              <h1 id="overview-greeting">Welcome back to Rai Music.</h1>
              <p>Your server's soundtrack starts here. Controlled in real-time with Rem.</p>
            </div>
            <button class="action-btn-pill secondary" onclick="switchPage('servers')">
              <i data-lucide="sliders-horizontal" style="width: 14px;"></i> Manage Server
            </button>
          </div>

          <!-- Connection & Health Row -->
          <div class="connection-panel">
            <div class="connection-card">
              <div class="connection-card-top">
                <div>
                  <div class="eyebrow">DISCORD ACCOUNT</div>
                  <h3 id="card-discord-username">Your Discord</h3>
                </div>
                <span class="connection-state" id="card-discord-badge">Connected</span>
              </div>
              <div class="connection-identity" id="card-discord-id-row">
                <img id="card-discord-avatar" src="https://rai-discord-bot.onrender.com/public/rem_avatar_static.png" alt="Avatar">
                <div>
                  <strong id="card-discord-tag">TheRealRai</strong>
                  <span id="card-discord-servers-count">Accessible Servers</span>
                </div>
              </div>
              <div class="guild-chips" id="overview-guild-chips">
                <span class="guild-chip">✦ ʀᴀɪ ʀᴀᴍ ✦</span>
                <span class="guild-chip">THOR APEX ⚡</span>
              </div>
              <p class="connection-footnote">Secure session active. Authorized to manage audio & voice.</p>
            </div>

            <div class="connection-card">
              <div class="connection-card-top">
                <div>
                  <div class="eyebrow">MUSICMAID SERVICE</div>
                  <h3>Bot health</h3>
                </div>
                <span class="connection-state" id="card-bot-badge">Online</span>
              </div>
              <div class="bot-health-line">
                <span class="bot-health-dot"></span>
                <strong>MusicMaid is online & streaming</strong>
              </div>
              <div class="bot-health-details">
                <span>Voice engine</span><strong id="health-voice-status">Ready</strong>
                <span>Database</span><strong id="health-db-status">Connected</strong>
              </div>
              <p class="connection-footnote">Zero-credit limits. Permanent Render hosting for your community.</p>
            </div>
          </div>

          <!-- Hero Banner with Rotating Vinyl -->
          <section class="hero-panel">
            <div class="hero-glow"></div>
            <div class="hero-copy">
              <div class="hero-tag"><span class="pulse-dot"></span> YOUR MUSIC, YOUR WORLD</div>
              <h2>Turn your server<br>into a <em>soundtrack.</em></h2>
              <p>One home for music, discovery, and the moments your community shares.</p>
              <div class="hero-actions">
                <button class="primary-button" onclick="switchPage('live')">
                  <i data-lucide="audio-lines" style="width: 15px;"></i> Open music hub
                </button>
                <button class="text-button" onclick="switchPage('rem')">
                  Meet Rem AI <i data-lucide="chevron-right" style="width: 14px;"></i>
                </button>
              </div>
            </div>
            <div class="hero-art">
              <div class="orbit orbit-one"></div>
              <div class="orbit orbit-two"></div>
              <div class="hero-disc">
                <div class="disc-inner">
                  <div class="disc-face">玲</div>
                </div>
              </div>
              <div class="floating-note note-one">♫</div>
              <div class="floating-note note-two">✦</div>
              <div class="art-caption">
                <span>REM'S FREQUENCY</span>
                <strong>Stay in your element.</strong>
              </div>
            </div>
          </section>

          <!-- Stats Grid -->
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-icon purple"><i data-lucide="radio" style="width: 16px;"></i></div>
              <div class="stat-label">Active sessions</div>
              <div class="stat-value" id="stat-sessions">01</div>
              <div class="stat-note">Live in Discord</div>
            </div>
            <div class="stat-card">
              <div class="stat-icon blue"><i data-lucide="music-2" style="width: 16px;"></i></div>
              <div class="stat-label">Tracks played today</div>
              <div class="stat-value">128</div>
              <div class="stat-note">+12% from yesterday</div>
            </div>
            <div class="stat-card">
              <div class="stat-icon pink"><i data-lucide="headphones" style="width: 16px;"></i></div>
              <div class="stat-label">Listeners</div>
              <div class="stat-value" id="stat-listeners">24</div>
              <div class="stat-note">Across voice channels</div>
            </div>
            <div class="stat-card">
              <div class="stat-icon orange"><i data-lucide="heart" style="width: 16px;"></i></div>
              <div class="stat-label">Song memories</div>
              <div class="stat-value">56</div>
              <div class="stat-note">Saved community moments</div>
            </div>
          </div>
        </div>

        <!-- LIVE MUSIC PAGE -->
        <div class="page-pane" id="pane-live">
          <div class="page-heading">
            <div>
              <div class="eyebrow">PLAYBACK STUDIO</div>
              <h1>Live music.</h1>
              <p>Select your server and voice channel — Rem joins and plays instantly.</p>
            </div>
            <div class="demo-tag bridge-online">
              <span class="pulse-dot"></span> LIVE BOT PLAYER
            </div>
          </div>

          <!-- SERVER & VOICE CHANNEL SELECTOR + INSTANT PLAY BAR -->
          <div class="live-controls-bar">
            <div>
              <label class="eyebrow" style="display:block; margin-bottom:3px;">1. SERVER</label>
              <select class="field-select" id="live-server-dropdown" onchange="onServerChange(this.value)">
                <option value="">Select Discord Server…</option>
              </select>
            </div>
            <div>
              <label class="eyebrow" style="display:block; margin-bottom:3px;">2. VOICE CHANNEL</label>
              <select class="field-select" id="live-vc-dropdown">
                <option value="">Select Voice Channel…</option>
              </select>
            </div>
            <button class="action-btn-pill secondary" onclick="connectToSelectedVoiceChannel()" style="margin-top:16px;">
              <i data-lucide="volume-2" style="width: 14px;"></i> Connect VC
            </button>
            <div style="flex: 1; min-width: 260px;">
              <label class="eyebrow" style="display:block; margin-bottom:3px;">3. SEARCH SONG OR PLAYLIST</label>
              <div style="display:flex; gap:8px;">
                <input class="quick-search-input" id="quick-song-input" placeholder="Type song name or paste YouTube/Spotify link..." onkeydown="if(event.key==='Enter') playSongFromInput(true)">
                <button class="action-btn-pill" onclick="playSongFromInput(true)">
                  <i data-lucide="play" style="width: 13px;"></i> Play Now
                </button>
                <button class="action-btn-pill secondary" onclick="playSongFromInput(false)">
                  <i data-lucide="plus" style="width: 13px;"></i> Queue
                </button>
              </div>
            </div>
          </div>

          <!-- Live Player & Queue Grid -->
          <div class="content-grid">
            <section class="panel player-panel">
              <div class="section-top">
                <div>
                  <div class="eyebrow">NOW PLAYING</div>
                  <h3 id="player-status-tag">Connected · Live</h3>
                </div>
                <span class="demo-tag" id="live-vc-name-chip">Voice: Connecting…</span>
              </div>
              <div class="album-art player-art">
                <i data-lucide="audio-lines" style="width: 52px; height: 52px;"></i>
                <span>RAI MUSIC</span>
                <small>REM LOSSLESS AUDIO · 320KBPS</small>
              </div>
              <div class="player-track">
                <div>
                  <h2 id="live-track-title">Ready to stream</h2>
                  <p id="live-track-artist">Select a song above or join voice</p>
                </div>
                <button class="action-btn-pill secondary" style="padding: 6px 10px;" onclick="notify('Added to favourites 💜')">
                  <i data-lucide="heart" style="width: 14px;"></i>
                </button>
              </div>
              <div class="track-progress">
                <div class="progress-times">
                  <span id="live-pos-time">0:00</span>
                  <span id="live-dur-time">0:00</span>
                </div>
                <div class="progress-line" onclick="handleSeek(event)">
                  <i id="live-progress-fill" style="width: 0%;"></i>
                </div>
              </div>
              <div class="player-controls">
                <button onclick="sendAction('PREVIOUS')" title="Previous"><i data-lucide="skip-back" style="width: 16px;"></i></button>
                <button class="main-play" id="btn-main-play" onclick="togglePlayPause()" title="Play / Pause">
                  <i data-lucide="play" style="width: 22px;"></i>
                </button>
                <button onclick="sendAction('SKIP')" title="Skip"><i data-lucide="skip-forward" style="width: 16px;"></i></button>
              </div>
              <div class="volume-control">
                <i data-lucide="volume-2" style="width: 16px;"></i>
                <input type="range" min="0" max="150" value="80" id="live-vol-slider" oninput="onVolumeChange(this.value)">
                <span id="live-vol-label">80%</span>
              </div>
            </section>

            <section class="panel queue-panel">
              <div class="section-top">
                <div>
                  <div class="eyebrow">UP NEXT</div>
                  <h3>Queue (<span id="queue-count-badge">0</span>)</h3>
                </div>
                <button class="text-button" onclick="sendAction('CLEAR')">Clear</button>
              </div>
              <div class="queue-list" id="queue-items-container">
                <div class="queue-item">
                  <div class="queue-cover"><i data-lucide="music-2" style="width: 16px;"></i></div>
                  <div class="queue-text">
                    <strong>Queue is empty</strong>
                    <span>Search a track or playlist above to stream!</span>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>

        <!-- COMMANDS PAGE -->
        <div class="page-pane" id="pane-commands">
          <div class="page-heading">
            <div>
              <div class="eyebrow">COMMAND CENTER</div>
              <h1>Discord Commands.</h1>
              <p>Everything Rem can do in your server text channels and through the web.</p>
            </div>
          </div>
          <div class="command-grid">
            <div class="command-card">
              <strong>/play &lt;song or url&gt;</strong>
              <p>Plays any track or playlist from YouTube, Spotify, or Soundcloud.</p>
              <code>/play Evergreen Tamil romantic songs</code>
            </div>
            <div class="command-card">
              <strong>/skip</strong>
              <p>Vote-skip or instantly skip to the next track in the queue.</p>
              <code>/skip</code>
            </div>
            <div class="command-card">
              <strong>/pause &amp; /resume</strong>
              <p>Temporarily pause playback or resume streaming.</p>
              <code>/pause</code>
            </div>
            <div class="command-card">
              <strong>/volume &lt;0–150&gt;</strong>
              <p>Sets playback volume for the entire listening room.</p>
              <code>/volume 80</code>
            </div>
            <div class="command-card">
              <strong>/autoplay</strong>
              <p>Rem automatically finds and queues recommendations when queue finishes.</p>
              <code>/autoplay</code>
            </div>
            <div class="command-card">
              <strong>/songmemory &lt;song&gt;</strong>
              <p>Saves quotes and cherished server memories attached to songs.</p>
              <code>/songmemory save After Dark</code>
            </div>
          </div>
        </div>

        <!-- REM AI PAGE -->
        <div class="page-pane" id="pane-rem">
          <div class="page-heading">
            <div>
              <div class="eyebrow">ARTIFICIAL COMPANION</div>
              <h1>Rem AI.</h1>
              <p>Tune Rem's musical mood to your server's late night or study vibe.</p>
            </div>
          </div>
          <div class="command-grid">
            <div class="command-card" style="cursor:pointer;" onclick="setVibe('Chill Lo-Fi')">
              <strong>🌙 2AM Late-Night Chill</strong>
              <p>Soft synthwave, lo-fi beats, and warm reverb tailored for night owls.</p>
              <button class="action-btn-pill secondary">Activate Vibe</button>
            </div>
            <div class="command-card" style="cursor:pointer;" onclick="setVibe('Anime Energy')">
              <strong>⚡ High-Energy Anime Openings</strong>
              <p>Upbeat J-Rock, high BPM shonen anthems, and hype soundtracks.</p>
              <button class="action-btn-pill secondary">Activate Vibe</button>
            </div>
          </div>
        </div>

        <!-- SERVERS PAGE -->
        <div class="page-pane" id="pane-servers">
          <div class="page-heading">
            <div>
              <div class="eyebrow">COMMUNITY WORKSPACES</div>
              <h1>Accessible Servers.</h1>
              <p>Manage the Discord servers where Rem is active.</p>
            </div>
          </div>
          <div class="guild-chips" id="full-servers-list" style="display:grid; grid-template-columns: repeat(3, 1fr); gap:12px;">
            <!-- Dynamically populated -->
          </div>
        </div>

        <!-- MEMBERS PAGE -->
        <div class="page-pane" id="pane-members">
          <div class="page-heading">
            <div>
              <div class="eyebrow">COMMUNITY MEMBERS</div>
              <h1>Active Listeners.</h1>
              <p>Members currently hanging out in your server voice channels.</p>
            </div>
          </div>
          <div id="members-list-container" class="command-card">
            <p>Select a server in Live Music to see connected listeners.</p>
          </div>
        </div>
      </div>
    </main>

    <!-- Bottom Mini Player -->
    <div class="mini-player" id="global-mini-player">
      <div class="mini-track">
        <div class="queue-cover"><i data-lucide="music-2" style="width: 18px;"></i></div>
        <div class="mini-info">
          <strong id="mini-track-title">Rai Music Player</strong>
          <span id="mini-track-artist">Select a server to begin</span>
        </div>
      </div>
      <div class="mini-controls">
        <button onclick="sendAction('PREVIOUS')" title="Previous"><i data-lucide="skip-back" style="width: 17px;"></i></button>
        <button class="mini-play-btn" onclick="togglePlayPause()" id="mini-play-btn" title="Play / Pause">
          <i data-lucide="play" style="width: 17px;"></i>
        </button>
        <button onclick="sendAction('SKIP')" title="Skip"><i data-lucide="skip-forward" style="width: 17px;"></i></button>
      </div>
    </div>
  </div>

  <div id="toast-container"></div>

  <script>
    let activeGuildId = '';
    let isPlaying = false;
    let trackDuration = 0;
    let trackPosition = 0;
    let progressTimer = null;

    function notify(msg) {
      const container = document.getElementById('toast-container');
      const el = document.createElement('div');
      el.className = 'toast';
      el.innerHTML = `<i data-lucide="check" style="width:14px; color:#64dfa7;"></i> <span>${msg}</span>`;
      container.appendChild(el);
      if (window.lucide) lucide.createIcons();
      setTimeout(() => { el.remove(); }, 3200);
    }

    function switchPage(page) {
      document.querySelectorAll('.page-pane').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
      const pane = document.getElementById('pane-' + page);
      const btn = document.getElementById('nav-' + page);
      if (pane) pane.classList.add('active');
      if (btn) btn.classList.add('active');
      const titleMap = {
        overview: 'Overview',
        live: 'Live music',
        servers: 'Server settings',
        commands: 'Command center',
        rem: 'Rem AI',
        members: 'Members'
      };
      document.getElementById('topbar-title').innerText = titleMap[page] || 'Overview';
      if (window.lucide) lucide.createIcons();
    }

    function formatTime(secs) {
      const s = Math.max(0, Math.floor(secs || 0));
      return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    }

    async function loadIdentity() {
      try {
        const res = await fetch('/api/auth/me');
        if (res.ok) {
          const data = await res.json();
          if (data && data.signedIn && data.user) {
            const u = data.user;
            document.getElementById('user-profile-zone').innerHTML = `
              <div class="connected-user">
                <img src="${u.avatarUrl || '/public/rem_avatar_static.png'}" alt="Avatar">
                <span>${u.globalName || u.username}</span>
                <a href="/api/auth/logout">Sign out</a>
              </div>
            `;
            document.getElementById('card-discord-username').innerText = u.globalName || u.username;
            document.getElementById('card-discord-tag').innerText = '@' + u.username;
            document.getElementById('card-discord-avatar').src = u.avatarUrl || '/public/rem_avatar_static.png';
            document.getElementById('overview-greeting').innerText = `Welcome back, ${u.globalName || u.username}.`;
          }
        }
      } catch (e) {
        console.debug('Auth fetch error', e);
      }
    }

    async function loadGuilds() {
      try {
        const res = await fetch('/api/music/guilds');
        if (res.ok) {
          const json = await res.json();
          const guilds = json.data?.guilds || [];
          const select = document.getElementById('live-server-dropdown');
          select.innerHTML = '';
          const chips = document.getElementById('overview-guild-chips');
          chips.innerHTML = '';
          const serversList = document.getElementById('full-servers-list');
          if (serversList) serversList.innerHTML = '';

          guilds.forEach((g, idx) => {
            const opt = document.createElement('option');
            opt.value = g.id;
            opt.innerText = g.name;
            select.appendChild(opt);

            const chip = document.createElement('span');
            chip.className = 'guild-chip';
            chip.innerText = g.name;
            chips.appendChild(chip);

            if (serversList) {
              const card = document.createElement('div');
              card.className = 'command-card';
              card.innerHTML = `<strong>${g.name}</strong><p>Status: ${g.bot_in_guild ? 'Connected' : 'Available'}</p><button class="action-btn-pill secondary" onclick="activeGuildId='${g.id}'; switchPage('live');">Select</button>`;
              serversList.appendChild(card);
            }
          });

          if (guilds.length > 0 && !activeGuildId) {
            activeGuildId = guilds[0].id;
            document.getElementById('sidebar-server-name').innerText = guilds[0].name;
            select.value = activeGuildId;
          }
          await onServerChange(activeGuildId);
        }
      } catch (e) {
        console.debug('Guild load note', e);
      }
    }

    async function onServerChange(guildId) {
      activeGuildId = guildId;
      const select = document.getElementById('live-server-dropdown');
      if (select) select.value = guildId;
      const opt = select ? select.options[select.selectedIndex] : null;
      if (opt) document.getElementById('sidebar-server-name').innerText = opt.text;

      // Fetch session and voice channels
      await refreshLiveSession();
    }

    async function refreshLiveSession() {
      if (!activeGuildId) return;
      try {
        const res = await fetch('/api/music/session?guild_id=' + encodeURIComponent(activeGuildId));
        if (res.ok) {
          const json = await res.json();
          const sess = json.data || {};

          // Update Voice Channel dropdown
          const vcSelect = document.getElementById('live-vc-dropdown');
          if (vcSelect && sess.available_voice_channels) {
            const currVal = vcSelect.value;
            vcSelect.innerHTML = '<option value="">Select Voice Channel…</option>';
            sess.available_voice_channels.forEach(vc => {
              const opt = document.createElement('option');
              opt.value = vc.id;
              opt.innerText = `${vc.name} (${vc.listeners} listeners)`;
              if (vc.is_current) opt.selected = true;
              vcSelect.appendChild(opt);
            });
            if (currVal && !sess.available_voice_channels.some(v => v.is_current)) {
              vcSelect.value = currVal;
            }
          }

          // Update Now Playing Info
          isPlaying = Boolean(sess.is_playing);
          const trk = sess.current_track;
          if (trk) {
            document.getElementById('live-track-title').innerText = trk.title || 'Playing';
            document.getElementById('live-track-artist').innerText = trk.artist || 'MusicMaid';
            document.getElementById('mini-track-title').innerText = trk.title || 'Playing';
            document.getElementById('mini-track-artist').innerText = trk.artist || 'MusicMaid';
            trackDuration = Number(sess.duration_seconds || trk.duration || 0);
            trackPosition = Number(sess.position_seconds || 0);
            document.getElementById('live-dur-time').innerText = formatTime(trackDuration);
            document.getElementById('live-pos-time').innerText = formatTime(trackPosition);
            const pct = trackDuration > 0 ? (trackPosition / trackDuration) * 100 : 0;
            document.getElementById('live-progress-fill').style.width = pct + '%';
          } else {
            document.getElementById('live-track-title').innerText = 'Nothing playing';
            document.getElementById('live-track-artist').innerText = 'Select a song to start streaming';
            document.getElementById('mini-track-title').innerText = 'Ready to stream';
            document.getElementById('mini-track-artist').innerText = 'Idle';
            document.getElementById('live-progress-fill').style.width = '0%';
          }

          // Update VC chip
          const vcName = sess.voice_channel_name || sess.channel_name || 'Not in voice';
          document.getElementById('live-vc-name-chip').innerText = 'Voice: #' + vcName;

          // Update Volume & Autoplay
          if (typeof sess.volume === 'number') {
            document.getElementById('live-vol-slider').value = sess.volume;
            document.getElementById('live-vol-label').innerText = sess.volume + '%';
          }

          // Update Play Buttons
          const mainBtn = document.getElementById('btn-main-play');
          const miniBtn = document.getElementById('mini-play-btn');
          const iconName = isPlaying ? 'pause' : 'play';
          mainBtn.innerHTML = `<i data-lucide="${iconName}" style="width: 22px;"></i>`;
          miniBtn.innerHTML = `<i data-lucide="${iconName}" style="width: 17px;"></i>`;
          if (window.lucide) lucide.createIcons();
        }

        // Fetch queue
        const qRes = await fetch('/api/music/queue?guild_id=' + encodeURIComponent(activeGuildId));
        if (qRes.ok) {
          const qJson = await qRes.json();
          const qTracks = qJson.data?.tracks || [];
          document.getElementById('queue-count-badge').innerText = qTracks.length;
          const container = document.getElementById('queue-items-container');
          if (qTracks.length === 0) {
            container.innerHTML = `
              <div class="queue-item">
                <div class="queue-cover"><i data-lucide="music-2" style="width: 16px;"></i></div>
                <div class="queue-text">
                  <strong>Queue is empty</strong>
                  <span>Search a track or playlist above to stream!</span>
                </div>
              </div>`;
          } else {
            container.innerHTML = qTracks.slice(0, 10).map((t, i) => `
              <div class="queue-item">
                <span style="font-size:10px; font-weight:700; color:#857ca0; width:16px;">${i+1}</span>
                <div class="queue-cover"><i data-lucide="music-2" style="width: 16px;"></i></div>
                <div class="queue-text">
                  <strong>${t.title}</strong>
                  <span>${t.artist || 'Unknown Artist'} · ${formatTime(t.duration)}</span>
                </div>
              </div>
            `).join('');
          }
          if (window.lucide) lucide.createIcons();
        }
      } catch (e) {
        console.debug('Session fetch note', e);
      }
    }

    async function sendAction(action, payload = {}) {
      if (!activeGuildId) return notify('Please select a server first.');
      try {
        const res = await fetch('/api/music/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            guild_id: activeGuildId,
            action: action,
            payload: payload
          })
        });
        const data = await res.json();
        if (data && data.success) {
          notify(data.data?.message || `Rem: ${action} sent.`);
          await refreshLiveSession();
        } else {
          notify(data?.error?.message || 'Control action rejected.');
        }
      } catch (e) {
        notify('Could not send control action: ' + e.message);
      }
    }

    async function connectToSelectedVoiceChannel() {
      const vcSelect = document.getElementById('live-vc-dropdown');
      const channelId = vcSelect ? vcSelect.value : '';
      if (!channelId) return notify('Please select a Voice Channel from the dropdown.');
      await sendAction('CONNECT_VOICE', { channel_id: channelId });
    }

    async function playSongFromInput(playNow = true) {
      const input = document.getElementById('quick-song-input');
      const query = input ? input.value.trim() : '';
      if (!query) return notify('Please enter a song name or link.');
      const vcSelect = document.getElementById('live-vc-dropdown');
      const channelId = vcSelect ? vcSelect.value : '';
      
      notify(playNow ? 'Connecting & playing song…' : 'Adding to queue…');
      await sendAction(playNow ? 'PLAY_NOW' : 'ENQUEUE', {
        query: query,
        channel_id: channelId || undefined
      });
      if (input) input.value = '';
    }

    function togglePlayPause() {
      sendAction(isPlaying ? 'PAUSE' : 'RESUME');
    }

    function onVolumeChange(vol) {
      document.getElementById('live-vol-label').innerText = vol + '%';
      sendAction('VOLUME', { volume: Number(vol) });
    }

    function setVibe(vibe) {
      notify(`Rem AI: Activating ${vibe} vibe in Discord 💜`);
      sendAction('AUTODJ_MOOD', { mood: vibe.toLowerCase() });
    }

    function handleGlobalSearch(e) {
      if (e.key === 'Enter') {
        const query = e.target.value.trim();
        if (query) {
          switchPage('live');
          const input = document.getElementById('quick-song-input');
          if (input) {
            input.value = query;
            playSongFromInput(true);
          }
        }
      }
    }

    window.addEventListener('DOMContentLoaded', async () => {
      if (window.lucide) lucide.createIcons();
      await loadIdentity();
      await loadGuilds();
      setInterval(refreshLiveSession, 4500);
    });
  </script>
</body>
</html>
"""
