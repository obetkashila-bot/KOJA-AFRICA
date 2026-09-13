const CACHE='koja-shell-v1';
const SHELL=['/','/health','/static/icons/koja-192.png','/static/icons/koja-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return; const u=new URL(e.request.url); if(u.origin!==location.origin)return; e.respondWith(fetch(e.request).then(r=>{if(r.ok && (u.pathname==='/'||u.pathname.startsWith('/static/'))) {const x=r.clone();caches.open(CACHE).then(c=>c.put(e.request,x));} return r;}).catch(()=>caches.match(e.request).then(r=>r||caches.match('/'))));});
