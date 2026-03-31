const CACHE_NAME = "capos-v1";
const STATIC_ASSETS = ["/", "/manifest.json"];

// Install: cache static shell
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: network-first for API, cache-first for static assets
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET and API/WS requests
  if (event.request.method !== "GET") return;
  if (url.pathname.startsWith("/api") || url.pathname.startsWith("/auth") || url.pathname.startsWith("/agent")) return;

  // HTML navigation: network-first with cache fallback
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((resp) => {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return resp;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(
      caches.match(event.request).then((cached) =>
        cached || fetch(event.request).then((resp) => {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return resp;
        })
      )
    );
    return;
  }
});

// Push notification handler
self.addEventListener("push", (event) => {
  let data = { title: "CapOS", body: "New event" };
  try {
    if (event.data) data = event.data.json();
  } catch {
    if (event.data) data.body = event.data.text();
  }

  event.waitUntil(
    self.registration.showNotification(data.title || "CapOS", {
      body: data.body || data.message || "New event",
      icon: "/icons/icon-192.svg",
      badge: "/icons/icon-192.svg",
      tag: data.tag || "capos-default",
      data: data,
    })
  );
});

// Notification click: focus or open app
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      if (clients.length > 0) return clients[0].focus();
      return self.clients.openWindow("/");
    })
  );
});
