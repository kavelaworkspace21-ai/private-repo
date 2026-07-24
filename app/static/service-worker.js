/*
 * Juriscite service worker.
 *
 * PRIVACY-FIRST (safety doctrine): this SW NEVER caches API responses (/api/*) — client/matter
 * data and auth tokens are always fetched fresh over the network and never stored on disk by the
 * cache. It only precaches PUBLIC static shell assets (CSS/JS/icons) + an offline page, so the app
 * shell loads instantly and shows a graceful offline screen when the network is unavailable.
 */
// BUMP THIS on EVERY release that changes ANY static asset — not just SHELL entries.
// The fetch handler also runtime-caches same-origin GETs into this same versioned cache,
// so returning PWA users keep old page JS until the version changes. (Bitten twice:
// v1 hid the Workbench nav link; v2 served a stale workbench.js without the WB-03 flow.)
const VERSION = 'juriscite-v10';   // v10: dashboard cube now shows the Juriscite logo mark (style.css + logo-mark.svg)
const SHELL = [
  '/static/style.css',
  '/static/utils.js',
  '/static/chart.umd.min.js',
  '/static/offline.html',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/apple-touch-icon.png',
  '/static/favicon.svg',
  '/static/logo-mark.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle same-origin GETs. Everything else (POST, cross-origin) goes straight to network.
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;

  // NEVER cache API / auth / data endpoints — always network, never stored.
  if (url.pathname.startsWith('/api/')) return;

  // Navigations (page loads): network-first, fall back to cached offline page when offline.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => caches.match('/static/offline.html'))
    );
    return;
  }

  // Static shell assets: stale-while-revalidate (fast load, refresh in background).
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.open(VERSION).then((cache) =>
        cache.match(req).then((cached) => {
          const network = fetch(req).then((res) => {
            if (res && res.status === 200) cache.put(req, res.clone());
            return res;
          }).catch(() => cached);
          return cached || network;
        })
      )
    );
  }
});
