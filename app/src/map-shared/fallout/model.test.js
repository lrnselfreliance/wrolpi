import {airProperties, settlingSpeed} from './atmosphere.js';
import {
    activityDown,
    contourAreas,
    decayFromH1,
    depositionGrid,
    hotlines,
    landedGrid,
    landingSpots,
    particleSizes,
    plumeBearing,
    risingCloud,
    SOURCE_NORMALIZATION,
    stabilizedCloud,
    windAt,
} from './model.js';
import {meanError, runNearField, runShot} from './validation.js';
import data from './nts-shots.json';
import nearField from './near-field-shots.json';

// A profile of one wind at every height, blowing toward `toward` degrees at `speed` m/s.
function steady(toward, speed) {
    const r = toward * Math.PI / 180;
    return [[0, speed * Math.sin(r), speed * Math.cos(r)]];
}

function run(profile, yieldKt = 10) {
    const spots = landingSpots({yieldKt, profile});
    return {spots, grid: depositionGrid(spots, {yieldKt})};
}

// The distance (km) from ground zero to the middle of the activity of `spots`.
function reach(spots) {
    let sx = 0, sy = 0, sum = 0;
    for (const s of spots) {
        sx += s.activity * s.x;
        sy += s.activity * s.y;
        sum += s.activity;
    }
    return Math.hypot(sx / sum, sy / sum) / 1000;
}

function angleBetween(a, b) {
    const d = Math.abs(a - b) % 360;
    return d > 180 ? 360 - d : d;
}

describe('the air', () => {
    test('is the standard atmosphere at sea level', () => {
        const {density, viscosity} = airProperties(0);
        expect(density).toBeCloseTo(1.225, 3);
        expect(viscosity).toBeCloseTo(1.789e-5, 7);
    });

    test('a 100 um particle falls slower than Stokes speed, slowed by drag', () => {
        // Stokes: 2600 * 9.81 * (1e-4)^2 / (18 * 1.789e-5) = 0.79 m/s, at which Re is 5.4: past
        // Stokes flow, so drag holds it to about 0.57 m/s, as for 100 um quartz sand.
        const speed = settlingSpeed(100e-6, 0);
        expect(speed).toBeGreaterThan(0.5);
        expect(speed).toBeLessThan(0.65);
    });

    test('larger particles fall faster, and all fall faster in thinner air', () => {
        expect(settlingSpeed(300e-6, 0)).toBeGreaterThan(settlingSpeed(100e-6, 0));
        expect(settlingSpeed(100e-6, 10000)).toBeGreaterThan(settlingSpeed(100e-6, 0));
    });
});

describe('the cloud', () => {
    test('stabilizes higher and wider for a larger yield', () => {
        let previous = {base: 0, top: 0, radius: 0};
        for (const yieldKt of [0.1, 1, 10, 100, 1000]) {
            const cloud = stabilizedCloud(yieldKt);
            expect(cloud.top).toBeGreaterThan(cloud.base);
            expect(cloud.base).toBeGreaterThan(previous.base);
            expect(cloud.top).toBeGreaterThan(previous.top);
            expect(cloud.radius).toBeGreaterThan(previous.radius);
            previous = cloud;
        }
    });

    test('rises from the fireball to its stabilized height', () => {
        const cloud = risingCloud(10);
        expect(cloud.initialTop).toBeLessThan(cloud.base);
        expect(cloud.initialRadius).toBeLessThan(cloud.radius);
        // SIMFIC Table 1: 300 s for 1-10 kt, 280 s for 100 kt, 200 s for 1 Mt.
        expect(risingCloud(1).stop).toBeCloseTo(300, 6);
        expect(risingCloud(100).stop).toBeCloseTo(280, 6);
        expect(risingCloud(1000).stop).toBeCloseTo(200, 6);
        expect(risingCloud(10).start).toBeGreaterThan(0);
    });

    test('rises from as high as the burst was', () => {
        const ground = risingCloud(15, 0), tower = risingCloud(15, 91);
        expect(tower.initialBase - ground.initialBase).toBeCloseTo(91, 6);
        expect(tower.top - ground.top).toBeCloseTo(91, 6);
    });

    test('carries its activity on particles averaging about DELFIC\'s nominal 229 um', () => {
        const sizes = particleSizes();
        const total = sizes.reduce((a, s) => a + s.activity, 0);
        const mean = sizes.reduce((a, s) => a + s.activity * s.diameter, 0) / total;
        expect(total).toBeLessThanOrEqual(1);
        expect(total).toBeGreaterThan(0.95);
        expect(mean * 1e6).toBeGreaterThan(229 * 0.9);
        expect(mean * 1e6).toBeLessThan(229 * 1.1);
    });
});

