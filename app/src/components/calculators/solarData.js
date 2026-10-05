import React from "react";

// Offline solar climatology for the Solar calculator: NASA POWER's 2001-2020 monthly averages on a
// 1° grid, built by scripts/build_solar_climatology.py.  The format is described in that script and
// must match PARAMETERS below.  The file is only fetched when the calculator opens.

export const CLIMATOLOGY_URL = `${process.env.PUBLIC_URL || ''}/data/solar-climatology.bin`;

// Attribution, as NASA asks (https://power.larc.nasa.gov/docs/referencing/) and CC BY 4.0 requires.  The
// build script writes the same text, with the API version and download date, to
// public/data/solar-climatology.LICENSE.txt; a test keeps the two in step.
export const CLIMATOLOGY_ACKNOWLEDGMENT = 'The data was obtained from National Aeronautics and Space '
    + 'Administration (NASA) Langley Research Center\'s Prediction Of Worldwide Energy Resources (POWER) project '
    + 'funded through the NASA Earth Science Division.';
export const CLIMATOLOGY_DATA_REFERENCE = 'The data was obtained from the POWER Project\'s POWER Climatology API '
    + 'v2.10.0 version on 2026/10/04.';
export const CLIMATOLOGY_LICENSE = 'Creative Commons Attribution 4.0 International (CC BY 4.0), '
    + 'https://creativecommons.org/licenses/by/4.0/';
export const CLIMATOLOGY_CHANGES = 'WROLPi modified the data: values are rounded to fit one byte each '
    + '(0.04 kWh/m²/day for irradiance, 0.004 for albedo, 0.5 °C for temperature), temperatures are averaged from '
    + 'NASA\'s 0.5° x 0.625° grid into 1° cells, and the calculator interpolates between cells.';

const MAGIC = 'WSOL';
const VERSION = 1;
const HEADER_BYTES = 8;
export const ROWS = 180;
export const COLUMNS = 360;
const MISSING = 255;

// Stored as round((value + offset) / step), in this order.
export const PARAMETERS = [
    {key: 'ghi', offset: 0, step: 0.04},
    {key: 'diffuse', offset: 0, step: 0.04},
    {key: 'albedo', offset: 0, step: 0.004},
    {key: 'temperature', offset: 70, step: 0.5},
];

const PARAMETER_BYTES = 12 * ROWS * COLUMNS;

// Validate a downloaded file and return its value grid.
export function decodeClimatology(buffer) {
    const bytes = new Uint8Array(buffer);
    const magic = String.fromCharCode(...bytes.slice(0, 4));
    if (magic !== MAGIC) {
        throw new Error('Not a solar climatology file');
    }
    if (bytes[4] !== VERSION || bytes[5] !== PARAMETERS.length) {
        throw new Error(`Unsupported solar climatology version ${bytes[4]}`);
    }
    if (bytes.length !== HEADER_BYTES + PARAMETERS.length * PARAMETER_BYTES) {
        throw new Error('Solar climatology file is truncated');
    }
    return bytes.subarray(HEADER_BYTES);
}

// Index of a stored value.
export const cellIndex = (parameter, month, row, column) =>
    parameter * PARAMETER_BYTES + (month * ROWS + row) * COLUMNS + column;

/**
 * Monthly averages at a location, bilinearly interpolated between the four surrounding cell centers.
 * Cells with no data are skipped.  Longitude wraps across the antimeridian; latitude is clamped at the
 * outermost cell centers.
 *
 * @returns {{ghi: number[], diffuse: number[], albedo: number[], temperature: number[]}} 12 values each,
 *          null for a month with no data
 */
export function lookupClimatology(grid, latitude, longitude) {
    const y = Math.min(ROWS - 1, Math.max(0, latitude + 90 - 0.5));
    const row0 = Math.floor(y);
    const row1 = Math.min(ROWS - 1, row0 + 1);
    const fy = y - row0;

    const x = longitude + 180 - 0.5;
    const xFloor = Math.floor(x);
    const fx = x - xFloor;
    const column0 = ((xFloor % COLUMNS) + COLUMNS) % COLUMNS;
    const column1 = (column0 + 1) % COLUMNS;

    const corners = [
        [row0, column0, (1 - fy) * (1 - fx)],
        [row0, column1, (1 - fy) * fx],
        [row1, column0, fy * (1 - fx)],
        [row1, column1, fy * fx],
    ];

    const result = {};
    PARAMETERS.forEach(({key, offset, step}, p) => {
        result[key] = Array.from({length: 12}, (_, month) => {
            let sum = 0, weight = 0;
            for (const [row, column, w] of corners) {
                const raw = grid[cellIndex(p, month, row, column)];
                if (raw !== MISSING && w > 0) {
                    sum += (raw * step - offset) * w;
                    weight += w;
                }
            }
            return weight > 0 ? sum / weight : null;
        });
    });
    return result;
}

let climatologyPromise = null;

// Fetch and decode the file once per page load.  A failed fetch is not cached, so it can be retried.
export function loadClimatology() {
    if (!climatologyPromise) {
        climatologyPromise = fetch(CLIMATOLOGY_URL)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Could not load solar data (${response.status})`);
                }
                return response.arrayBuffer();
            })
            .then(decodeClimatology)
            .catch(error => {
                climatologyPromise = null;
                throw error;
            });
    }
    return climatologyPromise;
}

// Drop the loaded file, so the next load fetches again.  Tests use this to simulate a failed download.
export function forgetClimatology() {
    climatologyPromise = null;
}

// The decoded grid, or null while loading.  `error` is set when the file could not be loaded.
export function useClimatology() {
    const [grid, setGrid] = React.useState(null);
    const [error, setError] = React.useState(null);

    React.useEffect(() => {
        let cancelled = false;
        loadClimatology()
            .then(g => !cancelled && setGrid(g))
            .catch(e => !cancelled && setError(e));
        return () => {
            cancelled = true;
        };
    }, []);

    return {grid, error, loading: !grid && !error};
}
