"""
Rem Official Login & Web Authentication Interface.
Provides an anime-inspired glassmorphism sign-in portal for Discord guild owners and audiophiles.
"""

LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Login — Rem Web Portal | Your Anime Music Companion</title>
  <meta name="description" content="Sign in to your Rem dashboard to control server playback, manage playlists, and customize audio settings.">
  <link rel="icon" type="image/png" href="/public/icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #080711;
      --bg-card: rgba(18, 15, 36, 0.75);
      --border-glow: rgba(168, 85, 247, 0.28);
      --border-bright: rgba(192, 132, 252, 0.65);
      --accent-purple: #9333ea;
      --accent-violet: #a855f7;
      --accent-neon: #c084fc;
      --accent-cyan: #06b6d4;
      --discord-blurple: #5865f2;
      --discord-hover: #4752c4;
      --text-white: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --radius: 20px;
      --shadow-neon: 0 0 45px rgba(168, 85, 247, 0.25);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: 'Outfit', sans-serif;
    }

    body {
      background: var(--bg-dark);
      color: var(--text-white);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 30px 20px;
      position: relative;
      overflow-x: hidden;
      background-image: 
        radial-gradient(circle at 10% 20%, rgba(147, 51, 234, 0.2) 0%, transparent 45%),
        radial-gradient(circle at 90% 80%, rgba(6, 182, 212, 0.15) 0%, transparent 45%),
        radial-gradient(circle at 50% 50%, rgba(236, 72, 153, 0.1) 0%, transparent 55%);
      background-attachment: fixed;
    }

    /* Floating particles effect */
    .ambient-glow {
      position: absolute;
      width: 600px;
      height: 600px;
      background: radial-gradient(circle, rgba(168, 85, 247, 0.18) 0%, transparent 70%);
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      pointer-events: none;
      filter: blur(60px);
      z-index: 0;
    }

    /* Back Button */
    .back-nav {
      position: absolute;
      top: 28px;
      left: 36px;
      z-index: 10;
    }

    .back-link {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.92rem;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-glow);
      backdrop-filter: blur(10px);
      transition: all 0.25s ease;
    }

    .back-link:hover {
      color: #fff;
      border-color: var(--accent-neon);
      background: rgba(168, 85, 247, 0.15);
      transform: translateX(-3px);
    }

    /* Main Container */
    .login-container {
      position: relative;
      z-index: 1;
      width: 100%;
      max-width: 1020px;
      background: var(--bg-card);
      border: 1px solid var(--border-glow);
      border-radius: 28px;
      overflow: hidden;
      box-shadow: var(--shadow-neon);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      display: grid;
      grid-template-columns: 1.05fr 1fr;
    }

    /* Visual Left Hero */
    .login-visual {
      position: relative;
      background: linear-gradient(135deg, rgba(20, 15, 45, 0.9), rgba(10, 8, 25, 0.95));
      padding: 50px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      overflow: hidden;
      border-right: 1px solid rgba(255, 255, 255, 0.06);
    }

    .visual-bg-img {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      opacity: 0.28;
      mix-blend-mode: luminosity;
      transition: transform 0.8s ease;
    }

    .login-container:hover .visual-bg-img {
      transform: scale(1.04);
    }

    .visual-content {
      position: relative;
      z-index: 2;
    }

    .brand-badge {
      display: inline-flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 24px;
    }

    .brand-logo {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      border: 2px solid var(--accent-neon);
      box-shadow: 0 0 20px rgba(192, 132, 252, 0.45);
      object-fit: cover;
    }

    .brand-title {
      font-size: 1.6rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #fff 30%, var(--accent-neon) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .visual-headline {
      font-size: 2.2rem;
      font-weight: 900;
      line-height: 1.2;
      letter-spacing: -0.5px;
      margin-bottom: 16px;
    }

    .visual-desc {
      color: var(--text-muted);
      font-size: 0.98rem;
      line-height: 1.6;
      margin-bottom: 30px;
    }

    .feature-highlights {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .highlight-item {
      display: flex;
      align-items: center;
      gap: 12px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.07);
      padding: 12px 18px;
      border-radius: 14px;
      font-size: 0.9rem;
      font-weight: 500;
      backdrop-filter: blur(8px);
    }

    .highlight-icon {
      font-size: 1.2rem;
    }

    .visual-footer {
      position: relative;
      z-index: 2;
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 0.85rem;
      color: var(--text-dim);
      padding-top: 24px;
    }

    .status-pip {
      width: 8px;
      height: 8px;
      background: #22c55e;
      border-radius: 50%;
      box-shadow: 0 0 10px #22c55e;
    }

    /* Form Right Panel */
    .login-form-panel {
      padding: 55px 45px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }

    .panel-header {
      margin-bottom: 32px;
    }

    .panel-header h2 {
      font-size: 1.9rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      margin-bottom: 8px;
    }

    .panel-header p {
      color: var(--text-muted);
      font-size: 0.95rem;
    }

    /* Discord OAuth Button */
    .btn-discord {
      width: 100%;
      padding: 15px 20px;
      border-radius: 14px;
      background: var(--discord-blurple);
      color: #fff;
      font-weight: 700;
      font-size: 1.05rem;
      text-decoration: none;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      transition: all 0.25s ease;
      box-shadow: 0 6px 20px rgba(88, 101, 242, 0.4);
      margin-bottom: 24px;
      border: none;
      cursor: pointer;
    }

    .btn-discord:hover {
      background: var(--discord-hover);
      box-shadow: 0 10px 28px rgba(88, 101, 242, 0.6);
      transform: translateY(-2px);
    }

    .discord-icon {
      width: 24px;
      height: 24px;
      fill: currentColor;
    }

    /* Divider */
    .divider {
      display: flex;
      align-items: center;
      text-align: center;
      margin: 10px 0 24px;
      color: var(--text-dim);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 1.2px;
      text-transform: uppercase;
    }

    .divider::before,
    .divider::after {
      content: '';
      flex: 1;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    .divider:not(:empty)::before { margin-right: 14px; }
    .divider:not(:empty)::after { margin-left: 14px; }

    /* Input Fields */
    .form-group {
      margin-bottom: 18px;
    }

    .form-label {
      display: block;
      font-size: 0.88rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 8px;
    }

    .input-wrap {
      position: relative;
    }

    .form-input {
      width: 100%;
      padding: 13px 16px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-glow);
      border-radius: 12px;
      color: #fff;
      font-size: 0.95rem;
      transition: all 0.25s ease;
      outline: none;
    }

    .form-input:focus {
      border-color: var(--accent-neon);
      background: rgba(255, 255, 255, 0.07);
      box-shadow: 0 0 15px rgba(168, 85, 247, 0.25);
    }

    .form-options {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      font-size: 0.88rem;
    }

    .remember-me {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text-muted);
      cursor: pointer;
    }

    .remember-me input {
      accent-color: var(--accent-purple);
      cursor: pointer;
    }

    .help-link {
      color: var(--accent-neon);
      text-decoration: none;
      font-weight: 500;
    }

    .help-link:hover {
      text-decoration: underline;
    }

    .btn-submit {
      width: 100%;
      padding: 14px;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--accent-purple), var(--accent-neon));
      color: #fff;
      font-weight: 700;
      font-size: 1rem;
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 18px rgba(147, 51, 234, 0.35);
      transition: all 0.25s ease;
    }

    .btn-submit:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(192, 132, 252, 0.5);
    }

    /* Guest Explore Demo Button */
    .demo-bar {
      margin-top: 24px;
      text-align: center;
      padding-top: 18px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
    }

    .demo-link {
      color: var(--text-dim);
      text-decoration: none;
      font-size: 0.88rem;
      transition: color 0.2s;
    }

    .demo-link span {
      color: var(--accent-cyan);
      font-weight: 600;
    }

    .demo-link:hover span {
      text-decoration: underline;
    }

    @media (max-width: 860px) {
      .login-container {
        grid-template-columns: 1fr;
      }
      .login-visual {
        display: none;
      }
      .back-nav {
        top: 18px;
        left: 20px;
      }
      .login-form-panel {
        padding: 40px 24px;
      }
    }
  </style>
