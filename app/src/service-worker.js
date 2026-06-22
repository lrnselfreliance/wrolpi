/* eslint-disable no-restricted-globals */

// WROLPi service worker (Workbox InjectManifest).  Production build only - `npm start` does not emit this,
// so local development is unaffected.  Scope is `/` (the build is served from the host root).
//
// v1 offline surface:
//   - The precached app shell makes all Calculators (incl. the One Time Pad, which is pure client-side
//     crypto - see otp.js) work fully offline.
//   - GET /api/inventory[/catalog] is cached NetworkFirst so inventories can be referenced offline.
//   - /api/status is NetworkOnly so the apiDown indicator always reflects reality.

import {clientsClaim} from 'workbox-core';
import {precacheAndRoute, createHandlerBoundToURL} from 'workbox-precaching';
import {registerRoute} from 'workbox-routing';
import {NetworkFirst, NetworkOnly} from 'workbox-strategies';
import {CacheableResponsePlugin} from 'workbox-cacheable-response';

clientsClaim();

// Precache the shell/JS/CSS emitted by the webpack build.  This is what lets the Calculators work offline.
precacheAndRoute(self.__WB_MANIFEST);

// react-router deep links (e.g. /inventory, /more/calculators) must resolve to the precached index.html when
// offline.  Serve index.html for navigation requests, but never for API, media, or file-asset requests.
const fileExtensionRegexp = new RegExp('/[^/?]+\\.[^/]+$');
registerRoute(
    ({request, url}) => {
        if (request.mode !== 'navigate') return false;
        if (url.pathname.startsWith('/api/')) return false;
        if (url.pathname.startsWith('/media/')) return false;
        if (url.pathname.match(fileExtensionRegexp)) return false;
        return true;
    },
    createHandlerBoundToURL(process.env.PUBLIC_URL + '/index.html')
);

// Status must always reflect reality - never serve a cached "up" status.
registerRoute(
    ({url}) => url.pathname === '/api/status',
    new NetworkOnly()
);

// Inventory is config-only and arrives in a single GET (see modules/inventory/api.py).  Cache it NetworkFirst
// so it stays fresh online and renders (read-only) offline.  GET only - PUT/POST writes won't match.
registerRoute(
    ({url, request}) => request.method === 'GET' && (
        url.pathname === '/api/inventory' ||
        url.pathname === '/api/inventory/' ||
        url.pathname === '/api/inventory/catalog'
    ),
    new NetworkFirst({
        cacheName: 'wrolpi-inventory',
        plugins: [new CacheableResponsePlugin({statuses: [200]})],
    })
);

// Proactively cache the inventory (and food catalog) the moment the worker activates, while the device is still
// online.  Relying on the page's first fetch is unreliable - especially on a fresh iOS "Add to Home Screen"
// install, where the just-installed worker is often not yet controlling the page when React fetches the
// inventory, so the NetworkFirst route never stores it and the offline page spins forever.  Caching at activate
// (with cache:'reload' to bypass the HTTP cache) guarantees an offline copy after the first online launch.
self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open('wrolpi-inventory');
        await Promise.allSettled([
            cache.add(new Request('/api/inventory', {cache: 'reload'})),
            cache.add(new Request('/api/inventory/catalog', {cache: 'reload'})),
        ]);
    })());
});

// Allow the page to tell a waiting SW to activate immediately (used by the update flow).
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
