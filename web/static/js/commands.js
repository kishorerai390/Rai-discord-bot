/**
 * Voicelink – commands.js
 * Search, filter, and modal for the commands page
 */

(function () {
  'use strict';

  // ── Category tabs ──────────────────────────────────────────────
  const tabs = document.querySelectorAll('.category-btn');
  const sections = document.querySelectorAll('.category-section');
  const cards = document.querySelectorAll('.command-card');
  const noResults = document.getElementById('no-results');
  const searchInput = document.getElementById('cmd-search');

  function activateTab(tab) {
    tabs.forEach(t => {
      t.classList.remove('active-tab', 'btn-primary', 'bg-brand-600', 'text-white', 'border-brand-700');
      t.classList.add('btn-ghost', 'text-slate-400');
    });
    tab.classList.add('active-tab', 'bg-surface-300', 'text-white');
    tab.classList.remove('btn-ghost', 'text-slate-400');
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      activateTab(tab);
      const cat = tab.dataset.category;
      const query = (searchInput?.value || '').toLowerCase().trim();

      sections.forEach(sec => {
        if (cat === 'all' || sec.dataset.category === cat) {
          sec.style.display = '';
        } else {
          sec.style.display = 'none';
        }
      });

      applySearch(query, cat);
    });
  });

  // ── Search ─────────────────────────────────────────────────────
  function applySearch(query, activeCat = 'all') {
    let visibleCount = 0;

    cards.forEach(card => {
      const name    = card.dataset.name || '';
      const aliases = card.dataset.aliases || '';
      const desc    = card.querySelector('p')?.textContent.toLowerCase() || '';
      const matches = !query || name.includes(query) || aliases.includes(query) || desc.includes(query);
      const catOk   = activeCat === 'all' || card.closest('.category-section')?.dataset.category === activeCat;

      const show = matches && catOk;
      card.style.display = show ? '' : 'none';
      if (show) visibleCount++;
    });

    // Hide empty category sections
    sections.forEach(sec => {
      const visible = [...sec.querySelectorAll('.command-card')].some(c => c.style.display !== 'none');
      sec.style.display = visible ? '' : 'none';
    });

    noResults.classList.toggle('hidden', visibleCount > 0);
  }

  searchInput?.addEventListener('input', () => {
    const activeTab = document.querySelector('.category-btn.active-tab');
    applySearch(searchInput.value.toLowerCase().trim(), activeTab?.dataset.category || 'all');
  });

  // ── Command modal ──────────────────────────────────────────────
  const modal = document.getElementById('cmd-modal');
  const modalContent = document.getElementById('modal-content');

  window.openCommandModal = function (cmd) {
    if (!modal || !modalContent) return;

    const aliases = cmd.aliases?.length ? cmd.aliases.map(a => `<code class="code text-xs bg-surface-400 px-1.5 py-0.5 rounded">${a}</code>`).join(' ') : '<span class="text-slate-600">None</span>';

    modalContent.innerHTML = `
      <div class="mb-4">
        <div class="flex items-start justify-between mb-2">
          <div>
            <h3 class="text-xl font-bold text-white font-mono">/${cmd.name}</h3>
            ${cmd.new ? '<span class="badge badge-sm bg-green-500/20 text-green-400 border-green-500/30 mt-1">NEW</span>' : ''}
          </div>
          ${cmd.premium ? '<span class="badge bg-yellow-500/20 text-yellow-400 border-yellow-500/30"><i class="fa-solid fa-star text-[10px] mr-1"></i>Premium</span>' : ''}
        </div>
        <p class="text-slate-400 text-sm leading-relaxed">${cmd.description}</p>
      </div>

      <div class="space-y-3 mb-4">
        ${cmd.usage ? `
        <div>
          <p class="text-xs text-slate-500 uppercase tracking-wider font-medium mb-1.5">Usage</p>
          <div class="bg-surface-300 rounded-lg px-3 py-2 font-mono text-sm text-brand-300 flex items-center justify-between group cursor-pointer"
               onclick="navigator.clipboard.writeText('${cmd.usage}').then(() => alert('Copied!'))">
            <span>${escHtml(cmd.usage)}</span>
            <i class="fa-solid fa-copy text-slate-600 group-hover:text-slate-400 text-xs transition"></i>
          </div>
        </div>` : ''}

        <div class="grid grid-cols-2 gap-3">
          <div>
            <p class="text-xs text-slate-500 uppercase tracking-wider font-medium mb-1.5">Aliases</p>
            <div class="flex flex-wrap gap-1">${aliases}</div>
          </div>
          ${cmd.cooldown ? `
          <div>
            <p class="text-xs text-slate-500 uppercase tracking-wider font-medium mb-1.5">Cooldown</p>
            <p class="text-sm text-slate-300 flex items-center gap-1.5">
              <i class="fa-solid fa-clock text-brand-400 text-xs"></i>${cmd.cooldown}s
            </p>
          </div>` : ''}
        </div>

        ${cmd.permissions ? `
        <div>
          <p class="text-xs text-slate-500 uppercase tracking-wider font-medium mb-1.5">Required Permissions</p>
          <span class="flex items-center gap-1.5 text-sm text-slate-300">
            <i class="fa-solid fa-lock text-yellow-500 text-xs"></i>${cmd.permissions}
          </span>
        </div>` : ''}

        ${cmd.examples?.length ? `
        <div>
          <p class="text-xs text-slate-500 uppercase tracking-wider font-medium mb-1.5">Examples</p>
          <div class="space-y-1">
            ${cmd.examples.map(ex => `
            <div class="bg-surface-300 rounded-lg px-3 py-1.5 font-mono text-xs text-slate-300">${escHtml(ex)}</div>
            `).join('')}
          </div>
        </div>` : ''}
      </div>
    `;

    modal.showModal();
  };

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Initialize first tab as active
  const firstTab = document.querySelector('.category-btn');
  if (firstTab) activateTab(firstTab);

})();