describe('the activity which comes down', () => {
    test('is all of it for a burst on or under the ground', () => {
        expect(activityDown(10, 0)).toBe(1);
        expect(activityDown(10, -5)).toBe(1);
    });

    test('is less the higher the burst, by its height scaled to the yield', () => {
        // George: 15 kt on a 300 ft tower, 121 ft/kt^(1/3): 0.45345^(121/65) = 0.23.
        expect(activityDown(15, 300 * 0.3048)).toBeCloseTo(0.229, 2);
        expect(activityDown(15, 200)).toBeLessThan(activityDown(15, 100));
        expect(activityDown(1000, 100)).toBeGreaterThan(activityDown(1, 100));
    });
});

describe('the winds', () => {
    test('are read between the heights of the profile, and as the nearest beyond them', () => {
        const profile = [[0, 0, 0], [1000, 10, -10]];
        expect(windAt(profile, 500)).toEqual([5, -5]);
        expect(windAt(profile, -10)).toEqual([0, 0]);
        expect(windAt(profile, 5000)).toEqual([10, -10]);
    });
});

describe('particles in the rising cloud', () => {
    const cloud = risingCloud(10);
    const {spots} = run(steady(90, 10));
    const heavy = spots.filter((s) => s.diameter > 1e-3);
    const light = spots.filter((s) => s.diameter > 60e-6 && s.diameter < 150e-6);

    test('drop out low if they are heavy: the stem', () => {
        expect(heavy.length).toBeGreaterThan(0);
        expect(Math.max(...heavy.map((s) => s.highest))).toBeLessThan(cloud.base);
    });

    test('ride to the stabilized cloud if they are light', () => {
        expect(Math.min(...light.map((s) => s.highest))).toBeGreaterThan(cloud.base * 0.9);
    });

    test('land near ground zero if heavy, far downwind if light', () => {
        expect(reach(heavy)).toBeLessThan(reach(light) / 5);
    });
});

