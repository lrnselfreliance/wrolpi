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
// The longest step (m) and time (s) a particle falls in at once through winds which change with
// place and time.
const FIELD_STEP = 250;
const FIELD_SECONDS = 1200;
// Rain's taking of fallout out of the air [Glasstone and Dolan, Tables 9.74a and b]: inside the rain
// cloud, per hour; below it, per hour in light, moderate and heavy rain (mm an hour).
const RAINOUT_PER_HOUR = Math.LN2 / 0.16;
const WASHOUT = [[1.27, Math.LN2 / 19], [5.08, Math.LN2 / 3.8], [11.94, Math.LN2 / 1.9]];
// What rain takes out on the way is put down as a spot for every so many meters (m).
const WET_MERGE = 10000;
// No wind: the profile of fall paths when the winds are taken where and when a particle is.
const CALM = [[0, 0, 0]];
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
function rise(cloud, path, height, profile, bottom, ground, winds = null) {
    let z = height, x = 0, y = 0, t = cloud.start, highest = z, highestAt = t;
    while (t < cloud.stop) {
        const dt = Math.min(Math.max(0.02 * t, 0.2), 5, cloud.stop - t);
        const w1 = updraft(cloud, z, t) - speedOn(path, z, bottom);
        const zMid = z + w1 * dt / 2;
        const w2 = updraft(cloud, zMid, t + dt / 2) - speedOn(path, zMid, bottom);
        const [u, v] = winds ? winds.at(x, y, zMid, t + dt / 2) : windAt(profile, zMid);
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

// How fast rain takes fallout out of the air (per second), at `altitude` (m above sea level) in rain
// of `mmPerHour` falling from `cloud` ([bottom, top], m above sea level, or null where unknown)
// [Glasstone and Dolan, 9.74 and Tables 9.74a and b].  Inside the rain cloud ("rainout") half is
// taken in about 0.16 hour, whatever the rain; below it ("washout") half in 19, 3.8 and 1.9 hours of
// light, moderate and heavy rain (0.05, 0.20 and 0.47 inch an hour).  Above the cloud, none.
export function scavengingRate(mmPerHour, altitude, cloud) {
    if (!(mmPerHour > 0)) return 0;
    if (cloud && altitude > cloud[1]) return 0;
    if (cloud && altitude >= cloud[0]) return RAINOUT_PER_HOUR / 3600;
    // Between the three rains, on a straight line in log rain against log rate; beyond them, along
    // the nearest stretch of it.
    const k = mmPerHour <= WASHOUT[1][0] ? 0 : 1;
    const [[r0, l0], [r1, l1]] = [WASHOUT[k], WASHOUT[k + 1]];
    const slope = Math.log(l1 / l0) / Math.log(r1 / r0);
    return l0 * Math.pow(mmPerHour / r0, slope) / 3600;
}

// Where a particle falling from `height`, `x0` m east and `y0` m north of ground zero, `t0` seconds
// after the burst, lands, carried by `winds` (see landingSpots) where and when it is: {at: [east,
// north, seconds] of where it lands and how long it took, or null if it is still falling at
// `maxSeconds`; remaining: the share of it not taken out by rain on the way}.  What rain takes out
// is put in `wet` ([{x, y, seconds (after the burst), share}]), a spot for every WET_MERGE meters of
// its way through rain.  It falls by up to FIELD_STEP meters at a time, and for no longer than
// FIELD_SECONDS, when the winds change little; it lands where the line of its last step meets the
// ground.
function landingThrough(winds, diameter, siteElevation, height, x0, y0, t0, bottom, ground, maxSeconds, wet) {
    let z = height, x = x0, y = y0, t = t0, above = z - ground(x, y);
    let remaining = 1, washed = null;
    const flush = () => {
        if (washed && washed.share > 0) {
            wet.push({x: washed.sx / washed.share, y: washed.sy / washed.share, seconds: washed.st / washed.share,
                share: washed.share});
        }
        washed = null;
    };
    const raining = wet && winds.rainAt;
    while (z > bottom) {
        const speed = settlingSpeedAt(diameter, siteElevation + z);
        const step = Math.min(FIELD_STEP, Math.max(speed * FIELD_SECONDS, FALL_STEP), z - bottom);
        const middle = z - step / 2;
        const dt = step / settlingSpeedAt(diameter, siteElevation + middle);
        const [u, v] = winds.at(x, y, middle, t + dt / 2);
        if (raining) {
            const mx = x + u * dt / 2, my = y + v * dt / 2;
            const [mm, cloud] = winds.rainAt(mx, my, t + dt / 2);
            const rate = scavengingRate(mm, siteElevation + middle, cloud);
            if (rate > 0) {
                // What little would be left is taken with the rest.
                let taken = remaining * (1 - Math.exp(-rate * dt));
                if (remaining - taken < 1e-4) taken = remaining;
                remaining -= taken;
                if (!washed) washed = {share: 0, sx: 0, sy: 0, st: 0, x0: mx, y0: my};
                washed.share += taken;
                washed.sx += taken * mx;
                washed.sy += taken * my;
                washed.st += taken * (t + dt / 2);
                if (Math.hypot(mx - washed.x0, my - washed.y0) > WET_MERGE) flush();
                if (remaining <= 0) {
                    flush();
                    return {at: null, remaining: 0};
                }
            } else {
                flush();
            }
        }
        const nextAbove = z - step - ground(x + u * dt, y + v * dt);
        if (nextAbove <= 0) {
            // Down to the ground, part of the way.
            const f = above > 0 ? above / (above - nextAbove) : 0;
            if (raining) flush();
            return {at: [x + f * u * dt, y + f * v * dt, t + f * dt - t0], remaining};
        }
        x += u * dt;
        y += v * dt;
        t += dt;
        z -= step;
        above = nextAbove;
        if (t > maxSeconds) {
            if (raining) flush();
            return {at: null, remaining};
        }
    }
    if (raining) flush();
    return {at: [x, y, t - t0], remaining};
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
//
// `winds`, if given, is {at(x, y, z, t)}: the wind [east, north] (m/s) x meters east and y north of
// ground zero, z meters above its ground, t seconds after the burst; a particle is then carried by
// the wind where it is, at the height it is, when it is there, and `profile` is not used.  If it
// also has rainAt(x, y, t), [mm an hour, cloud ([bottom, top], m above sea level) or null], rain
// takes fallout out of the air on the way down and puts it down there (spots with `wet`).
export function landingSpots({yieldKt, burstHeight = 0, profile, siteElevation = 0, maxHours = 48,
                                 volumeShare = VOLUME_ACTIVITY_SHARE, terrain = null, stabilized = null,
                                 winds = null}) {
    if (winds) profile = CALM;
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
            const r = rise(cloud, path, start, profile, bottom, ground, winds);
            let radius;
            if (!r.landed && r.height >= cloud.base) radius = cloud.radius;
            else {
                const f = (r.height - first.height) / Math.max(cloud.base - first.height, 1);
                radius = cloud.initialRadius + Math.min(Math.max(f, 0), 1) * (cloud.radius - cloud.initialRadius);
            }
            const parcel = activity * down / SUBDIVISIONS;
            // A spot where some of this parcel lands, `seconds` after the burst.
            const put = (x, y, seconds, share, wet) => {
                if (seconds > maxHours * 3600 || !(share > 0)) return;
                const falling = Math.max(seconds - r.highestAt, 1);
                const sigma = landedSigma(radius / 2, r.highest, Math.max(r.highest, 1) / falling);
                spots.push({x, y, sigma, diameter, highest: r.highest, activity: parcel * share, hours: seconds / 3600,
                    ...(wet ? {wet: true} : {})});
            };
            if (r.landed) {
                put(r.x, r.y, r.seconds, 1);
            } else if (winds) {
                const wet = [];
                const landed = landingThrough(winds, diameter, siteElevation, r.height, r.x, r.y, r.seconds, bottom,
                    ground, maxHours * 3600, wet);
                for (const w of wet) put(w.x, w.y, w.seconds, w.share, true);
                if (landed.at) put(landed.at[0], landed.at[1], r.seconds + landed.at[2], landed.remaining);
            } else {
                const [x, y, fallSeconds] = landing(path, r.height, r.x, r.y, bottom, ground);
                put(x, y, r.seconds + fallSeconds, 1);
            }
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
// south)}.  `bounds` and `cellSize` give a closer look at part of it; `boundsFloor` keeps the grid to
// where the dose rate can reach it.
export function depositionGrid(spots, {yieldKt, fissionFraction = 1, normalization = SOURCE_NORMALIZATION,
    maxCells = 1200, bounds = null, cellSize = null, boundsFloor = 0}) {
    let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity, narrowest = Infinity;
    // The grid covers the spots which can raise the dose rate to `boundsFloor` (R/hr) by themselves:
    // the faintest are carried thousands of km, and would stretch the grid past where anything is
    // drawn (or past the poles).  Spots outside it are left out.
    const peak = (s) => s.activity * normalization * yieldKt * fissionFraction / (2 * Math.PI * (s.sigma / 1000) ** 2);
    const counted = boundsFloor > 0 && spots.some((s) => peak(s) >= boundsFloor)
        ? spots.filter((s) => peak(s) >= boundsFloor) : spots;
    for (const s of counted) {
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

// The finest cell (m) a burst's narrow spots are looked at on, and how many of them a coarse cell is
// split into across, at most.
const FINE_CELL = 250;
const MOST_SPLITS = 32;

// `grid` (as depositionGrid gives it, of `spots`), with the peaks of narrow spots kept.
//
// A grid over many bursts far apart has cells kilometers wide, and a cell's value is the average over
// it: the hot, narrow fallout close to a small burst's ground zero, hundreds of meters wide, would be
// averaged down into a lower band.  So each burst's spots narrower than half a cell (spots of one
// `run`, as combineBursts gives them; all one run without it) are also put on a fine grid, and each
// cell gains the most any part of it is above the cell's average, by the burst which raises it most.
// The cell's average, which sums the bursts, is kept beneath.
export function sharpenGrid(grid, spots, {yieldKt = 1, fissionFraction = 1, normalization = SOURCE_NORMALIZATION} = {}) {
    const coarse = grid.cell;
    const runs = new Map();
    for (const s of spots) {
        if (!(s.sigma < coarse / 2)) continue;
        const run = s.run ?? 0;
        if (!runs.has(run)) runs.set(run, []);
        runs.get(run).push(s);
    }
    if (!runs.size) return grid;
    const extra = new Float64Array(grid.values.length);
    for (const narrow of runs.values()) {
        const narrowest = Math.min(...narrow.map((s) => s.sigma));
        const splits = Math.min(Math.ceil(coarse / Math.max(Math.min(narrowest / 2, FINE_CELL), 25)), MOST_SPLITS);
        if (splits < 2) continue;
        // The coarse cells the narrow spots reach.
        let i0 = Infinity, i1 = -Infinity, j0 = Infinity, j1 = -Infinity;
        for (const s of narrow) {
            i0 = Math.min(i0, Math.floor((s.x - 3 * s.sigma - grid.x0) / coarse));
            i1 = Math.max(i1, Math.floor((s.x + 3 * s.sigma - grid.x0) / coarse));
            j0 = Math.min(j0, Math.floor((s.y - 3 * s.sigma - grid.y0) / coarse));
            j1 = Math.max(j1, Math.floor((s.y + 3 * s.sigma - grid.y0) / coarse));
        }
        i0 = Math.max(i0, 0);
        j0 = Math.max(j0, 0);
        i1 = Math.min(i1, grid.nx - 1);
        j1 = Math.min(j1, grid.ny - 1);
        if (i1 < i0 || j1 < j0) continue;
        const cols = i1 - i0 + 1, rows = j1 - j0 + 1;
        const fine = depositionGrid(narrow, {
            yieldKt, fissionFraction, normalization, cellSize: coarse / splits,
            bounds: [grid.x0 + i0 * coarse, grid.y0 + j0 * coarse, grid.x0 + (i1 + 1) * coarse, grid.y0 + (j1 + 1) * coarse],
        });
        for (let j = 0; j < rows; j++) {
            for (let i = 0; i < cols; i++) {
                let most = 0, sum = 0;
                for (let b = 0; b < splits; b++) {
                    const row = (j * splits + b) * fine.nx + i * splits;
                    if (j * splits + b >= fine.ny) break;
                    for (let a = 0; a < splits && i * splits + a < fine.nx; a++) {
                        const v = fine.values[row + a];
                        sum += v;
                        if (v > most) most = v;
                    }
                }
                const k = (j0 + j) * grid.nx + i0 + i;
                const above = most - sum / (splits * splits);
                if (above > extra[k]) extra[k] = above;
            }
        }
    }
    const values = Float64Array.from(grid.values, (v, k) => v + extra[k]);
    return {...grid, values};
}

// How much stronger (or weaker) fallout is `hours` after a burst than at H+1: the Way-Wigner
// t^-1.2 of fission products' decay [Glasstone and Dolan, 9.145], good from about half an hour to
// months.
export function decayFromH1(hours) {
    return Math.pow(hours, -1.2);
}

// The earliest a spot is taken to land (hours): t^-1.2 is fitted from about half an hour, and
// grows without bound towards the burst.
const EARLIEST_ARRIVAL = 0.1;

// A grid like `like` (as depositionGrid gives it), of the spots landed by `hours`, each counted
// `weight(spot)` times its H+1 dose rate.  Every hour's grid has `like`'s cells, so it is drawn in
// the same place.
function timedGrid(spots, like, hours, weight, options) {
    const landed = [];
    for (const s of spots) {
        if (s.hours > hours) continue;
        const w = weight(s);
        if (w > 0) landed.push({...s, activity: s.activity * w});
    }
    let grid = depositionGrid(landed, {
        ...options, cellSize: like.cell,
        bounds: [like.x0, like.y0, like.x0 + like.nx * like.cell, like.y0 + like.ny * like.cell],
    });
    // The same cells as `like`, though rounding may have made one more.
    if (grid.nx !== like.nx || grid.ny !== like.ny) {
        const values = new Float64Array(like.nx * like.ny);
        for (let j = 0; j < like.ny; j++) {
            for (let i = 0; i < like.nx; i++) values[j * like.nx + i] = grid.values[j * grid.nx + i] || 0;
        }
        grid = {...like, values};
    }
    return sharpenGrid(grid, landed, options);
}

// The dose rate (R/hr) `hours` after the bursts on a grid like `like` (of `spots`): only the
// fallout which has landed by then, as strong as it is then.
export function landedGrid(spots, like, hours, {yieldKt = 1, fissionFraction = 1, normalization = SOURCE_NORMALIZATION} = {}) {
    const decay = decayFromH1(hours);
    return timedGrid(spots, like, hours, () => decay, {yieldKt, fissionFraction, normalization});
}

// The dose (R) someone outdoors gets from fallout which has fallen at `arrival` hours, from then
// until `hours`, for each R/hr of its H+1 dose rate: the integral of t^-1.2, 5 (ta^-0.2 - t^-0.2).
export function doseFromH1(arrival, hours) {
    const from = Math.max(arrival, EARLIEST_ARRIVAL);
    return hours > from ? 5 * (Math.pow(from, -0.2) - Math.pow(hours, -0.2)) : 0;
}

// The total dose (R) by `hours` after the bursts, of someone outdoors everywhere on a grid like
// `like` (of `spots`), from when each spot's fallout landed there.
export function doseGrid(spots, like, hours, {yieldKt = 1, fissionFraction = 1, normalization = SOURCE_NORMALIZATION} = {}) {
    return timedGrid(spots, like, hours, (s) => doseFromH1(s.hours, hours), {yieldKt, fissionFraction, normalization});
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
