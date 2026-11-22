// Where the local fallout of a surface burst lands, and how radioactive the ground is there.
// Shared by the app's map viewer and the standalone viewer: no imports from the app, no
// dependencies.
//
// The stabilized cloud is a cap, a skirt below it and a stem down to the ground, each holding its
// own share of the activity [Philippe]: the cap Gaussian in height, the skirt and stem even.  The
// cap is as wide as the stabilized cloud; the stem starts as narrow as the early fireball at the
// ground and widens up to the cap [DNAF-1].  The activity is
// carried on particles of every size; each size falls at its own speed through winds which change
// with height, so the large ones land near ground zero and the small ones far downwind, wherever
// the winds they fell through took them.  Each (size, starting height) lands as a Gaussian spot,
// which is as wide as the cloud was, and widens with the time the particle was in the air.
//
// Sources (each where it is used):
//   [DNAF-1]  DNAF-1: An Analytical Fallout Prediction Model and Code, DNA 6299F (1981), DTIC
//             ADA130291: cloud heights (Wilsey and Crisco's fits to observed clouds), cloud radius
//             (a fit to DELFIC), and DELFIC's standard particle size distribution.
//   [WSEG-10] Documentation and Analysis of the WSEG-10 Fallout Prediction Model, AFIT (1980), DTIC
//             ADA083515: the cloud's activity is Gaussian, and the cloud is 4 sigma tall and across.
//   [HPAC]    A Comparison of HPAC Dose-Rate Contour Plots to ... Local Fallout Data ..., AFIT
//             (2005), DTIC ADA438146: the theoretical source normalization constant.
//   [Philippe] Philippe et al., Reconstruction of fallout deposition from U.S. atmospheric nuclear
//             tests conducted in New Mexico and Nevada (arXiv 2307.11040): the shares of the
//             activity in the cap, skirt and stem, and their heights.  Glasstone and Dolan (1977,
//             9.61) give about 90% in the head of a land surface burst, the rest in the stem.

import {settlingSpeed} from './atmosphere.js';

const FEET = 0.3048;
const MPH = 0.44704;
const SQ_KM_PER_SQ_MI = 2.589988;

// The dose rate at H+1 hour, three feet above an ideal flat plane, of the fission products of one
// kiloton spread over one square kilometer: (R/hr) km^2 / kt.  The theoretical value [HPAC] is
// 2590 for the 75% of the activity which falls as local fallout; this is all of it, since the model
// itself decides how much falls locally (what is on particles too small to land in time does not).
export const SOURCE_NORMALIZATION = 2590 / 0.75;

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
const HEIGHT_BINS = 24;
const SKIRT_BINS = 8;
const STEM_BINS = 8;

// The shares of the activity in the cap, the skirt (from half the height of the cap's base up to it)
// and the stem (from the ground up to the skirt), for a surface or tower burst [Philippe].
export const CLOUD_PARTS = {cap: 0.775, skirt: 0.15, stem: 0.075};
// How finely a fall is integrated, in meters of height.
const FALL_STEP = 50;

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

// The stabilized cloud of a `yieldKt` burst: cap base and top heights above the ground [DNAF-1, (3)
// and (4)], its radius [DNAF-1, (5)], and the radius of the early cloud (the fireball, as it starts
// to rise) [DNAF-1, (2)], in meters.  (The early radius's exponent is read off a smudged scan as
// 0.33: the cube root by which fireball sizes scale.)
export function stabilizedCloud(yieldKt) {
    const w = yieldKt;
    const base = w <= 4.07 ? 2228 * Math.pow(w, 0.3463) : 2661 * Math.pow(w, 0.2198);
    let top;
    if (w < 2.29) top = 3597 * Math.pow(w, 0.2553);
    else if (w < 19) top = 3170 * Math.pow(w, 0.4077);
    else top = 6474 * Math.pow(w, 0.1650);
    const ln = Math.log(w);
    const radius = Math.exp(6.7553 + 0.32055 * ln + 0.01137478 * ln * ln);
    const earlyRadius = 108 * Math.pow(w, 0.33);
    return {base, top, radius, earlyRadius, yieldKt: w};
}

