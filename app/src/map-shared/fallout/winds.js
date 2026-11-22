// The field of forecast winds aloft (as the API gives it: modules/map/winds.py), as the fallout model
// reads it.  Shared by the app's map viewer and the standalone viewer: no imports from the app, no
// dependencies.
//
// A field is {source, fetched_at, spacing (degrees), points: [{lat, lon, elevation}], hours: [time],
// winds: [for each point: [for each hour: [[height (m above sea level), speed (m/s), direction the
// wind blows FROM (degrees)]]]], rain: [for each point: [mm in each hour]]}.  Its points are on whole
// multiples of its spacing.
//
// The model asks for the wind many times for every particle (where it is, how high, and when), so a
// field is first prepared: each point's winds, hour by hour, resampled to altitudes LEVEL_STEP apart.
// A wind is then read between the four points around a place, the two hours around a time, and the
// two altitudes around a height.

const METERS_PER_DEGREE = 111320;
const LEVEL_STEP = 250;
const LOWEST_LEVEL = -500;
const HIGHEST_LEVEL = 30000;
const LEVELS = Math.round((HIGHEST_LEVEL - LOWEST_LEVEL) / LEVEL_STEP) + 1;

// The hour of `hours` (UTC times) nearest `when` (a Date): its index.
export function nearestHour(hours, when = new Date()) {
    let best = 0, gap = Infinity;
    hours.forEach((time, i) => {
        const g = Math.abs(Date.parse(time) - when.getTime());
        if (g < gap) {
            best = i;
            gap = g;
        }
    });
    return best;
}

// How old (hours) `field` was at `when`.
export function forecastAge(field, when = new Date()) {
    return (when.getTime() - Date.parse(field.fetched_at)) / 3600000;
}

// Whether `field` runs out before `when`: the last hour it has is before it.
export function forecastExpired(field, when = new Date()) {
    return Date.parse(field.hours[field.hours.length - 1]) < when.getTime();
}

// One point's winds in one hour, as east and north (m/s) at each altitude of the levels.
function resample(winds, u, v, offset) {
    const sorted = [...winds].sort((a, b) => a[0] - b[0]);
    const east = sorted.map(([, speed, from]) => -speed * Math.sin(from * Math.PI / 180));
    const north = sorted.map(([, speed, from]) => -speed * Math.cos(from * Math.PI / 180));
    let k = 0;
    for (let l = 0; l < LEVELS; l++) {
        const altitude = LOWEST_LEVEL + l * LEVEL_STEP;
        while (k < sorted.length - 2 && sorted[k + 1][0] < altitude) k++;
        let e, n;
        if (sorted.length === 1 || altitude <= sorted[0][0]) {
            e = east[0];
            n = north[0];
        } else if (altitude >= sorted[sorted.length - 1][0]) {
            e = east[sorted.length - 1];
            n = north[sorted.length - 1];
        } else {
            const f = (altitude - sorted[k][0]) / (sorted[k + 1][0] - sorted[k][0]);
            e = east[k] + f * (east[k + 1] - east[k]);
            n = north[k] + f * (north[k + 1] - north[k]);
        }
        u[offset + l] = e;
        v[offset + l] = n;
    }
}

// A field, prepared for reading winds from it quickly.
export function prepareField(field) {
    const nPoints = field.points.length, nHours = field.hours.length;
    const u = new Float32Array(nPoints * nHours * LEVELS);
    const v = new Float32Array(nPoints * nHours * LEVELS);
    for (let p = 0; p < nPoints; p++) {
        for (let h = 0; h < nHours; h++) resample(field.winds[p][h], u, v, (p * nHours + h) * LEVELS);
    }
    // The points by where they are on the world's grid of the field's spacing.
    const spacing = field.spacing;
    const columns = Math.round(360 / spacing);
    const rows = Math.round(180 / spacing) + 1;
    const index = new Int32Array(columns * rows).fill(-1);
    field.points.forEach((point, p) => {
        const row = Math.round((point.lat + 90) / spacing);
        const column = ((Math.round((point.lon + 180) / spacing) % columns) + columns) % columns;
        index[row * columns + column] = p;
    });
    return {field, u, v, nHours, spacing, columns, rows, index, hoursMs: field.hours.map((t) => Date.parse(t))};
}

// The point of `prepared` at a grid row and column, or -1.
function pointAt(prepared, row, column) {
    if (row < 0 || row >= prepared.rows) return -1;
    const c = ((column % prepared.columns) + prepared.columns) % prepared.columns;
    return prepared.index[row * prepared.columns + c];
}

