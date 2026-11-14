// The areas a map can be exported by: the 7.5-minute quadrangles of a 1:24,000 topographic map.
//
// A quadrangle is 7.5 minutes of latitude by 7.5 minutes of longitude, its edges on whole multiples
// of that.  The grid is arithmetic, so it needs no data and covers the whole world.

export const QUAD_DEGREES = 0.125;
export const QUAD_SCALE = 24000;
// The grid is not drawn below this zoom: its cells would be too small to choose between.
export const QUAD_MIN_ZOOM = 8;

const QUADS_PER_DEGREE = 1 / QUAD_DEGREES;
// Web Mercator draws no further north or south than this.
const MAX_LATITUDE = 85;
const MAX_GRID_LINES = 400;

function wrapLongitude(lng) {
    return ((lng + 180) % 360 + 360) % 360 - 180;
}

function quadOf(row, col) {
    return {
        id: `${row}:${col}`,
        row,
        col,
        west: col * QUAD_DEGREES,
        south: row * QUAD_DEGREES,
        east: (col + 1) * QUAD_DEGREES,
        north: (row + 1) * QUAD_DEGREES,
    };
}

// The quadrangle a point is in, or null where there is none (off the map, or not a place).
export function quadAt(lng, lat) {
    if (!Number.isFinite(lng) || !Number.isFinite(lat) || Math.abs(lat) >= MAX_LATITUDE) return null;
    return quadOf(Math.floor(lat * QUADS_PER_DEGREE), Math.floor(wrapLongitude(lng) * QUADS_PER_DEGREE));
}

// The outline of a quadrangle, as GeoJSON.
export function quadPolygon(quad) {
    const {west, south, east, north} = quad;
    return {
        type: "Feature",
        properties: {id: quad.id},
        geometry: {
            type: "Polygon",
            coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        },
    };
}

export const EMPTY_FEATURES = {type: "FeatureCollection", features: []};

// The lines of the grid across `bounds` ({west, south, east, north}, as the map gives them; east may
// be past 180), as GeoJSON.  Null when there would be too many lines to be of use.
export function quadGridLines(bounds) {
    const south = Math.max(bounds.south, -MAX_LATITUDE);
    const north = Math.min(bounds.north, MAX_LATITUDE);
    const firstRow = Math.floor(south * QUADS_PER_DEGREE);
    const lastRow = Math.ceil(north * QUADS_PER_DEGREE);
    const firstCol = Math.floor(bounds.west * QUADS_PER_DEGREE);
    const lastCol = Math.ceil(bounds.east * QUADS_PER_DEGREE);
    if (!(lastRow > firstRow) || !(lastCol > firstCol)) return EMPTY_FEATURES;
    if ((lastRow - firstRow) + (lastCol - firstCol) > MAX_GRID_LINES) return null;

    const [west, east] = [firstCol * QUAD_DEGREES, lastCol * QUAD_DEGREES];
    const [bottom, top] = [firstRow * QUAD_DEGREES, lastRow * QUAD_DEGREES];
    const lines = [];
    for (let row = firstRow; row <= lastRow; row++) {
        lines.push([[west, row * QUAD_DEGREES], [east, row * QUAD_DEGREES]]);
    }
    for (let col = firstCol; col <= lastCol; col++) {
        lines.push([[col * QUAD_DEGREES, bottom], [col * QUAD_DEGREES, top]]);
    }
    return {
        type: "FeatureCollection",
        features: [{type: "Feature", properties: {}, geometry: {type: "MultiLineString", coordinates: lines}}],
    };
}

// 37.875 -> 37°52′30″
function degreesMinutesSeconds(value) {
    const seconds = Math.round(Math.abs(value) * 3600);
    const d = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    const pad = n => String(n).padStart(2, "0");
    return s ? `${d}°${pad(m)}′${pad(s)}″` : `${d}°${pad(m)}′`;
}

export function formatLatitude(lat) {
    return `${degreesMinutesSeconds(lat)}${lat < 0 ? "S" : "N"}`;
}

export function formatLongitude(lng) {
    return `${degreesMinutesSeconds(lng)}${lng < 0 ? "W" : "E"}`;
}

// What to call a quadrangle: where its southwest corner is.
export function quadLabel(quad) {
    return `${formatLatitude(quad.south)} ${formatLongitude(quad.west)}`;
}

// How far it is across and up a quadrangle on the ground (meters, along its middle), and on a sheet
// printed at 1:24,000 (millimeters).
export function quadSize(quad) {
    const latitude = (quad.south + quad.north) / 2 * Math.PI / 180;
    // The length of a degree on the WGS84 ellipsoid.
    const metersPerDegreeLatitude = 111132.92 - 559.82 * Math.cos(2 * latitude) + 1.175 * Math.cos(4 * latitude);
    const metersPerDegreeLongitude = 111412.84 * Math.cos(latitude) - 93.5 * Math.cos(3 * latitude)
        + 0.118 * Math.cos(5 * latitude);
    const widthMeters = metersPerDegreeLongitude * QUAD_DEGREES;
    const heightMeters = metersPerDegreeLatitude * QUAD_DEGREES;
    return {
        widthMeters,
        heightMeters,
        sheetWidthMm: widthMeters * 1000 / QUAD_SCALE,
        sheetHeightMm: heightMeters * 1000 / QUAD_SCALE,
    };
}
