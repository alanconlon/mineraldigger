/* MineralDigger service worker. Deliberately small, so it stays out of the way of the live site:
   - Pages (HTML): network first, always. A copy of each page you open is kept on the phone. Only if the
     network fails (or gives nothing for 8 seconds on a weak signal) is the saved copy shown, with a
     "saved copy" notice on top. With no saved copy you get the offline page.
   - Listing data (*.json): network first, saved copy only if the network fails.
   - Other same-origin images, icons, CSS and scripts: shown from the cache, refreshed in the background.
   - Everything else is left alone: non-GET requests, Stripe, Buttondown, map tiles and any other site.
   Cache names carry the build version; old caches are deleted when a new version activates. */
"use strict";
const VERSION = "__MD_VERSION__";
const PREFIX = "md-";
const STATIC_CACHE = PREFIX + "static-" + VERSION;
const PAGE_CACHE = PREFIX + "pages-" + VERSION;
const OFFLINE_URL = "/offline/";
const PRECACHE = [OFFLINE_URL, "/site.css", "/pwa.js", "/icons/icon-192.png", "/favicon.svg"];
const MAX_PAGES = 60;
const TIMEOUT_MS = 8 * 1000;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((c) => c.addAll(PRECACHE.map((u) => new Request(u, { cache: "reload" }))))
      .then(() => caches.open(PAGE_CACHE).then((c) => c.add("/")).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith(PREFIX) && k !== STATIC_CACHE && k !== PAGE_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function isHTML(res) { return (res.headers.get("content-type") || "").includes("text/html"); }
function cacheable(res) { return res && res.ok && (res.type === "basic" || res.type === "cors"); }

async function trim(cache) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - MAX_PAGES; i++) await cache.delete(keys[i]);
}

async function markSaved(res) {
  try {
    let when = "";
    const d = res.headers.get("date");
    if (d) when = " from " + new Date(d).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    const note = '<div role="status" style="background:#fff3cd;color:#3b2a00;border-bottom:1px solid #e6cf85;padding:9px 14px;font:14px/1.4 system-ui,-apple-system,sans-serif;text-align:center">' +
      "No signal, so this is a saved copy" + when + ". Details may have changed. " +
      '<a href="" style="color:inherit;font-weight:600">Try again</a></div>';
    const text = (await res.text()).replace(/<body([^>]*)>/i, (m) => m + note);
    const headers = new Headers(res.headers);
    headers.delete("content-length");
    return new Response(text, { status: 200, headers });
  } catch (e) {
    return res;
  }
}

async function offline() {
  return (await caches.match(OFFLINE_URL)) ||
    new Response("<!doctype html><meta name=viewport content='width=device-width'><title>Offline</title><p style='font:16px system-ui;padding:2em'>You're offline. Try again when you have a signal.</p>",
      { status: 503, headers: { "content-type": "text/html; charset=utf-8" } });
}

async function page(event) {
  const req = event.request;
  const cache = await caches.open(PAGE_CACHE);
  const network = fetch(req).then((res) => {
    if (cacheable(res) && isHTML(res) && !res.redirected) {
      const copy = res.clone();
      event.waitUntil(cache.put(req, copy).then(() => trim(cache)).catch(() => {}));
    }
    return res;
  });
  const saved = await cache.match(req, { ignoreVary: true });
  if (!saved) {
    return network.catch(offline);
  }
  let timer;
  const slow = new Promise((resolve) => { timer = setTimeout(() => resolve("slow"), TIMEOUT_MS); });
  const first = await Promise.race([network.then((r) => r, () => "failed"), slow]);
  clearTimeout(timer);
  if (first instanceof Response) return first;
  event.waitUntil(network.catch(() => {}));
  return markSaved(saved);
}

async function networkFirst(event) {
  const req = event.request;
  const cache = await caches.open(PAGE_CACHE);
  try {
    const res = await fetch(req);
    if (cacheable(res)) { const copy = res.clone(); event.waitUntil(cache.put(req, copy).catch(() => {})); }
    return res;
  } catch (e) {
    const saved = await cache.match(req);
    if (saved) return saved;
    throw e;
  }
}

async function staleWhileRevalidate(event) {
  const req = event.request;
  const cache = await caches.open(STATIC_CACHE);
  const hit = await cache.match(req);
  const network = fetch(req).then((res) => {
    if (cacheable(res)) { const copy = res.clone(); return cache.put(req, copy).then(() => res, () => res); }
    return res;
  });
  if (hit) { event.waitUntil(network.catch(() => {})); return hit; }
  return network;
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET" || req.headers.has("range")) return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const p = url.pathname;
  if (p === "/sw.js" || p.startsWith("/cdn-cgi/") || p.endsWith(".ics") || p.endsWith(".xml") || p.endsWith(".txt")) return;
  if (req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html")) {
    event.respondWith(page(event));
  } else if (p.endsWith(".json")) {
    event.respondWith(networkFirst(event));
  } else if (p.endsWith(".webmanifest")) {
    event.respondWith(staleWhileRevalidate(event));
  } else if (/\.(css|js|png|svg|jpe?g|webp|gif|ico|woff2?)$/.test(p)) {
    event.respondWith(staleWhileRevalidate(event));
  }
});
