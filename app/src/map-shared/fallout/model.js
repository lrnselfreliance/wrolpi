// Where the local fallout of a burst at the ground lands, and how radioactive the ground is there.
// Shared by the app's map viewer and the standalone viewer: no imports from the app, no
// dependencies.
//
// All of the activity starts in the early fireball, on particles of every size, and rises with the
// cloud [SIMFIC].  The cloud's base and top rise with the square root of time to their stabilized
// heights; inside it the air rises as fast as the cloud, and below it ever slower toward the
// ground.  Each particle rises with the air less its own settling speed, so a heavy particle drops
// out of the cloud low and early, near ground zero (the stem's close-in fallout), and a light one
// rides to the top of the cloud and falls far downwind.  Every particle is carried by the wind at
// the height it is at, while it rises and while it falls, and lands where it first meets the
// ground.  Each (size, starting height) lands as a Gaussian spot, as wide as the cloud was where it
// left it, and widened by the turbulence of the air on the way down.
//
// Sources (each where it is used):
//   [SIMFIC]  H. G. Norment, SIMFIC: A Simple, Efficient Fallout Prediction Model, DNA 5193F
//             (1979), DTIC ADA089187: the rising cloud, the particles' paths in it, how wide each is
//             when it leaves it, its widening by turbulence, and the share of the activity which
//             comes down for a burst above the ground.  SIMFIC matched DELFIC, the Department of
//             Defense's fallout code, on five test shots from 0.5 to 3380 kt.
//   [DNAF-1]  H. G. Norment, DNAF-1: An Analytical Fallout Prediction Model and Code, DNA 6299F
//             (1981), DTIC ADA130291: the stabilized cloud's heights (Wilsey and Crisco's fits to
//             observed clouds, which SIMFIC uses too), DELFIC's standard particle size distribution,
//             and the exposure rate of a kiloton of fission products spread over unit area.

import {settlingSpeedAt} from './atmosphere.js';

const FEET = 0.3048;
const MPH = 0.44704;
const SQ_KM_PER_SQ_MI = 2.589988;

// The exposure rate at H+1 hour, a meter above an ideal flat plane, of the fission products of one
// kiloton spread over one square kilometer: (R/hr) km^2 / kt [DNAF-1, (31)]: 6.9733e9 R m^2/(hr kt).
// (Glasstone and Dolan, 9.14, give 2900 rad/hr for a kiloton over a square mile: 7511 per km^2.)
// It is for all of the activity; the model decides how much of it lands locally.
export const SOURCE_NORMALIZATION = 6973.3;

// DELFIC's standard distribution of the number of particles over diameter [DNAF-1]: lognormal.
const NUMBER_MEDIAN_DIAMETER = 0.407e-6;
const GEOMETRIC_SD = 4.0;
// Activity is carried both through the volume of a particle (condensed into it while molten) and
// on its surface (condensed onto it later).  This share by volume makes the activity-weighted mean
// diameter 229 um, the "nominal particle" which DNAF-1 computed from DELFIC [DNAF-1, section 2.4].
export const VOLUME_ACTIVITY_SHARE = 0.6;

// Particles are tracked from 1 um to 4 mm.  Activity on smaller ones stays aloft for weeks (it is
// not local fallout); what is on larger ones is put on the largest.
const SMALLEST_DIAMETER = 1e-6;
const LARGEST_DIAMETER = 4e-3;
const SIZE_BINS = 48;
// How many heights in the early fireball each particle size starts from.
const SUBDIVISIONS = 10;
// How finely a fall is integrated, in meters of height.
const FALL_STEP = 50;
// When the cloud stops rising (s) [SIMFIC, Table 1, from DELFIC], for yields of 10^-3 to 10^5 kt.
const STOP_TIMES = [300, 300, 300, 300, 300, 280, 200, 160, 150];

// A wind table, as rows of [altitude (ft above sea level), direction the wind blows FROM (degrees),
// speed (mph)], as a profile of [height above ground (m), east (m/s), north (m/s)].
export function profileFromTable(rows, siteElevationFt) {
    return rows
        .map(([altitude, from, speed]) => {
            const toward = (from + 180) * Math.PI / 180;
            const s = speed * MPH;
            return [(altitude - siteElevationFt) * FEET, s * Math.sin(toward), s * Math.cos(toward)];
        })
        .sort((a, b) => a[0] - b[0]);
}

