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
  CircleHelp,
  Command,
  Disc3,
  Headphones,
  Heart,
  Home,
  History,
  Users,
  BellRing,
  Palette,
  ListMusic,
  Menu,
  Moon,
  MoreHorizontal,
  Music2,
  Pause,
  Play,
  Plus,
  Radio,
  Search,
  Settings,
  ShieldCheck,
  SkipBack,
  SkipForward,
  SlidersHorizontal,
  Sparkles,
  Volume2,
  WandSparkles,
  X,
  Zap,
} from 'lucide-react';

type Page =
  | 'overview'
  | 'live'
  | 'servers'
  | 'commands'
  | 'rem'
  | 'analytics'
  | 'history'
  | 'members'
  | 'notifications'
  | 'settings';

const tracks = [
  {
    title: 'KALYANI',
    artist: 'ARJN, Shreya Ghoshal',
    time: '3:42',
    tint: 'violet',
  },
  { title: 'Blue Bird', artist: 'Ikimono-gakari', time: '3:35', tint: 'blue' },
  { title: 'After Dark', artist: 'Mr.Kitty', time: '4:17', tint: 'pink' },
  { title: 'Snowfall', artist: 'Øneheart', time: '2:11', tint: 'ice' },
];
const commandData = [
  [
    '/play',
    'Music',
    'Play a song or add it to the queue',
    '/play <song or URL>',
  ],
  ['/pause', 'Music', 'Pause the current track', '/pause'],
  ['/resume', 'Music', 'Resume playback', '/resume'],
  ['/skip', 'Music', 'Skip to the next track', '/skip'],
  ['/queue', 'Music', 'View the upcoming queue', '/queue'],
  ['/volume', 'Music', 'Set playback volume', '/volume <0–100>'],
  ['/autoplay', 'Music', 'Toggle automatic recommendations', '/autoplay'],
  ['/lyrics', 'Discovery', 'Find lyrics for a track', '/lyrics <song>'],
  ['/radio2am', 'Discovery', 'Start a late-night radio vibe', '/radio2am'],
  [
    '/songmemory',
    'Community',
    'Save or revisit a song memory',
    '/songmemory save <song>',
  ],
  ['/rembond', 'Community', 'Check your bond level with Rem', '/rembond'],
  ['/help', 'Utility', 'Explore bot commands', '/help'],
].map(([name, category, detail, usage]) => ({ name, category, detail, usage }));

const navGroups = [
  {
    label: 'WORKSPACE',
    items: [
      { id: 'overview' as Page, label: 'Overview', icon: Home },
      { id: 'live' as Page, label: 'Live music', icon: AudioLines },
      { id: 'servers' as Page, label: 'Servers', icon: Disc3 },
      { id: 'members' as Page, label: 'Members', icon: Users },
      { id: 'history' as Page, label: 'Play history', icon: History },
    ],
  },
  {
    label: 'DISCOVER',
    items: [
      { id: 'rem' as Page, label: 'Rem AI', icon: Sparkles },
      { id: 'commands' as Page, label: 'Commands', icon: Command },
      { id: 'analytics' as Page, label: 'Analytics', icon: BarChart3 },
      { id: 'notifications' as Page, label: 'Notifications', icon: BellRing },
    ],
  },
  {
    label: 'PREFERENCES',
    items: [{ id: 'settings' as Page, label: 'Settings', icon: Settings }],
  },
];

