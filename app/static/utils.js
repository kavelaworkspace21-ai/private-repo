/* ══════════════════════════════════════
   Auth helpers
══════════════════════════════════════ */
const auth = {
  getToken()  { return localStorage.getItem('access_token'); },
  setTokens(access, refresh) {
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
  },
  clear() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_user');
  },
  logout() { auth.clear(); window.location.href = '/login'; },
  isLoggedIn() { return !!auth.getToken(); },
};

/* ══════════════════════════════════════
   API helper — attaches Bearer token
══════════════════════════════════════ */
const api = {
  _headers(extra = {}) {
    const h = { 'Content-Type': 'application/json', ...extra };
    const t = auth.getToken();
    if (t) h['Authorization'] = `Bearer ${t}`;
    return h;
  },
  async _handle(res) {
    if (res.status === 401) { auth.logout(); throw new Error('Unauthenticated'); }
    if (!res.ok) throw new Error(await res.text());
    if (res.status === 204) return null;
    return res.json();
  },
  async get(url)        { return this._handle(await fetch(url, { headers: this._headers() })); },
  async post(url, body) { return this._handle(await fetch(url, { method:'POST',   headers: this._headers(), body: JSON.stringify(body) })); },
  async patch(url, body){ return this._handle(await fetch(url, { method:'PATCH',  headers: this._headers(), body: JSON.stringify(body) })); },
  async del(url)        { return this._handle(await fetch(url, { method:'DELETE', headers: this._headers() })); },
};

/* ══════════════════════════════════════
   Nav — user chip + logout
══════════════════════════════════════ */
async function initNav() {
  const nav = document.querySelector('.topnav');
  if (!nav) return;

  // Inject the Workbench link once — static navs predate it (LSAI-WB-00).
  const linkBox = nav.querySelector('.nav-links');
  if (linkBox && !linkBox.querySelector('a[href="/workbench"]')) {
    const wb = document.createElement('a');
    wb.href = '/workbench';
    wb.textContent = 'Workbench';
    if (location.pathname === '/workbench') wb.className = 'active';
    const anchor = linkBox.querySelector('a[href="/drafting"]');
    if (anchor) anchor.after(wb); else linkBox.appendChild(wb);
  }

  if (!auth.isLoggedIn()) {
    // Show login link instead of user chip
    const right = nav.querySelector('.nav-right');
    if (right) right.innerHTML = `<a href="/login" class="btn btn-gold btn-sm">Sign In</a>`;
    return;
  }

  try {
    /* Cache ONLY what the nav chip renders. /api/auth/me also returns email, phone and
       professional_id; those were being written to localStorage and never read. Anything
       in localStorage is readable by any script on the page — an XSS, a bad dependency, a
       browser extension — so caching an advocate's email and phone there bought nothing
       and widened the blast radius. Pages that genuinely need the full profile (account.html)
       re-fetch /api/auth/me instead. */
    let user = JSON.parse(localStorage.getItem('current_user') || 'null');
    /* Purge PII an earlier build cached. Existing browsers already hold the full profile,
       so simply writing less from now on would leave their email and phone sitting there
       indefinitely — the stale copy has to be actively overwritten. */
    if (user && ('email' in user || 'phone' in user || 'professional_id' in user)) {
      user = { full_name: user.full_name, role: user.role, is_2fa_enabled: user.is_2fa_enabled };
      localStorage.setItem('current_user', JSON.stringify(user));
    }
    if (!user || !user.full_name) {
      const me = await api.get('/api/auth/me');
      user = { full_name: me.full_name, role: me.role, is_2fa_enabled: me.is_2fa_enabled };
      localStorage.setItem('current_user', JSON.stringify(user));
    }

    const right = document.getElementById('nav-right') || nav.querySelector('.nav-right');
    if (right) {
      const initials = user.full_name.split(' ').map(w => w[0]).slice(0,2).join('').toUpperCase();
      right.innerHTML = `
        <a href="/notifications" id="nav-bell" title="Notifications" aria-label="Notifications" style="position:relative;text-decoration:none;font-size:1.15rem;margin-right:.4rem;line-height:1;color:rgba(244,247,250,.65)">
          <svg class="lc lc-lg" aria-hidden="true"><use href="/static/lucide.svg#lc-bell"/></svg><span id="nav-bell-count" style="display:none;position:absolute;top:-6px;right:-8px;background:#DC4C64;color:#fff;font-size:.6rem;font-weight:800;min-width:15px;height:15px;border-radius:8px;padding:0 3px;text-align:center;line-height:15px"></span>
        </a>
        <a href="/account" class="nav-user" style="text-decoration:none" title="Account & settings">
          <div class="nav-avatar">${esc(initials)}</div>
          <div>
            <div class="nav-user-name">${esc(user.full_name.split(' ')[0])}</div>
            <div class="nav-user-role">${user.role.replace('_',' ')}${user.is_2fa_enabled ? ' 🔐' : ''}</div>
          </div>
        </a>
        <button onclick="auth.logout()" class="btn btn-ghost btn-sm" style="color:rgba(255,255,255,.5);border-color:rgba(255,255,255,.12);font-size:.78rem">Sign Out</button>`;
      refreshBell();
      maybeRequireConsent();
    }

    // Show 2FA setup banner if role requires it but not yet done
    if ((user.requires_2fa_setup || (
      ['advocate','judge','firm_admin','business'].includes(user.role) && !user.is_2fa_enabled
    )) && !document.querySelector('.banner-warning')) {   // de-dupe: initNav may run twice
      const banner = document.createElement('div');
      banner.className = 'banner-warning';
      banner.innerHTML = `⚠️ Your role requires 2FA. <a href="/setup-2fa">Set it up now →</a>`;
      const nav = document.querySelector('.topnav');
      nav?.insertAdjacentElement('afterend', banner);
    }
  } catch { /* token invalid — stay on page, they can still navigate */ }
}

