import {combineBursts, CUSTOM_WEAPON, DEFAULT_WEAPON, offsetFrom, targetWeapon} from './targets.js';
import {depositionGrid, landingSpots, sharpenGrid, SOURCE_NORMALIZATION} from './model.js';

describe('a target\'s weapon', () => {
    test('is the one chosen for it, with its yield and fission share', () => {
        expect(targetWeapon({weapon: 'w88'})).toMatchObject({key: 'w88', yieldKt: 455, fissionFraction: 0.5});
    });

    test('is the default when none was chosen, or the one chosen is no longer offered', () => {
        expect(targetWeapon({}).key).toBe(DEFAULT_WEAPON);
        expect(targetWeapon({weapon: 'retired-thing'}).key).toBe(DEFAULT_WEAPON);
    });

    test('keeps the target\'s own fission share over the weapon\'s', () => {
        expect(targetWeapon({weapon: 'w88', fission_fraction: 0.8}).fissionFraction).toBe(0.8);
    });

    test('may be a yield of the user\'s own', () => {
        expect(targetWeapon({weapon: CUSTOM_WEAPON, yield_kt: 20, fission_fraction: 1}))
            .toMatchObject({weapon: null, yieldKt: 20, fissionFraction: 1});
    });
});

describe('several bursts', () => {
    test('are placed from one origin', () => {
        const [x, y] = offsetFrom({lat: 0, lon: 0}, {lat: 1, lon: 1});
        expect(x).toBeCloseTo(111320, 0);
        expect(y).toBeCloseTo(111320, 0);
    });

    test('put down the fallout of each, by its fission yield, on one grid', () => {
        const profile = [[0, 10, 0]];
        const a = {lat: 40, lon: -105}, b = {lat: 40, lon: -104};
        const spots = landingSpots({yieldKt: 10, profile});
        const combined = combineBursts(a, [
            {burst: a, spots, yieldKt: 10, fissionFraction: 0.5},
            {burst: b, spots, yieldKt: 10, fissionFraction: 1},
        ]);
        expect(combined.length).toBe(spots.length * 2);
        const grid = depositionGrid(combined, {yieldKt: 1});
        const landed = spots.reduce((s, x) => s + x.activity, 0);
        const total = grid.values.reduce((s, v) => s + v, 0) * (grid.cell / 1000) ** 2;
        // 5 kt + 10 kt of fission.
        expect(total / (SOURCE_NORMALIZATION * 15 * landed)).toBeCloseTo(1, 2);
        // The second burst's spots are a degree of longitude east.
        expect(combined[spots.length].x - combined[0].x).toBeCloseTo(111320 * Math.cos(40 * Math.PI / 180), 0);
    });
});

describe('bursts far apart', () => {
    test('keep their plumes as wide east to west as at their own latitude', () => {
        const spot = {x: 1000, y: 0, sigma: 1, activity: 1, hours: 1};
        const origin = {lat: 40, lon: -75}, south = {lat: 25, lon: -80};
        const [combined] = combineBursts(origin, [{burst: south, spots: [spot], yieldKt: 1, fissionFraction: 1}]);
        const [dx] = offsetFrom(origin, south);
        // 1000 m east at 25 degrees is more of a degree of longitude than 1000 m at 40.
        expect(combined.x - dx).toBeCloseTo(1000 * Math.cos(40 * Math.PI / 180) / Math.cos(25 * Math.PI / 180), 6);
    });
});

describe('a small burst far from a large one', () => {
    // The highest dose rate (R/hr) on `grid` within `radius` m of x, y.
    function hottest(grid, x, y, radius) {
        let most = 0;
        for (let j = 0; j < grid.ny; j++) {
            for (let i = 0; i < grid.nx; i++) {
                const cx = grid.x0 + (i + 0.5) * grid.cell, cy = grid.y0 + (j + 0.5) * grid.cell;
                if (Math.hypot(cx - x, cy - y) <= radius) most = Math.max(most, grid.values[j * grid.nx + i]);
            }
        }
        return most;
    }

    test('keeps its hot fallout close to ground zero on a grid over both', () => {
        const profile = [[0, 0, 10]];
        const small = {lat: 40, lon: -100}, large = {lat: 40, lon: -95.3};
        const smallSpots = landingSpots({yieldKt: 1, profile});
        const alone = depositionGrid(smallSpots, {yieldKt: 1, boundsFloor: 0.1});
        const own = hottest(alone, 0, 0, 4000);
        expect(own).toBeGreaterThan(100);

        const spots = combineBursts(small, [
            {burst: small, spots: smallSpots, yieldKt: 1, fissionFraction: 1},
            {burst: large, spots: landingSpots({yieldKt: 300, profile}), yieldKt: 300, fissionFraction: 0.5},
        ]);
        const coarse = depositionGrid(spots, {yieldKt: 1, boundsFloor: 0.1});
        expect(coarse.cell).toBeGreaterThan(1000);
        // Averaged over cells kilometers wide, the 100 R/hr fallout is gone...
        expect(hottest(coarse, 0, 0, 4000)).toBeLessThan(100);
        // ...and sharpened, it is kept.
        const sharp = sharpenGrid(coarse, spots);
        expect(hottest(sharp, 0, 0, 4000)).toBeGreaterThan(Math.max(100, own * 0.6));
        expect(hottest(sharp, 0, 0, 4000)).toBeLessThan(own * 1.2);
        // Far downwind, where only wide fallout lands, the grid is as it was.
        const [lx, ly] = offsetFrom(small, large);
        const k = Math.floor((ly + 200000 - coarse.y0) / coarse.cell) * coarse.nx
            + Math.floor((lx - coarse.x0) / coarse.cell);
        expect(coarse.values[k]).toBeGreaterThan(0);
        expect(sharp.values[k]).toBe(coarse.values[k]);
    });
});

