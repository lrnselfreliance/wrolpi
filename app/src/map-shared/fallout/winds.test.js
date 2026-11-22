import {landingSpots} from './model.js';
import {
    fieldCovers,
    fieldWinds,
    forecastAge,
    forecastExpired,
    forecastRunsOut,
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
