const CACHE = 'koja-shell-2026-09-13-v2';
const SHELL = ['/', '/static/manifest.json', '/static/koja-logo.svg', '/static/favicon-48.png', '/static/favicon-180.png', '/static/favicon-192.png', '/static/icon-512.png', '/static/offline.html'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('koja-shell-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith((async () => {
    try {
      const network = await fetch(req);
      if (network.ok && (req.destination === 'document' || req.destination === 'script' || req.destination === 'style' || req.destination === 'image' || url.pathname.startsWith('/static/'))) {
        const copy = network.clone();
        caches.open(CACHE).then(cache => cache.put(req, copy)).catch(()=>{});
      }
      return network;
    } catch (e) {
      const cached = await caches.match(req);
      if (cached) return cached;
      if (req.destination === 'document') return caches.match('/static/offline.html');
      return new Response('', {status:503, statusText:'Offline'});
    }
  })());
});