// The wind (east, north; m/s) at `height` meters above the ground: linear between the heights of
// the profile, and as the nearest one beyond them.
export function windAt(profile, height) {
    if (height <= profile[0][0]) return [profile[0][1], profile[0][2]];
    const last = profile[profile.length - 1];
    if (height >= last[0]) return [last[1], last[2]];
    let i = 1;
    while (profile[i][0] < height) i++;
    const [z0, u0, v0] = profile[i - 1];
    const [z1, u1, v1] = profile[i];
    const f = (height - z0) / (z1 - z0);
    return [u0 + f * (u1 - u0), v0 + f * (v1 - v0)];
}

// One wind, as a uniform-wind model takes it: the mean of the profile over the height of the cloud.
export function uniformProfile(profile, top) {
    let u = 0, v = 0;
    const steps = 200;
    for (let i = 0; i < steps; i++) {
        const [du, dv] = windAt(profile, (i + 0.5) / steps * top);
        u += du / steps;
        v += dv / steps;
    }
    return [[0, u, v]];
}

// The stabilized cloud of a `yieldKt` burst: cap base and top heights above the burst [DNAF-1, (3)
// and (4)] and its radius [SIMFIC, (2.6.7)], in meters.
export function stabilizedCloud(yieldKt) {
    const w = yieldKt;
    const base = w <= 4.07 ? 2228 * Math.pow(w, 0.3463) : 2661 * Math.pow(w, 0.2198);
    let top;
    if (w < 2.29) top = 3597 * Math.pow(w, 0.2553);
    else if (w < 19) top = 3170 * Math.pow(w, 0.4077);
    else top = 6474 * Math.pow(w, 0.1650);
    const ln = Math.log(w);
    const radius = Math.exp(6.7553 + 0.32055 * ln + 0.01137478 * ln * ln);
    return {base, top, radius};
}

// The rising cloud of a `yieldKt` burst `burstHeight` meters above the ground [SIMFIC, 2.6]: it
// starts (s after the burst) as the fireball, `initialRadius` wide, between `initialBase` and
// `initialTop` (m above the ground), and rises until `stop` to between `base` and `top`, `radius`
// wide.  `stabilized` ({base, top}, m above the burst) is the cloud as observed, if it was.
export function risingCloud(yieldKt, burstHeight = 0, stabilized = null) {
    const w = yieldKt;
    const fit = {...stabilizedCloud(w), ...(stabilized || {})};
    const y = Math.min(Math.max(Math.log10(w), -3), 5) + 3;
    const k = Math.min(Math.floor(y), STOP_TIMES.length - 2);
    const initialRadius = 108 * Math.pow(w, 0.33);
    const initialBase = burstHeight + 90 * Math.cbrt(w);
    return {
        start: 2.07 * Math.pow(w, 0.13),
        stop: STOP_TIMES[k] + (y - k) * (STOP_TIMES[k + 1] - STOP_TIMES[k]),
        initialRadius,
        initialBase,
        initialTop: initialBase + 1.32288 * initialRadius,
        base: burstHeight + fit.base,
        top: burstHeight + Math.max(fit.top, fit.base + 1),
        radius: fit.radius,
    };
}

// The share of the activity which comes down as local fallout from a burst `burstHeight` meters
// above the ground [SIMFIC, (2.8.2), from DASA 1251 Volume 5]: all of it from a burst on the
// ground, ever less as the fireball touches the ground less.
export function activityDown(yieldKt, burstHeight) {
    const scaled = burstHeight / FEET / Math.cbrt(yieldKt);
    return scaled > 0 ? Math.pow(0.45345, scaled / 65) : 1;
}

// The error function (Abramowitz and Stegun 7.1.26; error under 1.5e-7).
function erf(x) {
    const sign = x < 0 ? -1 : 1;
    const t = 1 / (1 + 0.3275911 * Math.abs(x));
    const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t
        + 0.254829592) * t * Math.exp(-x * x);
    return sign * y;
}