</head>
<body>

  <div class="ambient-glow"></div>

  <!-- Back to Website -->
  <div class="back-nav">
    <a href="/" class="back-link">
      <span>←</span>
      <span>Back to Home</span>
    </a>
  </div>

  <!-- Login Card -->
  <div class="login-container">
    
    <!-- Visual Left Panel -->
    <div class="login-visual">
      <img src="/public/login_hero.jpg" alt="Rem Aesthetic" class="visual-bg-img" onerror="this.src='/public/musicmaid_headphone_hero.jpg'">
      
      <div class="visual-content">
        <div class="brand-badge">
          <img src="/public/musicmaid_avatar.jpg" alt="Rem Logo" class="brand-logo" onerror="this.src='/public/icon.png'">
          <span class="brand-title">Rem 🎧💜</span>
        </div>

        <h1 class="visual-headline">Your Anime Music Companion.</h1>
        <p class="visual-desc">Access real-time web playback controls, synchronized lyrics, cloud playlists, and audio equalizer filters across all your servers.</p>

        <div class="feature-highlights">
          <div class="highlight-item">
            <span class="highlight-icon">🎧</span>
            <span>Live Interactive Player Control</span>
          </div>
          <div class="highlight-item">
            <span class="highlight-icon">⚡</span>
            <span>Instant Lavalink v4 Audio Streaming</span>
          </div>
          <div class="highlight-item">
            <span class="highlight-icon">📂</span>
            <span>Cloud Playlists & Multi-Guild Sync</span>
          </div>
        </div>
      </div>

      <div class="visual-footer">
        <span class="status-pip"></span>
        <span>Secure Session • Discord OAuth2 Protocol</span>
      </div>
    </div>

    <!-- Form Right Panel -->
    <div class="login-form-panel">
      <div class="panel-header">
        <h2>Sign in to Rem</h2>
        <p>Choose your preferred sign-in method to continue</p>
      </div>

      <!-- Discord OAuth Button -->
      <a href="/api/auth/login" class="btn-discord" id="discord-oauth-btn">
        <svg class="discord-icon" viewBox="0 0 24 24">
          <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.893.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
        </svg>
        <span>Continue with Discord</span>
      </a>

      <div class="divider">or sign in with guild passkey</div>

      <!-- Guild Key Login Form -->
      <form id="passkey-form" onsubmit="handlePasskeySubmit(event)">
        <div class="form-group">
          <label class="form-label" for="guild-id">Guild ID or Owner Passcode</label>
          <div class="input-wrap">
            <input type="text" id="guild-id" class="form-input" placeholder="e.g. 1560990395666538529 or owner" required>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label" for="access-token">Secret Access Key</label>
          <div class="input-wrap">
            <input type="password" id="access-token" class="form-input" placeholder="••••••••••••••••" value="owner">
          </div>
        </div>

        <div class="form-options">
          <label class="remember-me">
            <input type="checkbox" checked>
            <span>Remember session</span>
          </label>
          <a href="https://discord.gg/wRCgB7vBQv" target="_blank" class="help-link">Need help?</a>
        </div>

        <button type="submit" class="btn-submit" id="submit-btn">
          <span>Authenticate & Open Dashboard</span>
        </button>

        <!-- 1-Click Creator / Owner Login -->
        <div style="margin-top:14px; text-align:center;">
          <button type="button" onclick="quickOwnerLogin()" style="background:rgba(255,215,0,0.12); border:1px solid rgba(255,215,0,0.4); color:#ffd700; border-radius:12px; padding:11px 16px; font-weight:700; font-size:0.88rem; cursor:pointer; width:100%; transition:all 0.25s ease; display:flex; align-items:center; justify-content:center; gap:8px;">
            <span>👑</span>
            <span>Bot Creator / Owner Direct Access</span>
          </button>
        </div>
      </form>

      <div class="demo-bar">
        <a href="/dashboard" class="demo-link">Want to explore without sign-in? <span>Open Live Dashboard ↗</span></a>
      </div>
    </div>

  </div>

  <script>
    async function handlePasskeySubmit(e) {
      e.preventDefault();
      const btn = document.getElementById('submit-btn');
      btn.innerText = 'Authenticating with Rem...';
      btn.style.opacity = '0.75';
      const guildId = document.getElementById('guild-id').value.trim();
      const tokenVal = document.getElementById('access-token').value.trim();
      try {
        const res = await fetch('/api/auth/passkey', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: guildId, passcode: tokenVal })
        });
        const json = await res.json();
        if (json.success && json.data && json.data.token) {
          localStorage.setItem('rai_session_token', json.data.token);
          btn.innerText = 'Authenticated! Opening Dashboard...';
          const target = (json.data.user && json.data.user.is_owner) ? '/owner' : '/dashboard';
          window.location.href = target + '?token=' + json.data.token;
          return;
        }
      } catch(err) {
        console.error("Passkey auth error:", err);
      }
      window.location.href = '/dashboard';
    }

    async function quickOwnerLogin() {
      try {
        const res = await fetch('/api/auth/passkey', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: '1457380609641938981', passcode: 'owner' })
        });
        const json = await res.json();
        if (json.success && json.data && json.data.token) {
          localStorage.setItem('rai_session_token', json.data.token);
          window.location.href = '/owner?token=' + json.data.token;
          return;
        }
      } catch(e) {
        console.error("Owner login error:", e);
      }
      window.location.href = '/owner';
    }
  </script>

</body>
</html>
"""
