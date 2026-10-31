// Service worker minimal : rend l'application installable et affiche une page hors-ligne.
const CACHE = "fusee-v1";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["/", "/icon-192.png"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET" || new URL(e.request.url).pathname.startsWith("/api/")) return;
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && new URL(e.request.url).pathname === "/") { const copy = r.clone(); caches.open(CACHE).then(c => c.put("/", copy)); }
    return r;
  }).catch(() => caches.match(e.request)));
});
