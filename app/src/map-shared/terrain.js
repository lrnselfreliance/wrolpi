// How the map reads a terrain (elevation) file: how deep into it to look, and how far apart the
// contour lines are.  Shared by the app's map viewer and the standalone viewer, which loads a copy
// of this file as it is: no imports from the app, no dependencies.

// How deep the terrain file which WROLPi offers goes, and what a file is taken to be when it does
// not say.
export const DEFAULT_TERRAIN_MAX_ZOOM = 8;
// No terrain file is read deeper than this.
const DEEPEST_TERRAIN_ZOOM = 15;

// How far apart the contour lines are at each zoom of the map: [minor, major], in the unit the map
// measures in.  A zoom between two of these uses the one below it.
//
// A 1:24,000 sheet has a line every 40 feet (or 20 meters), which is what the deepest have: finer
// lines than that are more than the terrain says, and more than a hillside has room for.
const CONTOUR_FEET = {
    4: [1000, 5000], 5: [500, 2500], 6: [200, 1000], 7: [200, 1000], 8: [100, 500],
    9: [100, 500], 10: [100, 500], 11: [40, 200], 12: [40, 200],
};
const CONTOUR_METERS = {
    4: [500, 2500], 5: [200, 1000], 6: [100, 500], 7: [100, 500], 8: [50, 200],
    9: [50, 200], 10: [50, 200], 11: [20, 100], 12: [20, 100],
};

// How deep a terrain file goes: the deepest zoom it has tiles of.  `file` is as the API lists it.
export function terrainMaxZoom(file) {
    const zoom = Number(file && file.max_zoom);
    if (!Number.isInteger(zoom) || zoom < 1) return DEFAULT_TERRAIN_MAX_ZOOM;
    return Math.min(zoom, DEEPEST_TERRAIN_ZOOM);
}

// The contour intervals for a terrain file which goes as deep as `maxZoom`.
//
// Only those the file can bear: lines 40 feet apart drawn from terrain too coarse for them are
// drawn where no line is.  A map zoomed in past the file's depth keeps the file's finest interval.
export function contourThresholds(imperial, maxZoom) {
    const all = imperial ? CONTOUR_FEET : CONTOUR_METERS;
    const deepest = Number.isFinite(maxZoom) ? maxZoom : DEFAULT_TERRAIN_MAX_ZOOM;
    const lowest = Math.min(...Object.keys(all).map(Number));
    const thresholds = {};
    for (const [zoom, intervals] of Object.entries(all)) {
        // A file shallower than every interval still has contours: the coarsest.
        if (Number(zoom) <= deepest || Number(zoom) === lowest) thresholds[zoom] = intervals;
    }
    return thresholds;
}