// The point of `prepared` nearest `lat`, `lon`.
export function nearestPoint(prepared, lat, lon) {
    let best = 0, gap = Infinity;
    prepared.field.points.forEach((point, p) => {
        const dLon = ((point.lon - lon + 540) % 360) - 180;
        const g = (point.lat - lat) ** 2 + (dLon * Math.cos(lat * Math.PI / 180)) ** 2;
        if (g < gap) {
            best = p;
            gap = g;
        }
    });
    return best;
}

// Whether `prepared` has points around `lat`, `lon` (all four of the grid cell it is in).
export function fieldCovers(prepared, lat, lon) {
    const row = Math.floor((lat + 90) / prepared.spacing);
    const column = Math.floor((lon + 180) / prepared.spacing);
    return [[0, 0], [1, 0], [0, 1], [1, 1]].every(([r, c]) => pointAt(prepared, row + r, column + c) >= 0);
}

// The winds of `prepared` as the model takes them for a burst at `lat0`, `lon0`, whose ground is
// `groundElevation` m above sea level, at `startMs` (a time): {at(x, y, z, t)}, the wind (east, north;
// m/s) x meters east and y north of ground zero, z meters above its ground, t seconds after the burst.
export function fieldWinds(prepared, {lat0, lon0, groundElevation = 0, startMs}) {
    const {u, v, nHours, spacing, hoursMs} = prepared;
    const perLon = METERS_PER_DEGREE * Math.cos(lat0 * Math.PI / 180);
    const hour0 = hoursMs[0];
    const corners = [[0, 0], [1, 0], [0, 1], [1, 1]];
    let lastCell = null, cellPoints = null;
    return {
        at(x, y, z, t) {
            const lat = lat0 + y / METERS_PER_DEGREE;
            const lon = lon0 + x / perLon;
            const fr = (lat + 90) / spacing, fc = (lon + 180) / spacing;
            const row = Math.floor(fr), column = Math.floor(fc);
            const dr = fr - row, dc = fc - column;
            // The points around a place are looked up once for every grid cell a particle is in.
            const cell = row * 100000 + column;
            if (cell !== lastCell) {
                lastCell = cell;
                cellPoints = corners.map(([r, c]) => pointAt(prepared, row + r, column + c));
                if (cellPoints.every((p) => p < 0)) cellPoints = [nearestPoint(prepared, lat, lon), -1, -1, -1];
            }
            const fh = Math.min(Math.max((startMs + t * 1000 - hour0) / 3600000, 0), nHours - 1);
            const h0 = Math.min(Math.floor(fh), nHours - 2 < 0 ? 0 : nHours - 2), dh = nHours > 1 ? fh - h0 : 0;
            const fl = Math.min(Math.max((groundElevation + z - LOWEST_LEVEL) / LEVEL_STEP, 0), LEVELS - 1.000001);
            const l0 = Math.floor(fl), dl = fl - l0;
            let east = 0, north = 0, weight = 0;
            for (let k = 0; k < 4; k++) {
                const p = cellPoints[k];
                if (p < 0) continue;
                const [r, c] = corners[k];
                // A lone nearest point (outside the field) has all of the weight.
                const w = cellPoints[1] < 0 && cellPoints[2] < 0 && cellPoints[3] < 0 && k === 0
                    ? 1 : (r ? dr : 1 - dr) * (c ? dc : 1 - dc);
                if (w <= 0) continue;
                const base0 = (p * nHours + h0) * LEVELS + l0;
                const base1 = base0 + (nHours > 1 ? LEVELS : 0);
                const e0 = u[base0] + dl * (u[base0 + 1] - u[base0]), e1 = u[base1] + dl * (u[base1 + 1] - u[base1]);
                const n0 = v[base0] + dl * (v[base0 + 1] - v[base0]), n1 = v[base1] + dl * (v[base1 + 1] - v[base1]);
                east += w * (e0 + dh * (e1 - e0));
                north += w * (n0 + dh * (n1 - n0));
                weight += w;
            }
            return weight > 0 ? [east / weight, north / weight] : [0, 0];
        },
    };
}

// How much rain (mm) the field has near `lat`, `lon` from hour `index` for `hours` hours: rain washes
// fallout down in places the model does not show.
export function rainNear(prepared, lat, lon, index, hours = 6) {
    const rain = prepared.field.rain?.[nearestPoint(prepared, lat, lon)] || [];
    return rain.slice(index, index + hours).reduce((a, mm) => a + (mm || 0), 0);
}