// The share of a lognormal distribution (median, geometric standard deviation) below `x`.
function lognormalBelow(x, median, gsd) {
    return 0.5 * (1 + erf(Math.log(x / median) / (Math.log(gsd) * Math.SQRT2)));
}

// The particle sizes: [{diameter (m), activity}], where activity is the share of all of the
// activity of the burst on particles of that size.  The shares add up to less than one: the rest is
// on particles too small to track.
export function particleSizes(volumeShare = VOLUME_ACTIVITY_SHARE) {
    const s2 = Math.log(GEOMETRIC_SD) ** 2;
    // Weighting the number distribution by d^3 (volume) or d^2 (surface) moves its median.
    const volumeMedian = NUMBER_MEDIAN_DIAMETER * Math.exp(3 * s2);
    const surfaceMedian = NUMBER_MEDIAN_DIAMETER * Math.exp(2 * s2);
    const below = (d) => volumeShare * lognormalBelow(d, volumeMedian, GEOMETRIC_SD)
        + (1 - volumeShare) * lognormalBelow(d, surfaceMedian, GEOMETRIC_SD);
    const sizes = [];
    const step = Math.log(LARGEST_DIAMETER / SMALLEST_DIAMETER) / SIZE_BINS;
    for (let i = 0; i < SIZE_BINS; i++) {
        const low = SMALLEST_DIAMETER * Math.exp(i * step);
        const high = low * Math.exp(step);
        const upper = i === SIZE_BINS - 1 ? 1 : below(high);
        sizes.push({diameter: Math.sqrt(low * high), activity: upper - below(low)});
    }
    return sizes;
}

// The fall of a particle of `diameter` from `top` down to `bottom` meters (zero or below: ground
// lower than ground zero): at each level (every FALL_STEP meters, from `bottom` up), how far it goes
// east and north, and for how many seconds, from there down to `bottom`.
function fall(diameter, top, bottom, profile, siteElevation) {
    const steps = Math.ceil((top - bottom) / FALL_STEP);
    const east = new Float64Array(steps + 1);
    const north = new Float64Array(steps + 1);
    const seconds = new Float64Array(steps + 1);
    for (let i = 1; i <= steps; i++) {
        const middle = bottom + (i - 0.5) * FALL_STEP;
        const dt = FALL_STEP / settlingSpeedAt(diameter, siteElevation + middle);
        const [u, v] = windAt(profile, middle);
        east[i] = east[i - 1] + u * dt;
        north[i] = north[i - 1] + v * dt;
        seconds[i] = seconds[i - 1] + dt;
    }
    return {east, north, seconds};
}

// The settling speed (m/s) on `path` at `height`.
function speedOn(path, height, bottom) {
    const i = Math.min(Math.max(Math.floor((height - bottom) / FALL_STEP) + 1, 1), path.seconds.length - 1);
    return FALL_STEP / (path.seconds[i] - path.seconds[i - 1]);
}

// Where a particle falling from `height`, `x0` m east and `y0` m north of ground zero, lands: the
// first level on the way down at which it is at or below the ground under it.  [east, north,
// seconds] of where it lands and how long it took.
function landing(path, height, x0, y0, bottom, ground) {
    const {east, north, seconds} = path;
    const start = Math.min(Math.max(Math.round((height - bottom) / FALL_STEP), 0), seconds.length - 1);
    for (let m = start - 1; m > 0; m--) {
        const x = x0 + east[start] - east[m];
        const y = y0 + north[start] - north[m];
        if (bottom + m * FALL_STEP <= ground(x, y)) return [x, y, seconds[start] - seconds[m]];
    }
    return [x0 + east[start] - east[0], y0 + north[start] - north[0], seconds[start] - seconds[0]];
}