/* Consent gate — invited members must accept terms on first login (DPDP) */
async function maybeRequireConsent() {
  if (location.pathname === '/consent') return;
  try {
    const r = await api.get('/api/auth/needs-consent');
    if (r && r.needs) window.location.href = '/consent';
  } catch (_) { /* don't block the app if this check fails */ }
}

/* Reminder bell — unread notification count in the nav */
async function refreshBell() {
  try {
    const { unread } = await api.get('/api/notifications/unread-count');
    const badge = document.getElementById('nav-bell-count');
    if (!badge) return;
    if (unread > 0) { badge.textContent = unread > 99 ? '99+' : unread; badge.style.display = ''; }
    else badge.style.display = 'none';
  } catch (_) { /* ignore */ }
}

/* ══════════════════════════════════════
   Auth guard — call on protected pages
══════════════════════════════════════ */
function requireAuth() {
  if (!auth.isLoggedIn()) {
    window.location.href = '/login';
    return false;
  }
  return true;
}

/* ══════════════════════════════════════
   Active nav link highlight
══════════════════════════════════════ */
function highlightNav() {
  document.querySelectorAll('.nav-links a').forEach(a => {
    const href = a.getAttribute('href');
    if (href === '/' ? location.pathname === '/' : location.pathname.startsWith(href)) {
      a.classList.add('active');
    }
  });
}

/* ══════════════════════════════════════
   UI helpers
══════════════════════════════════════ */
function toast(msg, type = '') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'show ' + type;
  clearTimeout(el._t);
  el._t = setTimeout(() => el.className = '', 3200);
}

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtDate(iso) {
  if (!iso) return '—';
  const [y,m,d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

function fmtAmt(n) {
  return '₹' + Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2 });
}

function todayISO() { return new Date().toISOString().slice(0, 10); }

function badge(val) {
  return `<span class="badge badge-${esc(val)}">${esc(val.replace(/_/g,' '))}</span>`;
}

function openModal(id)  { document.getElementById(id)?.classList.add('open'); }
function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }

/* Close modal on overlay click */
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
  }
});

function initTabs(containerSel) {
  const container = document.querySelector(containerSel);
  if (!container) return;
  container.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      container.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active', 'animate-in'));
      btn.classList.add('active');
      const panel = document.getElementById(btn.dataset.tab);
      if (panel) { panel.classList.add('active', 'animate-in'); }
    });
  });
}

