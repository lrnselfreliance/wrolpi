import {landingSpots, scavengingRate} from './model.js';
import {
    fieldCovers,
    fieldWinds,
    forecastAge,
    forecastCoversFallout,
    forecastExpired,
    forecastRunsOut,
    nearestAround,
    nearestHour,
    nearestPoint,
    prepareField,
    rainNear,
} from './winds.js';

const HOURS = ['2026-11-22T00:00Z', '2026-11-22T01:00Z', '2026-11-22T02:00Z'];
const START = Date.parse(HOURS[0]);

// A field over 60-62 N, 150-148 W, every degree, whose wind at every point, hour and height is given
// by `wind(lat, lon, hour)` as [speed, from].
function field(wind = () => [10, 270], {lats = [60, 61, 62], lons = [-150, -149, -148], rain = 0} = {}) {
    const points = [];
    for (const lat of lats) for (const lon of lons) points.push({lat, lon, elevation: 0});
    return {
        source: 'Open-Meteo', fetched_at: '2026-11-22T00:30:00+00:00', spacing: 1, points, hours: HOURS,
        winds: points.map(({lat, lon}) => HOURS.map((_, h) => {
            const [speed, from] = wind(lat, lon, h);
            return [[10, speed, from], [20000, speed, from]];
        })),
        rain: points.map(() => HOURS.map(() => rain)),
    };
}

// The middle of the activity of `spots` (km east, km north of ground zero).
function middle(spots) {
    let sx = 0, sy = 0, sum = 0;
    for (const s of spots) {
        sx += s.activity * s.x;
        sy += s.activity * s.y;
        sum += s.activity;
    }
    return [sx / sum / 1000, sy / sum / 1000];
}

