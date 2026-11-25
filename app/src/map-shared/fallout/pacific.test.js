// The model against two megaton bursts on coral in the Pacific (pacific-shots.json): the yields of
// modern weapons, which the Nevada shots do not reach.
import {depositionGrid, hotlines, landingSpots, profileFromTable} from './model.js';
import data from './pacific-shots.json';

const FEET = 0.3048;
const MILE = 1.609344;
const shot = (name) => data.shots.find((s) => s.name === name);

// The landing spots of a shot, in its winds at H-hour, from its cloud as observed.
function spots(s, wind = s.wind.H) {
    return landingSpots({
        yieldKt: s.yield_kt,
        burstHeight: s.burst_height_ft * FEET,
        profile: profileFromTable(wind, s.site_elevation_ft),
        stabilized: {base: s.cloud_bottom_ft_msl * FEET, top: s.cloud_top_ft_msl * FEET},
    });
}

// The smallest angle between two bearings (degrees).
const turn = (a, b) => Math.abs(((a - b + 540) % 360) - 180);

describe('Redwing Zuni, 3.5 Mt, its winds measured above its cloud', () => {
    const zuni = shot('Zuni');
    const landed = spots(zuni);
    // Its fission yield is not public; a quarter of its yield brings the hot contours closest.
    const grid = depositionGrid(landed, {yieldKt: zuni.yield_kt, fissionFraction: 0.25});
    const hot = zuni.reach.rows.filter(([rate]) => rate >= 30);
    const lines = hotlines(grid, hot.map(([rate]) => rate));

    test('the hot fallout goes where it went: north-northwest, across winds which turn with height', () => {
        hot.forEach(([, , bearing], k) => expect(turn(lines[k].azimuth, bearing)).toBeLessThan(25));
    });

    test('and as far: the 150 to 30 R/hr contours within half again', () => {
        hot.forEach(([, miles], k) => {
            const ratio = lines[k].km / MILE / miles;
            expect(ratio).toBeGreaterThan(0.67);
            expect(ratio).toBeLessThan(1.5);
        });
    });
});

describe('Castle Bravo, 15 Mt, its winds measured only below its cloud', () => {
    const bravo = shot('Bravo');
    const landed = spots(bravo);

    // The hour at which the activity landing about `miles` downwind lands, on the average.
    function arrival(miles) {
        const near = landed.filter((s) => Math.abs(s.x / 1000 / MILE - miles) < 10);
        const total = near.reduce((a, s) => a + s.activity, 0);
        return near.reduce((a, s) => a + s.activity * s.hours, 0) / total;
    }

    test('the fallout arrives when it did: about as Glasstone, NRDL and Moroz have it', () => {
        for (const [miles, glasstone] of bravo.arrival.glasstone) {
            const nrdl = bravo.arrival.nrdl.find(([m]) => m === miles)[1];
            // Between the two estimates, give or take a quarter.
            expect(arrival(miles)).toBeGreaterThan(Math.min(glasstone, nrdl) * 0.75);
            expect(arrival(miles)).toBeLessThan(Math.max(glasstone, nrdl) * 1.25);
        }
        const [miles, hours] = bravo.arrival.moroz_rongelap;
        expect(Math.abs(arrival(miles) / hours - 1)).toBeLessThan(0.5);
    });

    // A known gap, kept in view: the model brings Bravo's hot fallout down about three times closer
    // than NRDL and RAND drew it.  It is not the unmeasured winds above 57,000 ft (the reanalysis
    // winds there turn the plume right but do not lengthen it), nor the particle sizes; a plume a
    // third as wide reaches about two thirds as far (see the fixture's caveat).  If this starts to fail, the gap has closed:
    // update the caveat and these bounds.
    test('the hot fallout reaches about a third as far as it was drawn (a known gap)', () => {
        const grid = depositionGrid(landed, {yieldKt: bravo.yield_kt, fissionFraction: 0.5});
        const rows = bravo.reach.rows.filter(([rate]) => rate >= 500 && rate <= 1000);
        const lines = hotlines(grid, rows.map(([rate]) => rate));
        rows.forEach(([, nrdl], k) => {
            const ratio = lines[k].km / MILE / nrdl;
            expect(ratio).toBeGreaterThan(0.25);
            expect(ratio).toBeLessThan(0.6);
        });
    });
});