/* ── Favicon (branded, injected on every page that loads utils.js) ── */
function injectFavicon() {
  if (document.querySelector('link[rel="icon"]')) return;
  const l = document.createElement('link');
  l.rel = 'icon'; l.type = 'image/svg+xml'; l.href = '/static/favicon.svg';
  document.head.appendChild(l);
}

/* ── Footer with legal links + advocate-only identity (LSAI-LEGAL-01/02) ── */
function injectFooter() {
  if (document.getElementById('app-footer') || !document.querySelector('.topnav')) return;
  const f = document.createElement('div');
  f.id = 'app-footer';
  f.style.cssText = 'max-width:1280px;margin:2.5rem auto 0;padding:1.25rem 1.75rem;border-top:1px solid var(--border);' +
    'font-size:.74rem;color:var(--text-3);display:flex;gap:1rem;flex-wrap:wrap;align-items:center;justify-content:space-between';
  f.innerHTML = '<span>For advocates &amp; law firms only · AI output requires advocate review · No guaranteed outcomes.</span>' +
    '<span style="display:flex;gap:.9rem;flex-wrap:wrap">' +
    '<a href="/legal/terms" style="color:var(--text-3);text-decoration:none">Terms</a>' +
    '<a href="/legal/privacy" style="color:var(--text-3);text-decoration:none">Privacy</a>' +
    '<a href="/legal/acceptable-use" style="color:var(--text-3);text-decoration:none">Acceptable Use</a>' +
    '<a href="/legal/grievance" style="color:var(--text-3);text-decoration:none">Grievance</a>' +
    '<a href="/legal" style="color:var(--gold);text-decoration:none">All policies</a></span>';
  document.body.appendChild(f);
}

/* ── PWA: make Juriscite installable on Android & iOS (manifest + SW + install prompt) ── */
function injectPWA() {
  if (!document.querySelector('link[rel="manifest"]')) {
    const m = document.createElement('link');
    m.rel = 'manifest'; m.href = '/manifest.webmanifest';
    document.head.appendChild(m);
  }
  const metas = [
    ['apple-mobile-web-app-capable', 'yes'],
    ['mobile-web-app-capable', 'yes'],
    ['apple-mobile-web-app-status-bar-style', 'black-translucent'],
    ['apple-mobile-web-app-title', 'Juriscite'],
    ['theme-color', '#0B0B0F'],
  ];
  metas.forEach(([n, c]) => {
    if (!document.querySelector(`meta[name="${n}"]`)) {
      const el = document.createElement('meta'); el.name = n; el.content = c;
      document.head.appendChild(el);
    }
  });
  if (!document.querySelector('link[rel="apple-touch-icon"]')) {
    const l = document.createElement('link');
    l.rel = 'apple-touch-icon'; l.href = '/static/apple-touch-icon.png';
    document.head.appendChild(l);
  }
  // Register the service worker — secure context only (https or localhost).
  const secure = location.protocol === 'https:' ||
    ['localhost', '127.0.0.1'].includes(location.hostname);
  if ('serviceWorker' in navigator && secure) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js').catch(() => {});
    });
  }
  // Android/Chrome install button — appears only when the browser reports installability.
  let deferredPrompt = null;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    showInstallButton(() => {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(() => { deferredPrompt = null; hideInstallButton(); });
    });
  });
  window.addEventListener('appinstalled', hideInstallButton);
}

function showInstallButton(onClick) {
  if (document.getElementById('pwa-install')) return;
  const b = document.createElement('button');
  b.id = 'pwa-install';
  b.textContent = '⬇ Install Juriscite';
  b.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:9999;border:none;cursor:pointer;' +
    'background:linear-gradient(135deg,#C8A96A,#C8A96A);color:#0B0F14;font-weight:800;border-radius:24px;' +
    'padding:.7rem 1.1rem;font-size:.82rem;box-shadow:0 6px 20px rgba(0,0,0,.4)';
  b.onclick = onClick;
  document.body.appendChild(b);
}
function hideInstallButton() { document.getElementById('pwa-install')?.remove(); }

