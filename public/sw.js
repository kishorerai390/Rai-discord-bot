// Rem - Official Service Worker (PWA Offline Resilience & Cache)
const CACHE_NAME = 'rem-music-v1';
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/icon.png',
  '/public/rem_avatar_static.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Network-first for dynamic API routes, WebSockets and controls
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws') || event.request.method !== 'GET') {
    return;
  }

  // Cache-first with network fallback for images and static assets
  if (url.pathname.startsWith('/public/') || url.pathname.endsWith('.png') || url.pathname.endsWith('.jpg')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        return cached || fetch(event.request).then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
          }
          return response;
        }).catch(() => cached);
      })
    );
    return;
  }

  // Stale-while-revalidate for HTML documents
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});

