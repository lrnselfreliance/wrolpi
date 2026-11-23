import {burstBounds, dayCounter, dayField, parseClimatology} from './climatology.js';
import {depositionGrid, landingSpots} from './model.js';
import {fieldWinds, prepareField} from './winds.js';

// A month file of `days` days on a coarse grid (lat 90..-90 every 30, lon 0..330 every 30), two
// levels, each day with one wind everywhere: [east, north] m/s.
function file(days) {
    const header = {version: 1, month: 5, levels_hpa: [1000, 500], lat: [90, -30, 7], lon: [0, 30, 12],
        days: days.map((_, k) => `200${k}-05-01`), hour_utc: 12};
    const head = new TextEncoder().encode(JSON.stringify(header));
    const size = 2 * 7 * 12;
    const bytes = new Uint8Array(10 + head.length + 2 * size + days.length * 2 * size);
    bytes.set([...'WFCL'].map((c) => c.charCodeAt(0)), 0);
    const view = new DataView(bytes.buffer);
    view.setUint16(4, 1, true);
    view.setUint32(6, head.length, true);
    bytes.set(head, 10);
    let at = 10 + head.length;
    for (let c = 0; c < size; c++) view.setInt16(at + 2 * c, c < size / 2 ? 100 : 5500, true);
    at += 2 * size;
    days.forEach(([e, n]) => {
        for (let c = 0; c < size; c++) view.setInt8(at + c, e);
        for (let c = 0; c < size; c++) view.setInt8(at + size + c, n);
        at += 2 * size;
    });
    return bytes;
}

describe('the climatology', () => {
    test('is read from its file', () => {
        const clim = parseClimatology(file([[10, 0], [-5, 3]]));
        expect(clim.days).toBe(2);
        expect([clim.levels, clim.nlat, clim.nlon]).toEqual([2, 7, 12]);
        expect(clim.heights[0]).toBe(100);
        expect(clim.day(1).u[0]).toBe(-5);
        expect(clim.day(1).v[0]).toBe(3);
        expect(() => parseClimatology(new Uint8Array(20))).toThrow('Not a fallout climatology');
    });

    test('gives a day\'s winds around the bursts, as a field the model reads', () => {
        const clim = parseClimatology(file([[10, 0]]));
        const field = dayField(clim, 0, burstBounds([{lat: 30, lon: -120}, {lat: 30, lon: -90}]));
        // Only the points near the bursts: latitudes 30 +- 12 on this grid are 30; longitudes
        // -120 to -90 with the margin.
        expect(new Set(field.points.map((p) => p.lat))).toEqual(new Set([30]));
        expect(field.points.map((p) => p.lon).sort((a, b) => a - b)).toEqual([-120, -90]);
        // A west wind: from 270 degrees, 10 m/s, at the levels' heights.
        expect(field.winds[0][0]).toEqual([[100, 10, 270], [5500, 10, 270]]);
        expect(field.spacing).toBe(30);
    });

    test('takes in either side of the antimeridian', () => {
        const clim = parseClimatology(file([[10, 0]]));
        const lons = dayField(clim, 0, burstBounds([{lat: 0, lon: 179}])).points.map((p) => p.lon);
        expect(lons).toContain(180 - 360);
    });

    test('counts on how many days each place was reached', () => {
        const counter = dayCounter(1, 1000);
        const grid = (cells) => ({x0: 0, y0: 0, cell: 1000, nx: 3, ny: 1, values: cells});
        counter.add(grid([5, 0, 0]));
        counter.add(grid([5, 2, 0]));
        counter.add(grid([0, 0, 0.5]));
        const shares = counter.grid(0);
        expect(shares.days).toBe(3);
        expect(Array.from(shares.values)).toEqual([2 / 3, 1 / 3]);
        // Smoothed over neighbors (a cell all round): spread out, the total kept.
        const smooth = counter.grid(1);
        expect([smooth.nx, smooth.ny]).toEqual([4, 3]);
        expect(smooth.values.reduce((a, v) => a + v, 0)).toBeCloseTo(1, 10);
        expect(Math.max(...smooth.values)).toBeCloseTo(1 / 9, 10);
    });

    test('shows the fallout of each day\'s winds: two days east, one north', () => {
        const clim = parseClimatology(file([[10, 0], [10, 0], [0, 10]]));
        const burst = {lat: 30, lon: -120};
        const counter = dayCounter(1, 4000);
        for (let k = 0; k < clim.days; k++) {
            const winds = fieldWinds(prepareField(dayField(clim, k, burstBounds([burst]))),
                {lat0: burst.lat, lon0: burst.lon, startMs: Date.parse('2000-01-01T12:00Z')});
            counter.add(depositionGrid(landingSpots({yieldKt: 10, winds}), {yieldKt: 10, boundsFloor: 1}));
        }
        const shares = counter.grid(0);
        const at = (x, y) => shares.values[Math.floor((y - shares.y0) / shares.cell) * shares.nx + Math.floor((x - shares.x0) / shares.cell)];
        // 60 km east: two days of three; 60 km north: one.
        expect(at(60000, 0)).toBeCloseTo(2 / 3, 10);
        expect(at(0, 60000)).toBeCloseTo(1 / 3, 10);
    });
});
