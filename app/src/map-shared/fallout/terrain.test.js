import {decodeGrid, elevationAt, terrainAround} from './terrain.js';
import {landingSpots, stabilizedCloud} from './model.js';
import {meanError, runShot} from './validation.js';
import shots from './nts-shots.json';
import ntsTerrain from './nts-terrain.json';

// A grid from plain values (row by row from the south), in its compact form.
function encode(values, nx, ny, west = -1, south = -1, step = 0.5) {
    const bytes = new Uint8Array(values.length * 2);
    const view = new DataView(bytes.buffer);
    values.forEach((v, i) => view.setInt16(i * 2, v, true));
    return {west, south, step, nx, ny, meters_int16_le_base64: btoa(String.fromCharCode(...bytes))};
}

describe('an elevation grid', () => {
    const grid = decodeGrid(encode([0, 100, 200, 300], 2, 2));

    test('is decoded as it was written', () => {
        expect(Array.from(grid.values)).toEqual([0, 100, 200, 300]);
    });

    test('is read between its samples, and as the nearest edge beyond them', () => {
        expect(elevationAt(grid, -1, -1)).toBe(0);
        expect(elevationAt(grid, -0.75, -1)).toBe(50);
        expect(elevationAt(grid, -0.75, -0.75)).toBe(150);
        expect(elevationAt(grid, 10, 10)).toBe(300);
    });

    test('around a burst, is the height above the ground at ground zero', () => {
        const terrain = terrainAround(grid, -1, -1);
        expect(terrain.elevation).toBe(0);
        expect(terrain.ground(0, 0)).toBe(0);
        // Half a step (0.25 degrees) north is 100 m up.
        expect(terrain.ground(0, 0.25 * 111320)).toBeCloseTo(100, 0);
        expect(terrain.lowest).toBe(0);
    });

    test('of the Nevada Test Site, has its shots at the elevations recorded for them', () => {
        const nts = decodeGrid(ntsTerrain);
        for (const shot of shots.shots) {
            // Within 60 m: the grid is sampled every 0.03 degrees (about 3 km).
            expect(Math.abs(elevationAt(nts, shot.lon, shot.lat) - shot.site_elevation_ft * 0.3048)).toBeLessThan(60);
        }
    });
});

describe('fallout over terrain', () => {
    const cloud = stabilizedCloud(10);
    // Blowing east at 15 m/s at every height.
    const profile = [[0, 15, 0]];
    const flat = landingSpots({cloud, profile});

    test('lands as on flat ground, when the ground is flat', () => {
        const spots = landingSpots({cloud, profile, terrain: {ground: () => 0, lowest: 0}});
        expect(spots).toEqual(flat);
    });

    // A ridge 1500 m high, from 20 to 40 km downwind.
    const ridge = {ground: (x) => (x > 20000 && x < 40000 ? 1500 : 0), lowest: 0};
    const share = (spots, test) => spots.filter((s) => test(s.x)).reduce((a, s) => a + s.activity, 0);

    test('piles up on a ridge in its way, and spares the valley behind it', () => {
        const spots = landingSpots({cloud, profile, terrain: ridge});
        const onRidge = (x) => x > 20000 && x < 40000;
        const behind = (x) => x >= 40000 && x < 80000;
        expect(share(spots, onRidge)).toBeGreaterThan(1.3 * share(flat, onRidge));
        expect(share(spots, behind)).toBeLessThan(share(flat, behind));
    });

    test('lands sooner on the ridge, having fallen less far', () => {
        const spots = landingSpots({cloud, profile, terrain: ridge});
        const hours = (list) => list.filter((s) => s.x > 20000 && s.x < 40000)
            .reduce((a, s) => a + s.activity * s.hours, 0) / share(list, (x) => x > 20000 && x < 40000);
        expect(hours(spots)).toBeLessThan(hours(flat));
    });

    test('lands further on in a valley below ground zero', () => {
        const valley = {ground: (x) => (x > 5000 ? -1000 : 0), lowest: -1000};
        const spots = landingSpots({cloud, profile, terrain: valley});
        const reach = (list) => list.reduce((a, s) => a + s.activity * s.x, 0) / list.reduce((a, s) => a + s.activity, 0);
        expect(reach(spots)).toBeGreaterThan(reach(flat));
    });

    test('of the six Nevada tests, matches them as well as on flat ground', () => {
        // Measured 2.00 with and without terrain: their close-in fallout fell on the flats where they
        // were fired, and terrain moves what fell 50 to 400 km away by 0.5 to 25 km.
        const terrain = decodeGrid(ntsTerrain);
        const results = shots.shots.map((shot) => runShot(shot, {terrain}));
        expect(meanError(results, (r) => r.transport)).toBeLessThan(2.2);
    });
});
