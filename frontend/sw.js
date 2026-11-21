const CACHE_NAME = "voice-register-v2";
const shell = ["./", "./index.html", "./styles.css", "./app.js", "./manifest.json", "./audio-worklet.js", "./icon.svg"];
const allowed = new Set(shell.map((path) => new URL(path, self.registration.scope).href));

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(shell)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith("voice-register-") && key !== CACHE_NAME)
      .map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET" || !allowed.has(event.request.url)) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
