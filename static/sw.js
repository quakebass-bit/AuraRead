const CACHE_NAME = 'auraread-cache-v1';

self.addEventListener('install', (e) => {
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(clients.claim());
});

self.addEventListener('fetch', (e) => {
    // Пропускаем синтез речи и сохранение прогресса напрямую в сеть
    if (e.request.url.includes('/synthesize') || e.request.url.includes('/save_progress')) {
        return;
    }
    e.respondWith(
        fetch(e.request).catch(() => caches.match(e.request))
    );
});