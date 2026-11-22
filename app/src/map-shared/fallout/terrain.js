// The ground under a fallout plume: an elevation grid, as the model reads it.  Shared by the app's
// map viewer and the standalone viewer: no imports from the app, no dependencies.
//
// A grid is {west, south (degrees), step (degrees between samples), nx, ny, values (meters, row by
// row from the south)}.

const METERS_PER_DEGREE = 111320;

// A grid from its compact form: elevations as little-endian 16-bit integers, in base64.
export function decodeGrid({west, south, step, nx, ny, meters_int16_le_base64: data}) {
    const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
    const view = new DataView(bytes.buffer);
    const values = new Float32Array(nx * ny);
    for (let i = 0; i < values.length; i++) values[i] = view.getInt16(i * 2, true);
    return {west, south, step, nx, ny, values};
}

// The elevation (m) at `lon`, `lat`: bilinear between the samples, and as the nearest edge beyond
// them.
export function elevationAt(grid, lon, lat) {
    const fx = Math.min(Math.max((lon - grid.west) / grid.step, 0), grid.nx - 1);
    const fy = Math.min(Math.max((lat - grid.south) / grid.step, 0), grid.ny - 1);
    const i = Math.min(Math.floor(fx), grid.nx - 2);
    const j = Math.min(Math.floor(fy), grid.ny - 2);
    const dx = fx - i, dy = fy - j;
    const v = grid.values;
    // A sample with no number is left out, and the others weighed as they are.
    let sum = 0, weight = 0;
    for (const [a, b, w] of [[i, j, (1 - dx) * (1 - dy)], [i + 1, j, dx * (1 - dy)],
        [i, j + 1, (1 - dx) * dy], [i + 1, j + 1, dx * dy]]) {
        const value = v[b * grid.nx + a];
        if (w > 0 && Number.isFinite(value)) {
            sum += value * w;
            weight += w;
        }
    }
    return weight > 0 ? sum / weight : NaN;
}

// The terrain around a burst at `lon`, `lat`, as the model takes it: {ground(x, y), lowest, elevation}.
// ground(x, y) is the height of the ground x meters east and y north of ground zero above the ground
// at ground zero; lowest is the lowest it gets anywhere on the grid; elevation is that of ground zero.
export function terrainAround(grid, lon, lat) {
    const elevation = elevationAt(grid, lon, lat);
    const perLon = METERS_PER_DEGREE * Math.cos(lat * Math.PI / 180);
    let lowest = Infinity;
    for (const v of grid.values) if (Number.isFinite(v)) lowest = Math.min(lowest, v);
    if (!Number.isFinite(lowest)) lowest = elevation;
    return {
        elevation,
        lowest: lowest - elevation,
        // Where the grid has no number, the ground is as high as ground zero.
        ground: (x, y) => {
            const e = elevationAt(grid, lon + x / perLon, lat + y / METERS_PER_DEGREE) - elevation;
            return Number.isFinite(e) ? e : 0;
        },
    };
}