describe('a field of winds aloft', () => {
    test('finds the hour nearest a time, how old it is, and when it runs out', () => {
        expect(nearestHour(HOURS, new Date('2026-11-22T00:20Z'))).toBe(0);
        expect(nearestHour(HOURS, new Date('2026-11-22T00:40Z'))).toBe(1);
        expect(nearestHour(HOURS, new Date('2026-11-23T00:00Z'))).toBe(2);
        const f = field();
        expect(forecastAge(f, new Date('2026-11-22T03:30Z'))).toBeCloseTo(3, 10);
        expect(forecastExpired(f, new Date('2026-11-22T01:00Z'))).toBe(false);
        expect(forecastExpired(f, new Date('2026-11-22T03:00Z'))).toBe(true);
    });

    test('knows when it ends before a burst\'s fallout is down', () => {
        const hours = Array.from({length: 72}, (_, h) => new Date(START + h * 3600000).toISOString());
        const f = {hours};
        // A burst at the first hour has its 48 hours; one at the 30th does not.
        expect(forecastRunsOut(f, 0)).toBeNull();
        expect(forecastRunsOut(f, 23)).toBeNull();
        expect(forecastRunsOut(f, 30)).toBe(Date.parse(hours[71]));
    });

    test('reads the wind as east and north; a west wind blows east', () => {
        const winds = fieldWinds(prepareField(field()), {lat0: 61, lon0: -149, startMs: START});
        const [east, north] = winds.at(0, 0, 1000, 0);
        expect(east).toBeCloseTo(10, 4);
        expect(north).toBeCloseTo(0, 4);
    });

    test('reads between the points around a place, between hours, and between heights', () => {
        // The wind gets stronger to the east, and with time.
        const prepared = prepareField(field((lat, lon, h) => [10 * (lon + 151) + h * 6, 270]));
        const winds = fieldWinds(prepared, {lat0: 61, lon0: -149, startMs: START});
        const perLon = 111320 * Math.cos(61 * Math.PI / 180);
        expect(winds.at(0, 0, 1000, 0)[0]).toBeCloseTo(20, 3);
        expect(winds.at(perLon / 2, 0, 1000, 0)[0]).toBeCloseTo(25, 3);
        expect(winds.at(0, 0, 1000, 1800)[0]).toBeCloseTo(23, 3);
        // Beyond its hours, the nearest.
        expect(winds.at(0, 0, 1000, 99 * 3600)[0]).toBeCloseTo(32, 3);

        // Calm below, windy above.
        const sheared = field();
        sheared.winds = sheared.winds.map((hours) => hours.map(() => [[0, 0, 270], [2000, 20, 270]]));
        const up = fieldWinds(prepareField(sheared), {lat0: 61, lon0: -149, groundElevation: 500, startMs: START});
        expect(up.at(0, 0, 500, 0)[0]).toBeCloseTo(10, 3);
    });

    test('knows where it reaches, and outside it uses the nearest point', () => {
        const prepared = prepareField(field((lat, lon) => [lon === -148 ? 30 : 10, 270]));
        expect(fieldCovers(prepared, 61.5, -148.5)).toBe(true);
        expect(fieldCovers(prepared, 63.5, -148.5)).toBe(false);
        expect(prepared.field.points[nearestPoint(prepared, 61.2, -147.6)]).toMatchObject({lat: 61, lon: -148});
        const winds = fieldWinds(prepared, {lat0: 61, lon0: -140, startMs: START});
        expect(winds.at(0, 0, 1000, 0)[0]).toBeCloseTo(30, 3);
        // The points which can be nearest in each cell outside it are found once, and kept.
        expect(prepared.nearCandidates.size).toBe(1);
        expect(winds.at(0, 0, 3000, 600)[0]).toBeCloseTo(30, 3);
        expect(prepared.nearCandidates.size).toBe(1);
    });

    test('finds the nearest point anywhere as quickly as it may, and the same one', () => {
        // Points 3 degrees apart, some missing, near the antimeridian and the pole.
        const points = [];
        for (let lat = 63; lat <= 87; lat += 3) {
            for (const lon of [168, 171, 174, 177, 180, -177, -174, -171]) {
                if ((lat * 7 + lon) % 5 !== 0) points.push({lat, lon: lon === 180 ? -180 : lon, elevation: 0});
            }
        }
        const prepared = prepareField({spacing: 3, points, hours: HOURS,
            winds: points.map(() => HOURS.map(() => [[10, 10, 270]])), rain: points.map(() => HOURS.map(() => 0))});
        let seed = 7;
        const random = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
        for (let i = 0; i < 5000; i++) {
            // Some carried round the world, more than once.
            const lat = 40 + 50 * random(), lon = 140 + 80 * random() - (random() < 0.5 ? 360 : 0) + 360 * Math.floor(7 * random() - 3);
            const row = Math.floor(lat / 3) + prepared.rowOffset, column = Math.floor(lon / 3);
            expect(nearestAround(prepared, row, column, lat, lon)).toBe(nearestPoint(prepared, lat, lon));
        }
        // Each cell's points looked through are kept, and are fewer than all of them.
        const kept = [...prepared.nearCandidates.values()];
        expect(Math.max(...kept.map((near) => near.length))).toBeLessThan(points.length);
    });

    test('outside it, rains as its nearest point does', () => {
        const prepared = prepareField(field(() => [10, 270], {rain: 4}));
        const winds = fieldWinds(prepared, {lat0: 61, lon0: -140, startMs: START});
        expect(winds.rainAt(0, 0, 0)[0]).toBeCloseTo(4, 6);
        expect(prepared.nearCandidates.size).toBe(1);
    });

    test('wraps at the antimeridian', () => {
        const prepared = prepareField(field((lat, lon) => [lon === 179 ? 10 : 20, 270],
            {lats: [51, 52], lons: [179, -180]}));
        expect(fieldCovers(prepared, 51.5, 179.5)).toBe(true);
        const winds = fieldWinds(prepared, {lat0: 51.5, lon0: 179.5, startMs: START});
        expect(winds.at(0, 0, 1000, 0)[0]).toBeCloseTo(15, 3);
    });

    test('reads a point\'s own wind there, and half of each between two, at spacings which do not divide 90', () => {
        for (const spacing of [4, 8]) {
            const lats = [32, 32 + spacing, 32 + 2 * spacing], lons = [-120, -120 + spacing, -120 + 2 * spacing];
            const f = field((lat, lon) => [lat + (lon + 200) / 1000, 270], {lats, lons});
            f.spacing = spacing;
            const prepared = prepareField(f);
            const at = (lat, lon) => fieldWinds(prepared, {lat0: lat, lon0: lon, startMs: START}).at(0, 0, 1000, 0)[0];
            const own = (lat, lon) => lat + (lon + 200) / 1000;
            expect(at(lats[1], lons[1])).toBeCloseTo(own(lats[1], lons[1]), 4);
            expect(at(lats[1] + spacing / 2, lons[1])).toBeCloseTo((own(lats[1], lons[1]) + own(lats[2], lons[1])) / 2, 4);
            expect(at(lats[1], lons[1] + spacing / 2)).toBeCloseTo((own(lats[1], lons[1]) + own(lats[1], lons[2])) / 2, 4);
            expect(fieldCovers(prepared, lats[1] + 1, lons[1] + 1)).toBe(true);
            expect(fieldCovers(prepared, lats[2] + 1, lons[1] + 1)).toBe(false);
        }
    });

    test('adds up the rain near a place', () => {
        expect(rainNear(prepareField(field(undefined, {rain: 0.5})), 61, -149, 1, 6)).toBeCloseTo(1, 10);
    });
});

