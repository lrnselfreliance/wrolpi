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

// The hours a burst's fallout comes down in.
export const LANDING_HOURS = 48;

// When the forecast runs out for a burst at hour `index` of `field`: the time (ms) of its last hour, if
// that is before the burst's fallout is down (LANDING_HOURS after it), or null.  From then on the
// last hour's winds are held.
export function forecastRunsOut(field, index) {
    const last = Date.parse(field.hours[field.hours.length - 1]);
    return Date.parse(field.hours[index]) + LANDING_HOURS * 3600000 > last ? last : null;
}

// Whether `field` has the winds for fallout from bursts at `when`: an hour within one of then, and
// the winds until all the fallout is down (LANDING_HOURS after).  After that the fallout on the ground
// only weakens, which takes no winds.
export function forecastCoversFallout(field, when = new Date()) {
    if (!field?.hours?.length) return false;
    const index = nearestHour(field.hours, when);
    if (Math.abs(Date.parse(field.hours[index]) - when.getTime()) > 3600000) return false;
    return forecastRunsOut(field, index) === null;
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
    // Each point's rain (mm in each hour) and the cloud it falls from ([bottom, top], m above sea
    // level; NaN where there is none, or the field does not say).
    const rain = new Float32Array(nPoints * nHours);
    const cloudBottom = new Float32Array(nPoints * nHours).fill(NaN);
    const cloudTop = new Float32Array(nPoints * nHours).fill(NaN);
    let rains = false;
    for (let p = 0; p < nPoints; p++) {
        for (let h = 0; h < nHours; h++) {
            const mm = field.rain?.[p]?.[h] || 0;
            rain[p * nHours + h] = mm;
            if (mm > 0) rains = true;
            const cloud = field.clouds?.[p]?.[h];
            if (cloud) {
                cloudBottom[p * nHours + h] = cloud[0];
                cloudTop[p * nHours + h] = cloud[1];
            }
        }
    }
    // The points by where they are on the world's grid of the field's spacing: rows and columns
    // count whole spacings from the equator and the prime meridian (the points are on multiples of
    // the spacing, which divides 360 but need not divide 90 or 180), rows from the south pole's.
    const spacing = field.spacing;
    const columns = Math.round(360 / spacing);
    const rowOffset = Math.ceil(90 / spacing);
    const rows = 2 * rowOffset + 1;
    const index = new Int32Array(columns * rows).fill(-1);
    field.points.forEach((point, p) => {
        const row = Math.round(point.lat / spacing) + rowOffset;
        const column = ((Math.round(point.lon / spacing) % columns) + columns) % columns;
        index[row * columns + column] = p;
    });
    return {field, u, v, rain, cloudBottom, cloudTop, rains, nHours, spacing, columns, rows, rowOffset, index,
        hoursMs: field.hours.map((t) => Date.parse(t))};
}

// The point of `prepared` at a grid row and column, or -1.
function pointAt(prepared, row, column) {
    if (row < 0 || row >= prepared.rows) return -1;
    const c = ((column % prepared.columns) + prepared.columns) % prepared.columns;
    return prepared.index[row * prepared.columns + c];
}

// The degrees of longitude from `lon` east to `to`, -180 to 180, however far round the world either
// is (a particle may be carried round it).
function lonGap(to, lon) {
    let gap = (to - lon + 540) % 360;
    if (gap < 0) gap += 360;
    return gap - 180;
}

// The point of `prepared` nearest `lat`, `lon`.
export function nearestPoint(prepared, lat, lon) {
    let best = 0, gap = Infinity;
    prepared.field.points.forEach((point, p) => {
        const dLon = lonGap(point.lon, lon);
        const g = (point.lat - lat) ** 2 + (dLon * Math.cos(lat * Math.PI / 180)) ** 2;
        if (g < gap) {
            best = p;
            gap = g;
        }
    });
    return best;
}

// The point of `prepared` nearest `lat`, `lon`, in its grid cell `row`, `column`: as nearestPoint
// finds it, but looking only through the points which can be nearest somewhere in the cell (kept for
// each cell).  Particles carried past the field enter many cells, and looking through all the points
// for each was most of the time a burst took.
export function nearestAround(prepared, row, column, lat, lon) {
    if (!prepared.nearCandidates) prepared.nearCandidates = new Map();
    const key = row * 100000 + column;
    let near = prepared.nearCandidates.get(key);
    if (!near) {
        near = candidatesOf(prepared, row, column);
        prepared.nearCandidates.set(key, near);
    }
    const points = prepared.field.points;
    let best = near[0], gap = Infinity;
    // As nearestPoint reckons it, in the same order: the same point, even where two are as near.
    for (const p of near) {
        const point = points[p];
        const dLon = lonGap(point.lon, lon);
        const g = (point.lat - lat) ** 2 + (dLon * Math.cos(lat * Math.PI / 180)) ** 2;
        if (g < gap) {
            best = p;
            gap = g;
        }
    }
    return best;
}

