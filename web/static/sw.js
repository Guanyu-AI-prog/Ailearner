const CACHE_NAME = 'ailearner-v1';
const STATIC_ASSETS = [
  '/',
  '/chat',
  '/static/style.css',
  '/static/app.js',
  '/static/manifest.json',
  '/static/icon-192.svg',
  '/static/icon-512.svg',
];

// 安装：缓存核心页面
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// 激活：清理旧缓存
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 请求拦截：静态资源走缓存，API请求走网络
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // API 请求（对话、评估等）始终走网络
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/chat/stream')) {
    return;
  }

  e.respondWith(
    caches.match(e.request).then((cached) => {
      // 有缓存就先返回，同时后台更新
      const fetched = fetch(e.request).then((response) => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
        }
        return response;
      }).catch(() => cached);

      return cached || fetched;
    })
  );
});