describe('fallout in a field of winds', () => {
    test('a field of one wind lands the fallout where that wind does', () => {
        const steady = landingSpots({yieldKt: 10, profile: [[0, 10, 0]]});
        const fromField = landingSpots({
            yieldKt: 10, winds: fieldWinds(prepareField(field()), {lat0: 61, lon0: -149, startMs: START}),
        });
        const [a, b] = [middle(steady), middle(fromField)];
        expect(Math.abs(b[0] / a[0] - 1)).toBeLessThan(0.01);
        expect(Math.abs(b[1])).toBeLessThan(0.5);
    });

    test('meets the ground where that wind does, over a ridge', () => {
        // A slope from 100 km downwind up to a ridge 3 km high at 130 km: what falls below its top
        // lands on it.
        const terrain = {lowest: 0, ground: (x) => Math.min(Math.max((x - 100000) / 10, 0), 3000)};
        const steady = landingSpots({yieldKt: 10, profile: [[0, 10, 0]], terrain});
        const fromField = landingSpots({
            yieldKt: 10, terrain, winds: fieldWinds(prepareField(field()), {lat0: 61, lon0: -149, startMs: START}),
        });
        const onRidge = (spots) => spots.filter((s) => s.x > 100000 && s.x < 131000)
            .reduce((a, s) => a + s.activity, 0);
        expect(onRidge(steady)).toBeGreaterThan(0.01);
        expect(Math.abs(onRidge(fromField) / onRidge(steady) - 1)).toBeLessThan(0.1);
    });

    test('the plume turns where the wind turns', () => {
        // West winds west of 149 W, south winds east of it: fallout carried east, about 100 km, is then
        // carried north, and goes no further east.
        const turning = field((lat, lon) => [10, lon <= -149 ? 270 : 180],
            {lats: [60, 61, 62, 63, 64, 65], lons: [-151, -150, -149, -148, -147, -146]});
        const spots = landingSpots({
            yieldKt: 100, winds: fieldWinds(prepareField(turning), {lat0: 61, lon0: -150.9, startMs: START}),
        });
        const far = spots.filter((s) => Math.hypot(s.x, s.y) > 200000);
        expect(far.length).toBeGreaterThan(0);
        expect(Math.max(...far.map((s) => s.x))).toBeLessThan(160000);
        expect(middle(far)[1]).toBeGreaterThan(150);
    });

    test('the plume turns when the wind turns', () => {
        // West winds for the first hour, then south winds.
        const later = field((lat, lon, h) => [10, h === 0 ? 270 : 180], {lats: [58, 59, 60, 61, 62, 63, 64]});
        const spots = landingSpots({
            yieldKt: 100, winds: fieldWinds(prepareField(later), {lat0: 61, lon0: -149, startMs: START}),
        });
        const late = spots.filter((s) => s.hours > 3);
        expect(middle(late)[1]).toBeGreaterThan(middle(late)[0]);
    });
});

