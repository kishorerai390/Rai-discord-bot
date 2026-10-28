/**
 * Voicelink – player.js
 * Real-time music player controller via WebSocket
 */

(function () {
  'use strict';

  // ── State ──────────────────────────────────────────────────────
  let ws = null;
  let reconnectTimer = null;
  let progressInterval = null;
  let positionMs = 0;
  let durationMs = 0;
  let isPlaying = false;

  // ── DOM refs ───────────────────────────────────────────────────
  const $  = id => document.getElementById(id);
  const $$ = sel => document.querySelectorAll(sel);

  const dom = {
    wsDot:       $('ws-dot'),
    wsLabel:     $('ws-label'),
    guildSelect: $('guild-select'),
    playBtn:     $('play-btn'),
    playIcon:    $('play-icon'),
    prevBtn:     $('prev-btn'),
    nextBtn:     $('next-btn'),
    shuffleBtn:  $('shuffle-btn'),
    loopBtn:     $('loop-btn'),
    likeBtn:     $('like-btn'),
    trackTitle:  $('track-title'),
    trackAuthor: $('track-author'),
    trackArt:    $('track-art'),
    artPlaceholder: $('art-placeholder'),
    progressFill:   $('progress-fill'),
    progressBar:    $('progress-bar'),
    positionDisplay: $('position-display'),
    durationDisplay: $('duration-display'),
    volumeSlider:    $('volume-slider'),
    volumeSliderMob: $('volume-slider-mobile'),
    volumeDisplay:   $('volume-display'),
    queueList:   $('queue-list'),
    queueCount:  $('queue-count'),
    addInput:    $('add-track-input'),
    addBtn:      $('add-track-btn'),
    clearBtn:    $('clear-queue-btn'),
    filterBtns:  $$('.filter-btn'),
  };

  // ── Toast helper ────────────────────────────────────────────────
  function toast(msg, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.className = `toast-item ${type}`;
    const icon = type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle';
    el.innerHTML = `<i class="fa-solid ${icon}"></i><span>${msg}</span>`;
    container.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
  }

  // ── Time formatting ────────────────────────────────────────────
  function msToTime(ms) {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, '0')}`;
  }

  // ── Progress ticker ────────────────────────────────────────────
  function startProgressTicker() {
    clearInterval(progressInterval);
    if (!isPlaying || durationMs <= 0) return;
    progressInterval = setInterval(() => {
      positionMs = Math.min(positionMs + 1000, durationMs);
      const pct = (positionMs / durationMs) * 100;
      if (dom.progressFill) dom.progressFill.style.width = `${pct}%`;
      if (dom.positionDisplay) dom.positionDisplay.textContent = msToTime(positionMs);
      if (positionMs >= durationMs) clearInterval(progressInterval);
    }, 1000);
  }

  // ── WebSocket ──────────────────────────────────────────────────
  function connect(guildId) {
    if (ws) ws.close();
    if (!guildId) { setWsStatus('disconnected'); return; }

    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${protocol}://${location.host}/ws/player/${guildId}`);

    ws.onopen = () => {
      setWsStatus('connected');
      clearTimeout(reconnectTimer);
      toast('Connected to player', 'success');
    };

    ws.onmessage = (e) => {
      try { handleMessage(JSON.parse(e.data)); }
      catch { console.warn('WS parse error', e.data); }
    };

    ws.onclose = () => {
      setWsStatus('disconnected');
      reconnectTimer = setTimeout(() => connect(guildId), 5000);
    };

    ws.onerror = () => setWsStatus('error');
  }

  function setWsStatus(status) {
    if (!dom.wsDot || !dom.wsLabel) return;
    const map = {
      connected:    ['bg-green-500',  'Connected'],
      disconnected: ['bg-slate-500',  'Disconnected'],
      error:        ['bg-red-500',    'Error'],
    };
    const [color, label] = map[status] || map.disconnected;
    dom.wsDot.className   = `w-1.5 h-1.5 rounded-full ${color}`;
    dom.wsLabel.textContent = label;
  }

  function send(action, data = {}) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      toast('Not connected to player', 'error');
      return;
    }
    ws.send(JSON.stringify({ action, ...data }));
  }

  // ── Message handler ────────────────────────────────────────────
  function handleMessage(msg) {
    switch (msg.type) {
      case 'state':       updateFullState(msg.data); break;
      case 'track_start': onTrackStart(msg.data);    break;
      case 'track_end':   onTrackEnd();               break;
      case 'queue':       updateQueue(msg.data);      break;
      case 'volume':      updateVolume(msg.data.volume); break;
      case 'filter':      updateFilter(msg.data);     break;
      case 'error':       toast(msg.message, 'error'); break;
    }
  }

  function updateFullState(state) {
    isPlaying  = state.is_playing;
    positionMs = state.position;
    durationMs = state.duration;
    updatePlayBtn(isPlaying);
    updateTrack(state.current_track);
    updateQueue(state.queue);
    updateVolume(state.volume);
    updateShuffleLoop(state.shuffle, state.loop);
    startProgressTicker();
  }

  function onTrackStart(track) {
    isPlaying = true;
    positionMs = 0;
    durationMs = track.duration_ms;
    updatePlayBtn(true);
    updateTrack(track);
    startProgressTicker();
    toast(`▶ ${track.title}`, 'info');
  }

  function onTrackEnd() {
    isPlaying = false;
    updatePlayBtn(false);
    clearInterval(progressInterval);
  }

  function updateTrack(track) {
    if (!track) return;
    durationMs = track.duration_ms || 0;
    if (dom.trackTitle)  dom.trackTitle.textContent  = track.title  || 'Unknown';
    if (dom.trackAuthor) dom.trackAuthor.textContent = track.author || '';
    if (dom.durationDisplay) dom.durationDisplay.textContent = msToTime(durationMs);
    if (dom.trackArt) {
      if (track.thumbnail) {
        dom.trackArt.src = track.thumbnail;
        dom.trackArt.classList.remove('hidden');
        dom.artPlaceholder?.classList.add('hidden');
      } else {
        dom.trackArt.classList.add('hidden');
        dom.artPlaceholder?.classList.remove('hidden');
      }
    }
  }

  function updatePlayBtn(playing) {
    if (!dom.playIcon) return;
    dom.playIcon.className = `fa-solid ${playing ? 'fa-pause' : 'fa-play'} text-xl`;
  }

  function updateVolume(vol) {
    if (dom.volumeSlider)    dom.volumeSlider.value    = vol;
    if (dom.volumeSliderMob) dom.volumeSliderMob.value = vol;
    if (dom.volumeDisplay)   dom.volumeDisplay.textContent = `${vol}%`;
  }

  function updateShuffleLoop(shuffle, loop) {
    dom.shuffleBtn?.classList.toggle('text-brand-400', shuffle);
    dom.shuffleBtn?.classList.toggle('text-slate-500', !shuffle);
    dom.loopBtn?.classList.toggle('text-brand-400', loop);
    dom.loopBtn?.classList.toggle('text-slate-500', !loop);
  }

  function updateFilter({ filter, active }) {
    document.querySelectorAll(`.filter-btn[data-filter="${filter}"]`).forEach(btn => {
      btn.classList.toggle('active', active);
    });
  }

  // ── Queue rendering ────────────────────────────────────────────
  function updateQueue(queue = []) {
    if (!dom.queueList) return;
    if (dom.queueCount) {
      dom.queueCount.textContent = `${queue.length} track${queue.length !== 1 ? 's' : ''}`;
    }
    if (queue.length === 0) {
      dom.queueList.innerHTML = `
        <div id="empty-queue" class="flex flex-col items-center justify-center py-16 text-center text-slate-600">
          <i class="fa-solid fa-music text-4xl mb-3 opacity-20"></i>
          <p class="font-medium text-slate-500">The queue is empty</p>
          <p class="text-xs mt-1">Add a song above or use /play in Discord</p>
        </div>`;
      return;
    }
    dom.queueList.innerHTML = queue.map((t, i) => `
      <div class="queue-item group flex items-center gap-3 p-3 rounded-xl hover:bg-surface-300 transition-all duration-150 cursor-grab"
           data-index="${i}" data-id="${t.id}">
        <div class="flex-shrink-0 text-slate-600 group-hover:text-slate-400 transition opacity-0 group-hover:opacity-100">
          <i class="fa-solid fa-grip-vertical text-xs"></i>
        </div>
        <span class="flex-shrink-0 text-xs text-slate-600 w-5 text-center">${i + 1}</span>
        <div class="flex-shrink-0 w-9 h-9 rounded-lg bg-surface-400 overflow-hidden">
          ${t.thumbnail ? `<img src="${t.thumbnail}" alt="" class="w-full h-full object-cover" />` : '<div class="w-full h-full flex items-center justify-center"><i class="fa-solid fa-music text-slate-600 text-xs"></i></div>'}
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm text-white truncate font-medium">${escHtml(t.title)}</p>
          <p class="text-xs text-slate-500 truncate">${escHtml(t.author)} · ${t.duration}</p>
        </div>
        <div class="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition">
          <button class="play-track-btn btn btn-xs btn-ghost text-slate-500 hover:text-white" data-index="${i}" title="Play now">
            <i class="fa-solid fa-play text-xs"></i>
          </button>
          <button class="remove-track-btn btn btn-xs btn-ghost text-slate-500 hover:text-red-400" data-index="${i}" title="Remove">
            <i class="fa-solid fa-xmark text-xs"></i>
          </button>
        </div>
      </div>`).join('');

    initSortable();
    dom.queueList.querySelectorAll('.play-track-btn').forEach(btn =>
      btn.addEventListener('click', () => send('skip_to', { index: +btn.dataset.index })));
    dom.queueList.querySelectorAll('.remove-track-btn').forEach(btn =>
      btn.addEventListener('click', () => send('remove', { index: +btn.dataset.index })));
  }

  function escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Sortable queue ─────────────────────────────────────────────
  let sortable = null;
  function initSortable() {
    if (sortable) sortable.destroy();
    if (!dom.queueList || !window.Sortable) return;
    sortable = Sortable.create(dom.queueList, {
      animation: 150,
      ghostClass: 'sortable-ghost',
      chosenClass: 'sortable-chosen',
      handle: '.fa-grip-vertical',
      onEnd: (evt) => {
        send('move', { from: evt.oldIndex, to: evt.newIndex });
      },
    });
  }

  // ── Progress bar seek ──────────────────────────────────────────
  dom.progressBar?.addEventListener('click', (e) => {
    const rect = dom.progressBar.getBoundingClientRect();
    const pct  = (e.clientX - rect.left) / rect.width;
    const pos  = Math.floor(pct * durationMs);
    send('seek', { position: pos });
    positionMs = pos;
    if (dom.progressFill) dom.progressFill.style.width = `${pct * 100}%`;
    if (dom.positionDisplay) dom.positionDisplay.textContent = msToTime(pos);
  });

  // ── Button events ──────────────────────────────────────────────
  dom.playBtn?.addEventListener('click',    () => send('pause_resume'));
  dom.prevBtn?.addEventListener('click',    () => send('previous'));
  dom.nextBtn?.addEventListener('click',    () => send('skip'));
  dom.shuffleBtn?.addEventListener('click', () => send('shuffle'));
  dom.loopBtn?.addEventListener('click',    () => send('loop'));
  dom.clearBtn?.addEventListener('click',   () => { if (confirm('Clear the entire queue?')) send('clear'); });

  dom.likeBtn?.addEventListener('click', () => {
    send('like');
    const icon = dom.likeBtn.querySelector('i');
    if (icon) {
      icon.className = icon.className.includes('fa-regular')
        ? 'fa-solid fa-heart text-red-400'
        : 'fa-regular fa-heart';
    }
  });

  // Volume
  function onVolume(val) { send('volume', { value: +val }); updateVolume(val); }
  dom.volumeSlider?.addEventListener('input',    e => onVolume(e.target.value));
  dom.volumeSliderMob?.addEventListener('input', e => onVolume(e.target.value));

  // Add track
  function addTrack() {
    const query = dom.addInput?.value.trim();
    if (!query) return;
    send('play', { query });
    dom.addInput.value = '';
    toast('Adding to queue…', 'info');
  }
  dom.addBtn?.addEventListener('click', addTrack);
  dom.addInput?.addEventListener('keydown', e => { if (e.key === 'Enter') addTrack(); });

  // Filters
  dom.filterBtns?.forEach(btn =>
    btn.addEventListener('click', () => send('filter', { filter: btn.dataset.filter })));

  // Guild select
  dom.guildSelect?.addEventListener('change', () => {
    const id = dom.guildSelect.value;
    if (id) {
      history.replaceState({}, '', `?guild=${id}`);
      connect(id);
    }
  });

  // ── Init ───────────────────────────────────────────────────────
  const guildId = new URLSearchParams(location.search).get('guild') || (dom.guildSelect?.value ?? '');
  if (guildId) connect(guildId);

})();

