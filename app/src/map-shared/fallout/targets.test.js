import {combineBursts, CUSTOM_WEAPON, DEFAULT_WEAPON, middleOf, offsetFrom, targetWeapon} from './targets.js';
import {depositionGrid, landingSpots, SOURCE_NORMALIZATION} from './model.js';

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
        expect(middleOf([{lat: 0, lon: 0}, {lat: 2, lon: 4}])).toEqual({lat: 1, lon: 2});
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