describe('rain', () => {
    // The hours for half to be taken out at a rate (per second).
    const half = (rate) => Math.LN2 / rate / 3600;

    test('takes fallout out of the air as Glasstone has it', () => {
        const cloud = [1000, 5000];
        // Inside the rain cloud, half in 0.16 hour whatever the rain.
        expect(half(scavengingRate(1, 3000, cloud))).toBeCloseTo(0.16, 6);
        expect(half(scavengingRate(20, 3000, cloud))).toBeCloseTo(0.16, 6);
        // Below it, half in 19, 3.8 and 1.9 hours of light, moderate and heavy rain.
        expect(half(scavengingRate(1.27, 500, cloud))).toBeCloseTo(19, 6);
        expect(half(scavengingRate(5.08, 500, cloud))).toBeCloseTo(3.8, 6);
        expect(half(scavengingRate(11.94, 500, cloud))).toBeCloseTo(1.9, 6);
        // Between and beyond them, more rain takes more.
        expect(scavengingRate(3, 500, cloud)).toBeGreaterThan(scavengingRate(2, 500, cloud));
        expect(scavengingRate(30, 500, cloud)).toBeGreaterThan(scavengingRate(11.94, 500, cloud));
        // Above the rain cloud, and without rain, none; where the cloud is not known, washout.
        expect(scavengingRate(10, 6000, cloud)).toBe(0);
        expect(scavengingRate(0, 3000, cloud)).toBe(0);
        expect(half(scavengingRate(5.08, 3000, null))).toBeCloseTo(3.8, 6);
    });

    // A field of west winds, rain falling from a cloud 1 to 4 km high where `raining(lat, lon)`.
    function rainy(raining, mm = 5) {
        const f = field(undefined, {lats: [59, 60, 61, 62, 63], lons: [-150, -149, -148, -147, -146, -145, -144, -143]});
        f.rain = f.points.map(({lat, lon}) => HOURS.map(() => (raining(lat, lon) ? mm : 0)));
        f.clouds = f.points.map(() => HOURS.map(() => [1000, 4000]));
        return f;
    }
    const run = (f, maxHours = 48) => landingSpots({yieldKt: 10, maxHours,
        winds: fieldWinds(prepareField(f), {lat0: 61, lon0: -149.5, startMs: START})});
    const total = (spots) => spots.reduce((a, s) => a + s.activity, 0);
    const between = (spots, x0, x1) => total(spots.filter((s) => s.x >= x0 && s.x < x1));

    test('moves fallout, but does not make or lose any', () => {
        // However long it takes to come down: without rain, the finest takes longer than 48 hours.
        const dry = run(rainy(() => false), 1e6);
        const wet = run(rainy(() => true), 1e6);
        expect(dry.some((s) => s.wet)).toBe(false);
        expect(wet.some((s) => s.wet)).toBe(true);
        expect(total(wet)).toBeCloseTo(total(dry), 10);
        // In 48 hours, rain brings down some of what would still be in the air.
        expect(total(run(rainy(() => true)))).toBeGreaterThan(total(run(rainy(() => false))));
        // Taken out on the way, it comes down sooner, and nearer.
        const reach = (spots) => spots.reduce((a, s) => a + s.activity * s.x, 0) / total(spots);
        expect(reach(wet)).toBeLessThan(reach(dry) * 0.8);
    });

    test('brings fallout down where it rains: a hot spot downwind', () => {
        // Rain at the points from 147 W to 145 W: read between the points, it falls from 148 W to
        // 144 W, about 80 to 300 km downwind.
        const dry = run(rainy(() => false));
        const band = run(rainy((lat, lon) => lon >= -147 && lon <= -145));
        const perLon = 111320 * Math.cos(61 * Math.PI / 180);
        const [x0, x1] = [(-148 + 149.5) * perLon, (-144 + 149.5) * perLon];
        expect(between(band, x0, x1)).toBeGreaterThan(between(dry, x0, x1) * 1.5);
        // Taken out on the way, less is left to come down beyond it.
        expect(between(band, x1, 1e7)).toBeLessThan(between(dry, x1, 1e7) * 0.7);
        // Upwind of the rain, nothing changes.
        expect(between(band, -1e6, x0 - 30000)).toBeCloseTo(between(dry, -1e6, x0 - 30000), 10);
    });
});


