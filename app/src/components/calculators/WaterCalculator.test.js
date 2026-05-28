import {
    CONTAINERS,
    containersNeeded,
    dailyDemand,
    DURATION_STOPS,
    formatDuration,
    totalWater,
    WATER_PRESETS,
    waterWeight,
} from "./WaterCalculator";

describe('dailyDemand', () => {
    test('sums each category count times its rate', () => {
        // 2 men * 1 + 1 woman * 0.9 + 3 children * 0.5 = 2 + 0.9 + 1.5 = 4.4
        const demand = dailyDemand({men: 2, women: 1, children: 3}, {men: 1, women: 0.9, children: 0.5});
        expect(demand).toBeCloseTo(4.4, 5);
    });

    test('includes the pregnant/nursing category', () => {
        // 1 man * 1 + 1 pregnant * 1.6 = 2.6
        const demand = dailyDemand({men: 1, women: 0, children: 0, pregnant: 1},
            {men: 1, women: 0.9, children: 0.8, pregnant: 1.6});
        expect(demand).toBeCloseTo(2.6, 5);
    });

    test('ignores blank, zero, and negative counts/rates', () => {
        expect(dailyDemand({men: '', women: 0, children: -2}, {men: 1, women: 1, children: 1})).toBe(0);
        // A category with a count but no rate contributes nothing.
        expect(dailyDemand({men: 5, women: 1, children: 0}, {men: '', women: 2, children: 5})).toBe(2);
    });

    test('handles string inputs from form fields', () => {
        expect(dailyDemand({men: '1', women: '1', children: ''}, {men: '1.0', women: '0.9', children: '0.6'}))
            .toBeCloseTo(1.9, 5);
    });
});

describe('totalWater', () => {
    test('multiplies daily demand by the number of days', () => {
        expect(totalWater(4, 14)).toBe(56);
    });

    test('returns null when demand or days is not positive', () => {
        expect(totalWater(0, 14)).toBeNull();
        expect(totalWater(4, 0)).toBeNull();
        expect(totalWater(NaN, 14)).toBeNull();
    });
});

describe('containersNeeded', () => {
    test('rounds up to a whole number of containers and reports the spare capacity', () => {
        // 56 gallons into 5-gallon buckets -> 12 buckets (60 gal), 4 gal spare.
        expect(containersNeeded(56, 5)).toEqual({count: 12, leftover: 4});
    });

    test('an exact fit has no leftover', () => {
        expect(containersNeeded(110, 55)).toEqual({count: 2, leftover: 0});
    });

    test('any positive volume needs at least one container', () => {
        expect(containersNeeded(0.1, 55)).toEqual({count: 1, leftover: 54.9});
    });

    test('returns null for impossible inputs', () => {
        expect(containersNeeded(0, 5)).toBeNull();
        expect(containersNeeded(10, 0)).toBeNull();
    });
});

describe('waterWeight', () => {
    test('imperial uses ~8.345 lb per gallon', () => {
        expect(waterWeight(10, false)).toBeCloseTo(83.45, 2);
    });

    test('metric uses 1 kg per liter', () => {
        expect(waterWeight(10, true)).toBe(10);
    });

    test('returns null for non-positive volume', () => {
        expect(waterWeight(0, false)).toBeNull();
    });
});

describe('formatDuration', () => {
    test('labels by the appropriate unit and groups cleanly', () => {
        expect(formatDuration(1)).toBe('1 day');
        expect(formatDuration(5)).toBe('5 days');
        expect(formatDuration(7)).toBe('7 days');
        expect(formatDuration(14)).toBe('2 weeks');
        expect(formatDuration(21)).toBe('3 weeks');
        expect(formatDuration(30)).toBe('1 month');
        expect(formatDuration(90)).toBe('3 months');
        expect(formatDuration(360)).toBe('1 year');
        expect(formatDuration(540)).toBe('18 months');
        expect(formatDuration(720)).toBe('2 years');
    });

    test('non-positive durations show an em-dash', () => {
        expect(formatDuration(0)).toBe('—');
    });

    test('every slider stop produces a label (never an awkward day count past a month)', () => {
        DURATION_STOPS.forEach(days => {
            const label = formatDuration(days);
            expect(label).not.toBe('—');
            // Beyond a month we should never show a raw "N days" label.
            if (days > 30) {
                expect(label).not.toMatch(/day/);
            }
        });
    });
});

describe('constants', () => {
    const CATEGORIES = ['men', 'women', 'children', 'pregnant'];

    test('presets define imperial and metric rates for every category', () => {
        for (const preset of Object.values(WATER_PRESETS)) {
            for (const system of [preset.imperial, preset.metric]) {
                for (const cat of CATEGORIES) {
                    expect(system[cat]).toBeGreaterThan(0);
                }
            }
        }
    });

    test('comfortable preset is wetter than the minimum for every category', () => {
        const {minimum, comfortable} = WATER_PRESETS;
        for (const cat of CATEGORIES) {
            expect(comfortable.imperial[cat]).toBeGreaterThan(minimum.imperial[cat]);
            expect(comfortable.metric[cat]).toBeGreaterThan(minimum.metric[cat]);
        }
    });

    test('pregnant/nursing rate exceeds the baseline woman rate', () => {
        for (const preset of Object.values(WATER_PRESETS)) {
            expect(preset.imperial.pregnant).toBeGreaterThan(preset.imperial.women);
            expect(preset.metric.pregnant).toBeGreaterThan(preset.metric.women);
        }
    });

    test('every container has a unique key and positive capacities', () => {
        const keys = CONTAINERS.map(c => c.key);
        expect(new Set(keys).size).toBe(keys.length);
        CONTAINERS.forEach(c => {
            expect(c.gallons).toBeGreaterThan(0);
            expect(c.liters).toBeGreaterThan(0);
        });
    });

    test('duration stops are strictly increasing and start at one day', () => {
        expect(DURATION_STOPS[0]).toBe(1);
        for (let i = 1; i < DURATION_STOPS.length; i++) {
            expect(DURATION_STOPS[i]).toBeGreaterThan(DURATION_STOPS[i - 1]);
        }
    });
});
