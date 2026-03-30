// No-op service worker — prevents stale cache issues
// The app works fine without a SW; this file exists only to
// replace any previously installed SW so the browser stops caching.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
  );
  self.clients.claim();
});