// The cloud's base and top (m) and how fast they rise (m/s) `t` seconds after the burst
// [SIMFIC, (2.2.1), (2.2.2)].
function cloudAt(cloud, t) {
    const span = Math.sqrt(cloud.stop) - Math.sqrt(cloud.start);
    if (t >= cloud.stop) return {base: cloud.base, top: cloud.top, baseSpeed: 0, topSpeed: 0};
    const s = (Math.sqrt(t) - Math.sqrt(cloud.start)) / span;
    return {
        base: cloud.initialBase + s * (cloud.base - cloud.initialBase),
        top: cloud.initialTop + s * (cloud.top - cloud.initialTop),
        baseSpeed: (cloud.base - cloud.initialBase) / (2 * Math.sqrt(t) * span),
        topSpeed: (cloud.top - cloud.initialTop) / (2 * Math.sqrt(t) * span),
    };
}

// How fast the air rises (m/s) at `height` `t` seconds after the burst: inside the cloud, linear
// between its base and top; below it, slowing linearly to nothing at the ground [SIMFIC, (2.2.3),
// (2.2.4)]; nothing once the cloud stops.
function updraft(cloud, height, t) {
    const c = cloudAt(cloud, t);
    if (c.baseSpeed === 0) return 0;
    if (height >= c.base) {
        const f = Math.min((height - c.base) / Math.max(c.top - c.base, 1), 1);
        return c.baseSpeed + f * (c.topSpeed - c.baseSpeed);
    }
    return c.baseSpeed * Math.max(height, 0) / c.base;
}

// The rise of a particle from `height` in the fireball, until the cloud stops: {height, x, y (m),
// highest (m), highest at (s), landed (whether it met the ground first), seconds}.  `ground` is
// ignored when it is null.
function rise(cloud, path, height, profile, bottom, ground) {
    let z = height, x = 0, y = 0, t = cloud.start, highest = z, highestAt = t;
    while (t < cloud.stop) {
        const dt = Math.min(Math.max(0.02 * t, 0.2), 5, cloud.stop - t);
        const w1 = updraft(cloud, z, t) - speedOn(path, z, bottom);
        const zMid = z + w1 * dt / 2;
        const w2 = updraft(cloud, zMid, t + dt / 2) - speedOn(path, zMid, bottom);
        const [u, v] = windAt(profile, zMid);
        z += w2 * dt;
        x += u * dt;
        y += v * dt;
        t += dt;
        if (z > highest) {
            highest = z;
            highestAt = t;
        }
        if (ground && z <= ground(x, y)) return {height: z, x, y, highest, highestAt, landed: true, seconds: t};
        if (!ground && z < bottom) break;
    }
    return {height: z, x, y, highest, highestAt, landed: false, seconds: t};
}

// How wide (sigma, m) a spot is when it lands: as wide as the cloud was where it left it,
// `sigma0`, widened by the turbulence of the air while it fell from `highest` m at `speed` m/s
// on average [SIMFIC, (2.7.3), (2.7.4), after Walton and Wilkins].
export function landedSigma(sigma0, highest, speed) {
    const a = Math.pow(sigma0, 2 / 3);
    const z = Math.pow(Math.max(highest, 1), 2 / 3);
    if (z < 3.83155 * speed * (1e3 - a)) return Math.sqrt((a + 0.26099 * z / speed) ** 3);
    return Math.sqrt(7.8297e5 * z / speed + 3e6 * a - 2e9);
}

