// The climatology: the winds aloft of 30 real past days of a month, the whole world, as
// wrolpi/scripts/build_fallout_climatology.py writes them.  With no forecast to go on, the fallout of
// the bursts is found in each day's winds, and the map shows on how many of the days it reached each
// place.  Shared by the app's map viewer and the standalone viewer: no imports from the app.
//
// A month's file (after gzip): 'WFCL', version (uint16 LE), header length (uint32 LE), the header
// (JSON), the heights of the levels (int16 LE, [level][lat][lon], m), then each day's u and v (int8,
// [level][lat][lon], m/s).

// How far around the bursts a day's winds are read (degrees).
export const CLIMATE_MARGIN = 12;

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
    return {header, levels, nlat, nlon, heights, day, days};
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

// How many days reached each place: a counter of days' grids (as depositionGrid gives them, all
// around the same origin), at or above `rate`, on cells `cell` meters wide.
export function dayCounter(rate, cell) {
    const counts = new Map();
    let days = 0;
    return {
        add(grid) {
            days++;
            const seen = new Set();
            for (let j = 0; j < grid.ny; j++) {
                for (let i = 0; i < grid.nx; i++) {
                    if (!(grid.values[j * grid.nx + i] >= rate)) continue;
                    const x = grid.x0 + (i + 0.5) * grid.cell, y = grid.y0 + (j + 0.5) * grid.cell;
                    seen.add(`${Math.floor(x / cell)},${Math.floor(y / cell)}`);
                }
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

