// Installable shell only. Never intercept authenticated API requests or cache credentials.
const CACHE='reason-cloud-shell-03';
const SHELL=['/','/style.css','/cloud.js','/icon.svg','/manifest.webmanifest'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL))));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))));
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.origin!==location.origin||!SHELL.includes(u.pathname))return;e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});