// How wide (sigma, m) the stem is at the ground [DNAF-1, (23)]: as the early cloud for a small
// burst, whose fallout starts before the cloud has gone far, and wider for a large one, whose
// earliest fallout has fallen a long way.
export function stemSigma(yieldKt, earlyRadius) {
    if (yieldKt <= 10) return earlyRadius;
    if (yieldKt >= 1000) return 2.5 * earlyRadius;
    return earlyRadius * (1 + 3 * Math.log10(yieldKt)) / 4;
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

// The fall of a particle of `diameter` from the top of the cloud down to `bottom` meters (zero or
// below: ground lower than ground zero): at each level (every FALL_STEP meters, from `bottom` up),
// how far it goes east and north, and for how many seconds, from there down to `bottom`.
function fall(diameter, top, bottom, profile, siteElevation) {
    const steps = Math.ceil((top - bottom) / FALL_STEP);
    const east = new Float64Array(steps + 1);
    const north = new Float64Array(steps + 1);
    const seconds = new Float64Array(steps + 1);
    for (let i = 1; i <= steps; i++) {
        const middle = bottom + (i - 0.5) * FALL_STEP;
        const dt = FALL_STEP / settlingSpeed(diameter, siteElevation + middle);
        const [u, v] = windAt(profile, middle);
        east[i] = east[i - 1] + u * dt;
        north[i] = north[i - 1] + v * dt;
        seconds[i] = seconds[i - 1] + dt;
    }
    return {east, north, seconds};
}

// Where a particle which starts at level `start` of `path` lands: the first level on the way down at
// which it is at or below the ground under it.  [east, north, seconds] from where it started.
function landing(path, start, bottom, ground) {
    const {east, north, seconds} = path;
    for (let m = start - 1; m > 0; m--) {
        const x = east[start] - east[m];
        const y = north[start] - north[m];
        if (bottom + m * FALL_STEP <= ground(x, y)) return [x, y, seconds[start] - seconds[m]];
    }
    return [east[start] - east[0], north[start] - north[0], seconds[start] - seconds[0]];
}

// The heights the activity starts falling from, once the cloud has stabilized: [{z (m above the
// ground), weight (share of the activity), sigma (m, how wide it is there)}].  `cloud` is as
// stabilizedCloud gives it; `parts` are the shares of the cap, skirt and stem (CLOUD_PARTS).
export function cloudHeights(cloud, parts = CLOUD_PARTS) {
    const heights = [];
    // The cap is Gaussian in height between its base and top, which are 2 sigma either side of its
    // center [WSEG-10]; it is half its radius wide [DNAF-1, (26)].
    const center = (cloud.base + cloud.top) / 2;
    const sigmaHeight = Math.max((cloud.top - cloud.base) / 4, 1);
    const capSigma = cloud.radius / 2;
    const cap = [];
    for (let j = 0; j < HEIGHT_BINS; j++) {
        const z = cloud.base + (j + 0.5) / HEIGHT_BINS * (cloud.top - cloud.base);
        cap.push({z, weight: Math.exp(-0.5 * ((z - center) / sigmaHeight) ** 2), sigma: capSigma});
    }
    const capTotal = cap.reduce((a, h) => a + h.weight, 0);
    for (const h of cap) heights.push({...h, weight: parts.cap * h.weight / capTotal});
    // Below the cap, the stem widens from the early cloud at the ground to the cap at its base
    // [DNAF-1, (25)].
    const groundSigma = Math.min(stemSigma(cloud.yieldKt ?? 1, cloud.earlyRadius ?? capSigma), capSigma);
    const widthAt = (z) => groundSigma + (capSigma - groundSigma) * z / cloud.base;
    const even = (low, high, bins, share) => {
        for (let j = 0; j < bins; j++) {
            const z = low + (j + 0.5) / bins * (high - low);
            heights.push({z, weight: share / bins, sigma: widthAt(z)});
        }
    };
    if (parts.skirt) even(cloud.base / 2, cloud.base, SKIRT_BINS, parts.skirt);
    if (parts.stem) even(0, cloud.base / 2, STEM_BINS, parts.stem);
    return heights;
}

// The spots where the activity lands: [{x, y (m east and north of ground zero), sigma (m),
// activity (share of the burst's activity), hours (in the air)}].
//
// `cloud` is as stabilizedCloud gives it (or as observed); `profile` is as profileFromTable gives
// it.  `diffusivity` (m^2/s) is how fast a spot widens with time in the air; `maxHours` is when
// the ground is looked at: what lands later is not counted.
//
// `terrain`, if given, is {ground(x, y), lowest}: the height (m) of the ground x meters east and y
// north of ground zero, above the ground at ground zero, and the lowest it gets.  A particle lands
// where it first meets the ground: early on a ridge in its way, late in a valley.  Without it the
// ground is flat.
export function landingSpots({cloud, profile, siteElevation = 0, diffusivity = 1000, maxHours = 48,
                                 volumeShare = VOLUME_ACTIVITY_SHARE, terrain = null, parts = CLOUD_PARTS}) {
    const bottom = terrain ? Math.min(0, Math.floor(terrain.lowest / FALL_STEP) * FALL_STEP) : 0;
    const ground = terrain ? terrain.ground : () => 0;
    // Where the activity starts falling from: {z, weight (share of the activity), sigma}.
    const heights = cloudHeights(cloud, parts);
    const spots = [];
    for (const {diameter, activity} of particleSizes(volumeShare)) {
        if (activity <= 0) continue;
        const path = fall(diameter, cloud.top, bottom, profile, siteElevation);
        for (const {z, weight, sigma} of heights) {
            const start = Math.min(Math.round((z - bottom) / FALL_STEP), path.seconds.length - 1);
            const [x, y, seconds] = landing(path, start, bottom, ground);
            if (seconds > maxHours * 3600) continue;
            spots.push({
                x,
                y,
                sigma: Math.sqrt(sigma ** 2 + 2 * diffusivity * seconds),
                activity: activity * weight,
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
// south)}.
export function depositionGrid(spots, {yieldKt, fissionFraction = 1, normalization = SOURCE_NORMALIZATION,
    maxCells = 1200}) {
    let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity, narrowest = Infinity;
    for (const s of spots) {
        west = Math.min(west, s.x - 3 * s.sigma);
        east = Math.max(east, s.x + 3 * s.sigma);
        south = Math.min(south, s.y - 3 * s.sigma);
        north = Math.max(north, s.y + 3 * s.sigma);
        narrowest = Math.min(narrowest, s.sigma);
    }
    const span = Math.max(east - west, north - south);
    const cell = Math.max(span / maxCells, Math.min(narrowest / 2, 250), 25);
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