/* ── Accessibility: skip link, label association, live-region toast (a11y pass) ── */
function injectA11y() {
  // Skip-to-content link → first main region (keyboard users bypass the nav).
  const main = document.querySelector('.page, main, .acct-wrap, .drafts-wrap, .legal-layout');
  if (main) {
    if (!main.id) main.id = 'main';
    main.setAttribute('tabindex', '-1');
    if (!document.querySelector('.skip-link')) {
      const sk = document.createElement('a');
      sk.className = 'skip-link';
      sk.href = '#' + main.id;
      sk.textContent = 'Skip to content';
      document.body.insertAdjacentElement('afterbegin', sk);
    }
  }
  // Toast = polite live region so screen readers announce success/error messages.
  const t = document.getElementById('toast');
  if (t) { t.setAttribute('role', 'status'); t.setAttribute('aria-live', 'polite'); t.setAttribute('aria-atomic', 'true'); }
  // Associate each label with its input (forms use sibling <label>+<input> without for/id).
  document.querySelectorAll('.form-group').forEach((g, i) => {
    const lbl = g.querySelector('label');
    const inp = g.querySelector('input, select, textarea');
    if (lbl && inp && !inp.id && !lbl.htmlFor) {
      const id = 'fld_' + i + '_' + Math.random().toString(36).slice(2, 7);
      inp.id = id; lbl.htmlFor = id;
    }
  });
}

/* ── Boot ── */
injectFavicon();
injectPWA();
injectFooter();
highlightNav();
initNav();
injectA11y();

/* ══════════════════════════════════════════════════════════════════════════
   Liquid-Glass 3D tilt enhancer (owner-directed 2026-07-12).
   Pointer-follow tilt + specular glare on key cards. Fully defensive:
   no-ops on touch / reduced-motion, idempotent, watches for dynamic tiles.
   Adds only a .tilt3d class + one .glass-glare span — never alters app markup
   or handlers, so every existing function keeps working.
   ══════════════════════════════════════════════════════════════════════════ */
(function () {
  try {
    var fine = window.matchMedia && window.matchMedia('(hover:hover) and (pointer:fine)').matches;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion:reduce)').matches;
    if (!fine || reduce) return;

    var SEL = '.stat-card,.hero-stat-card,.module-tile,.doc-type-card,.wb-tile,[data-tilt]';
    var MAX = 6; // degrees

    function enhance(el) {
      if (!el || el.__tilt) return;
      el.__tilt = true;
      el.classList.add('tilt3d');
      var glare = document.createElement('span');
      glare.className = 'glass-glare';
      el.appendChild(glare);
      var raf = 0;
      el.addEventListener('mousemove', function (e) {
        if (raf) return;
        raf = requestAnimationFrame(function () {
          raf = 0;
          var r = el.getBoundingClientRect();
          var px = (e.clientX - r.left) / r.width;   // 0..1
          var py = (e.clientY - r.top) / r.height;
          el.style.setProperty('--ry', ((px - 0.5) * 2 * MAX).toFixed(2) + 'deg');
          el.style.setProperty('--rx', ((0.5 - py) * 2 * MAX).toFixed(2) + 'deg');
          el.style.setProperty('--gx', (px * 100).toFixed(1) + '%');
          el.style.setProperty('--gy', (py * 100).toFixed(1) + '%');
        });
      });
      el.addEventListener('mouseleave', function () {
        el.style.setProperty('--rx', '0deg');
        el.style.setProperty('--ry', '0deg');
      });
    }

    function scan(root) {
      try { (root || document).querySelectorAll(SEL).forEach(enhance); } catch (_) {}
    }

    if (document.readyState !== 'loading') scan();
    else document.addEventListener('DOMContentLoaded', function () { scan(); });

    // Dynamically-rendered tiles (workbench, lists) get enhanced as they arrive.
    var mo = new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var added = muts[i].addedNodes;
        for (var j = 0; j < added.length; j++) {
          var n = added[j];
          if (n.nodeType === 1) {
            if (n.matches && n.matches(SEL)) enhance(n);
            scan(n);
          }
        }
      }
    });
    if (document.body) mo.observe(document.body, { childList: true, subtree: true });
    else document.addEventListener('DOMContentLoaded', function () {
      mo.observe(document.body, { childList: true, subtree: true });
    });
  } catch (_) { /* enhancement only — never break the page */ }
})();
