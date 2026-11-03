// Service worker minimal : rend l'application installable et affiche une page hors-ligne.
const CACHE = "fusee-v3";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["/", "/icon-192.png"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET" || new URL(e.request.url).pathname.startsWith("/api/")) return;
  const page = e.request.mode === "navigate";  // la page : toujours la version du Mac, jamais une vieille copie
  e.respondWith((page ? fetch(e.request.url, {cache: "no-store", credentials: "include"}) : fetch(e.request)).then(r => {
    if (r.ok && new URL(e.request.url).pathname === "/") { const copy = r.clone(); caches.open(CACHE).then(c => c.put("/", copy)); }
    return r;
  }).catch(() => caches.match(e.request)));
});

// Notifications envoyées par Fusée (chiffrées de bout en bout)
self.addEventListener("push", e => {
  let d = {title: "Fusée 🚀", body: "", url: "/"};
  try { d = Object.assign(d, e.data.json()); } catch (err) {}
  e.waitUntil(self.registration.showNotification(d.title, {body: d.body, icon: "/icon-192.png", badge: "/icon-192.png",
    data: {url: d.url}, tag: "fusee-" + Date.now()}));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(list => {
    for (const c of list) { if ("focus" in c) { c.navigate(url).catch(() => {}); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
