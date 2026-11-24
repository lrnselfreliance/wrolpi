// The fallout's work, as the page or a worker (fallout.worker.js, by pool.js) does it: the same
// functions either way, so the fallout is the same.  No imports from the app.
import {climateDay, parseClimatology, reachedCells} from './climatology.js';
import {landingSpots} from './model.js';
import {terrainAround} from './terrain.js';
import {fieldWinds, nearestPoint, prepareField} from './winds.js';

// The winds over bursts, from `winds`: {prepared (a field, as prepareField gives it), startMs}, each
// burst carried by the winds where it is from that time; or {profile}, one profile over them all.
// {windsFor(burst, groundElevation), as landingSpots takes them; groundOf(burst), how high (m) its
// ground is until the terrain is read: the field's ground near it, or the sea's}.
export function burstWinds({prepared = null, startMs = 0, profile = null}) {
    if (!prepared) return {windsFor: () => ({profile}), groundOf: () => 0};
    return {
        windsFor: (b, groundElevation) => ({winds: fieldWinds(prepared, {lat0: b.lat, lon0: b.lon, groundElevation, startMs})}),
        groundOf: (b) => prepared.field.points[nearestPoint(prepared, b.lat, b.lon)].elevation,
    };
}

// Where the fallout of `burst` lands, in `windsFor` (as burstWinds gives them), over `terrain` (an
// elevation grid, as terrain.js reads it) or flat ground from `groundOf(burst)`: {spots (those on
// the map), offMap (whether some were not)}.
export function burstSpots(burst, {windsFor, groundOf, terrain = null}) {
    const around = terrain ? terrainAround(terrain, burst.lon, burst.lat) : null;
    const ground = around ? around.elevation : groundOf(burst);
    const spots = landingSpots({yieldKt: burst.yieldKt, ...windsFor(burst, ground), terrain: around,
        siteElevation: Math.max(ground, 0)});
    // A spot not on the map (from ground with no number under it) would break the whole grid.
    const finite = spots.filter((s) => Number.isFinite(s.x) && Number.isFinite(s.y) && s.sigma > 0);
    return {spots: finite, offMap: finite.length < spots.length};
}

// How many bursts of a day a worker does between the progress it reports.
const PROGRESS_EVERY = 8;

// The tasks of a worker, from what pool.js starts it with, `start`: `kind` 'days' (a past day each:
// `bytes`, the month unzipped; `bursts`; `rate`), or 'bursts' (a burst each: `bursts`; `field` (a
// forecast) and `startMs`, or `profile`; `terrain`, or null).  (k, progress(done)) => {result,
// transfer (what of it to transfer), done}.
function tasksOf(start) {
    if (start.kind === 'days') {
        const clim = parseClimatology(new Uint8Array(start.bytes));
        const {bursts, rate} = start;
        return async (k, progress) => {
            let done = 0;
            const grid = await climateDay(clim, k, bursts, {
                onBurst: () => {
                    if (++done % PROGRESS_EVERY === 0) progress(done);
                },
            });
            const reached = reachedCells(grid, rate);
            return {result: reached, transfer: [reached.indexes.buffer], done};
        };
    }
    const {bursts, field, startMs, profile, terrain} = start;
    const winds = burstWinds({prepared: field ? prepareField(field) : null, startMs, profile});
    return async (k) => ({result: burstSpots(bursts[k], {...winds, terrain}), transfer: [], done: 1});
}

// Answer pool.js's messages to a worker, `scope` (its self): 'start' says what the tasks need; each
// 'task' (`k`) it does, saying how much of it it has done ('progress'), then its result ('done'), or
// why it could not ('error').
export function serveFallout(scope) {
    let task = null;
    scope.onmessage = async ({data}) => {
        if (data.type === 'start') {
            try {
                task = tasksOf(data);
            } catch (e) {
                scope.postMessage({type: 'error', message: String(e?.stack || e)});
            }
            return;
        }
        if (data.type !== 'task' || !task) return;
        const {k} = data;
        try {
            const {result, transfer, done} = await task(k, (n) => scope.postMessage({type: 'progress', k, done: n}));
            scope.postMessage({type: 'done', k, done, result}, transfer);
        } catch (e) {
            scope.postMessage({type: 'error', k, message: String(e?.stack || e)});
        }
    };
}
