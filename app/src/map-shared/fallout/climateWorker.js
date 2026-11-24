// A worker for the past days' fallout, or null where a browser has none.  Alone in its own file:
// Jest cannot read import.meta, so it is given a stand-in (package.json, "jest").
export function makeClimateWorker() {
    if (typeof Worker === 'undefined') return null;
    return new Worker(new URL('./climate.worker.js', import.meta.url));
}
