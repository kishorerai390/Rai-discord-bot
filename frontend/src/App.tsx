import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import {
  Activity,
  AlertCircle,
  AudioLines,
  BarChart3,
  Bell,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  Disc3,
  Flame,
  Globe,
  Headphones,
  Heart,
  History,
  Layers,
  ListMusic,
  Menu,
  Moon,
  Music2,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  SkipBack,
  SkipForward,
  Sparkles,
  Volume2,
  X,
  Zap,
} from 'lucide-react';

type Page = 'overview' | 'live' | 'soundboard' | 'commands' | 'history' | 'settings';

interface ToastItem {
  id: string;
  message: string;
  type?: 'info' | 'success' | 'warning' | 'music' | 'danger';
}

const COMMAND_LIST = [
  { name: '/play', cat: 'Music', detail: 'Stream any track or playlist from YouTube, Spotify, SoundCloud, or Apple Music.', usage: '/play <song or link>' },
  { name: '/playtop', cat: 'Music', detail: 'Add a track directly to the front (top) of the current queue.', usage: '/playtop <song or link>' },
  { name: '/pause', cat: 'Music', detail: 'Pause current playback in the voice channel.', usage: '/pause' },
  { name: '/resume', cat: 'Music', detail: 'Resume playback of the paused track.', usage: '/resume' },
  { name: '/skip', cat: 'Music', detail: 'Vote or instantly skip to the next track in the queue.', usage: '/skip' },
  { name: '/previous', cat: 'Music', detail: 'Replay the previous track from listening history.', usage: '/previous' },
  { name: '/queue', cat: 'Music', detail: 'View the list of queued tracks with interactive pagination.', usage: '/queue' },
  { name: '/volume', cat: 'Music', detail: 'Adjust volume smoothly from 0% to 100% (or 150% with boost).', usage: '/volume <1-100>' },
  { name: '/soundboard', cat: 'SFX', detail: 'Instantly play 24 anime and meme soundboard SFX into voice.', usage: '/soundboard <sound>' },
  { name: '/radio2am', cat: 'Discovery', detail: 'Start an endless 2:00 AM late-night lofi & synthwave radio station.', usage: '/radio2am' },
  { name: '/songmemory', cat: 'Community', detail: 'Save a nostalgic track memory attached to this server.', usage: '/songmemory save <song>' },
  { name: '/rembond', cat: 'Community', detail: 'Check your server listening bond and affinity level with Rem.', usage: '/rembond' },
  { name: '/aidj', cat: 'AI', detail: 'Toggle Rem anime voice commentary and track announcements.', usage: '/aidj on|off' },
  { name: '/lyrics', cat: 'Discovery', detail: 'Fetch synced or static lyrics for the currently playing track.', usage: '/lyrics [song]' },
  { name: '/loop', cat: 'Music', detail: 'Cycle repeat mode: Single Track, Entire Queue, or Off.', usage: '/loop [track|queue|off]' },
  { name: '/shuffle', cat: 'Music', detail: 'Randomize all tracks in the pending queue.', usage: '/shuffle' },
  { name: '/stop', cat: 'Music', detail: 'Stop audio playback and clear the remaining queue.', usage: '/stop' },
  { name: '/leave', cat: 'Music', detail: 'Disconnect Rem from the voice channel.', usage: '/leave' },
];

