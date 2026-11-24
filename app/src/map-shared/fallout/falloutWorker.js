// A fallout worker (fallout.worker.js), or null where a browser has none.  Alone in its own file:
// Jest cannot read import.meta, so it is given a stand-in (package.json, "jest").
export function makeFalloutWorker() {
    if (typeof Worker === 'undefined') return null;
    return new Worker(new URL('./fallout.worker.js', import.meta.url));
}