describe('a field of one hour (a past day\'s)', () => {
    // Winds which change from place to place, but not from hour to hour.
    const wind = (lat, lon) => [10 + (lat - 60) * 5 + (lon + 150) * 3, 250];
    const hours = field(wind);
    const oneHour = {...hours, hours: [HOURS[0]], winds: hours.winds.map((w) => [w[0]]), rain: hours.rain.map(() => [0])};

    test('holds its winds through the hours, as read from a field of the same winds every hour', () => {
        const held = fieldWinds(prepareField(oneHour), {lat0: 61, lon0: -149, startMs: START});
        const each = fieldWinds(prepareField(hours), {lat0: 61, lon0: -149, startMs: START});
        expect(held.held).toBe(true);
        expect(each.held).toBeUndefined();
        for (const [x, y, z] of [[0, 0, 0], [20000, -30000, 5000], [-45000, 50000, 15000], [10000, 10000, 30000]]) {
            const [e1, n1] = held.at(x, y, z, 3600);
            const [e2, n2] = each.at(x, y, z, 3600);
            expect(e1).toBeCloseTo(e2, 6);
            expect(n1).toBeCloseTo(n2, 6);
        }
        // Far past the field: the wind of its nearest point.
        const [e, n] = held.at(0, 900000, 5000, 0);
        const [speed] = wind(62, -149);
        expect(Math.hypot(e, n)).toBeCloseTo(speed, 6);
    });

    test('carries a burst\'s fallout where the full model does, with the paths kept', () => {
        const winds = fieldWinds(prepareField(oneHour), {lat0: 60.5, lon0: -149.5, startMs: START});
        for (const yieldKt of [15, 250, 1000]) {
            const held = landingSpots({yieldKt, winds});
            const full = landingSpots({yieldKt, winds: {...winds, held: false}});
            expect(held.length).toBe(full.length);
            const sum = (spots) => spots.reduce((a, s) => a + s.activity, 0);
            expect(sum(held)).toBeCloseTo(sum(full), 10);
            const [hx, hy] = middle(held), [fx, fy] = middle(full);
            const reach = Math.hypot(fx, fy);
            expect(reach).toBeGreaterThan(50);
            expect(Math.hypot(hx - fx, hy - fy) / reach).toBeLessThan(0.01);
            // Spot by spot: the winds over ground zero carry the rising cloud (which drifts about
            // 10 km) much as the winds where it is.
            const apart = Math.max(...held.map((s, i) => Math.hypot(s.x - full[i].x, s.y - full[i].y)));
            expect(apart).toBeLessThan(4000);
        }
        // Kept: a second burst of the same yield gives the same spots.
        expect(landingSpots({yieldKt: 250, winds})).toEqual(landingSpots({yieldKt: 250, winds}));
    });
});

describe('a forecast covering the fallout', () => {
    // 60 hours from START.
    const long = {hours: Array.from({length: 60}, (_, h) => new Date(START + h * 3600000).toISOString())};
    const at = (hours) => new Date(START + hours * 3600000);

    test('has the winds from now until all the fallout is down', () => {
        expect(forecastCoversFallout(long, at(0))).toBe(true);
        expect(forecastCoversFallout(long, at(11.4))).toBe(true);
        // Its last hour (59) is before the fallout of bursts at 12 is down (48 hours after).
        expect(forecastCoversFallout(long, at(12))).toBe(false);
    });

    test('has an hour near now', () => {
        expect(forecastCoversFallout(long, at(-2))).toBe(false);
        expect(forecastCoversFallout(long, at(70))).toBe(false);
        expect(forecastCoversFallout({hours: HOURS}, at(0))).toBe(false);
        expect(forecastCoversFallout(null)).toBe(false);
        expect(forecastCoversFallout({hours: []})).toBe(false);
    });
});
