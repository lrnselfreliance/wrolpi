import {WEAPON_CHOICES} from './FalloutPanel';

describe('the fallout panel\'s weapons', () => {
    test('are grouped by country, then a yield of one\'s own', () => {
        const groups = WEAPON_CHOICES.map((g) => g.group);
        expect(groups[0]).toBe('United States');
        expect(groups).toContain('Russia');
        expect(groups).toContain('Improvised nuclear device');
        expect(groups[groups.length - 1]).toBe('Other');
        expect(WEAPON_CHOICES[groups.length - 1].items.map((i) => i.value)).toEqual(['custom']);
    });

    test('each read differently, by name and yield', () => {
        const labels = WEAPON_CHOICES.flatMap((g) => g.items.map((i) => i.label));
        expect(new Set(labels).size).toBe(labels.length);
        expect(labels).toContain('B61-12 bomb, 0.3 kt');
    });

    test('say their yield', () => {
        const w88 = WEAPON_CHOICES[0].items.find((i) => i.value === 'w88');
        expect(w88.label).toBe('W88 (Trident II D5), 455 kt');
    });
});

describe('the fallout panel\'s winds', () => {
    const {windProfile, hourLabel} = require('./FalloutPanel');
    const forecast = {
        elevation: 600,
        hours: [{time: '2026-11-22T00:00Z', winds: [[610, 2, 180], [1500, 10, 270]]}],
    };

    test('take a forecast hour\'s winds, at heights above ground zero', () => {
        const profile = windProfile({wind: 'forecast', forecast, hour: 0, groundElevation: 100});
        expect(profile.map((p) => p[0])).toEqual([510, 1400]);
    });

    test('fall back to one wind at every height until there is a forecast', () => {
        const profile = windProfile({wind: 'forecast', forecast: null, direction: 270, speed: 10});
        expect(profile).toHaveLength(1);
        expect(profile[0][1]).toBeGreaterThan(0);
    });

    test('mark the hour nearest now', () => {
        expect(hourLabel('2026-11-22T00:00Z', true)).toMatch(/\(now\)$/);
        expect(hourLabel('2026-11-22T00:00Z', false)).not.toMatch(/now/);
    });
});

describe('the fallout of several bursts', () => {
    const {simulateBursts} = require('./FalloutPanel');
    const profileFor = () => [[0, 10, 0]];
    const bursts = [
        {lat: 40, lon: -105, yieldKt: 10, fissionFraction: 0.5},
        {lat: 40.5, lon: -104, yieldKt: 100, fissionFraction: 0.5},
    ];

    test('is drawn on one grid around the first burst', async () => {
        const one = await simulateBursts(bursts.slice(0, 1), {profileFor, useTerrain: false});
        const both = await simulateBursts(bursts, {profileFor, useTerrain: false});
        expect(both.origin).toBe(bursts[0]);
        const sum = (g) => g.values.reduce((a, v) => a + v, 0) * g.cell ** 2;
        expect(sum(both.grid)).toBeGreaterThan(sum(one.grid) * 5);
        expect(both.terrainStatus).toMatch(/terrain is off/);
    });

    test('stops when it is no longer wanted', async () => {
        expect(await simulateBursts(bursts, {profileFor, useTerrain: false, cancelled: () => true})).toBeNull();
    });
});

describe('the fallout image', () => {
    const {imageRows} = require('./FalloutPanel');

    test('takes each row from the grid row at its own latitude', () => {
        // A grid from 20 to 80 degrees north, around 40: a tenth of a degree a row.
        const grid = {y0: -20 * 111320, cell: 11132, ny: 600, nx: 1};
        const rows = imageRows(grid, 40, 600);
        // The top row is the grid's northernmost, the bottom its southernmost.
        expect(rows[0]).toBe(599);
        expect(rows[599]).toBe(0);
        // Halfway down the image, in Web Mercator, is well north of halfway in latitude (50 degrees).
        expect(rows[300]).toBeGreaterThan(330);
        for (let r = 1; r < 600; r++) expect(rows[r]).toBeLessThanOrEqual(rows[r - 1]);
    });

    test('is the plain grid over a small area', () => {
        const grid = {y0: -5000, cell: 100, ny: 100, nx: 1};
        const rows = imageRows(grid, 40, 100);
        expect(rows[0]).toBe(99);
        expect(Math.abs(rows[50] - 49)).toBeLessThanOrEqual(1);
    });
});