describe('a burst in a steady wind', () => {
    test('puts its plume downwind', () => {
        for (const toward of [0, 90, 200, 300]) {
            const {grid} = run(steady(toward, 10));
            expect(angleBetween(plumeBearing(grid, 0.1), toward)).toBeLessThan(2);
        }
    });

    test('carries it about twice as far in twice the wind', () => {
        const ratio = reach(run(steady(90, 20)).spots) / reach(run(steady(90, 10)).spots);
        expect(ratio).toBeGreaterThan(1.8);
        expect(ratio).toBeLessThan(2.2);
    });

    test('spreads it evenly around ground zero in a calm', () => {
        expect(reach(run(steady(0, 0)).spots)).toBeLessThan(0.01);
    });

    test('loses none of the activity which lands', () => {
        const yieldKt = 10;
        const {spots, grid} = run(steady(45, 15), yieldKt);
        const landed = spots.reduce((a, s) => a + s.activity, 0);
        const total = grid.values.reduce((a, v) => a + v, 0) * (grid.cell / 1000) ** 2;
        expect(total / (SOURCE_NORMALIZATION * yieldKt * landed)).toBeCloseTo(1, 2);
    });

    test('puts down less of it, the higher the burst', () => {
        const share = (burstHeight) => landingSpots({yieldKt: 10, burstHeight, profile: steady(90, 10)})
            .reduce((a, s) => a + s.activity, 0);
        expect(share(100)).toBeLessThan(share(0) * 0.5);
    });

    test('measures how far downwind each contour reaches, and in which direction', () => {
        const {spots} = run(steady(90, 10));
        const grid = depositionGrid(spots, {yieldKt: 10, bounds: [-50000, -50000, 150000, 50000], cellSize: 250});
        // Contours which end inside the grid: one cut off by its edge reaches only as far as that.
        const [high, low] = hotlines(grid, [100, 10]);
        expect(low.km).toBeGreaterThan(high.km);
        expect(low.km).toBeLessThan(140);
        expect(angleBetween(low.azimuth, 90)).toBeLessThan(3);
        expect(hotlines(grid, [1e9])[0]).toEqual({km: 0, azimuth: null});
    });

    test('draws a smaller area at a higher dose rate', () => {
        const [high, low] = contourAreas(run(steady(90, 10)).grid, [10, 1]);
        expect(high).toBeGreaterThan(0);
        expect(low).toBeGreaterThan(high);
    });

    test('covers only where the dose rate can reach a floor, when given one', () => {
        const {spots} = run(steady(90, 30));
        const all = depositionGrid(spots, {yieldKt: 10});
        const kept = depositionGrid(spots, {yieldKt: 10, boundsFloor: 0.01});
        expect(kept.nx * kept.cell).toBeLessThan(all.nx * all.cell);
        // What shows (0.1 R/hr and up) is all inside the smaller grid.
        const [shown, shownAll] = [contourAreas(kept, [0.1])[0], contourAreas(all, [0.1])[0]];
        expect(Math.abs(shown / shownAll - 1)).toBeLessThan(0.02);
    });

    test('of a megaton, draws a 1000 R/hr contour near ground zero', () => {
        const spots = landingSpots({yieldKt: 1000, profile: steady(90, 6.7)});
        const grid = depositionGrid(spots, {yieldKt: 1000, bounds: [-30000, -30000, 120000, 30000], cellSize: 250});
        expect(contourAreas(grid, [1000])[0]).toBeGreaterThan(10);
    });
});

describe('a burst in winds which turn with height', () => {
    test('puts its plume between them, toward the winds the activity fell through', () => {
        const top = stabilizedCloud(10).top;
        const bearing = plumeBearing(run([[0, 15, 0], [top, 0, 15]]).grid, 0.1);
        expect(bearing).toBeGreaterThan(10);
        expect(bearing).toBeLessThan(80);
    });

    test('puts the plume of a higher cloud further toward the winds higher up', () => {
        const winds = [[0, 15, 0], [20000, 0, 15]];
        const low = plumeBearing(run(winds, 1).grid, 0.1);
        const high = plumeBearing(run(winds, 1000).grid, 0.1);
        expect(low - high).toBeGreaterThan(10);
    });
});

// Close-in fallout measured after three Nevada surface bursts (near-field-shots.json): contours of
// 35 to 1000 R/hr within a few km of ground zero.  These hold the model to what was measured; a
// change which makes it worse should fail here.
describe('the close-in fallout of three surface bursts', () => {
    const results = Object.fromEntries(nearField.shots.map((shot) => [shot.name, runNearField(shot)]));

    test('of Jangle Sugar and Small Boy, is matched within about a factor of two to three', () => {
        // Measured: Sugar 2.36 in area, 1.69 in hotline length (DELFIC 1.40/1.43, WSEG-10
        // 2.14/1.64); Small Boy 1.99/1.42 (DELFIC 2.92/1.96).
        for (const name of ['Jangle Sugar', 'Small Boy']) {
            expect(results[name].area.error).toBeLessThan(2.6);
            expect(results[name].hotline.error).toBeLessThan(1.9);
        }
    });

    test('of Johnie Boy, is within a factor of four below its crater', () => {
        // Its 1000 R/hr contour (0.28 km^2) is debris thrown out of the crater, which no model
        // here has; DELFIC drew it 10 times too small, and this model draws none.  The 100 and 50
        // R/hr contours were measured 3.7 and 3.8 times too big.
        const r = results['Johnie Boy'];
        const observed = nearField.shots.find((s) => s.name === 'Johnie Boy').contours.observed.area_km2;
        for (const i of [1, 2]) {
            expect(r.area.values[i] / observed[i]).toBeLessThan(4.2);
            expect(r.area.values[i] / observed[i]).toBeGreaterThan(1);
        }
    });

    test('lies in the direction measured', () => {
        // Measured: within 9 degrees for every contour but Small Boy's two highest (47 and 29).
        for (const r of Object.values(results)) {
            const shot = nearField.shots.find((s) => s.name === r.name);
            r.azimuth.forEach((azimuth, i) => {
                if (azimuth === null || shot.contours.rates[i] >= 500) return;
                expect(angleBetween(azimuth, shot.contours.observed.azimuth[i])).toBeLessThan(12);
            });
        }
    });
});

