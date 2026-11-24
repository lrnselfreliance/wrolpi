// The fallout's work, as the page or a worker (fallout.worker.js, by pool.js) does it: the same
// functions either way, so the fallout is the same.  No imports from the app.
import {climateDay, parseClimatology, reachedCells} from './climatology.js';
import {depositionGrid, gridFrame, landingSpots, sharpening} from './model.js';
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

// How many parts the bursts' grid is made in (by as many workers, at most).  Always as many, by the
// page or by workers: the parts are added up in the same order, so the grid is the same.
export const GRID_PARTS = 6;

// The spots of bursts (as combineBursts gives them, each with its `run`) in GRID_PARTS parts of
// about as many spots, a burst's spots all in one part (sharpening looks at a burst's at once).
export function gridParts(spots) {
    const runs = new Map();
    for (const s of spots) {
        if (!runs.has(s.run)) runs.set(s.run, []);
        runs.get(s.run).push(s);
    }
    const parts = Array.from({length: GRID_PARTS}, () => []);
    // The largest first, each to the part with the fewest so far.
    for (const run of [...runs.values()].sort((a, b) => b.length - a.length)) {
        let least = 0;
        for (let p = 1; p < GRID_PARTS; p++) if (parts[p].length < parts[least].length) least = p;
        for (const s of run) parts[least].push(s);
    }
    return parts.filter((p) => p.length);
}

// The frame (as gridFrame gives it) of the bursts' grid, of their `spots`: as far as the faintest
// band drawn, `floor` (R/hr at H+1); no further, where nothing would show.
export function burstsFrame(spots, floor) {
    return gridFrame(spots, {yieldKt: 1, boundsFloor: floor});
}

// One part of the bursts' grid, on `frame`: the dose rates of the part's `spots`, and how much they
// sharpen each cell (or null), as Float64Arrays.
export function gridPart(frame, spots) {
    return {values: depositionGrid(spots, {yieldKt: 1, frame}).values, extra: sharpening(frame, spots)};
}

// The bursts' grid from its parts (in order): the dose rates added up, and each cell sharpened by
// the most any part sharpens it.  The hot fallout close to a small burst is not averaged away in a
// grid over them all (sharpenGrid).
export function joinParts(frame, parts) {
    const values = new Float64Array(frame.nx * frame.ny);
    const extra = new Float64Array(frame.nx * frame.ny);
    for (const part of parts) {
        for (let k = 0; k < values.length; k++) values[k] += part.values[k];
        if (part.extra) for (let k = 0; k < extra.length; k++) if (part.extra[k] > extra[k]) extra[k] = part.extra[k];
    }
    for (let k = 0; k < values.length; k++) values[k] += extra[k];
    return {...frame, values};
}

// How many bursts of a day a worker does between the progress it reports.
const PROGRESS_EVERY = 8;

// The tasks of a worker, from what pool.js starts it with, `start`: `kind` 'days' (a past day each:
// `bytes`, the month unzipped; `bursts`; `rate`), 'bursts' (a burst each: `bursts`; `field` (a
// forecast) and `startMs`, or `profile`; `terrain`, or null), or 'grid' (a part of the bursts' grid
// each, on `frame`; the task gives its `spots`).  (task, progress(done)) => {result, transfer (what
// of it to transfer), done}.
function tasksOf(start) {
    if (start.kind === 'days') {
        const clim = parseClimatology(new Uint8Array(start.bytes));
        const {bursts, rate} = start;
        return async ({k}, progress) => {
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
    if (start.kind === 'grid') {
        return async ({spots}) => {
            const part = gridPart(start.frame, spots);
            return {result: part, transfer: [part.values.buffer, ...(part.extra ? [part.extra.buffer] : [])], done: 1};
        };
    }
    const {bursts, field, startMs, profile, terrain} = start;
    const winds = burstWinds({prepared: field ? prepareField(field) : null, startMs, profile});
    return async ({k}) => ({result: burstSpots(bursts[k], {...winds, terrain}), transfer: [], done: 1});
}

// Answer pool.js's messages to a worker, `scope` (its self): 'start' says what the tasks need; each
// 'task' (`k`, and what else it needs) it does, saying how much of it it has done ('progress'), then its result ('done'), or
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
            const {result, transfer, done} = await task(data, (n) => scope.postMessage({type: 'progress', k, done: n}));
            scope.postMessage({type: 'done', k, done, result}, transfer);
        } catch (e) {
            scope.postMessage({type: 'error', k, message: String(e?.stack || e)});
        }
    };
}
