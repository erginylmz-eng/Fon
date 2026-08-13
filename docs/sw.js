// TEFAS Takip - basit "once ag, olmazsa onbellek" (network-first) service worker.
// Amac: telefonda ana ekrana eklenince uygulama gibi acilabilsin ve internet
// yoksa en son gorulen veriyi gosterebilsin. Veri her gun degistigi icin
// cevrimici oldugunda HER ZAMAN aga gidilir; onbellek sadece cevrimdisi
// yedek olarak kullanilir.
const CACHE_NAME = 'tefas-takip-v1';
const PRECACHE_URLS = [
  'index.html',
  'karar.html',
  'karsilastir.html',
  'fon.html',
  'disaaktar.html',
  'manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return; // CDN kaynaklarina (Chart.js vb.) dokunma

  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const resClone = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, resClone));
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});
