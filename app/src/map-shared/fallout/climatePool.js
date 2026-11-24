// The past days' fallout, spread over workers (climate.worker.js), each on its own core: a worker
// is given a day, and when it is done, the next day not yet given.  No imports from the app.

// The most workers run at once: past this, more add heat more than speed.
export const MOST_WORKERS = 6;

// How many workers to run on a device which says it has `hardwareConcurrency` cores and
// `deviceMemory` GB (navigator; either may be missing): one core is left for the page, and a
// device with little memory runs few (each worker holds a month, about 40-60 MB in all).
export function workerCount({hardwareConcurrency, deviceMemory} = {}) {
    const cores = Number(hardwareConcurrency) || 2;
    let count = Math.min(Math.max(cores - 1, 1), MOST_WORKERS);
    if (deviceMemory && deviceMemory <= 2) count = Math.min(count, 2);
    return count;
}

// Each day of `clim` for `bursts`, by `count` workers from `makeWorker()`: the cells reached at
// `rate` of every day (as reachedCells gives them, in the order of the days), or null if `signal`
// (an AbortSignal) is aborted, which stops the workers at once.  `onProgress(done, total)` hears
// how many bursts are done of all the days'.  Rejects if a worker fails (or cannot be made).
export function runClimateDays({clim, bursts, rate, count, makeWorker, signal, onProgress = () => null}) {
    return new Promise((resolve, reject) => {
        const workers = [];
        const days = new Array(clim.days).fill(null);
        const doneOf = new Array(clim.days).fill(0);
        const total = clim.days * bursts.length;
        let next = 0, finished = 0, over = false;
        const stop = () => {
            over = true;
            for (const w of workers) w.terminate();
            signal?.removeEventListener('abort', aborted);
        };
        const aborted = () => {
            if (over) return;
            stop();
            resolve(null);
        };
        const fail = (error) => {
            if (over) return;
            stop();
            reject(error);
        };
        const progress = () => onProgress(doneOf.reduce((a, n) => a + n, 0), total);
        const give = (worker) => {
            if (next < clim.days) worker.postMessage({type: 'day', k: next++});
        };
        const heard = (worker, data) => {
            if (over) return;
            if (data.type === 'error') {
                fail(new Error(data.message));
                return;
            }
            doneOf[data.k] = data.done;
            if (data.type === 'day') {
                days[data.k] = data.reached;
                finished++;
                if (finished === clim.days) {
                    stop();
                    progress();
                    resolve(days);
                    return;
                }
                give(worker);
            }
            progress();
        };
        const failed = (e) => fail(new Error(e.message || 'A fallout worker failed'));
        if (signal?.aborted) {
            resolve(null);
            return;
        }
        signal?.addEventListener('abort', aborted);
        const plain = bursts.map(({lat, lon, yieldKt, fissionFraction}) => ({lat, lon, yieldKt, fissionFraction}));
        try {
            for (let i = 0; i < Math.min(count, clim.days); i++) {
                const worker = makeWorker();
                if (!worker) throw new Error('No worker could be made');
                workers.push(worker);
                worker.onerror = failed;
                worker.onmessage = ({data}) => heard(worker, data);
                worker.postMessage({type: 'start', bytes: clim.bytes, bursts: plain, rate});
                give(worker);
            }
        } catch (e) {
            fail(e);
        }
    });
}