function App() {
  const [page, setPage] = useState<Page>('overview');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [playing, setPlaying] = useState(true);
  const [autoplay, setAutoplay] = useState(true);
  const [volume, setVolume] = useState(72);
  const [activeTrack, setActiveTrack] = useState(0);
  const [mood, setMood] = useState('Chill');
  const [commandSearch, setCommandSearch] = useState('');
  const [commandCategory, setCommandCategory] = useState('All');
  const [globalSearch, setGlobalSearch] = useState('');
  const [server, setServer] = useState('rai fam');
  interface ToastItem {
    id: string;
    message: string;
    type?: 'info' | 'success' | 'warning' | 'music' | 'danger';
  }
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [showAllQueue, setShowAllQueue] = useState(false);
  const [settings, setSettings] = useState({
    notifications: true,
    compact: false,
    publicStats: false,
    safeMode: true,
  });
  const [channel, setChannel] = useState('music-room');
  const [djRole, setDjRole] = useState('MusicMaid DJ');
  const [saved, setSaved] = useState(false);
  const [theme, setTheme] = useState('Midnight');
  const [discordAccount, setDiscordAccount] = useState<any | null>(null);
  const [discordGuilds, setDiscordGuilds] = useState<any[]>([]);
  const [botStatus, setBotStatus] = useState<any | null>(null);
  const [connectionLoading, setConnectionLoading] = useState(true);
  const [connectionError, setConnectionError] = useState('');
  const [liveGuildId, setLiveGuildId] = useState('');
  const [liveSession, setLiveSession] = useState<any | null>(null);
  const [liveQueue, setLiveQueue] = useState<any[]>([]);
  const [liveGuilds, setLiveGuilds] = useState<any[]>([]);
  const [liveBridgeReady, setLiveBridgeReady] = useState(false);
  const [liveBridgeError, setLiveBridgeError] = useState('');

  const notify = (message: string, type: 'info' | 'success' | 'warning' | 'music' | 'danger' = 'info') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => [...prev.slice(-3), { id, message, type }]);
    window.setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3500);
  };
  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  const summonRem = async (preferredVcId?: string) => {
    const channels = liveSession?.available_voice_channels || [];
    const target = preferredVcId || (channels.length > 0 ? String(channels[0].id) : '');
    if (!target) {
      notify('No voice channels found in this server. Please create or join one first!', 'warning');
      return;
    }
    const vcObj = channels.find((c: any) => String(c.id) === String(target));
    const vcName = vcObj?.name || 'Voice Channel';
    notify(`Summoning Rem to #${vcName}... 🔊`, 'music');
    await runLiveControl('CONNECT_VOICE', { channel_id: target });
    notify(`✨ Rem connected to #${vcName}! Ready to play.`, 'success');
  };

  useEffect(() => {
    let active = true;
    const loadConnections = async () => {
      const query = new URLSearchParams(window.location.search);
      const incomingToken = query.get('token') || query.get('session_token');
      if (incomingToken) {
        try { localStorage.setItem('rai_session_token', incomingToken); } catch {}
      }
      const code = query.get('code');
      const state = query.get('state');

      if (code || state) {
        query.delete('code');
        query.delete('state');
        const cleanUrl = window.location.pathname +
          (query.toString() ? '?' + query.toString() : '') + window.location.hash;
        window.history.replaceState({}, '', cleanUrl);
        try {
          if (!code || !state) throw new Error('Discord callback is missing code or state.');
          const callback = await api.post('/api/auth/callback', { code, state });
          if (callback.data?.sessionId) {
            try { localStorage.setItem('rai_session_token', callback.data.sessionId); } catch {}
          }
          if (!callback.data?.connected) {
            throw new Error(callback.data?.error || 'Discord sign-in was not completed.');
          }
        } catch (error) {
          if (active) {
            const message = error instanceof Error ? error.message : 'Unknown callback error';
            setConnectionError('Discord sign-in failed: ' + message);
          }
        }
      }

      const [discordResult, botResult] = await Promise.allSettled([
        api.get('/api/auth/me'),
        api.get('/api/bot/status'),
      ]);
      if (!active) return;

      if (discordResult.status === 'fulfilled') {
        const data = discordResult.value.data;
        if (data?.signedIn && data.user) {
          if (data.sessionId) {
            try { localStorage.setItem('rai_session_token', data.sessionId); } catch {}
          }
          setDiscordAccount(data.user);
          setDiscordGuilds(Array.isArray(data.guilds) ? data.guilds : []);
        } else {
          setDiscordAccount(null);
          setDiscordGuilds([]);
        }
      } else {
        setConnectionError('Discord account status could not be loaded.');
      }

      if (botResult.status === 'fulfilled') {
        setBotStatus(botResult.value.data);
      } else {
        setBotStatus({ reachable: false, botStatus: 'unavailable' });
      }

      const errorParam = query.get('error');
      const detailsParam = query.get('details');
      if (errorParam === 'oauth_exchange_failed') {
        setConnectionError(`Discord sign-in failed: ${detailsParam || 'Discord rejected authorization code'}`);
      } else if (errorParam) {
        setConnectionError(`Sign-in notice: ${errorParam} ${detailsParam || ''}`.trim());
      } else if (query.get('discord') === 'error') {
        setConnectionError('Discord sign-in failed. Please reconnect and check the OAuth redirect URL.');
      } else if (query.get('discord') === 'connected') {
        setConnectionError('');
      }
      if (query.has('discord')) {
        query.delete('discord');
        const nextUrl = window.location.pathname +
          (query.toString() ? '?' + query.toString() : '') + window.location.hash;
        window.history.replaceState({}, '', nextUrl);
      }
      setConnectionLoading(false);
    };
    loadConnections();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!discordAccount) {
      setLiveSession(null);
      setLiveQueue([]);
      setLiveGuilds([]);
      setLiveBridgeReady(false);
      return;
    }
    let active = true;
    const refresh = async () => {
      try {
        const guildResponse = await api.get('/api/music/guilds');
        const guilds = guildResponse.data?.data?.guilds ?? [];
        const available = guilds.filter((guild: any) => guild.bot_in_guild);
        if (active) setLiveGuilds(available);
        if (!available.length) {
          if (active) {
            setLiveBridgeReady(true);
            setLiveSession(null);
            setLiveQueue([]);
            setLiveBridgeError('MusicMaid is not in an accessible server.');
          }
          return;
        }
        const selected = available.some((guild: any) => String(guild.id) === liveGuildId)
          ? liveGuildId
          : String(available[0].id);
        if (!liveGuildId && active) setLiveGuildId(selected);
        const [session, queue] = await Promise.all([
          api.get('/api/music/session?guild_id=' + encodeURIComponent(selected)),
          api.get('/api/music/queue?guild_id=' + encodeURIComponent(selected)),
        ]);
        if (!active) return;
        const data = session.data?.data ?? null;
        setLiveSession(data);
        setLiveQueue(queue.data?.data?.tracks ?? []);
        setLiveBridgeReady(true);
        setLiveBridgeError('');
        if (typeof data?.volume === 'number') setVolume(data.volume);
        if (typeof data?.auto_dj === 'boolean') setAutoplay(data.auto_dj);
        if (typeof data?.is_playing === 'boolean') setPlaying(data.is_playing);
      } catch (error) {
        if (!active) return;
        setLiveBridgeReady(false);
        setLiveBridgeError(error instanceof Error ? error.message : 'Bot bridge unavailable');
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [discordAccount, liveGuildId]);

  const runLiveControl = async (action: string, payload: Record<string, unknown> = {}) => {
    if (!liveGuildId) return notify('No MusicMaid server is selected.');
    if (!liveBridgeReady) return notify('MusicMaid bridge is offline. Controls are disabled until it reconnects.');
    try {
      const response = await api.post('/api/music/control', { guild_id: liveGuildId, action, payload });
      if (response.data?.success === false) throw new Error(response.data?.error?.message || 'Action rejected');
      notify('MusicMaid: ' + action.toLowerCase().replaceAll('_', ' ') + ' sent.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Control failed';
      setLiveBridgeError(message);
      notify(message);
    }
  };

  const connectDiscord = () => {
    setConnectionError('');
    window.location.assign('/api/auth/login');
  };

  const disconnectDiscord = async () => {
    try {
      try { localStorage.removeItem('rai_session_token'); } catch {}
      await api.post('/api/auth/logout');
      setDiscordAccount(null);
      setDiscordGuilds([]);
      setConnectionError('');
      notify('Discord account disconnected.');
    } catch {
      setConnectionError('Could not sign out. Please try again.');
    }
  };
  const filteredCommands = useMemo(
    () =>
      commandData.filter(
        item =>
          (item.name + ' ' + item.detail + ' ' + item.usage)
            .toLowerCase()
            .includes(commandSearch.toLowerCase()) &&
          (commandCategory === 'All' || item.category === commandCategory)
      ),
    [commandSearch, commandCategory]
  );
  const go = (next: Page) => {
    setPage(next);
    setMobileOpen(false);
  };
  const changeTrack = (direction: number) => {
    setActiveTrack(
      current => (current + direction + tracks.length) % tracks.length
    );
    setPlaying(true);
  };
  const titleMap: Record<Page, string> = {
    overview: 'Overview',
    live: 'Live music',
    servers: 'Server settings',
    commands: 'Command center',
    rem: 'Rem AI',
    analytics: 'Analytics',
    history: 'Play history',
    members: 'Members & roles',
    notifications: 'Notifications',
    settings: 'Preferences',
  };

  return (
    <div className={'shell theme-' + theme.toLowerCase()}>
      {mobileOpen && (
        <button
          className="mobile-scrim"
          aria-label="Close menu"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className={'sidebar ' + (mobileOpen ? 'sidebar-open' : '')}>
        <div className="brand">
          <div className="brand-mark">
            <Headphones size={21} strokeWidth={2.5} />
          </div>
          <div>
            <div className="brand-name">
              RAI<span> MUSIC</span>
            </div>
            <div className="brand-sub">THE SOUND OF YOUR SERVER</div>
          </div>
          <button
            className="icon-button sidebar-close"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>
        <div
          className="server-switch"
          onClick={() => go('servers')}
          role="button"
          tabIndex={0}
        >
          <div className="server-avatar">R</div>
          <div className="server-meta">
            <strong>{server}</strong>
            <span>Preview workspace</span>
          </div>
          <ChevronDown size={15} className="muted" />
        </div>
        <nav className="nav-groups">
          {navGroups.map(group => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.items.map(item => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    className={'nav-item ' + (page === item.id ? 'active' : '')}
                    onClick={() => go(item.id)}
                  >
                    <Icon size={17} />
                    <span>{item.label}</span>
                    {item.id === 'live' && <i className="nav-live-dot" />}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="rem-card">
            <div className="rem-orb">
              <Sparkles size={18} />
            </div>
            <div>
              <strong>Rem is here</strong>
              <span>Ready to find your vibe?</span>
            </div>
            <button
              className="tiny-arrow"
              onClick={() => go('rem')}
              aria-label="Open Rem AI"
            >
              <ChevronRight size={16} />
            </button>
          </div>
          <div className="profile-row">
            <div className="profile-avatar">K</div>
            <div className="profile-meta">
              <strong>Server owner</strong>
              <span>Preview account</span>
            </div>
            <MoreHorizontal size={18} className="muted" />
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="top-left">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={20} />
            </button>
            <div className="breadcrumbs">
              <span>Workspace</span>
              <ChevronRight size={14} />
              <strong>{titleMap[page]}</strong>
            </div>
          </div>
          <div className="top-actions">
            <label className="searchbox">
              <Search size={16} />
              <input
                value={globalSearch}
                onChange={e => setGlobalSearch(e.target.value)}
                placeholder="Search anything..."
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    setCommandSearch(globalSearch);
                    go('commands');
                  }
                }}
              />
              <kbd>⌘ K</kbd>
            </label>

            {/* Feature 2: Active Voice Channel Badge & Instant Summon Rem */}
            {liveSession?.voice_channel_name ? (
              <button
                className="vc-header-badge connected"
                onClick={() => go('live')}
                title="Click to manage playback in this voice channel"
              >
                <Volume2 size={13} className="pulse-icon" />
                <span>#{liveSession.voice_channel_name}</span>
              </button>
            ) : (
              <button
                className="vc-header-badge summon"
                onClick={() => summonRem()}
                title="Instantly summon Rem into your voice channel"
              >
                <Zap size={13} />
                <span>Summon Rem</span>
              </button>
            )}

            <button
              className="icon-button notification"
              onClick={() => go('notifications')}
              aria-label="Open notifications"
            >
              <Bell size={18} />
              <i />
            </button>

            {/* Feature 1: Header Avatar & Active Server/VC Dropdown */}
            {discordAccount ? (
              <div className="user-menu-wrapper">
                <button
                  className="user-chip-btn"
                  onClick={() => setUserMenuOpen(prev => !prev)}
                  aria-label="User profile and server menu"
                >
                  <img
                    src={discordAccount.avatarUrl || 'https://cdn.discordapp.com/embed/avatars/0.png'}
                    alt=""
                    className="user-chip-avatar"
                  />
                  <span>{discordAccount.globalName || discordAccount.username}</span>
                  <ChevronDown size={13} />
                </button>
                {userMenuOpen && (
                  <div className="user-dropdown-card">
                    <div className="user-dropdown-header">
                      <img
                        src={discordAccount.avatarUrl || 'https://cdn.discordapp.com/embed/avatars/0.png'}
                        alt=""
                        className="user-dropdown-avatar"
                      />
                      <div className="user-dropdown-info">
                        <span className="user-dropdown-name">{discordAccount.globalName || discordAccount.username}</span>
                        <span className="user-dropdown-tag">@{discordAccount.username}</span>
                      </div>
                    </div>
                    <div className="user-dropdown-section">
                      <span className="user-dropdown-label">Active Server</span>
                      <select
                        className="user-server-select"
                        value={liveGuildId}
                        onChange={e => {
                          setLiveGuildId(e.target.value);
                          notify('Switched active server!', 'info');
                        }}
                      >
                        {liveGuilds.length === 0 && <option value="">No bot servers found</option>}
                        {liveGuilds.map((g: any) => (
                          <option key={g.id} value={String(g.id)}>{g.name}</option>
                        ))}
                      </select>
                    </div>
                    <div className="user-dropdown-section">
                      <span className="user-dropdown-label">Voice Channel</span>
                      <div className="user-vc-card">
                        <span className={`user-vc-status ${liveSession?.voice_channel_name ? '' : 'disconnected'}`}>
                          {liveSession?.voice_channel_name ? (
                            <>
                              <Volume2 size={13} /> #{liveSession.voice_channel_name}
                            </>
                          ) : (
                            '🔇 Not in VC'
                          )}
                        </span>
                        <button
                          className="primary-button"
                          style={{ fontSize: 10, padding: '4px 8px', borderRadius: 6 }}
                          onClick={() => {
                            summonRem();
                            setUserMenuOpen(false);
                          }}
                        >
                          Summon
                        </button>
                      </div>
                    </div>
                    <div className="user-dropdown-footer">
                      <button
                        className="text-button"
                        style={{ fontSize: 11 }}
                        onClick={() => {
                          go('settings');
                          setUserMenuOpen(false);
                        }}
                      >
                        Preferences
                      </button>
                      <button
                        className="user-signout-btn"
                        onClick={() => {
                          disconnectDiscord();
                          setUserMenuOpen(false);
                        }}
                      >
                        Sign out
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <button className="connect-button" onClick={connectDiscord}>
                Connect Discord <ChevronRight size={15} />
              </button>
            )}
          </div>
        </header>
        <div className="page-content">
          <ConnectionPanel
            discordAccount={discordAccount}
            guilds={discordGuilds}
            botStatus={botStatus}
            loading={connectionLoading}
            error={connectionError}
            onConnect={connectDiscord}
            onDisconnect={disconnectDiscord}
          />
          {page === 'overview' && (
            <Overview
              go={go}
              playing={playing}
              setPlaying={setPlaying}
              activeTrack={activeTrack}
            />
          )}
          {page === 'live' && (
            <LiveMusic
              playing={playing}
              setPlaying={setPlaying}
              volume={volume}
              setVolume={setVolume}
              activeTrack={activeTrack}
              changeTrack={changeTrack}
              autoplay={autoplay}
              setAutoplay={setAutoplay}
              showAllQueue={showAllQueue}
              setShowAllQueue={setShowAllQueue}
              notify={notify}
              liveSession={liveSession}
              liveQueue={liveQueue}
              liveGuilds={liveGuilds}
              liveGuildId={liveGuildId}
              setLiveGuildId={setLiveGuildId}
              liveBridgeReady={liveBridgeReady}
              liveBridgeError={liveBridgeError}
              onControl={runLiveControl}
            />
          )}
          {page === 'servers' && (
            <Servers
              server={server}
              setServer={setServer}
              channel={channel}
              setChannel={setChannel}
              djRole={djRole}
              setDjRole={setDjRole}
              saved={saved}
              setSaved={setSaved}
              notify={notify}
            />
          )}
          {page === 'commands' && (
            <Commands
              search={commandSearch}
              setSearch={setCommandSearch}
              category={commandCategory}
              setCategory={setCommandCategory}
              commands={filteredCommands}
            />
          )}
          {page === 'rem' && (
            <RemAI mood={mood} setMood={setMood} notify={notify} />
          )}
          {page === 'analytics' && <Analytics />}
          {page === 'history' && <HistoryPage notify={notify} />}
          {page === 'members' && <MembersPage guilds={discordGuilds} discordAccount={discordAccount} notify={notify} />}
          {page === 'notifications' && <NotificationsPage botStatus={botStatus} />}
          {page === 'settings' && (
            <SettingsPage
              settings={settings}
              setSettings={setSettings}
              notify={notify}
              discordAccount={discordAccount}
              theme={theme}
              setTheme={setTheme}
            />
          )}
        </div>
        <footer className="footer">
          <span>© 2026 Rai Music</span>
          <span>
            <i className="footer-dot" />
            {discordAccount
              ? 'Discord connected · Music controls are in preview'
              : 'Preview mode · Music controls are in preview'}
          </span>
          <button onClick={() => go('commands')}>
            <CircleHelp size={14} /> Help center
          </button>
        </footer>
      </main>
      {liveSession?.current_track && (
        <div className="mini-player">
          <div className="mini-track">
            <div className="mini-cover violet"><Music2 size={17} /></div>
            <div className="mini-info">
              <strong>{liveSession.current_track.title || 'Now playing'}</strong>
              <span>{liveSession.current_track.artist || 'MusicMaid'}</span>
            </div>
          </div>
          <div className="mini-controls">
            <div className="mini-buttons">
              <button className="mini-play" onClick={() => runLiveControl(playing ? 'PAUSE' : 'RESUME')} aria-label={playing ? 'Pause' : 'Resume'}>
                {playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
              </button>
              <button onClick={() => runLiveControl('SKIP')} aria-label="Skip"><SkipForward size={16} /></button>
            </div>
          </div>
        </div>
      )
      }
      {/* Feature 3: Interactive Toast Notification System */}
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

function ConnectionPanel({
  discordAccount,
  guilds,
  botStatus,
  loading,
  error,
  onConnect,
  onDisconnect,
}: any) {
  const botReachable = Boolean(botStatus?.reachable);
  const botOnline = botStatus?.botStatus === 'online';

  return (
    <section className="connection-panel">
      <div className="connection-card">
        <div className="connection-card-top">
          <div>
            <div className="eyebrow">DISCORD ACCOUNT</div>
            <h3>{discordAccount ? 'Your Discord' : 'Connect your Discord'}</h3>
          </div>
          <span className={'connection-state ' + (discordAccount ? 'connected' : '')}>
            {loading ? 'Checking' : discordAccount ? 'Connected' : 'Not linked'}
          </span>
        </div>
        {loading ? (
          <p className="connection-muted">Checking your secure connection…</p>
        ) : discordAccount ? (
          <>
            <div className="connection-identity">
              <img src={discordAccount.avatarUrl} alt="" />
              <div>
                <strong>{discordAccount.globalName || discordAccount.username}</strong>
                <span>@{discordAccount.username} · {guilds.length} accessible servers</span>
              </div>
              <button className="connection-signout" onClick={onDisconnect}>Sign out</button>
            </div>
            <div className="guild-list">
              {guilds.slice(0, 5).map((guild: any) => (
                <span className="guild-chip" key={guild.id}>
                  {guild.iconUrl && <img src={guild.iconUrl} alt="" />}
                  {guild.name}
                </span>
              ))}
              {guilds.length > 5 && <span className="guild-chip more-guilds">+{guilds.length - 5} more</span>}
              {guilds.length === 0 && <span className="connection-muted">No servers were returned for this Discord account.</span>}
            </div>
          </>
        ) : (
          <div className="connection-empty">
            <p>Sign in to show your Discord identity and the servers you can access.</p>
            <button className="primary-button" onClick={onConnect}>
              <ShieldCheck size={15} /> Continue with Discord
            </button>
          </div>
        )}
        {error && <p className="connection-error">{error}</p>}
        <p className="connection-footnote">Requests only: identify + guilds. No server permissions are granted.</p>
      </div>
      <div className="connection-card bot-connection-card">
        <div className="connection-card-top">
          <div>
            <div className="eyebrow">MUSICMAID SERVICE</div>
            <h3>Bot health</h3>
          </div>
          <span className={'connection-state ' + (botOnline ? 'connected' : '')}>
            {loading ? 'Checking' : !botReachable ? 'Unavailable' : botOnline ? 'Online' : 'Starting'}
          </span>
        </div>
        <div className="bot-health-line">
          <span className={'bot-health-dot ' + (botOnline ? 'online' : '')} />
          <strong>{!botReachable ? 'Health check unavailable' : botOnline ? 'MusicMaid is online' : 'MusicMaid is starting'}</strong>
        </div>
        <div className="bot-health-details">
          <span>Voice engine</span>
          <strong>{botReachable ? (botStatus.voiceReady ? 'Ready' : 'Not ready') : 'Unknown'}</strong>
          <span>Database</span>
          <strong>{botReachable ? botStatus.databaseStatus : 'Unknown'}</strong>
        </div>
        <p className="connection-footnote">Read-only health check. No playback, queue, or voice actions are sent.</p>
      </div>
    </section>
  );
}

function PageHeading({
  eyebrow,
  title,
  subtitle,
  action,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action && <div className="heading-action">{action}</div>}
    </div>
  );
}
function StatCard({
  icon,
  label,
  value,
  note,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  note: string;
  tone: string;
}) {
  return (
    <div className="stat-card">
      <div className={'stat-icon ' + tone}>{icon}</div>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-note">{note}</div>
    </div>
  );
}
function QuickCard({
  icon,
  title,
  desc,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
  onClick: () => void;
}) {
  return (
    <button className="quick-card" onClick={onClick}>
      <div className="quick-icon">{icon}</div>
      <div>
        <strong>{title}</strong>
        <span>{desc}</span>
      </div>
      <ChevronRight size={17} />
    </button>
  );
}

function Overview({ go, playing, setPlaying, activeTrack }: any) {
  return (
    <>
      <PageHeading
        eyebrow="YOUR MUSIC COMMAND CENTER"
        title="Good evening, Kishore."
        subtitle="Your server's soundtrack starts here. Here's what's happening with Rem."
        action={
          <button className="outline-button" onClick={() => go('servers')}>
            <SlidersHorizontal size={15} /> Manage server
          </button>
        }
      />
      <section className="hero-panel">
        <div className="hero-glow" />
        <div className="hero-copy">
          <div className="hero-tag">
            <span className="pulse-dot" /> YOUR MUSIC, YOUR WORLD
          </div>
          <h2>
            Turn your server
            <br />
            into a <em>soundtrack.</em>
          </h2>
          <p>
            One home for music, discovery, and the moments your community
            shares.          </p>
          <div className="hero-actions">
            <button className="primary-button" onClick={() => go('live')}>
              <AudioLines size={16} /> Open music hub
            </button>
            <button className="text-button" onClick={() => go('rem')}>
              Meet Rem AI <ChevronRight size={15} />
            </button>
          </div>
        </div>
        <div className="hero-art">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="hero-disc">
            <div className="disc-inner">
              <div className="disc-face">玲</div>
            </div>
          </div>
          <div className="floating-note note-one">♫</div>
          <div className="floating-note note-two">✦</div>
          <div className="art-caption">
            <span>REM'S FREQUENCY</span>
            <strong>Stay in your element.</strong>
          </div>
        </div>
        <div className="hero-bottom">
          <span>
            <i /> Rem is ready in this preview
          </span>
          <span>01 / YOUR WORKSPACE</span>
        </div>
      </section>
      <div className="stats-grid">
        <StatCard
          icon={<Radio size={17} />}
          label="Active sessions"
          value="03"
          note="Sample server data"
          tone="purple"
        />
        <StatCard
          icon={<Music2 size={17} />}
          label="Tracks played today"
          value="128"
          note="+12% from yesterday"
          tone="blue"
        />
        <StatCard
          icon={<Headphones size={17} />}
          label="Listeners"
          value="24"
          note="Across demo servers"
          tone="pink"
        />
        <StatCard
          icon={<Heart size={17} />}
          label="Saved memories"
          value="56"
          note="Community favourites"
          tone="orange"
        />
      </div>
      <div className="content-grid overview-grid">
        <section className="panel now-panel">
          <div className="section-top">
            <div>
              <div className="eyebrow">THE SOUND RIGHT NOW</div>
              <h3>Now playing</h3>
            </div>
            <span className="demo-tag">DEMO SESSION</span>
          </div>
          <div className="now-content">
            <div className={'album-art large ' + tracks[activeTrack].tint}>
              <AudioLines size={42} />
              <span>
                RAI
                <br />
                RADIO
              </span>
            </div>
            <div className="now-details">
              <div className="track-kicker">FEATURED TRACK</div>
              <h2>{tracks[activeTrack].title}</h2>
              <p>{tracks[activeTrack].artist}</p>
              <div className="waveform">
                {Array.from({ length: 34 }, (_, i) => (
                  <i key={i} style={{ height: 12 + ((i * 17) % 31) + 'px' }} />
                ))}
              </div>
              <div className="now-meta">
                <span>
                  <Disc3 size={13} /> rai fam · music-room
                </span>
                <span>02:14 / 03:42</span>
              </div>
              <div className="now-buttons">
                <button
                  className="play-button"
                  onClick={() => setPlaying(!playing)}
                >
                  {playing ? (
                    <Pause size={16} fill="currentColor" />
                  ) : (
                    <Play size={16} fill="currentColor" />
                  )}
                  {playing ? 'Pause preview' : 'Play preview'}
                </button>
                <button
                  className="icon-button dark-icon"
                  onClick={() => go('live')}
                  aria-label="Open player"
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          </div>
        </section>
        <section className="panel activity-panel">
          <div className="section-top">
            <div>
              <div className="eyebrow">COMMUNITY PULSE</div>
              <h3>Listening activity</h3>
            </div>
            <button className="more-button" onClick={() => go('analytics')}>
              <MoreHorizontal size={19} />
            </button>
          </div>
          <div className="activity-number">
            24 <span>listeners today</span>
          </div>
          <div className="activity-chart">
            {[
              22, 34, 29, 48, 38, 57, 45, 67, 51, 72, 61, 85, 66, 91, 73, 59,
              77, 64, 86, 68, 95, 71, 82, 62,
            ].map((v, i) => (
              <i key={i} style={{ height: v + '%' }} />
            ))}
          </div>
          <div className="chart-labels">
            <span>12 AM</span>
            <span>6 AM</span>
            <span>12 PM</span>
            <span>6 PM</span>
            <span>NOW</span>
          </div>
          <div className="activity-foot">
            <span>
              <i className="legend-dot" /> Listening minutes
            </span>
            <strong>+18.4%</strong>
          </div>
        </section>
      </div>
      <div className="section-heading">
        <div>
          <div className="eyebrow">MAKE IT YOURS</div>
          <h3>Jump back in</h3>
        </div>
        <button className="text-button" onClick={() => go('commands')}>
          Explore commands <ChevronRight size={15} />
        </button>
      </div>
      <div className="quick-grid">
        <QuickCard
          icon={<WandSparkles />}
          title="Find your mood"
          desc="Let Rem pick the vibe."
          onClick={() => go('rem')}
        />
        <QuickCard
          icon={<ListMusic />}
          title="Manage the queue"
          desc="See what's coming next."
          onClick={() => go('live')}
        />
        <QuickCard
          icon={<Command />}
          title="Command library"
          desc="Everything Rem can do."
          onClick={() => go('commands')}
        />
      </div>
    </>
  );
}

function LiveMusic({
  volume,
  setVolume,
  autoplay,
  showAllQueue,
  setShowAllQueue,
  notify,
  liveSession,
  liveQueue,
  liveGuilds,
  liveGuildId,
  setLiveGuildId,
  liveBridgeReady,
  liveBridgeError,
  onControl,
}: any) {
  const [selectedVcId, setSelectedVcId] = useState('');
  const [trackQuery, setTrackQuery] = useState('');
  const track = liveSession?.current_track;
  const duration = Number(liveSession?.duration_seconds ?? track?.duration ?? 0);
  const position = Number(liveSession?.position_seconds ?? 0);
  const formatTime = (seconds: number) => {
    const value = Math.max(0, Math.floor(seconds));
    return Math.floor(value / 60) + ':' + String(value % 60).padStart(2, '0');
  };
  const current = track
    ? { title: track.title || 'Unknown track', artist: track.artist || 'Unknown artist', time: formatTime(duration), tint: 'violet' }
    : { title: 'Nothing playing', artist: 'Join MusicMaid to a voice channel', time: '0:00', tint: 'violet' };
  const queueTracks = Array.isArray(liveQueue) ? liveQueue : [];
  const isPlaying = Boolean(liveSession?.is_playing);
  const progress = duration > 0 ? Math.min(100, position / duration * 100) : 0;
  return (
    <>
      <PageHeading
        eyebrow="PLAYBACK STUDIO"
        title="Live music."
        subtitle="Your listening room, with every control in one place."
        action={
          <div className="live-heading-actions">
            <select
              className="field-select live-server-select"
              aria-label="Choose live music server"
              value={liveGuildId}
              onChange={event => setLiveGuildId(event.target.value)}
              disabled={!liveGuilds.length}
            >
              {liveGuilds.length === 0 && <option value="">No bot servers found</option>}
              {liveGuilds.map((guild: any) => (
                <option key={guild.id} value={String(guild.id)}>{guild.name}</option>
              ))}
            </select>
            <select
              className="field-select live-server-select"
              aria-label="Choose voice channel"
              value={selectedVcId}
              onChange={event => {
                const vcId = event.target.value;
                setSelectedVcId(vcId);
                if (vcId) {
                  onControl('CONNECT_VOICE', { channel_id: vcId });
                  notify('Connecting bot to voice channel...', 'music');
                }
              }}
            >
              <option value="">🔊 Select Voice Channel…</option>
              {(liveSession?.available_voice_channels || []).map((vc: any) => (
                <option key={vc.id} value={String(vc.id)}>
                  🔊 {vc.name} {vc.members_count ? `(${vc.members_count} listening)` : ''}
                </option>
              ))}
            </select>
            <button
              className="primary-button"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 14px', borderRadius: 9, fontSize: 11 }}
              onClick={() => {
                const vcId = selectedVcId || (liveSession?.available_voice_channels?.[0]?.id ? String(liveSession.available_voice_channels[0].id) : '');
                if (vcId) {
                  onControl('CONNECT_VOICE', { channel_id: vcId });
                  notify('🔊 Summoned Rem to voice channel!', 'music');
                } else {
                  notify('Please select a voice channel to summon Rem!', 'warning');
                }
              }}
            >
              <Zap size={14} /> Summon Rem
            </button>
            <span className={'demo-tag ' + (liveBridgeReady ? 'bridge-online' : 'bridge-offline')}>
              <span className="pulse-dot" /> {liveBridgeReady ? 'LIVE BOT PLAYER' : 'BOT BRIDGE OFFLINE'}
            </span>
          </div>
        }
      />
      <div className="quick-queue-bar" style={{ marginBottom: 16 }}>
        <input
          type="text"
          placeholder="Search song or paste YouTube/Spotify link to play in this voice channel..."
          value={trackQuery}
          onChange={e => setTrackQuery(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && trackQuery.trim()) {
              onControl('ENQUEUE', { query: trackQuery.trim(), channel_id: selectedVcId });
              notify(`Added "${trackQuery}" to voice channel!`);
              setTrackQuery('');
            }
          }}
        />
        <button
          className="primary-button"
          style={{ height: 42, padding: '0 18px', borderRadius: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}
          onClick={() => {
            if (trackQuery.trim()) {
              onControl('ENQUEUE', { query: trackQuery.trim(), channel_id: selectedVcId });
              notify(`Added "${trackQuery}" to voice channel!`);
              setTrackQuery('');
            }
          }}
        >
          <Play size={15} fill="currentColor" /> Play in VC
        </button>
      </div>
      <div className="content-grid live-grid">
        <section className="panel player-panel">
          <div className="section-top">
            <div>
              <div className="eyebrow">NOW PLAYING</div>
              <h3>Music player</h3>
            </div>
            <span className="status-chip">
              <i /> {liveBridgeReady ? (track ? 'Discord live' : 'Connected · Idle') : 'Not connected'}
            </span>
          </div>
          <div className={'album-art player-art ' + current.tint}>
            <div className="art-ring" />
            <AudioLines size={54} />
            <span>RAI MUSIC</span>
            <small>REM RADIO · VOL. 01</small>
          </div>
          <div className="player-track">
            <h2>{current.title}</h2>
            <p>{current.artist}</p>
            <button
              className="like-button"
              onClick={() => notify('Added to favourites (preview).')}
            >
              <Heart size={17} />
            </button>
          </div>
          <div className="track-progress">
            <div className="progress-times">
              <span>{formatTime(position)}</span>
              <span>{current.time}</span>
            </div>
            <div className="progress-line">
              <i style={{ width: progress + '%' }} />
            </div>
          </div>
          <div className="player-controls">
            <button onClick={() => onControl('PREVIOUS')} aria-label="Previous track" disabled={!liveBridgeReady || !track}><SkipBack size={19} /></button>
            <button className="main-play" onClick={() => onControl(isPlaying ? 'PAUSE' : 'RESUME')} aria-label={isPlaying ? 'Pause playback' : 'Resume playback'} disabled={!liveBridgeReady || !track}>
              {isPlaying ? <Pause size={21} fill="currentColor" /> : <Play size={21} fill="currentColor" />}
            </button>
            <button onClick={() => onControl('SKIP')} aria-label="Next track" disabled={!liveBridgeReady || !track}><SkipForward size={19} /></button>
          </div>
          <div className="volume-control">
            <Volume2 size={16} />
            <input
              aria-label="Volume"
              type="range"
              min="0"
              max="100"
              value={volume}
              disabled={!liveBridgeReady}
              onChange={e => {
                const next = Number(e.target.value);
                setVolume(next);
                onControl('VOLUME', { volume: next });
              }}
            />
            <span>{volume}%</span>
          </div>
          <div className="player-note">
            <ShieldCheck size={15} /> {liveBridgeReady ? 'Controls are sent to the live MusicMaid bot.' : (liveBridgeError || 'Secure bot bridge setup is required.')}
          </div>
        </section>
        <section className="panel queue-panel">
          <div className="section-top">
            <div>
              <div className="eyebrow">UP NEXT</div>
              <h3>
                Queue <span className="count-bubble">{queueTracks.length}</span>
              </h3>
            </div>
            <button
              className="more-button"
              onClick={() => setShowAllQueue(!showAllQueue)}
            >
              {showAllQueue ? 'Less' : 'View all'} <ChevronRight size={15} />
            </button>
          </div>
          <div className="queue-current">
            <div className={'queue-cover ' + current.tint}>
              <AudioLines size={18} />
            </div>
            <div className="queue-text">
              <strong>{current.title}</strong>
              <span>{current.artist}</span>
            </div>
            <span className="playing-bars">
              <i />
              <i />
              <i />
            </span>
          </div>
          <div className="queue-label">COMING UP</div>
          {queueTracks.slice(0, showAllQueue ? 20 : 3).map((item: any, i: number) => (
            <div className="queue-item" key={item.url || item.title + i}>
              <span className="queue-index">{String(i + 1).padStart(2, '0')}</span>
              <div className="queue-cover small violet"><Music2 size={15} /></div>
              <div className="queue-text">
                <strong>{item.title}</strong>
                <span>{item.artist || 'Unknown artist'}</span>
              </div>
              <span className="queue-duration">{formatTime(Number(item.duration || 0))}</span>
            </div>
          ))}
          <button
            className="add-queue"
            disabled
            title="Queue requests will be enabled after the secure bot bridge is deployed"
            onClick={() => notify('Queue requests are not enabled yet.')}
          >
            <Plus size={16} /> Add to queue
          </button>
          <div className="autoplay-row">
            <div className="autoplay-icon">
              <Sparkles size={17} />
            </div>
            <div>
              <strong>Smart autoplay</strong>
              <span>Keep the vibe going</span>
            </div>
            <button
              className={'toggle ' + (autoplay ? 'on' : '')}
              onClick={() => onControl('AUTODJ_TOGGLE')}
              disabled={!liveBridgeReady}
              aria-label="Toggle autoplay"
            >
              <i />
            </button>
          </div>
        </section>
      </div>
    </>
  );
}

function Servers({
  server,
  setServer,
  channel,
  setChannel,
  djRole,
  setDjRole,
  saved,
  setSaved,
  notify,
}: any) {
  return (
    <>
      <PageHeading
        eyebrow="YOUR COMMUNITY"
        title="Server settings."
        subtitle="Live Discord server settings are not connected yet. This page is read-only."
        action={<span className="demo-tag">NOT CONNECTED</span>}
      />
      <div className="server-hero panel">
        <div className="server-big-avatar">R</div>
        <div className="server-big-info">
          <div className="eyebrow">DISCORD SERVER</div>
          <h2>Server data unavailable</h2>
          <p>Connect a server-settings API before displaying its name or description here.</p>
          <span className="connected-label">
            <i /> No live server settings loaded
          </span>
        </div>
        <span className="demo-tag">SERVER SELECTOR UNAVAILABLE</span>
      </div>
      <div className="settings-layout">
        <section className="panel settings-card">
          <div className="section-top">
            <div>
              <div className="eyebrow">VOICE & TEXT</div>
              <h3>Channel routing</h3>
            </div>
            <Radio size={19} className="muted" />
          </div>
          <div className="settings-unavailable">
            <p>Music request channel and DJ role cannot be loaded or saved because this dashboard has no Discord server-settings endpoint.</p>
            <p>Nothing on this page changes your Discord server.</p>
          </div>
        </section>
        <section className="panel settings-card">
          <div className="section-top">
            <div>
              <div className="eyebrow">BOT STATUS</div>
              <h3>Connection overview</h3>
            </div>
            <Bot size={19} className="muted" />
          </div>
          <div className="connection-empty">
            <div className="connection-orb">
              <Headphones size={25} />
            </div>
            <h4>Discord isn't connected yet</h4>
            <p>
              Connect a Discord application and secure bot API before enabling
              live server management.
            </p>
            <button
              className="outline-button"
              onClick={() =>
                notify(
                  'OAuth setup is required. No production connection was attempted.'
                )
              }
            >
              <ShieldCheck size={15} /> Setup connection
            </button>
          </div>
        </section>
      </div>
    </>
  );
}

function Commands({ search, setSearch, category, setCategory, commands }: any) {
  const cats = ['All', 'Music', 'Discovery', 'Community', 'Utility'];
  return (
    <>
      <PageHeading
        eyebrow="REM'S TOOLKIT"
        title="Command center."
        subtitle="A quick guide to the commands that keep your community moving."
        action={<div className="command-count">{commands.length} COMMANDS</div>}
      />
      <div className="command-toolbar">
        <label className="command-search">
          <Search size={17} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search commands or what they do..."
          />
        </label>
        <div className="filter-pills">
          {cats.map(cat => (
            <button
              key={cat}
              className={category === cat ? 'selected' : ''}
              onClick={() => setCategory(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>
      <div className="command-list">
        {commands.map((item: any) => (
          <div className="command-row" key={item.name}>
            <div className="command-symbol">
              <Command size={17} />
            </div>
            <div className="command-details">
              <strong>{item.name}</strong>
              <span>{item.detail}</span>
            </div>
            <span className="category-tag">{item.category}</span>
            <code>{item.usage}</code>
            <button
              className="copy-command"
              onClick={() => navigator.clipboard?.writeText(item.usage)}
              title="Copy usage"
            >
              <Plus size={16} />
            </button>
          </div>
        ))}
        {commands.length === 0 && (
          <div className="empty-state">
            <Search size={25} />
            <strong>No commands found</strong>
            <span>Try a different search or category.</span>
          </div>
        )}
      </div>
      <div className="tip-banner">
        <Sparkles size={18} />
        <div>
          <strong>Quick tip</strong>
          <span>
            Use slash commands in Discord for the clearest experience. Prefix
            support depends on your bot configuration.
          </span>
        </div>
      </div>
    </>
  );
}

function RemAI({ mood, setMood, notify }: any) {
  const moods = [
    { name: 'Chill', icon: Moon, desc: 'Soft edges, slow nights' },
    { name: 'Sad', icon: Heart, desc: 'Feel it, then heal' },
    { name: 'Hype', icon: Zap, desc: 'Turn the energy up' },
    { name: 'Focus', icon: Activity, desc: 'Lock in and flow' },
    { name: 'Romantic', icon: Sparkles, desc: 'A little softer' },
  ];
  const picks: Record<string, string[]> = {
    Chill: ['Snowfall', 'Resonance', 'Aruarian Dance'],
    Sad: ['Glimpse of Us', 'Ref:rain', 'Somewhere Only We Know'],
    Hype: ['The Rumbling', 'Kick Back', 'SPECIALZ'],
    Focus: ['Experience', 'Time', 'A Walk'],
    Romantic: ['KALYANI', 'Until I Found You', 'Sparkle'],
  };
  return (
    <>
      <PageHeading
        eyebrow="A LITTLE MAGIC, A LOT OF MUSIC"
        title="What's your vibe?"
        subtitle="Tell Rem how you're feeling. She'll shape a discovery mix around your mood."
        action={
          <span className="rem-status">
            <Sparkles size={14} /> REM AI PREVIEW
          </span>
        }
      />
      <section className="mood-hero">
        <div className="mood-copy">
          <div className="eyebrow">YOUR PERSONAL MUSIC COMPANION</div>
          <h2>
            Every mood has
            <br />a <em>soundtrack.</em>
          </h2>
          <p>Pick a feeling. Rem will sketch out a mix to match the moment.</p>
          <div className="rem-signature">
            <div className="rem-avatar">玲</div>
            <div>
              <strong>Rem</strong>
              <span>Here for your every vibe.</span>
            </div>
          </div>
        </div>
        <div className="mood-visual">
          <div className="mood-halo" />
          <div className="mood-character">玲</div>
          <div className="sparkle s1">✦</div>
          <div className="sparkle s2">✧</div>
          <div className="sparkle s3">✦</div>
        </div>
      </section>
      <div className="section-heading mood-heading">
        <div>
          <div className="eyebrow">CHOOSE YOUR FREQUENCY</div>
          <h3>How are we feeling?</h3>
        </div>
      </div>
      <div className="mood-grid">
        {moods.map(item => {
          const Icon = item.icon;
          return (
            <button
              key={item.name}
              className={
                'mood-card ' + (mood === item.name ? 'mood-selected' : '')
              }
              onClick={() => setMood(item.name)}
            >
              <div className="mood-icon">
                <Icon size={21} />
              </div>
              <strong>{item.name}</strong>
              <span>{item.desc}</span>
              {mood === item.name && (
                <i className="mood-check">
                  <Check size={13} />
                </i>
              )}
            </button>
          );
        })}
      </div>
      <section className="panel mix-panel">
        <div className="section-top">
          <div>
            <div className="eyebrow">CURATED FOR THIS MOMENT</div>
            <h3>Your {mood.toLowerCase()} mix</h3>
          </div>
          <span className="mix-count">03 TRACKS</span>
        </div>
        <div className="mix-tracks">
          {picks[mood].map((name, i) => (
            <div className="mix-track" key={name}>
              <span className="mix-number">0{i + 1}</span>
              <div className={'mix-cover tint-' + i}>
                <Music2 size={17} />
              </div>
              <div>
                <strong>{name}</strong>
                <span>
                  {
                    [
                      'A Rem discovery pick',
                      'Community favourite',
                      'A little hidden gem',
                    ][i]
                  }
                </span>
              </div>
              <button
                onClick={() =>
                  notify('Connect Discord to play this mix in your server.')
                }
              >
                <Play size={15} />
              </button>
            </div>
          ))}
        </div>
        <button
          className="primary-button mix-button"
          onClick={() =>
            notify(
              'Your mood mix is ready in preview. Connect Discord to play it.'
            )
          }
        >
          <WandSparkles size={16} /> Create my mix
        </button>
      </section>
    </>
  );
}

function Analytics() {
  const bars = [
    32, 44, 38, 57, 48, 70, 61, 52, 77, 66, 88, 72, 94, 69, 83, 58, 75, 91, 63,
    80, 55, 73, 89, 67,
  ];
  return (
    <>
      <PageHeading
        eyebrow="THE COMMUNITY SOUNDTRACK"
        title="Your numbers, in rhythm."
        subtitle="A snapshot of how your community listens. All figures below are sample data."
        action={<span className="demo-tag">SAMPLE ANALYTICS</span>}
      />
      <div className="stats-grid analytics-stats">
        <StatCard
          icon={<Headphones size={17} />}
          label="Listening minutes"
          value="4,820"
          note="+14.2% this week"
          tone="purple"
        />
        <StatCard
          icon={<Music2 size={17} />}
          label="Tracks played"
          value="1,284"
          note="Across sample servers"
          tone="blue"
        />
        <StatCard
          icon={<Heart size={17} />}
          label="Top saved track"
          value="KALYANI"
          note="42 community saves"
          tone="pink"
        />
        <StatCard
          icon={<Activity size={17} />}
          label="Peak listeners"
          value="38"
          note="Friday · 9:30 PM"
          tone="orange"
        />
      </div>
      <section className="panel analytics-panel">
        <div className="section-top">
          <div>
            <div className="eyebrow">WEEKLY OVERVIEW</div>
            <h3>Listening activity</h3>
          </div>
          <select className="small-select">
            <option>Last 7 days</option>
            <option>Last 30 days</option>
          </select>
        </div>
        <div className="big-chart">
          {bars.map((v, i) => (
            <div className="bar-wrap" key={i}>
              <i style={{ height: v + '%' }} />
            </div>
          ))}
        </div>
        <div className="big-chart-labels">
          <span>MON</span>
          <span>TUE</span>
          <span>WED</span>
          <span>THU</span>
          <span>FRI</span>
          <span>SAT</span>
          <span>SUN</span>
        </div>
      </section>
      <div className="content-grid analytics-lower">
        <section className="panel">
          <div className="eyebrow">TOP TRACKS</div>
          <h3 className="panel-title">Community favourites</h3>
          {tracks.map((track, i) => (
            <div className="rank-row" key={track.title}>
              <b>0{i + 1}</b>
              <div className={'queue-cover ' + track.tint}>
                <Music2 size={15} />
              </div>
              <div className="queue-text">
                <strong>{track.title}</strong>
                <span>{track.artist}</span>
              </div>
              <strong className="rank-value">
                {[42, 37, 29, 18][i]} plays
              </strong>
            </div>
          ))}
        </section>
        <section className="panel">
          <div className="eyebrow">SERVER SPOTLIGHT</div>
          <h3 className="panel-title">Most active spaces</h3>
          {[
            ['rai fam', '68%', 'purple'],
            ['Anime Lounge', '47%', 'blue'],
            ['Music Lab', '31%', 'pink'],
          ].map(item => (
            <div className="space-row" key={item[0]}>
              <div>
                <strong>{item[0]}</strong>
                <span>{item[1]} of sample activity</span>
              </div>
              <div className="space-track">
                <i className={item[2]} style={{ width: item[1] }} />
              </div>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}

function HistoryPage({ notify }: any) {
  const history: any[] = [];
  const [query, setQuery] = useState('');
  const visible = history.filter(track => (track.title + ' ' + track.artist).toLowerCase().includes(query.toLowerCase()));
  return (
    <>
      <PageHeading eyebrow="YOUR LISTENING TRAIL" title="Play history." subtitle="Playback history is not available from the connected bot data yet." />
      <section className="panel history-panel">
        <div className="history-toolbar">
          <label className="history-search"><Search size={15} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Find a track or artist" /></label>
          <span className="mix-count">{visible.length} TRACKS</span>
        </div>
        {visible.map((track, index) => (
          <div className="history-row" key={track.title}>
            <span className="history-number">{String(index + 1).padStart(2, '0')}</span>
            <div className={'queue-cover ' + track.tint}><Music2 size={16} /></div>
            <div className="queue-text"><strong>{track.title}</strong><span>{track.artist}</span></div>
            <span className="history-when">{track.when}</span>
            <span className="queue-duration">{track.duration}</span>
            <button className="outline-button history-add" onClick={() => notify('Added to the local preview queue.')}><Plus size={14} /> Queue</button>          </div>
        ))}
        {visible.length === 0 && <div className="history-empty">No tracks match that search.</div>}
      </section>
      <p className="connection-footnote">No history is shown because the bot does not currently expose a history feed to this dashboard.</p>
    </>
  );
}

function MembersPage({ guilds, discordAccount, notify }: any) {
  const members: any[] = [];
  return (
    <>
      <PageHeading eyebrow="COMMUNITY CONTROL ROOM" title="Members & roles." subtitle="Review connected servers and explore a safe member-management preview." action={<span className="demo-tag">READ-ONLY / PREVIEW</span>} />
      <div className="stats-grid member-stats">
        <StatCard icon={<Users size={17} />} label="Accessible servers" value={discordAccount ? String(guilds.length) : '—'} note={discordAccount ? 'From Discord OAuth' : 'Connect Discord first'} tone="purple" />
        <StatCard icon={<ShieldCheck size={17} />} label="Permission scope" value="Read only" note="identify + guilds" tone="blue" />
        <StatCard icon={<Headphones size={17} />} label="DJ role" value="MusicMaid" note="Preview configuration" tone="pink" />
        <StatCard icon={<Users size={17} />} label="Bot member data" value="—" note="Not provided by the bridge" tone="orange" />
      </div>
      <section className="panel member-server-panel">
        <div className="section-top"><div><div className="eyebrow">DISCORD ACCESS</div><h3>Your accessible servers</h3></div><span className="mix-count">{discordAccount ? 'LIVE OAUTH DATA' : 'NOT CONNECTED'}</span></div>
        {discordAccount && guilds.length ? <div className="member-server-list">{guilds.map((guild: any) => <div className="member-server-row" key={guild.id}>{guild.iconUrl ? <img src={guild.iconUrl} alt="" /> : <div className="server-avatar">{guild.name.slice(0, 1)}</div>}<strong>{guild.name}</strong><span>{guild.owner ? 'Owner' : 'Accessible'}</span></div>)}</div> : <p className="connection-muted">Connect Discord to load the servers your account can access. No server changes are made.</p>}
      </section>
      <section className="panel member-directory-panel">
        <div className="section-top"><div><div className="eyebrow">BOT DATA</div><h3>Roles & community access</h3></div><span className="mix-count">UNAVAILABLE</span></div>
        <p className="connection-muted">The connected bot bridge does not provide a member roster or role data yet. No sample members are displayed, and this panel makes no role changes.</p>
      </section>
    </>
  );
}

function NotificationsPage({ botStatus }: any) {
  const [read, setRead] = useState<string[]>([]);
  const notices = [
    { id: 'health', title: botStatus?.reachable ? 'MusicMaid health check completed' : 'MusicMaid health check unavailable', body: botStatus?.reachable ? 'The production health endpoint responded.' : 'The production health endpoint did not respond. Try refreshing later.', time: 'Live status', kind: botStatus?.reachable ? 'success' : 'warning' },
    { id: 'oauth', title: 'Discord connection is protected', body: 'OAuth currently requests identify and guilds only.', time: 'Security', kind: 'info' },
    { id: 'preview', title: 'Preview mode is active', body: 'Player, queue, role editing and server settings do not change your live bot.', time: 'Workspace', kind: 'info' },
  ];
  return (
    <>
      <PageHeading eyebrow="UPDATES & SERVICE EVENTS" title="Notifications." subtitle="A single place for connection, service and workspace alerts." action={<span className="demo-tag">{notices.length - read.length} UNREAD</span>} />
      <section className="panel notification-list">
        <div className="section-top"><div><div className="eyebrow">INBOX</div><h3>Recent activity</h3></div><button className="outline-button" onClick={() => setRead(notices.map(item => item.id))}>Mark all read</button></div>
        {notices.map(item => <article className={'notice-row ' + (read.includes(item.id) ? 'notice-read' : '')} key={item.id}><span className={'notice-icon ' + item.kind}><BellRing size={16} /></span><div className="notice-copy"><strong>{item.title}</strong><p>{item.body}</p><span>{item.time}</span></div><button className="notice-mark" onClick={() => setRead(current => current.includes(item.id) ? current.filter(id => id !== item.id) : [...current, item.id])}>{read.includes(item.id) ? 'Unread' : 'Mark read'}</button></article>)}
      </section>
    </>
  );
}

function SettingsPage({ settings, setSettings, notify, discordAccount, theme, setTheme }: any) {
  const groups = [
    {
      key: 'notifications',
      title: 'Product notifications',
      desc: 'Updates about new features and important activity.',
    },
    {
      key: 'compact',
      title: 'Compact interface',
      desc: 'Reduce spacing for a denser dashboard.',
    },
    {
      key: 'publicStats',
      title: 'Public server statistics',
      desc: 'Allow public display of community listening stats.',
    },
    {
      key: 'safeMode',
      title: 'Safe preview mode',
      desc: 'Keep all player actions local until integrations are configured.',
    },
  ];
  return (
    <>
      <PageHeading
        eyebrow="MAKE RAI YOURS"
        title="Preferences."
        subtitle="Fine-tune the way your Rai Music workspace feels."
      />
      <div className="settings-layout">
        <section className="panel settings-card">
          <div className="eyebrow">WORKSPACE</div>
          <h3 className="settings-title">Interface & privacy</h3>
          {groups.map(item => (
            <div className="preference-row" key={item.key}>
              <div>
                <strong>{item.title}</strong>
                <span>{item.desc}</span>
              </div>
              <button
                className={'toggle ' + (settings[item.key] ? 'on' : '')}
                onClick={() =>
                  setSettings((current: any) => ({
                    ...current,
                    [item.key]: !current[item.key],
                  }))
                }
                aria-label={'Toggle ' + item.title}
              >
                <i />
              </button>
            </div>
          ))}
        </section>
        <section className="panel settings-card">
          <div className="section-top"><div><div className="eyebrow">APPEARANCE</div><h3 className="settings-title">Dashboard theme</h3></div><Palette size={19} className="muted" /></div>
          <p className="field-hint">Choose an accent style for your Rai Music workspace.</p>
          <div className="theme-options">
            {['Midnight', 'Aurora', 'Mono'].map(option => <button key={option} className={'theme-option ' + (theme === option ? 'selected' : '')} onClick={() => { setTheme(option); notify(option + ' theme applied.'); }}><span className={'theme-swatch ' + option.toLowerCase()} /><strong>{option}</strong>{theme === option && <Check size={14} />}</button>)}
          </div>
        </section>
        <section className="panel settings-card">
          <div className="eyebrow">ACCOUNT & INTEGRATIONS</div>
          <h3 className="settings-title">Connected services</h3>
          <div className="integration-row">
            <div className="integration-icon discord-icon">D</div>
            <div>
              <strong>Discord</strong>
              <span>{discordAccount ? 'Connected as @' + discordAccount.username : 'Not connected'}</span>
            </div>
            <span className="integration-state">{discordAccount ? 'Linked' : 'Not linked'}</span>
          </div>
          <div className="integration-row">
            <div className="integration-icon bot-icon">
              <Bot size={19} />
            </div>
            <div>
              <strong>Rai Music Bot</strong>
              <span>Production service is isolated</span>
            </div>
            <span className="integration-state safe">Protected</span>
          </div>
          <div className="integration-row">
            <div className="integration-icon">
              <ShieldCheck size={19} />
            </div>
            <div>
              <strong>Safe preview mode</strong>
              <span>All controls use sample data</span>
            </div>
            <span className="integration-state safe">On</span>
          </div>
          <button
            className="outline-button full-button"
            onClick={() =>
              notify('Integration setup will be a separate, secure step.')
            }
          >
            Manage integrations <ChevronRight size={15} />
          </button>
        </section>
      </div>
    </>
  );
}
export default App;