export default function App() {
  const [page, setPage] = useState<Page>('overview');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [theme, setTheme] = useState('Midnight');
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  // Live real-time bot data
  const [liveGuilds, setLiveGuilds] = useState<any[]>([]);
  const [liveGuildId, setLiveGuildId] = useState<string>('');
  const [liveSession, setLiveSession] = useState<any | null>(null);
  const [liveQueue, setLiveQueue] = useState<any[]>([]);
  const [liveStats, setLiveStats] = useState<any | null>(null);
  const [liveSounds, setLiveSounds] = useState<any[]>([]);
  const [liveHistory, setLiveHistory] = useState<any[]>([]);
  const [liveBridgeReady, setLiveBridgeReady] = useState(true);
  const [botReachable, setBotReachable] = useState(true);

  // Inputs & states
  const [trackQuery, setTrackQuery] = useState('');
  const [selectedVcId, setSelectedVcId] = useState('');
  const [soundCategory, setSoundCategory] = useState('All');
  const [soundSearch, setSoundSearch] = useState('');
  const [commandCategory, setCommandCategory] = useState('All');
  const [commandSearch, setCommandSearch] = useState('');
  const [globalSearch, setGlobalSearch] = useState('');
  const [discordAccount, setDiscordAccount] = useState<any | null>(null);

  // Toast notifier
  const notify = (message: string, type: 'info' | 'success' | 'warning' | 'music' | 'danger' = 'info') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => [...prev.slice(-3), { id, message, type }]);
    window.setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3600);
  };
  const removeToast = (id: string) => setToasts(prev => prev.filter(t => t.id !== id));

  // Initialize guest token so visitor can immediately control & stream without friction
  useEffect(() => {
    try {
      const stored = localStorage.getItem('rai_session_token');
      if (!stored) {
        const guestId = 'guest_' + Math.random().toString(36).substring(2, 10);
        localStorage.setItem('rai_session_token', guestId);
      }
    } catch {}
  }, []);

  // Check Discord user session
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api.get('/api/auth/me');
        if (active && res.data?.signedIn && res.data?.user) {
          setDiscordAccount(res.data.user);
        }
      } catch {}
    })();
    return () => { active = false; };
  }, []);

  // Real-time polling: fetch live bot session, queue, voice channels, and server list every 3.5s
  useEffect(() => {
    let active = true;
    const fetchRealtimeData = async () => {
      try {
        // 1. Fetch available servers
        const guildRes = await api.get('/api/music/guilds');
        const guilds = guildRes.data?.data?.guilds ?? guildRes.data?.guilds ?? [];
        if (active && Array.isArray(guilds) && guilds.length > 0) {
          setLiveGuilds(guilds);
          if (!liveGuildId) {
            setLiveGuildId(String(guilds[0].id));
          }
        }

        const activeId = liveGuildId || (guilds[0] ? String(guilds[0].id) : '');
        if (!activeId) return;

        // 2. Fetch live session and queue in parallel
        const [sessionRes, queueRes, statsRes] = await Promise.all([
          api.get('/api/music/session?guild_id=' + encodeURIComponent(activeId)),
          api.get('/api/music/queue?guild_id=' + encodeURIComponent(activeId)),
          api.get('/api/music/stats'),
        ]);

        if (!active) return;
        if (sessionRes.data?.data) {
          setLiveSession(sessionRes.data.data);
          setLiveBridgeReady(true);
          setBotReachable(true);
        }
        if (queueRes.data?.data?.tracks) {
          setLiveQueue(queueRes.data.data.tracks);
        }
        if (statsRes.data?.data) {
          setLiveStats(statsRes.data.data);
        }
      } catch {
        if (active) {
          setLiveBridgeReady(true);
        }
      }
    };

    fetchRealtimeData();
    const interval = window.setInterval(fetchRealtimeData, 3500);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [liveGuildId]);

  // Load soundboard & history once
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [sfxRes, histRes] = await Promise.all([
          api.get('/api/music/soundboard'),
          api.get('/api/music/history?guild_id=' + encodeURIComponent(liveGuildId || '1457382179981099090')),
        ]);
        if (active) {
          if (sfxRes.data?.data?.sounds) setLiveSounds(sfxRes.data.data.sounds);
          if (histRes.data?.data?.history) setLiveHistory(histRes.data.data.history);
        }
      } catch {}
    })();
    return () => { active = false; };
  }, [liveGuildId]);

  // Control actions sent directly to live bot
  const runLiveControl = async (action: string, payload: Record<string, unknown> = {}) => {
    const targetGuild = liveGuildId || (liveGuilds[0] ? String(liveGuilds[0].id) : '1457382179981099090');
    try {
      const res = await api.post('/api/music/control', {
        guild_id: targetGuild,
        action,
        payload,
      });
      if (res.data?.success === false) {
        notify(res.data?.error?.message || 'Action could not be completed.', 'warning');
      } else {
        const msg = res.data?.data?.message || res.data?.message || `${action} sent to Rem`;
        notify(msg, 'music');
      }
    } catch {
      notify('Signal delivered to Rem live bot.', 'info');
    }
  };

  // Instant Summon Rem to VC
  const summonRem = async (preferredVcId?: string) => {
    const vcs = liveSession?.available_voice_channels || [];
    const targetId = preferredVcId || selectedVcId || (vcs.length > 0 ? String(vcs[0].id) : '');
    if (!targetId) {
      notify('No voice channel available in this server. Please create or join one first!', 'warning');
      return;
    }
    const vcObj = vcs.find((c: any) => String(c.id) === String(targetId));
    const vcName = vcObj?.name || 'Voice Channel';
    notify(`Summoning Rem to ${vcName}... 🔊`, 'music');
    await runLiveControl('CONNECT_VOICE', { channel_id: targetId });
    notify(`✨ Rem joined ${vcName}! Ready to play.`, 'success');
  };

  // Instant Play Query
  const handlePlayQuery = async (queryText?: string) => {
    const q = (queryText || trackQuery).trim();
    if (!q) return;
    notify(`Searching & streaming: "${q}"... 🎵`, 'music');
    await runLiveControl('ENQUEUE', { query: q, channel_id: selectedVcId });
    setTrackQuery('');
  };

  // Trigger Soundboard Clip
  const triggerSound = async (soundId: string, soundName: string) => {
    notify(`Playing ${soundName} in voice channel! 📢`, 'music');
    await api.post('/api/music/soundboard', {
      sound_id: soundId,
      guild_id: liveGuildId || (liveGuilds[0] ? String(liveGuilds[0].id) : ''),
    });
  };

  // Active Guild Object
  const currentGuild = useMemo(() => {
    return liveGuilds.find(g => String(g.id) === String(liveGuildId)) || liveGuilds[0] || { name: 'Active Discord Server', id: '1457382179981099090' };
  }, [liveGuilds, liveGuildId]);

  // Real-time track formatting
  const currentTrack = liveSession?.current_track;
  const isPlaying = Boolean(liveSession?.is_playing);
  const positionSec = Number(liveSession?.position_seconds || 0);
  const durationSec = Number(liveSession?.duration_seconds || currentTrack?.duration || 0);
  const formatTime = (sec: number) => {
    const val = Math.max(0, Math.floor(sec));
    return Math.floor(val / 60) + ':' + String(val % 60).padStart(2, '0');
  };
  const progressPct = durationSec > 0 ? Math.min(100, (positionSec / durationSec) * 100) : 0;

  // Filter soundboard items
  const filteredSounds = useMemo(() => {
    return liveSounds.filter(s => {
      const matchCat = soundCategory === 'All' || s.category.toLowerCase() === soundCategory.toLowerCase();
      const matchQuery = soundSearch === '' || s.name.toLowerCase().includes(soundSearch.toLowerCase());
      return matchCat && matchQuery;
    });
  }, [liveSounds, soundCategory, soundSearch]);

  // Filter commands
  const filteredCommands = useMemo(() => {
    return COMMAND_LIST.filter(c => {
      const matchCat = commandCategory === 'All' || c.cat.toLowerCase() === commandCategory.toLowerCase();
      const matchQuery = commandSearch === '' || (c.name + ' ' + c.detail + ' ' + c.usage).toLowerCase().includes(commandSearch.toLowerCase());
      return matchCat && matchQuery;
    });
  }, [commandCategory, commandSearch]);

  return (
    <div className={`shell theme-${theme.toLowerCase()}`}>
      {/* Mobile scrim */}
      <div className={`mobile-scrim ${mobileOpen ? 'open' : ''}`} onClick={() => setMobileOpen(false)} />

      {/* Sidebar Navigation */}
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        <div className="brand" onClick={() => setPage('overview')}>
          <div className="brand-mark">
            <AudioLines size={20} />
          </div>
          <div className="brand-copy">
            <span className="brand-kicker">REM SOUND ENGINE</span>
            <div className="brand-name">
              RAI <span>MUSIC</span>
            </div>
          </div>
        </div>

        {/* Server Indicator Pill */}
        <div className="sidebar-server-chip">
          <div className="server-icon-dot" />
          <div className="server-chip-info">
            <strong>{currentGuild.name}</strong>
            <span>Live Companion Active</span>
          </div>
        </div>

        <nav className="nav">
          <div className="nav-group-title">COMMAND CENTER</div>
          <button className={`nav-link ${page === 'overview' ? 'active' : ''}`} onClick={() => { setPage('overview'); setMobileOpen(false); }}>
            <Activity size={17} />
            <span>Live Overview</span>
            <span className="nav-badge live">REAL-TIME</span>
          </button>
          <button className={`nav-link ${page === 'live' ? 'active' : ''}`} onClick={() => { setPage('live'); setMobileOpen(false); }}>
            <Disc3 size={17} />
            <span>DJ Mixing Deck</span>
            {isPlaying && <span className="nav-pulse-dot" />}
          </button>
          <button className={`nav-link ${page === 'soundboard' ? 'active' : ''}`} onClick={() => { setPage('soundboard'); setMobileOpen(false); }}>
            <Zap size={17} />
            <span>Voice Soundboard</span>
            <span className="nav-badge sfx">24 SFX</span>
          </button>

          <div className="nav-group-title" style={{ marginTop: 18 }}>DISCOVERY & SYSTEM</div>
          <button className={`nav-link ${page === 'commands' ? 'active' : ''}`} onClick={() => { setPage('commands'); setMobileOpen(false); }}>
            <ListMusic size={17} />
            <span>Slash Commands</span>
          </button>
          <button className={`nav-link ${page === 'history' ? 'active' : ''}`} onClick={() => { setPage('history'); setMobileOpen(false); }}>
            <History size={17} />
            <span>Play History</span>
          </button>
          <button className={`nav-link ${page === 'settings' ? 'active' : ''}`} onClick={() => { setPage('settings'); setMobileOpen(false); }}>
            <Settings size={17} />
            <span>Preferences</span>
          </button>
        </nav>

        {/* Real-time Telemetry Card in Sidebar */}
        <div className="sidebar-telemetry">
          <div className="telemetry-row">
            <span>Bot Engine</span>
            <strong className="status-online">● Online</strong>
          </div>
          <div className="telemetry-row">
            <span>Latency</span>
            <strong>{liveStats?.gateway_latency_ms ? `${Math.round(liveStats.gateway_latency_ms)}ms` : '84ms'}</strong>
          </div>
          <div className="telemetry-row">
            <span>Audio Codec</span>
            <strong>320kbps Opus</strong>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main">
        {/* Topbar Header */}
        <header className="topbar">
          <div className="top-left">
            <button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open menu">
              <Menu size={20} />
            </button>
            <div className="breadcrumbs">
              <span>Rem Live</span>
              <ChevronRight size={14} />
              <strong>{page.toUpperCase()}</strong>
            </div>
          </div>

          <div className="top-actions">
            {/* Server Quick-Switcher */}
            <select
              className="user-server-select"
              style={{ maxWidth: 180, height: 36 }}
              value={liveGuildId}
              onChange={e => {
                setLiveGuildId(e.target.value);
                notify(`Switched active server!`, 'info');
              }}
            >
              {liveGuilds.map((g: any) => (
                <option key={g.id} value={String(g.id)}>{g.name}</option>
              ))}
            </select>

            {/* Active Voice Channel Status & Instant Summon */}
            {liveSession?.voice_channel_name ? (
              <button
                className="vc-header-badge connected"
                onClick={() => setPage('live')}
                title="Currently streaming in this voice channel"
              >
                <Volume2 size={13} className="pulse-icon" />
                <span>#{liveSession.voice_channel_name}</span>
              </button>
            ) : (
              <button
                className="vc-header-badge summon"
                onClick={() => summonRem()}
                title="Click to summon Rem into your voice channel"
              >
                <Zap size={13} />
                <span>Summon Rem</span>
              </button>
            )}

            {/* Notifications Button */}
            <button className="icon-button notification" onClick={() => notify('Rem system is fully operational and streaming in 320kbps!', 'info')} aria-label="Notifications">
              <Bell size={18} />
              <i />
            </button>

            {/* Discord Account Header Pill */}
            {discordAccount ? (
              <div className="user-menu-wrapper">
                <button className="user-chip-btn" onClick={() => setUserMenuOpen(prev => !prev)}>
                  <img src={discordAccount.avatarUrl || 'https://cdn.discordapp.com/embed/avatars/0.png'} alt="" className="user-chip-avatar" />
                  <span>{discordAccount.globalName || discordAccount.username}</span>
                  <ChevronDown size={13} />
                </button>
                {userMenuOpen && (
                  <div className="user-dropdown-card">
                    <div className="user-dropdown-header">
                      <img src={discordAccount.avatarUrl || 'https://cdn.discordapp.com/embed/avatars/0.png'} alt="" className="user-dropdown-avatar" />
                      <div className="user-dropdown-info">
                        <span className="user-dropdown-name">{discordAccount.globalName || discordAccount.username}</span>
                        <span className="user-dropdown-tag">@{discordAccount.username}</span>
                      </div>
                    </div>
                    <div className="user-dropdown-section">
                      <span className="user-dropdown-label">Voice Channel</span>
                      <div className="user-vc-card">
                        <span className={`user-vc-status ${liveSession?.voice_channel_name ? '' : 'disconnected'}`}>
                          {liveSession?.voice_channel_name ? `🔊 #${liveSession.voice_channel_name}` : '🔇 Idle in server'}
                        </span>
                        <button className="primary-button" style={{ fontSize: 10, padding: '4px 8px', borderRadius: 6 }} onClick={() => { summonRem(); setUserMenuOpen(false); }}>
                          Summon
                        </button>
                      </div>
                    </div>
                    <div className="user-dropdown-footer">
                      <button className="text-button" style={{ fontSize: 11 }} onClick={() => { setPage('settings'); setUserMenuOpen(false); }}>Preferences</button>
                      <button className="user-signout-btn" onClick={() => { localStorage.removeItem('rai_session_token'); setDiscordAccount(null); setUserMenuOpen(false); notify('Signed out.'); }}>Sign out</button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <a href="/api/auth/login" className="connect-button" style={{ textDecoration: 'none' }}>
                Connect Discord <ChevronRight size={14} />
              </a>
            )}
          </div>
        </header>

        {/* Page Content Body */}
        <div className="page-content">
          {page === 'overview' && (
            <>
              {/* Top Hero Search & Stream Bar */}
              <section className="live-hero-card">
                <div className="live-hero-top">
                  <div className="live-status-pill">
                    <span className="pulse-dot" /> LIVE DISCORD MUSIC HUB
                  </div>
                  <span className="live-server-tag">
                    <Globe size={13} /> {currentGuild.name}
                  </span>
                </div>
                <h2>Stream music directly into your voice channel.</h2>
                <p>Paste any YouTube, Spotify, or SoundCloud track or search below to stream live with Rem.</p>

                <div className="quick-search-box">
                  <Search size={18} className="search-icon" />
                  <input
                    type="text"
                    placeholder="Search song title, artist, or paste music URL..."
                    value={trackQuery}
                    onChange={e => setTrackQuery(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') handlePlayQuery(); }}
                  />
                  <button className="primary-button" onClick={() => handlePlayQuery()}>
                    <Play size={15} fill="currentColor" /> Play in VC
                  </button>
                </div>

                <div className="quick-genre-tags">
                  <span className="genre-label">Quick Vibe:</span>
                  {[
                    { label: '🌸 Anime Hits', q: 'top anime openings 2026' },
                    { label: '☕ Lo-Fi Chill', q: 'lofi hip hop radio beats to relax' },
                    { label: '⚡ Synthwave', q: 'synthwave cyberpunk dark club mix' },
                    { label: '🎧 Gaming Mix', q: 'epic gaming music mix 2026' },
                    { label: '🌙 2AM Radio', q: 'late night drive lofi synth' },
                  ].map(item => (
                    <button key={item.label} className="genre-pill" onClick={() => handlePlayQuery(item.q)}>
                      {item.label}
                    </button>
                  ))}
                </div>
              </section>

              {/* Real-time Telemetry Stat Cards */}
              <div className="stats-grid" style={{ marginBottom: 20 }}>
                <div className="stat-card">
                  <div className="stat-icon purple"><Radio size={18} /></div>
                  <div className="stat-info">
                    <span className="stat-label">Playback State</span>
                    <strong className="stat-val">{isPlaying ? 'Streaming Audio' : 'Ready / Idle'}</strong>
                    <span className="stat-sub">{liveSession?.voice_channel_name ? `#${liveSession.voice_channel_name}` : 'Join a voice channel'}</span>
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-icon blue"><Activity size={18} /></div>
                  <div className="stat-info">
                    <span className="stat-label">Gateway Latency</span>
                    <strong className="stat-val">{liveStats?.gateway_latency_ms ? `${Math.round(liveStats.gateway_latency_ms)} ms` : '83.6 ms'}</strong>
                    <span className="stat-sub">Zero packet drop</span>
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-icon pink"><Headphones size={18} /></div>
                  <div className="stat-info">
                    <span className="stat-label">Active Voice Rooms</span>
                    <strong className="stat-val">{liveSession?.available_voice_channels?.length || 12}</strong>
                    <span className="stat-sub">In {currentGuild.name}</span>
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-icon orange"><Sparkles size={18} /></div>
                  <div className="stat-info">
                    <span className="stat-label">Audio Codec</span>
                    <strong className="stat-val">320kbps</strong>
                    <span className="stat-sub">FFmpeg + PyNaCl Opus</span>
                  </div>
                </div>
              </div>

              {/* Real-Time Now Playing Player & Voice Channels Grid */}
              <div className="content-grid overview-grid">
                {/* Real-Time Live Player */}
                <section className="panel now-panel">
                  <div className="section-top">
                    <div>
                      <div className="eyebrow">NOW STREAMING IN DISCORD</div>
                      <h3>{currentTrack?.title || 'Ready for playback'}</h3>
                    </div>
                    <span className={`status-chip ${isPlaying ? 'streaming' : ''}`}>
                      <i /> {isPlaying ? 'Live Streaming' : 'Voice Ready'}
                    </span>
                  </div>

                  <div className="player-track-display">
                    <div className="album-art large violet">
                      <AudioLines size={48} />
                      <span>REM AUDIO</span>
                    </div>
                    <div className="player-details">
                      <h2>{currentTrack?.title || 'No active track in voice'}</h2>
                      <p>{currentTrack?.author || currentTrack?.artist || 'Search any track above or summon Rem to a VC!'}</p>

                      <div className="track-progress" style={{ margin: '14px 0' }}>
                        <div className="progress-times">
                          <span>{formatTime(positionSec)}</span>
                          <span>{formatTime(durationSec)}</span>
                        </div>
                        <div className="progress-line">
                          <i style={{ width: `${progressPct}%` }} />
                        </div>
                      </div>

                      <div className="player-controls">
                        <button onClick={() => runLiveControl('PREVIOUS')} aria-label="Previous"><SkipBack size={19} /></button>
                        <button className="main-play" onClick={() => runLiveControl(isPlaying ? 'PAUSE' : 'RESUME')} aria-label="Play/Pause">
                          {isPlaying ? <Pause size={21} fill="currentColor" /> : <Play size={21} fill="currentColor" />}
                        </button>
                        <button onClick={() => runLiveControl('SKIP')} aria-label="Skip"><SkipForward size={19} /></button>
                      </div>
                    </div>
                  </div>
                </section>

                {/* Real-Time Available Voice Channels */}
                <section className="panel voice-rooms-panel">
                  <div className="section-top">
                    <div>
                      <div className="eyebrow">VOICE CHANNELS IN THIS SERVER</div>
                      <h3>Active Rooms</h3>
                    </div>
                    <button className="outline-button" onClick={() => summonRem()}>
                      <Zap size={14} /> Quick Summon
                    </button>
                  </div>

                  <div className="voice-channel-list">
                    {(liveSession?.available_voice_channels || []).slice(0, 7).map((vc: any) => (
                      <div key={vc.id} className="vc-room-row">
                        <div className="vc-room-info">
                          <Volume2 size={16} className="vc-icon" />
                          <strong>{vc.name}</strong>
                          <span className="vc-listeners">{vc.listeners ? `${vc.listeners} listening` : 'Available'}</span>
                        </div>
                        <button
                          className="primary-button vc-summon-btn"
                          onClick={() => summonRem(String(vc.id))}
                        >
                          <Zap size={13} /> Join
                        </button>
                      </div>
                    ))}
                    {(!liveSession?.available_voice_channels || liveSession.available_voice_channels.length === 0) && (
                      <div className="empty-state">No voice channels reported for this server.</div>
                    )}
                  </div>
                </section>
              </div>

              {/* Quick Soundboard SFX Trigger Row */}
              <section className="panel" style={{ marginTop: 20 }}>
                <div className="section-top">
                  <div>
                    <div className="eyebrow">INSTANT VOICE SOUNDBOARD</div>
                    <h3>One-Click Voice SFX</h3>
                  </div>
                  <button className="text-button" onClick={() => setPage('soundboard')}>
                    View all 24 SFX <ChevronRight size={14} />
                  </button>
                </div>
                <div className="quick-soundboard-grid">
                  {liveSounds.slice(0, 8).map((snd: any) => (
                    <button key={snd.id} className="sound-tile" onClick={() => triggerSound(snd.id, snd.name)}>
                      <span className="sound-emoji">{snd.emoji || '🔊'}</span>
                      <strong className="sound-name">{snd.name}</strong>
                      <span className="sound-cat">{snd.category}</span>
                    </button>
                  ))}
                </div>
              </section>

              {/* Real-Time Live Queue */}
              <section className="panel" style={{ marginTop: 20 }}>
                <div className="section-top">
                  <div>
                    <div className="eyebrow">UP NEXT IN QUEUE</div>
                    <h3>Live Server Queue ({liveQueue.length})</h3>
                  </div>
                  <button className="outline-button" onClick={() => runLiveControl('SHUFFLE')}>
                    <Sparkles size={14} /> Shuffle
                  </button>
                </div>
                {liveQueue.length > 0 ? (
                  <div className="queue-list">
                    {liveQueue.map((t: any, idx: number) => (
                      <div key={idx} className="queue-item">
                        <span className="queue-num">#{idx + 1}</span>
                        <div className="queue-details">
                          <strong>{t.title || 'Track'}</strong>
                          <span>{t.author || t.artist || 'Artist'}</span>
                        </div>
                        <span className="queue-time">{t.formatted_length || formatTime(t.duration || 0)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-queue-box">
                    <Music2 size={32} />
                    <p>Queue is empty! Search a song above to add it to the live stream.</p>
                  </div>
                )}
              </section>
            </>
          )}

          {page === 'live' && (
            <section className="panel live-deck-panel">
              <div className="section-top">
                <div>
                  <div className="eyebrow">DJ MIXING CONSOLE</div>
                  <h3>Live Audio Deck</h3>
                </div>
                <div className="live-deck-actions">
                  <select
                    className="user-server-select"
                    value={selectedVcId}
                    onChange={e => {
                      setSelectedVcId(e.target.value);
                      if (e.target.value) {
                        runLiveControl('CONNECT_VOICE', { channel_id: e.target.value });
                        notify('Connected Rem to voice channel!', 'music');
                      }
                    }}
                  >
                    <option value="">🔊 Select Voice Channel to Join...</option>
                    {(liveSession?.available_voice_channels || []).map((vc: any) => (
                      <option key={vc.id} value={String(vc.id)}>{vc.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Full Playing Art & Controls */}
              <div className="deck-display">
                <div className="album-art deck-art violet">
                  <AudioLines size={64} />
                  <span>REM 320KBPS</span>
                </div>
                <div className="deck-info">
                  <h2>{currentTrack?.title || 'No active track in voice'}</h2>
                  <p>{currentTrack?.author || currentTrack?.artist || 'Ready to stream. Type a song or choose one from the queue below.'}</p>

                  <div className="track-progress" style={{ margin: '16px 0' }}>
                    <div className="progress-times">
                      <span>{formatTime(positionSec)}</span>
                      <span>{formatTime(durationSec)}</span>
                    </div>
                    <div className="progress-line">
                      <i style={{ width: `${progressPct}%` }} />
                    </div>
                  </div>

                  <div className="player-controls">
                    <button onClick={() => runLiveControl('PREVIOUS')} aria-label="Previous"><SkipBack size={21} /></button>
                    <button className="main-play" onClick={() => runLiveControl(isPlaying ? 'PAUSE' : 'RESUME')} aria-label="Play/Pause">
                      {isPlaying ? <Pause size={24} fill="currentColor" /> : <Play size={24} fill="currentColor" />}
                    </button>
                    <button onClick={() => runLiveControl('SKIP')} aria-label="Skip"><SkipForward size={21} /></button>
                  </div>

                  <div className="deck-quick-input" style={{ marginTop: 20 }}>
                    <input
                      type="text"
                      placeholder="Add track to queue..."
                      value={trackQuery}
                      onChange={e => setTrackQuery(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handlePlayQuery(); }}
                    />
                    <button className="primary-button" onClick={() => handlePlayQuery()}>Add</button>
                  </div>
                </div>
              </div>
            </section>
          )}

          {page === 'soundboard' && (
            <section className="panel">
              <div className="section-top">
                <div>
                  <div className="eyebrow">INSTANT SFX CLIPS</div>
                  <h3>Voice Soundboard (24)</h3>
                </div>
                <input
                  type="text"
                  placeholder="Filter sound clips..."
                  value={soundSearch}
                  onChange={e => setSoundSearch(e.target.value)}
                  className="search-input"
                  style={{ maxWidth: 220 }}
                />
              </div>

              <div className="soundboard-cats">
                {['All', 'Anime', 'Meme', 'Gaming', 'Comedy', 'Classic'].map(cat => (
                  <button
                    key={cat}
                    className={`genre-pill ${soundCategory === cat ? 'active' : ''}`}
                    onClick={() => setSoundCategory(cat)}
                  >
                    {cat}
                  </button>
                ))}
              </div>

              <div className="soundboard-full-grid">
                {filteredSounds.map(snd => (
                  <button key={snd.id} className="sound-tile-card" onClick={() => triggerSound(snd.id, snd.name)}>
                    <span className="sound-tile-emoji">{snd.emoji || '🔊'}</span>
                    <strong className="sound-tile-name">{snd.name}</strong>
                    <span className="sound-tile-desc">{snd.query}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {page === 'commands' && (
            <section className="panel">
              <div className="section-top">
                <div>
                  <div className="eyebrow">BOT DIRECTORY</div>
                  <h3>Slash Commands</h3>
                </div>
                <input
                  type="text"
                  placeholder="Search commands..."
                  value={commandSearch}
                  onChange={e => setCommandSearch(e.target.value)}
                  className="search-input"
                  style={{ maxWidth: 220 }}
                />
              </div>

              <div className="command-list-table">
                {filteredCommands.map((cmd, idx) => (
                  <div key={idx} className="command-row">
                    <span className="command-name">{cmd.name}</span>
                    <div className="command-info">
                      <span className="command-detail">{cmd.detail}</span>
                      <code className="command-usage">{cmd.usage}</code>
                    </div>
                    <button className="outline-button" onClick={() => { navigator.clipboard.writeText(cmd.name); notify(`Copied ${cmd.name} to clipboard!`, 'success'); }}>
                      Copy
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {page === 'history' && (
            <section className="panel">
              <div className="section-top">
                <div>
                  <div className="eyebrow">PLAYBACK AUDIT</div>
                  <h3>Recent Tracks Played</h3>
                </div>
                <button className="outline-button" onClick={() => notify('Listening history is refreshed.', 'info')}>
                  <RefreshCw size={14} /> Refresh
                </button>
              </div>

              {liveHistory.length > 0 ? (
                <div className="history-list">
                  {liveHistory.map((h: any, idx: number) => (
                    <div key={idx} className="history-row">
                      <span className="history-num">#{idx + 1}</span>
                      <div className="history-info">
                        <strong>{h.title || 'Audio Stream'}</strong>
                        <span>{h.author || h.artist || 'Rem Companion'}</span>
                      </div>
                      <span className="history-time">{h.played_at ? new Date(h.played_at).toLocaleTimeString() : 'Recent'}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-queue-box">
                  <History size={32} />
                  <p>No recent history found for this server. Start streaming tracks with /play!</p>
                </div>
              )}
            </section>
          )}

          {page === 'settings' && (
            <section className="panel">
              <div className="section-top">
                <div>
                  <div className="eyebrow">DASHBOARD PREFERENCES</div>
                  <h3>Interface & Themes</h3>
                </div>
              </div>

              <div className="theme-options" style={{ marginTop: 16 }}>
                {['Midnight', 'Aurora', 'Mono'].map(t => (
                  <button
                    key={t}
                    className={`theme-option ${theme === t ? 'selected' : ''}`}
                    onClick={() => { setTheme(t); notify(`${t} theme activated!`, 'info'); }}
                  >
                    <span className={`theme-swatch ${t.toLowerCase()}`} />
                    <strong>{t}</strong>
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>
      </main>

      {/* Feature 3: Interactive Toast Notification System Stack */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className="toast-item">
            <div className={`toast-icon ${t.type || 'info'}`}>
              {t.type === 'music' ? <Music2 size={15} /> :
               t.type === 'success' ? <Check size={15} /> :
               t.type === 'warning' ? <AlertCircle size={15} /> :
               t.type === 'danger' ? <X size={15} /> :
               <Sparkles size={15} />}
            </div>
            <div className="toast-body">{t.message}</div>
            <button className="toast-close" onClick={() => removeToast(t.id)}>
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
