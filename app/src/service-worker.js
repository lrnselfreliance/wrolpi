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

// Allow the page to tell a waiting SW to activate immediately (used by the update flow).
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
