// How well the model matches the fallout measured after six Nevada tests (nts-shots.json), and how
// well HPAC, the DoD's hazard model, matched the same measurements.
//
// The measure is the area inside each measured dose-rate contour: predicted / observed.  A shot's
// error is the geometric mean of how far off each contour is (2 = off by a factor of two, either
// way); its bias is the geometric mean of the ratios (above 1 = too big).
//
// Two questions are kept apart:
//   transport: with the right amount of activity on the ground, does it land in the right places?
//              The prediction is scaled so its grounded UTRDR (the measured amount) matches.
//   a priori:  with nothing taken from the measurements, as the map would run.

import {
    contourAreas,
    depositionGrid,
    groundedUtrdr,
    hotlines,
    landingSpots,
    plumeBearing,
    profileFromTable,
    risingCloud,
    scaleToUtrdr,
    stabilizedCloud,
    uniformProfile,
} from './model.js';
import {terrainAround} from './terrain.js';

const FEET = 0.3048;
const SQ_KM_PER_SQ_MI = 2.589988;

// The geometric mean of how far off each ratio is, and of the ratios.
export function areaError(predicted, observed) {
    const logs = [];
    predicted.forEach((p, i) => {
        const o = observed[i];
        if (o === null || o === undefined) return;
        // A contour predicted nowhere counts as off by the smallest area the grid could show.
        logs.push(Math.log(Math.max(p, 0.01) / o));
    });
    const n = logs.length;
    return {
        error: Math.exp(logs.reduce((a, l) => a + Math.abs(l), 0) / n),
        bias: Math.exp(logs.reduce((a, l) => a + l, 0) / n),
        contours: n,
    };
}

// The stabilized cloud of a shot as observed ({base, top}, m above the burst), or null where its top
// was not measured; a base which was not measured is taken from the fit.
export function observedCloud(shot) {
    if (!shot.cloud_top_ft_msl) return null;
    const above = shot.site_elevation_ft + Math.max(shot.burst_height_ft, 0);
    const top = (shot.cloud_top_ft_msl - above) * FEET;
    const fit = stabilizedCloud(shot.yield_kt);
    const base = shot.cloud_bottom_ft_msl ? (shot.cloud_bottom_ft_msl - above) * FEET : Math.min(fit.base, top * 0.6);
    return {base, top};
}

// The landing spots of a shot.  options: uniform (one wind, the mean over the cloud), surface (one
// wind, the one at the ground: what a person would read off a weather report), observedCloud (the
// cloud as observed, not as the fits give it), volumeShare, terrain (an elevation grid, as
// decodeGrid gives it: particles land on the ground under them, not on a plane at the height of
// ground zero).
export function shotSpots(shot, options = {}) {
    const burstHeight = Math.max(shot.burst_height_ft, 0) * FEET;
    const stabilized = options.observedCloud ? observedCloud(shot) : null;
    let profile = profileFromTable(shot.wind, shot.site_elevation_ft);
    if (options.uniform) profile = uniformProfile(profile, risingCloud(shot.yield_kt, burstHeight, stabilized).top);
    if (options.surface) profile = [profile[0]];
    return landingSpots({
        yieldKt: shot.yield_kt,
        burstHeight,
        profile,
        siteElevation: shot.site_elevation_ft * FEET,
        volumeShare: options.volumeShare,
        stabilized,
        terrain: options.terrain ? terrainAround(options.terrain, shot.lon, shot.lat) : null,
    });
}

// Run the model on one of the six shots (nts-shots.json); options as shotSpots takes them.
export function runShot(shot, options = {}) {
    const grid = depositionGrid(shotSpots(shot, options), {yieldKt: shot.yield_kt});
    const {dose_rates: rates, observed} = shot.areas_sq_mi;
    const lowest = Math.min(...rates);
    const priori = contourAreas(grid, rates);
    const scale = scaleToUtrdr(grid, rates, shot.yield_kt, shot.grounded_utrdr.observed);
    const transport = contourAreas(grid, rates, scale);
    return {
        name: shot.name,
        rates,
        observed,
        apriori: {areas: priori, ...areaError(priori, observed),
            utrdr: groundedUtrdr(grid, rates, shot.yield_kt), bearing: plumeBearing(grid, lowest)},
        transport: {areas: transport, scale, ...areaError(transport, observed),
            bearing: plumeBearing(grid, lowest, scale)},
        hpac403: areaError(shot.areas_sq_mi.hpac_4_03, observed),
        hpac404: areaError(shot.areas_sq_mi.hpac_4_04, observed),
    };
}

// Run the model on one of the three close-in shots (near-field-shots.json), on a fine grid around
// ground zero: the area (km^2), hotline (km) and azimuth of each contour, and how far off each is,
// beside how far off DNAF-1, DELFIC and WSEG-10 were.
export function runNearField(shot, options = {}) {
    const grid = depositionGrid(shotSpots(shot, options), {
        yieldKt: shot.yield_kt, fissionFraction: shot.fission_kt / shot.yield_kt,
        bounds: [-20000, -20000, 20000, 20000], cellSize: 40,
    });
    const {rates, observed} = shot.contours;
    const area = contourAreas(grid, rates).map((a) => a * SQ_KM_PER_SQ_MI);
    const lines = hotlines(grid, rates);
    const others = {};
    for (const model of ['dnaf1', 'delfic', 'wseg10']) {
        const p = shot.contours[model];
        if (p) others[model] = {area: areaError(p.area_km2, observed.area_km2), hotline: areaError(p.hotline_km, observed.hotline_km)};
    }
    return {
        name: shot.name,
        area: {values: area, ...areaError(area, observed.area_km2)},
        hotline: {values: lines.map((l) => l.km), ...areaError(lines.map((l) => l.km), observed.hotline_km)},
        azimuth: lines.map((l) => l.azimuth),
        others,
    };
}

// The geometric mean of the shots' errors.
export function meanError(results, pick) {
    return Math.exp(results.reduce((a, r) => a + Math.log(pick(r).error), 0) / results.length);
}
