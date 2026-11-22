import {airProperties, settlingSpeed} from './atmosphere.js';
import {
    CLOUD_PARTS,
    cloudHeights,
    contourAreas,
    depositionGrid,
    landingSpots,
    particleSizes,
    plumeBearing,
    SOURCE_NORMALIZATION,
    stabilizedCloud,
    windAt,
} from './model.js';
import {meanError, runShot} from './validation.js';
import data from './nts-shots.json';

// A profile of one wind at every height, blowing toward `toward` degrees at `speed` m/s.
function steady(toward, speed) {
    const r = toward * Math.PI / 180;
    return [[0, speed * Math.sin(r), speed * Math.cos(r)]];
}

function run(profile, yieldKt = 10) {
    const cloud = stabilizedCloud(yieldKt);
    const spots = landingSpots({cloud, profile});
    return {spots, grid: depositionGrid(spots, {yieldKt})};
}

// The distance (km) from ground zero to the middle of the activity.
function reach(grid) {
    let sx = 0, sy = 0, sum = 0;
    for (let j = 0; j < grid.ny; j++) {
        for (let i = 0; i < grid.nx; i++) {
            const v = grid.values[j * grid.nx + i];
            sx += v * (grid.x0 + (i + 0.5) * grid.cell);
            sy += v * (grid.y0 + (j + 0.5) * grid.cell);
            sum += v;
        }
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

describe('the cloud and its particles', () => {
    test('rises higher and spreads wider for a larger yield', () => {
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

describe('the cloud\'s cap, skirt and stem', () => {
    const cloud = stabilizedCloud(100);
    const heights = cloudHeights(cloud);
    const share = (test) => heights.filter((h) => test(h.z)).reduce((a, h) => a + h.weight, 0);

    test('hold all of the activity, in the shares of a surface burst', () => {
        expect(share(() => true)).toBeCloseTo(1, 10);
        expect(share((z) => z >= cloud.base)).toBeCloseTo(CLOUD_PARTS.cap, 10);
        expect(share((z) => z >= cloud.base / 2 && z < cloud.base)).toBeCloseTo(CLOUD_PARTS.skirt, 10);
        expect(share((z) => z < cloud.base / 2)).toBeCloseTo(CLOUD_PARTS.stem, 10);
        // About 90% in the head, the rest in the stem (Glasstone and Dolan 9.61).
        expect(CLOUD_PARTS.cap + CLOUD_PARTS.skirt).toBeGreaterThan(0.85);
    });

    test('narrow from the cap down to the early fireball at the ground', () => {
        const lowest = heights.reduce((a, h) => (h.z < a.z ? h : a));
        const cap = heights.find((h) => h.z > cloud.base);
        expect(cap.sigma).toBeCloseTo(cloud.radius / 2, 6);
        expect(lowest.sigma).toBeLessThan(cap.sigma / 2);
        expect(lowest.sigma).toBeGreaterThan(cloud.earlyRadius);
    });

    test('put more fallout near ground zero than the cap alone', () => {
        const profile = steady(90, 6.7);
        const near = (parts) => {
            const grid = depositionGrid(landingSpots({cloud, profile, parts}), {yieldKt: 100});
            return contourAreas(grid, [300])[0];
        };
        expect(near(CLOUD_PARTS)).toBeGreaterThan(1.2 * near({cap: 1, skirt: 0, stem: 0}));
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

describe('a burst in a steady wind', () => {
    test('puts its plume downwind', () => {
        for (const toward of [0, 90, 200, 300]) {
            const {grid} = run(steady(toward, 10));
            expect(angleBetween(plumeBearing(grid, 0.1), toward)).toBeLessThan(2);
        }
    });

    test('carries it about twice as far in twice the wind', () => {
        const ratio = reach(run(steady(90, 20)).grid) / reach(run(steady(90, 10)).grid);
        expect(ratio).toBeGreaterThan(1.8);
        expect(ratio).toBeLessThan(2.2);
    });

    test('spreads it evenly around ground zero in a calm', () => {
        const {grid} = run(steady(0, 0));
        expect(reach(grid)).toBeLessThan(grid.cell / 1000);
    });

    test('loses none of the activity which lands', () => {
        const yieldKt = 10;
        const {spots, grid} = run(steady(45, 15), yieldKt);
        const landed = spots.reduce((a, s) => a + s.activity, 0);
        const total = grid.values.reduce((a, v) => a + v, 0) * (grid.cell / 1000) ** 2;
        expect(total / (SOURCE_NORMALIZATION * yieldKt * landed)).toBeCloseTo(1, 2);
    });

    test('draws a smaller area at a higher dose rate', () => {
        const [high, low] = contourAreas(run(steady(90, 10)).grid, [10, 1]);
        expect(high).toBeGreaterThan(0);
        expect(low).toBeGreaterThan(high);
    });
});

describe('a burst in winds which turn with height', () => {
    // East at the ground, turning to north at the top of the cloud.
    const cloud = stabilizedCloud(10);
    const turning = [[0, 15, 0], [cloud.top, 0, 15]];

    test('puts its plume between them, toward the winds the activity fell through', () => {
        const bearing = plumeBearing(run(turning).grid, 0.1);
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

// Six Nevada tests (nts-shots.json).  These hold the model to what the prototype measured
// (fallout-plan.md, Validation); a change which makes it worse should fail here.
describe('the fallout measured after six Nevada tests', () => {
    const results = data.shots.map((shot) => [shot, runShot(shot)]);

    test('is matched within about a factor of two in area, given the amount of activity which landed', () => {
        // Measured 2.00.  HPAC 4.03 and 4.04 were off by 2.61 and 3.27 on the same contours, though
        // they were not given the amount which landed (see "a priori" below).
        const error = meanError(results.map(([, r]) => r), (r) => r.transport);
        expect(error).toBeLessThan(2.2);
    });

    test('is over-predicted a priori, most of all for bursts above the ground', () => {
        // The model assumes a burst on the ground.  A tower or balloon burst puts far less activity
        // on the ground nearby, which is not modeled: the map draws no fallout for an air burst.
        for (const [shot, r] of results) {
            expect(r.apriori.bias).toBeGreaterThan(1);
            if (shot.placement === 'subsurface') expect(r.apriori.error).toBeLessThan(3.5);
        }
    });

    test('is downwind on the bearing the winds aloft give, for most of the shots', () => {
        // Measured: within 6 degrees for four, 44 (Ess) and 23 (Johnie Boy) for the others.  The wind
        // is one sounding at H-hour, which is not the wind the plume met hours later and 100 miles
        // away.
        const misses = results.map(([shot, r]) => angleBetween(r.transport.bearing, shot.observed_bearing_deg));
        misses.sort((a, b) => a - b);
        expect(misses[3]).toBeLessThan(10);
        expect(misses[5]).toBeLessThan(50);
    });
});