// The points of `prepared` (in order) which can be the nearest somewhere in grid cell `row`,
// `column`: those which, at their nearest to the cell, are as near as the point nearest at its
// farthest.
function candidatesOf(prepared, row, column) {
    const {spacing, rowOffset} = prepared;
    const south = (row - rowOffset) * spacing, north = south + spacing;
    const middle = (column + 0.5) * spacing, halfWidth = spacing / 2;
    // How much a degree of longitude counts in the cell, at least and at most (by |cos(lat)|).
    const scale = (degrees) => Math.abs(Math.cos(degrees * Math.PI / 180));
    const crosses = (period, offset) => Math.floor((south - offset) / period) !== Math.floor((north - offset) / period);
    const least = crosses(180, 90) ? 0 : Math.min(scale(south), scale(north));
    const most = crosses(180, 0) ? 1 : Math.max(scale(south), scale(north));
    const points = prepared.field.points;
    const nearest = new Float64Array(points.length), farthest = new Float64Array(points.length);
    let bound = Infinity;
    points.forEach((point, p) => {
        const dLat0 = Math.max(0, south - point.lat, point.lat - north);
        const dLat1 = Math.max(Math.abs(point.lat - south), Math.abs(point.lat - north));
        const d = Math.abs(lonGap(point.lon, middle));
        const dLon0 = Math.max(0, d - halfWidth), dLon1 = Math.min(180, d + halfWidth);
        nearest[p] = dLat0 ** 2 + (dLon0 * least) ** 2;
        farthest[p] = dLat1 ** 2 + (dLon1 * most) ** 2;
        bound = Math.min(bound, farthest[p]);
    });
    // A little past the bound: rounding is not to leave out a point which is as near.
    const limit = bound * (1 + 1e-9) + 1e-12;
    const near = [];
    for (let p = 0; p < points.length; p++) if (nearest[p] <= limit) near.push(p);
    return Int32Array.from(near);
}

// Whether `prepared` has points around `lat`, `lon` (all four of the grid cell it is in).
export function fieldCovers(prepared, lat, lon) {
    const row = Math.floor(lat / prepared.spacing) + prepared.rowOffset;
    const column = Math.floor(lon / prepared.spacing);
    return [[0, 0], [1, 0], [0, 1], [1, 1]].every(([r, c]) => pointAt(prepared, row + r, column + c) >= 0);
}

