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
    landingSpots,
    plumeBearing,
    profileFromTable,
    scaleToUtrdr,
    stabilizedCloud,
    uniformProfile,
} from './model.js';
import {terrainAround} from './terrain.js';

const FEET = 0.3048;

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

// The cloud of a shot: as the fits give it, or as it was observed (heights in the table are above
// sea level; the observed base is taken from the fit where it was not measured).
export function shotCloud(shot, observed = false) {
    const fit = stabilizedCloud(shot.yield_kt);
    if (!observed) return fit;
    const top = (shot.cloud_top_ft_msl - shot.site_elevation_ft) * FEET;
    const base = shot.cloud_bottom_ft_msl
        ? (shot.cloud_bottom_ft_msl - shot.site_elevation_ft) * FEET
        : Math.min(fit.base, top * 0.6);
    return {...fit, base, top};
}

// Run the model on a shot.  options: uniform (one wind, the mean over the cloud), surface (one wind,
// the one at the ground: what a person would read off a weather report), observedCloud,
// diffusivity, volumeShare, terrain (an elevation grid, as decodeGrid gives it: particles land on
// the ground under them, not on a plane at the height of ground zero).
export function runShot(shot, options = {}) {
    const cloud = shotCloud(shot, options.observedCloud);
    let profile = profileFromTable(shot.wind, shot.site_elevation_ft);
    if (options.uniform) profile = uniformProfile(profile, cloud.top);
    if (options.surface) profile = [profile[0]];
    const spots = landingSpots({
        cloud, profile,
        siteElevation: shot.site_elevation_ft * FEET,
        diffusivity: options.diffusivity,
        volumeShare: options.volumeShare,
        terrain: options.terrain ? terrainAround(options.terrain, shot.lon, shot.lat) : null,
    });
    const grid = depositionGrid(spots, {yieldKt: shot.yield_kt});
    const {dose_rates: rates, observed} = shot.areas_sq_mi;
    const lowest = Math.min(...rates);
    const priori = contourAreas(grid, rates);
    const scale = scaleToUtrdr(grid, rates, shot.yield_kt, shot.grounded_utrdr.observed);
    const transport = contourAreas(grid, rates, scale);
    return {
        name: shot.name,
        cloud,
        rates,
        observed,
        apriori: {areas: priori, ...areaError(priori, observed),
            utrdr: groundedUtrdr(grid, rates, shot.yield_kt)},
        transport: {areas: transport, scale, ...areaError(transport, observed),
            bearing: plumeBearing(grid, lowest, scale)},
        hpac403: areaError(shot.areas_sq_mi.hpac_4_03, observed),
        hpac404: areaError(shot.areas_sq_mi.hpac_4_04, observed),
    };
}

// The geometric mean of the shots' errors.
export function meanError(results, pick) {
    return Math.exp(results.reduce((a, r) => a + Math.log(pick(r).error), 0) / results.length);
}
