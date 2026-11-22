import {forecastAge, forecastExpired, forecastProfile, nearestHour, rainAhead} from './winds.js';

const forecast = {
    lat: 61, lon: -149, elevation: 600, fetched_at: '2026-11-22T00:30:00+00:00',
    hours: [
        {time: '2026-11-22T00:00Z', precipitation: 0, winds: [[610, 2, 180], [1500, 10, 270]]},
        {time: '2026-11-22T01:00Z', precipitation: 1.2, winds: [[610, 3, 90], [1500, 12, 0]]},
        {time: '2026-11-22T02:00Z', precipitation: 0.5, winds: [[610, 4, 0], [1500, 14, 45]]},
    ],
};

describe('a forecast of the winds aloft', () => {
    test('gives the hour nearest a time', () => {
        expect(nearestHour(forecast, new Date('2026-11-22T00:20Z'))).toBe(0);
        expect(nearestHour(forecast, new Date('2026-11-22T00:40Z'))).toBe(1);
        expect(nearestHour(forecast, new Date('2026-11-23T00:00Z'))).toBe(2);
    });

    test('gives an hour\'s winds as heights above ground zero, blowing where the wind goes', () => {
        const [low, high] = forecastProfile(forecast.hours[0], 100);
        // From the south at 2 m/s, 510 m above a ground zero 100 m above sea level: blowing north.
        expect(low[0]).toBe(510);
        expect(low[1]).toBeCloseTo(0, 10);
        expect(low[2]).toBeCloseTo(2, 10);
        // From the west at 10 m/s: blowing east.
        expect(high[0]).toBe(1400);
        expect(high[1]).toBeCloseTo(10, 10);
        expect(high[2]).toBeCloseTo(0, 10);
    });

    test('keeps a wind below ground zero, for ground lower still', () => {
        expect(forecastProfile(forecast.hours[0], 1000)[0][0]).toBe(-390);
    });

    test('adds up the rain ahead', () => {
        expect(rainAhead(forecast, 0, 2)).toBeCloseTo(1.2, 10);
        expect(rainAhead(forecast, 1)).toBeCloseTo(1.7, 10);
    });

    test('knows how old it is, and when it runs out', () => {
        expect(forecastAge(forecast, new Date('2026-11-22T03:30Z'))).toBeCloseTo(3, 10);
        expect(forecastExpired(forecast, new Date('2026-11-22T01:00Z'))).toBe(false);
        expect(forecastExpired(forecast, new Date('2026-11-22T03:00Z'))).toBe(true);
    });
});
