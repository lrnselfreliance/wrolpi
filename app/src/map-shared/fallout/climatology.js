// The climatology: the winds aloft of 30 real past days of a month, the whole world, as
// wrolpi/scripts/build_fallout_climatology.py writes them.  With no forecast to go on, the fallout of
// the bursts is found in each day's winds, and the map shows on how many of the days it reached each
// place.  Shared by the app's map viewer and the standalone viewer: no imports from the app.
//
// A month's file (after gzip): 'WFCL', version (uint16 LE), header length (uint32 LE), the header
// (JSON), the heights of the levels (int16 LE, [level][lat][lon], m), then each day's u and v (int8,
// [level][lat][lon], m/s).

import {depositionGrid, landingSpots, sharpenGrid} from './model.js';
import {combineBursts} from './targets.js';
import {fieldWinds, prepareField} from './winds.js';

// How far around the bursts a day's winds are read (degrees).
export const CLIMATE_MARGIN = 12;
// A day's grid reaches as far as this dose rate (R/hr at H+1): the faintest band the map draws.
const DAY_FLOOR = 0.1;

// The bytes of a gzip file, unzipped (in a browser).
export async function gunzip(buffer) {
    const DecompressionStream = typeof window === 'undefined' ? undefined : window.DecompressionStream;
    if (!DecompressionStream) throw new Error('This browser cannot unzip the past days\' winds');
    const stream = new Blob([buffer]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Uint8Array(await new Response(stream).arrayBuffer());
}

// A month, from its unzipped bytes: {header, levels, nlat, nlon, heights, day(k) -> {u, v}, days}.
export function parseClimatology(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const magic = String.fromCharCode(...bytes.subarray(0, 4));
    if (magic !== 'WFCL') throw new Error('Not a fallout climatology file');
    const version = view.getUint16(4, true);
    if (version !== 1) throw new Error(`A climatology of version ${version} is not understood`);
    const headLength = view.getUint32(6, true);
    const header = JSON.parse(new TextDecoder().decode(bytes.subarray(10, 10 + headLength)));
    const levels = header.levels_hpa.length, nlat = header.lat[2], nlon = header.lon[2];
    const size = levels * nlat * nlon;
    let at = 10 + headLength;
    // Int16 may not be aligned in the file: copied out.
    const heights = new Int16Array(size);
    for (let i = 0; i < size; i++) heights[i] = view.getInt16(at + 2 * i, true);
    at += 2 * size;
    const days = header.days.length;
    if (bytes.byteLength < at + days * 2 * size) throw new Error('The climatology file is short');
    const start = at;
    const day = (k) => ({
        u: new Int8Array(bytes.buffer, bytes.byteOffset + start + k * 2 * size, size),
        v: new Int8Array(bytes.buffer, bytes.byteOffset + start + k * 2 * size + size, size),
    });
    return {bytes, header, levels, nlat, nlon, heights, day, days};
}

// The latitude and longitude of grid row `j` and column `i` (longitude from -180 to 180).
function place(clim, j, i) {
    const [lat0, dlat] = clim.header.lat, [lon0, dlon] = clim.header.lon;
    return [lat0 + j * dlat, ((lon0 + i * dlon + 180) % 360 + 360) % 360 - 180];
}

// Day `k`'s winds over `bounds` ([south, west, north, east], degrees, widened by CLIMATE_MARGIN), as
// a field of one hour (winds.js), at `time` (its hour, any time: the winds are held).
export function dayField(clim, k, bounds, time = '2000-01-01T12:00Z') {
    const [south, west, north, east] = bounds;
    const lonMargin = CLIMATE_MARGIN / Math.cos(Math.min(Math.max(Math.abs(south), Math.abs(north)), 80) * Math.PI / 180);
    const {u, v} = clim.day(k);
    const plane = clim.nlat * clim.nlon;
    const points = [], winds = [];
    for (let j = 0; j < clim.nlat; j++) {
        for (let i = 0; i < clim.nlon; i++) {
            const [lat, lon] = place(clim, j, i);
            if (lat < south - CLIMATE_MARGIN || lat > north + CLIMATE_MARGIN) continue;
            // Between west and east, with the margin, either side of the antimeridian.
            if (![lon, lon - 360, lon + 360].some((l) => l >= west - lonMargin && l <= east + lonMargin)) continue;
            const rows = [];
            for (let l = 0; l < clim.levels; l++) {
                const c = l * plane + j * clim.nlon + i;
                const e = u[c], n = v[c];
                rows.push([clim.heights[c], Math.hypot(e, n), (Math.atan2(-e, -n) * 180 / Math.PI + 360) % 360]);
            }
            points.push({lat, lon, elevation: 0});
            winds.push([rows]);
        }
    }
    return {source: 'climatology', fetched_at: time, spacing: clim.header.lat[1] < 0 ? -clim.header.lat[1] : clim.header.lat[1],
        points, hours: [time], winds, rain: points.map(() => [0])};
}

// The south, west, north, east of `bursts` ({lat, lon}).
export function burstBounds(bursts) {
    const lats = bursts.map((b) => b.lat), lons = bursts.map((b) => b.lon);
    return [Math.min(...lats), Math.min(...lons), Math.max(...lats), Math.max(...lons)];
}

// The fallout of `bursts` ([{lat, lon, yieldKt, fissionFraction}]) in day `k` of `clim`, on flat
// ground at sea level: a grid around the first burst, as depositionGrid gives it.  `onBurst()` hears
// each burst done, and is awaited (to let the page draw); null once `stopped()`.
export async function climateDay(clim, k, bursts, {onBurst = () => null, stopped = () => false} = {}) {
    const prepared = prepareField(dayField(clim, k, burstBounds(bursts)));
    const startMs = Date.parse(prepared.field.hours[0]);
    const runs = [];
    for (const b of bursts) {
        const winds = fieldWinds(prepared, {lat0: b.lat, lon0: b.lon, groundElevation: 0, startMs});
        const spots = landingSpots({yieldKt: b.yieldKt, winds, siteElevation: 0})
            .filter((s) => Number.isFinite(s.x) && Number.isFinite(s.y) && s.sigma > 0);
        runs.push({burst: b, spots, yieldKt: b.yieldKt, fissionFraction: b.fissionFraction});
        await onBurst();
        if (stopped()) return null;
    }
    const spots = combineBursts(bursts[0], runs);
    return sharpenGrid(depositionGrid(spots, {yieldKt: 1, boundsFloor: DAY_FLOOR}), spots);
}

// The cells of `grid` at or above `rate`: {x0, y0, cell, nx, indexes}, small enough to pass from a
// worker.
export function reachedCells(grid, rate) {
    const indexes = [];
    for (let c = 0; c < grid.values.length; c++) if (grid.values[c] >= rate) indexes.push(c);
    return {x0: grid.x0, y0: grid.y0, cell: grid.cell, nx: grid.nx, indexes: Int32Array.from(indexes)};
}

// How many bursts a worker does between the progress it reports.
const PROGRESS_EVERY = 8;

// Answer climatePool.js's messages to a worker, `scope` (its self): 'start' gives it the month's
// unzipped bytes, the bursts and the rate; each 'day' (`k`) it calculates, saying how many bursts
// it has done ('progress'), then the cells reached ('day'), or why it could not ('error').
export function serveClimateDays(scope) {
    let clim = null, bursts = null, rate = 1;
    scope.onmessage = async ({data}) => {
        if (data.type === 'start') {
            clim = parseClimatology(new Uint8Array(data.bytes));
            bursts = data.bursts;
            rate = data.rate;
            return;
        }
        if (data.type !== 'day') return;
        const {k} = data;
        try {
            let done = 0;
            const grid = await climateDay(clim, k, bursts, {
                onBurst: () => {
                    if (++done % PROGRESS_EVERY === 0) scope.postMessage({type: 'progress', k, done});
                },
            });
            const reached = reachedCells(grid, rate);
            scope.postMessage({type: 'day', k, done, reached}, [reached.indexes.buffer]);
        } catch (e) {
            scope.postMessage({type: 'error', k, message: String(e?.stack || e)});
        }
    };
}

// How many days reached each place: a counter of days' grids (as depositionGrid gives them, all
// around the same origin), at or above `rate`, on cells `cell` meters wide.
export function dayCounter(rate, cell) {
    const counts = new Map();
    let days = 0;
    return {
        // A day: its grid, or the cells of it reached (as reachedCells gives them).
        add(day) {
            days++;
            const {x0, y0, cell: size, nx, indexes} = day.indexes ? day : reachedCells(day, rate);
            const seen = new Set();
            for (const c of indexes) {
                const x = x0 + (c % nx + 0.5) * size, y = y0 + (Math.floor(c / nx) + 0.5) * size;
                seen.add(`${Math.floor(x / cell)},${Math.floor(y / cell)}`);
            }
            for (const key of seen) counts.set(key, (counts.get(key) || 0) + 1);
        },
        // The share of days (0..1) on a grid of `cell` cells around the places reached, each the
        // average over itself and its neighbors within `smooth` cells.
        grid(smooth = 1) {
            if (!counts.size) return null;
            let i0 = Infinity, i1 = -Infinity, j0 = Infinity, j1 = -Infinity;
            for (const key of counts.keys()) {
                const [i, j] = key.split(',').map(Number);
                i0 = Math.min(i0, i); i1 = Math.max(i1, i); j0 = Math.min(j0, j); j1 = Math.max(j1, j);
            }
            i0 -= smooth; j0 -= smooth; i1 += smooth; j1 += smooth;
            const nx = i1 - i0 + 1, ny = j1 - j0 + 1;
            const raw = new Float64Array(nx * ny);
            for (const [key, n] of counts) {
                const [i, j] = key.split(',').map(Number);
                raw[(j - j0) * nx + (i - i0)] = n / days;
            }
            const values = new Float64Array(nx * ny);
            const width = (2 * smooth + 1) ** 2;
            for (let j = 0; j < ny; j++) {
                for (let i = 0; i < nx; i++) {
                    let sum = 0;
                    for (let b = -smooth; b <= smooth; b++) {
                        const jj = j + b;
                        if (jj < 0 || jj >= ny) continue;
                        for (let a = -smooth; a <= smooth; a++) {
                            const ii = i + a;
                            if (ii >= 0 && ii < nx) sum += raw[jj * nx + ii];
                        }
                    }
                    values[j * nx + i] = sum / width;
                }
            }
            return {x0: i0 * cell, y0: j0 * cell, cell, nx, ny, values, days};
        },
        get days() {
            return days;
        },
    };
}