// The spots where the activity lands: [{x, y (m east and north of ground zero), sigma (m),
// activity (share of the burst's activity), hours (after the burst), diameter (m, of its
// particles), highest (m, the highest they rose)}].
//
// `yieldKt` and `burstHeight` (m above the ground) are of the burst; `profile` is as
// profileFromTable gives it; `maxHours` is when the ground is looked at: what lands later is not
// counted.  `stabilized` is the cloud as observed ({base, top}, m above the burst), if it was.
//
// `terrain`, if given, is {ground(x, y), lowest}: the height (m) of the ground x meters east and y
// north of ground zero, above the ground at ground zero, and the lowest it gets.  A particle lands
// where it first meets the ground: early on a ridge in its way, late in a valley.  Without it the
// ground is flat.
export function landingSpots({yieldKt, burstHeight = 0, profile, siteElevation = 0, maxHours = 48,
                                 volumeShare = VOLUME_ACTIVITY_SHARE, terrain = null, stabilized = null}) {
    const cloud = risingCloud(yieldKt, Math.max(burstHeight, 0), stabilized);
    const down = activityDown(yieldKt, burstHeight);
    // Paths go down to 2 km below ground zero: the first parcel of a size to leave the cloud is
    // followed below the ground until the cloud stops [SIMFIC, 2.6], and valleys may be that deep.
    const bottom = Math.min(-2000, terrain ? Math.floor(terrain.lowest / FALL_STEP) * FALL_STEP : 0);
    const ground = terrain ? terrain.ground : () => 0;
    const top = Math.max(cloud.top, cloud.initialTop) + 500;
    const spots = [];
    for (const {diameter, activity} of particleSizes(volumeShare)) {
        if (activity <= 0) continue;
        const path = fall(diameter, top, bottom, profile, siteElevation);
        // The first of this size to leave the cloud does so from the base of the fireball, as wide as
        // it; those which leave later, higher, are wider, up to the stabilized cloud [SIMFIC, (2.6.8)].
        const first = rise(cloud, path, cloud.initialBase, profile, bottom, null);
        for (let j = 0; j < SUBDIVISIONS; j++) {
            const start = cloud.initialBase + (j + 0.5) / SUBDIVISIONS * (cloud.initialTop - cloud.initialBase);
            const r = rise(cloud, path, start, profile, bottom, ground);
            let x = r.x, y = r.y, seconds = r.seconds;
            if (!r.landed) {
                const [dx, dy, fallSeconds] = landing(path, r.height, r.x, r.y, bottom, ground);
                x = dx;
                y = dy;
                seconds += fallSeconds;
            }
            if (seconds > maxHours * 3600) continue;
            let radius;
            if (!r.landed && r.height >= cloud.base) radius = cloud.radius;
            else {
                const f = (r.height - first.height) / Math.max(cloud.base - first.height, 1);
                radius = cloud.initialRadius + Math.min(Math.max(f, 0), 1) * (cloud.radius - cloud.initialRadius);
            }
            const falling = Math.max(seconds - r.highestAt, 1);
            const sigma = landedSigma(radius / 2, r.highest, Math.max(r.highest, 1) / falling);
            spots.push({
                x, y, sigma, diameter, highest: r.highest,
                activity: activity * down / SUBDIVISIONS,
                hours: seconds / 3600,
            });
        }
    }
    return spots;
}

// The share of a spot (center `mean`, `sigma`) which lands in each cell of a row of cells
// (`start`, `cell` wide); [first cell, shares].
function cellShares(mean, sigma, start, cell, count) {
    const first = Math.max(0, Math.floor((mean - 4 * sigma - start) / cell));
    const last = Math.min(count - 1, Math.floor((mean + 4 * sigma - start) / cell));
    const shares = [];
    let previous = erf((start + first * cell - mean) / (sigma * Math.SQRT2));
    for (let i = first; i <= last; i++) {
        const next = erf((start + (i + 1) * cell - mean) / (sigma * Math.SQRT2));
        shares.push((next - previous) / 2);
        previous = next;
    }
    return [first, shares];
}

