import {depositionGrid, profileFromTable, sharpenGrid} from './model.js';
import {combineBursts} from './targets.js';
import {burstsFrame, burstSpots, burstWinds, GRID_PARTS, gridPart, gridParts, joinParts} from './work.js';

describe('the bursts\' grid, in parts', () => {
    const winds = burstWinds({profile: profileFromTable([[0, 270, 20], [30000, 260, 50]], 0)});
    const bursts = Array.from({length: 9}, (_, i) => ({lat: 35 + 0.3 * i, lon: -110 + 0.6 * i, yieldKt: [1, 20, 300][i % 3],
        fissionFraction: 0.5}));
    const spots = combineBursts(bursts[0], bursts.map((b) => ({burst: b, spots: burstSpots(b, winds).spots,
        yieldKt: b.yieldKt, fissionFraction: b.fissionFraction})));

    test('keeps each burst\'s spots in one part, and every spot once', () => {
        const parts = gridParts(spots);
        expect(parts.length).toBe(GRID_PARTS);
        expect(parts.reduce((n, p) => n + p.length, 0)).toBe(spots.length);
        const partOf = new Map();
        parts.forEach((p, i) => p.forEach((s) => {
            expect(partOf.get(s.run) ?? i).toBe(i);
            partOf.set(s.run, i);
        }));
        expect(partOf.size).toBe(bursts.length);
    });

    test('is the grid of all the spots at once, sharpened', () => {
        const frame = burstsFrame(spots, 1);
        const joined = joinParts(frame, gridParts(spots).map((p) => gridPart(frame, p)));
        const whole = sharpenGrid(depositionGrid(spots, {yieldKt: 1, boundsFloor: 1}), spots);
        expect([joined.x0, joined.y0, joined.cell, joined.nx, joined.ny]).toEqual([whole.x0, whole.y0, whole.cell, whole.nx, whole.ny]);
        let most = 0, gap = 0;
        for (let k = 0; k < whole.values.length; k++) {
            most = Math.max(most, whole.values[k]);
            gap = Math.max(gap, Math.abs(joined.values[k] - whole.values[k]));
        }
        expect(most).toBeGreaterThan(100);
        // The same but for the order the numbers are added in.
        expect(gap).toBeLessThan(most * 1e-12);
        // And the narrow hot spots are kept: sharper than the plain grid.
        const plain = depositionGrid(spots, {yieldKt: 1, frame});
        const peak = (g) => g.values.reduce((a, v) => Math.max(a, v), 0);
        expect(peak(joined)).toBeGreaterThan(peak(plain) * 1.01);
    });
});