// The winds of `prepared` as the model takes them for a burst at `lat0`, `lon0`, whose ground is
// `groundElevation` m above sea level, at `startMs` (a time): {at(x, y, z, t)}, the wind (east, north;
// m/s) x meters east and y north of ground zero, z meters above its ground, t seconds after the burst.
export function fieldWinds(prepared, {lat0, lon0, groundElevation = 0, startMs}) {
    const {u, v, nHours, spacing, rowOffset, hoursMs} = prepared;
    const perLon = METERS_PER_DEGREE * Math.cos(lat0 * Math.PI / 180);
    const hour0 = hoursMs[0];
    const corners = [[0, 0], [1, 0], [0, 1], [1, 1]];
    let lastCell = null, cellPoints = null;
    // One hour (a past day's): the winds hold through the hours, and are read without them.
    if (nHours === 1) return {held: true, at: heldAt(prepared, lat0, lon0, perLon, groundElevation)};
    return {
        at(x, y, z, t) {
            const lat = lat0 + y / METERS_PER_DEGREE;
            const lon = lon0 + x / perLon;
            const fr = lat / spacing + rowOffset, fc = lon / spacing;
            const row = Math.floor(fr), column = Math.floor(fc);
            const dr = fr - row, dc = fc - column;
            // The points around a place are looked up once for every grid cell a particle is in.
            const cell = row * 100000 + column;
            if (cell !== lastCell) {
                lastCell = cell;
                cellPoints = corners.map(([r, c]) => pointAt(prepared, row + r, column + c));
                if (cellPoints.every((p) => p < 0)) cellPoints = [nearestAround(prepared, row, column, lat, lon), -1, -1, -1];
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
        // The rain (mm an hour) x meters east and y north of ground zero, t seconds after the burst,
        // between the points around and the hours around, and the cloud it falls from at the
        // nearest of them ([bottom, top], m above sea level, or null).  Absent where the field has
        // no rain at all.
        ...(prepared.rains ? {rainAt: (x, y, t) => rainAt(prepared, lat0 + y / METERS_PER_DEGREE, lon0 + x / perLon,
            Math.min(Math.max((startMs + t * 1000 - hour0) / 3600000, 0), nHours - 1))} : {}),
    };
}

// The point of `prepared` nearest the middle of a grid cell outside it, kept: particles carried far
// past the field enter many such cells.
function nearestOfCell(prepared, row, column) {
    if (!prepared.nearestOfCell) prepared.nearestOfCell = new Map();
    const cell = row * 100000 + column;
    let p = prepared.nearestOfCell.get(cell);
    if (p === undefined) {
        p = nearestPoint(prepared, (row - prepared.rowOffset + 0.5) * prepared.spacing, (column + 0.5) * prepared.spacing);
        prepared.nearestOfCell.set(cell, p);
    }
    return p;
}

// fieldWinds' at(x, y, z) of a field of one hour.
function heldAt(prepared, lat0, lon0, perLon, groundElevation) {
    const {u, v, spacing, rowOffset} = prepared;
    let lastCell = null, p00 = -1, p10 = -1, p01 = -1, p11 = -1, lone = false;
    return (x, y, z) => {
        const lat = lat0 + y / METERS_PER_DEGREE;
        const lon = lon0 + x / perLon;
        const fr = lat / spacing + rowOffset, fc = lon / spacing;
        const row = Math.floor(fr), column = Math.floor(fc);
        const dr = fr - row, dc = fc - column;
        const cell = row * 100000 + column;
        if (cell !== lastCell) {
            lastCell = cell;
            p00 = pointAt(prepared, row, column);
            p10 = pointAt(prepared, row + 1, column);
            p01 = pointAt(prepared, row, column + 1);
            p11 = pointAt(prepared, row + 1, column + 1);
            lone = p00 < 0 && p10 < 0 && p01 < 0 && p11 < 0;
            if (lone) p00 = nearestOfCell(prepared, row, column);
        }
        const fl = Math.min(Math.max((groundElevation + z - LOWEST_LEVEL) / LEVEL_STEP, 0), LEVELS - 1.000001);
        const l0 = Math.floor(fl), dl = fl - l0;
        let east = 0, north = 0, weight = 0;
        const add = (p, w) => {
            if (p < 0 || w <= 0) return;
            const b = p * LEVELS + l0;
            east += w * (u[b] + dl * (u[b + 1] - u[b]));
            north += w * (v[b] + dl * (v[b + 1] - v[b]));
            weight += w;
        };
        if (lone) add(p00, 1);
        else {
            add(p00, (1 - dr) * (1 - dc));
            add(p10, dr * (1 - dc));
            add(p01, (1 - dr) * dc);
            add(p11, dr * dc);
        }
        return weight > 0 ? [east / weight, north / weight] : [0, 0];
    };
}

// The rain of `prepared` at `lat`, `lon`, `fh` hours into it: [mm an hour, cloud or null].
function rainAt(prepared, lat, lon, fh) {
    const {rain, cloudBottom, cloudTop, nHours, spacing, rowOffset} = prepared;
    const fr = lat / spacing + rowOffset, fc = lon / spacing;
    const row = Math.floor(fr), column = Math.floor(fc), dr = fr - row, dc = fc - column;
    const h0 = Math.min(Math.floor(fh), Math.max(nHours - 2, 0)), dh = nHours > 1 ? fh - h0 : 0;
    const h1 = nHours > 1 ? h0 + 1 : h0;
    let mm = 0, weight = 0, best = -1, bestWeight = -1;
    for (const [r, c] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
        const p = pointAt(prepared, row + r, column + c);
        if (p < 0) continue;
        const w = (r ? dr : 1 - dr) * (c ? dc : 1 - dc);
        mm += w * (rain[p * nHours + h0] * (1 - dh) + rain[p * nHours + h1] * dh);
        weight += w;
        if (w > bestWeight) {
            best = p;
            bestWeight = w;
        }
    }
    if (best < 0) {
        best = nearestAround(prepared, row, column, lat, lon);
        mm = rain[best * nHours + h0] * (1 - dh) + rain[best * nHours + h1] * dh;
        weight = 1;
    }
    const k = best * nHours + (dh < 0.5 ? h0 : h1);
    const cloud = Number.isFinite(cloudBottom[k]) ? [cloudBottom[k], cloudTop[k]] : null;
    return [weight > 0 ? mm / weight : 0, cloud];
}

// How much rain (mm) the field has near `lat`, `lon` from hour `index` for `hours` hours: rain washes
// fallout down in places the model does not show.
export function rainNear(prepared, lat, lon, index, hours = 6) {
    const rain = prepared.field.rain?.[nearestPoint(prepared, lat, lon)] || [];
    return rain.slice(index, index + hours).reduce((a, mm) => a + (mm || 0), 0);
}