// Six Nevada tests (nts-shots.json), measured out to hundreds of km.
describe('the fallout measured after six Nevada tests', () => {
    const results = data.shots.map((shot) => [shot, runShot(shot)]);

    test('is matched within about a factor of two in area, given the amount of activity which landed', () => {
        // Measured 1.92.  HPAC 4.03 and 4.04 were off by 2.61 and 3.27 on the same contours, though
        // they were not given the amount which landed.
        const error = meanError(results.map(([, r]) => r), (r) => r.transport);
        expect(error).toBeLessThan(2.1);
    });

    test('is over-predicted a priori by a factor of about four', () => {
        // Measured 4.18 (George 4.8, Ess 5.0, Zucchini 7.9, Priscilla 3.9, Smoky 1.9, Johnie Boy 3.8),
        // every shot too high.  Without SIMFIC's height-of-burst factor it was 8.9.
        const error = meanError(results.map(([, r]) => r), (r) => r.apriori);
        expect(error).toBeLessThan(4.6);
        for (const [, r] of results) expect(r.apriori.bias).toBeGreaterThan(1);
    });

    test('is downwind on the bearing the winds aloft give, for most of the shots', () => {
        // Measured: within 8 degrees for four, 43 (Ess) and 24 (Johnie Boy) for the others.  The wind
        // is one sounding at H-hour, which is not the wind the plume met hours later and 100 miles
        // away.
        const misses = results.map(([shot, r]) => angleBetween(r.transport.bearing, shot.observed_bearing_deg));
        misses.sort((a, b) => a - b);
        expect(misses[3]).toBeLessThan(10);
        expect(misses[5]).toBeLessThan(50);
    });
});

describe('fallout hour by hour', () => {
    const spots = landingSpots({yieldKt: 10, profile: steady(90, 10)});
    const all = depositionGrid(spots, {yieldKt: 10, boundsFloor: 0.1});
    const sum = (grid) => grid.values.reduce((a, v) => a + v, 0);

    test('decays as t^-1.2 from H+1', () => {
        expect(decayFromH1(1)).toBe(1);
        // The 7-10 rule: seven times later, about a tenth.
        expect(decayFromH1(7)).toBeCloseTo(0.097, 3);
    });

    test('shows only what has landed, on the same cells, as strong as it is then', () => {
        const early = landedGrid(spots, all, 1, {yieldKt: 10});
        const late = landedGrid(spots, all, 48, {yieldKt: 10});
        for (const grid of [early, late]) {
            expect([grid.x0, grid.y0, grid.cell, grid.nx, grid.ny]).toEqual([all.x0, all.y0, all.cell, all.nx, all.ny]);
        }
        // By an hour, the fallout close in has landed, and not the far: less than all of it.
        const landedSoon = spots.filter((s) => s.hours <= 1).reduce((a, s) => a + s.activity, 0);
        const landed = spots.reduce((a, s) => a + s.activity, 0);
        expect(landedSoon / landed).toBeGreaterThan(0.2);
        expect(landedSoon / landed).toBeLessThan(0.95);
        // The far end of the plume is still empty an hour in.
        const far = (grid) => {
            let v = 0;
            for (let j = 0; j < grid.ny; j++) v += grid.values[j * grid.nx + grid.nx - 3];
            return v;
        };
        expect(far(all)).toBeGreaterThan(0);
        expect(far(early)).toBe(0);
        // Two days in, everything that lands is down, at 48^-1.2 of its H+1 rate (sharpening only adds).
        expect(sum(late)).toBeGreaterThanOrEqual(sum(all) * decayFromH1(48) * 0.999);
        expect(sum(late)).toBeLessThan(sum(all) * decayFromH1(48) * 1.2);
    });
});

