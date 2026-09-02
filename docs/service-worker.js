// 퀀트 코인 전략 웹 대시보드 PWA 서비스 워커
const CACHE_NAME = 'quant-dashboard-v1.8.6';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './manifest.json',
  './icons/icon.svg',
  './images/backtest_main.png',
  './images/backtest_sub_eth.png',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js'
];

// 1. 서비스 워커 설치 이벤트: 핵심 앱 셸 캐싱 및 즉시 대기열 통과
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

// 2. 활성화 이벤트: 구버전 캐시 정리 및 즉시 클라이언트 제어
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// 3. 네트워크 요청 가로채기 이벤트: HTML 네비게이션 및 실시간 상태 JSON은 네트워크 우선(Network-First), 정적 아이콘/매니페스트는 캐시 우선(Cache-First)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  const isHtml = event.request.mode === 'navigate' || url.pathname.endsWith('index.html') || url.pathname.endsWith('/');
  const isStatusJson = url.pathname.endsWith('status.json');

  // HTML 문서 및 전략 상태 데이터: 네트워크 우선 (항상 최신 버전 반영)
  if (isHtml || isStatusJson) {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return networkResponse;
        })
        .catch(() => {
          // 오프라인 상태일 때 로컬 캐시로 안전하게 폴백
          return caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) return cachedResponse;
            if (isHtml) return caches.match('./index.html');
          });
        })
    );
    return;
  }

  // 정적 자산(아이콘, 매니페스트): 캐시 우선
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then((networkResponse) => {
        if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
          return networkResponse;
        }
        const responseToCache = networkResponse.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, responseToCache);
        });
        return networkResponse;
      });
    })
  );
});