// The dose rate at H+1 hour (R/hr, three feet above the ground) on a grid of square cells around
// the spots: {x0, y0 (m, the south-west corner), cell (m), nx, ny, values (row by row, from the
// south)}.  `bounds` and `cellSize` give a closer look at part of it.
export function depositionGrid(spots, {yieldKt, fissionFraction = 1, normalization = SOURCE_NORMALIZATION,
    maxCells = 1200, bounds = null, cellSize = null}) {
    let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity, narrowest = Infinity;
    for (const s of spots) {
        west = Math.min(west, s.x - 3 * s.sigma);
        east = Math.max(east, s.x + 3 * s.sigma);
        south = Math.min(south, s.y - 3 * s.sigma);
        north = Math.max(north, s.y + 3 * s.sigma);
        narrowest = Math.min(narrowest, s.sigma);
    }
    // A grid over `bounds` ([west, south, east, north], m from ground zero) with cells `cellSize`
    // wide, when given: a close look at part of the fallout.
    if (bounds) [west, south, east, north] = bounds;
    const span = Math.max(east - west, north - south);
    const cell = cellSize || Math.max(span / maxCells, Math.min(narrowest / 2, 250), 25);
    const nx = Math.ceil((east - west) / cell);
    const ny = Math.ceil((north - south) / cell);
    const values = new Float64Array(nx * ny);
    const cellKm2 = (cell / 1000) ** 2;
    const perShare = normalization * yieldKt * fissionFraction / cellKm2;
    for (const s of spots) {
        const [ix, xs] = cellShares(s.x, s.sigma, west, cell, nx);
        const [iy, ys] = cellShares(s.y, s.sigma, south, cell, ny);
        const amount = s.activity * perShare;
        for (let j = 0; j < ys.length; j++) {
            const row = (iy + j) * nx + ix;
            const a = amount * ys[j];
            for (let i = 0; i < xs.length; i++) values[row + i] += a * xs[i];
        }
    }
    return {x0: west, y0: south, cell, nx, ny, values};
}

// The area (square miles) where the dose rate is at least each of `doseRates`.
export function contourAreas(grid, doseRates, scale = 1) {
    const cellSqMi = (grid.cell / 1000) ** 2 / SQ_KM_PER_SQ_MI;
    return doseRates.map((rate) => {
        let n = 0;
        for (const v of grid.values) if (v * scale >= rate) n++;
        return n * cellSqMi;
    });
}

// The grounded unit time reference dose rate, (R/hr) km^2 / kt, as [HPAC] measures it from
// contours: each place counts as the highest of `doseRates` it is above, times its area.
export function groundedUtrdr(grid, doseRates, yieldKt, scale = 1) {
    const rates = [...doseRates].sort((a, b) => b - a);
    const cellKm2 = (grid.cell / 1000) ** 2;
    let sum = 0;
    for (const v of grid.values) {
        const r = v * scale;
        for (const rate of rates) {
            if (r >= rate) {
                sum += rate;
                break;
            }
        }
    }
    return sum * cellKm2 / yieldKt;
}

// The scale on the grid at which its grounded UTRDR is `target`.
export function scaleToUtrdr(grid, doseRates, yieldKt, target) {
    let low = 1e-6, high = 1e6;
    for (let i = 0; i < 60; i++) {
        const mid = Math.sqrt(low * high);
        if (groundedUtrdr(grid, doseRates, yieldKt, mid) < target) low = mid; else high = mid;
    }
    return Math.sqrt(low * high);
}

// How far (km) the furthest place where the dose rate is at least each of `doseRates` is from ground
// zero, and in which direction (degrees clockwise from north): the hotline length and azimuth.
export function hotlines(grid, doseRates, scale = 1) {
    return doseRates.map((rate) => {
        let far = -1, azimuth = null;
        for (let j = 0; j < grid.ny; j++) {
            for (let i = 0; i < grid.nx; i++) {
                if (grid.values[j * grid.nx + i] * scale < rate) continue;
                const x = grid.x0 + (i + 0.5) * grid.cell, y = grid.y0 + (j + 0.5) * grid.cell;
                const d = Math.hypot(x, y);
                if (d > far) {
                    far = d;
                    azimuth = (Math.atan2(x, y) * 180 / Math.PI + 360) % 360;
                }
            }
        }
        return far < 0 ? {km: 0, azimuth: null} : {km: far / 1000, azimuth};
    });
}

// The direction (degrees clockwise from north) from ground zero to the middle of the activity
// where the dose rate is at least `rate`.
export function plumeBearing(grid, rate, scale = 1) {
    let sx = 0, sy = 0;
    for (let j = 0; j < grid.ny; j++) {
        for (let i = 0; i < grid.nx; i++) {
            const v = grid.values[j * grid.nx + i] * scale;
            if (v < rate) continue;
            sx += v * (grid.x0 + (i + 0.5) * grid.cell);
            sy += v * (grid.y0 + (j + 0.5) * grid.cell);
        }
    }
    return (Math.atan2(sx, sy) * 180 / Math.PI + 360) % 360;
}
