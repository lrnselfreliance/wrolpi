// The fallout, spread over workers (fallout.worker.js), each on its own core: a worker is given a
// task (a past day, or a burst), and when it is done, the next not yet given.  No imports from the
// app.

// The most workers run at once: past this, more add heat more than speed.
export const MOST_WORKERS = 6;

// How many workers to run on a device which says it has `hardwareConcurrency` cores and
// `deviceMemory` GB (navigator; either may be missing): one core is left for the page, and a
// device with little memory runs few (each worker of the past days holds a month, about 40-60 MB
// in all).
export function workerCount({hardwareConcurrency, deviceMemory} = {}) {
    const cores = Number(hardwareConcurrency) || 2;
    let count = Math.min(Math.max(cores - 1, 1), MOST_WORKERS);
    if (deviceMemory && deviceMemory <= 2) count = Math.min(count, 2);
    return count;
}

// `tasks` tasks (0..tasks-1) done by `count` workers from `makeWorker()`, each given `start` (a
// message: what every task needs), then a task (with what `payload(k)` gives, if it needs more),
// and when it is done the next not yet given: the results, in the order of the tasks, or null if
// `signal` (an AbortSignal) is aborted, which stops the workers at once.  A task's worker says how much of it is done ('progress'), then its result
// ('done'); `onProgress(done, total)` hears how much of all of them is done, of `total`.  Rejects if
// a worker fails (or cannot be made).  The workers answer as work.js's serveFallout does.
export function runPool({tasks, start, payload = () => null, total, count, makeWorker, signal, onProgress = () => null}) {
    return new Promise((resolve, reject) => {
        const workers = [];
        const results = new Array(tasks).fill(null);
        const doneOf = new Array(tasks).fill(0);
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
            if (next >= tasks) return;
            const k = next++;
            worker.postMessage({type: 'task', k, ...payload(k)});
        };
        const heard = (worker, data) => {
            if (over) return;
            if (data.type === 'error') {
                fail(new Error(data.message));
                return;
            }
            doneOf[data.k] = data.done;
            if (data.type === 'done') {
                results[data.k] = data.result;
                finished++;
                if (finished === tasks) {
                    stop();
                    progress();
                    resolve(results);
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
        if (!tasks) {
            resolve(results);
            return;
        }
        signal?.addEventListener('abort', aborted);
        try {
            for (let i = 0; i < Math.min(count, tasks); i++) {
                const worker = makeWorker();
                if (!worker) throw new Error('No worker could be made');
                workers.push(worker);
                worker.onerror = failed;
                worker.onmessage = ({data}) => heard(worker, data);
                worker.postMessage({type: 'start', ...start});
                give(worker);
            }
        } catch (e) {
            fail(e);
        }
    });
}
