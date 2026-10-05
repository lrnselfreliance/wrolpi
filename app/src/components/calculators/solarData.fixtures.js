import {cellIndex, COLUMNS, PARAMETERS, ROWS} from "./solarData";

// Build a climatology file for tests, the same format scripts/build_solar_climatology.py writes.
// `valueAt(key, month, latitude, longitude)` returns the value for a cell center, or null for no data.
export function encodeClimatology(valueAt) {
    const header = 8;
    const bytes = new Uint8Array(header + PARAMETERS.length * 12 * ROWS * COLUMNS);
    bytes.set([...'WSOL'].map(c => c.charCodeAt(0)), 0);
    bytes[4] = 1;
    bytes[5] = PARAMETERS.length;
    PARAMETERS.forEach(({key, offset, step}, p) => {
        for (let month = 0; month < 12; month++) {
            for (let row = 0; row < ROWS; row++) {
                for (let column = 0; column < COLUMNS; column++) {
                    const value = valueAt(key, month, row - 89.5, column - 179.5);
                    bytes[header + cellIndex(p, month, row, column)] = value === null
                        ? 255
                        : Math.max(0, Math.min(254, Math.round((value + offset) / step)));
                }
            }
        }
    });
    return bytes.buffer;
}

// A plain climatology: the same sunny 40°N profile everywhere.
export const SUNNY_GHI = [2.6, 3.5, 4.7, 5.8, 6.5, 7.2, 7.0, 6.2, 5.2, 4.0, 2.9, 2.3];
export const MILD_TEMPERATURE = [0, 2, 6, 10, 15, 21, 24, 23, 18, 11, 4, 0];

// Encoding the 3 MB file is slow, so it is built once and shared; nothing writes to it.
let uniform = null;
export const uniformClimatology = () => {
    if (!uniform) {
        uniform = encodeClimatology((key, month) => ({
            ghi: SUNNY_GHI[month],
            diffuse: SUNNY_GHI[month] * 0.3,
            albedo: 0.2,
            temperature: MILD_TEMPERATURE[month],
        })[key]);
    }
    return uniform;
};

// Make `fetch` return a climatology file.
export function mockClimatologyFetch(buffer = uniformClimatology()) {
    global.fetch = jest.fn(() => Promise.resolve({ok: true, arrayBuffer: () => Promise.resolve(buffer)}));
    return global.fetch;
}
