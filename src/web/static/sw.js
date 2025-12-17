self.addEventListener('install', (event) => {
    console.log('Service Worker installing.');
});

self.addEventListener('fetch', (event) => {
    // Simple pass-through for now, can implement caching later
    event.respondWith(fetch(event.request));
});
