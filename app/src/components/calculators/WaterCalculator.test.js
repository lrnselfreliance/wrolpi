import {
    clampNonNegative,
    computeStorage,
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

describe('daily demand including extra', () => {
    test('adds extra demand on top of per-person demand', () => {
        const base = dailyDemand({men: 2, women: 1}, {men: 1, women: 0.9});
        expect(base).toBeCloseTo(2.9, 5);

        const totalWithExtra = base + 5; // 5 extra gallons per day
        expect(totalWithExtra).toBeCloseTo(7.9, 5);
    });

    test('extra demand works when there are no people', () => {
        const base = dailyDemand({men: 0, women: 0, children: 0, pregnant: 0}, {men: 1, women: 1});
        expect(base).toBe(0);

        const totalWithExtra = base + 12;
        expect(totalWithExtra).toBe(12);
    });

    test('treats non-positive extra as zero', () => {
        const base = dailyDemand({men: 1}, {men: 2});
        expect(base + Math.max(0, Number(-3))).toBe(2);
        expect(base + Math.max(0, Number(''))).toBe(2);
    });
});

describe('totalWater', () => {
    test('returns null for non-positive inputs', () => {
        expect(totalWater(0, 14)).toBeNull();
        expect(totalWater(4, 0)).toBeNull();
        expect(totalWater(-5, 10)).toBeNull();
        expect(totalWater(10, NaN)).toBeNull();
    });

    test('computes total for valid positive inputs', () => {
        expect(totalWater(4.5, 14)).toBe(63);
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

    test('handles values very close to container boundaries (floating point)', () => {
        // Just under 2 full 5-gal buckets
        const result = containersNeeded(9.999999, 5);
        expect(result.count).toBe(2);
        expect(result.leftover).toBeCloseTo(0.000001, 5);
    });

    test('returns null for impossible inputs', () => {
        expect(containersNeeded(0, 5)).toBeNull();
        expect(containersNeeded(10, 0)).toBeNull();
        expect(containersNeeded(NaN, 5)).toBeNull();
    });
});

describe('waterWeight', () => {
    test('returns null for non-positive volume', () => {
        expect(waterWeight(0, false)).toBeNull();
        expect(waterWeight(-3, true)).toBeNull();
    });

    test('converts using standard densities', () => {
        expect(waterWeight(10, false)).toBeCloseTo(83.45, 2);
        expect(waterWeight(10, true)).toBe(10);
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

describe('data invariants (presets, containers, duration stops)', () => {
    test('pregnant/nursing rate is meaningfully higher than baseline woman rate', () => {
        for (const preset of Object.values(WATER_PRESETS)) {
            expect(preset.imperial.pregnant).toBeGreaterThan(preset.imperial.women);
            expect(preset.metric.pregnant).toBeGreaterThan(preset.metric.women);
        }
    });

    test('comfortable preset uses higher rates than minimum', () => {
        const {minimum, comfortable} = WATER_PRESETS;
        ['men', 'women', 'children', 'pregnant'].forEach(cat => {
            expect(comfortable.imperial[cat]).toBeGreaterThan(minimum.imperial[cat]);
            expect(comfortable.metric[cat]).toBeGreaterThan(minimum.metric[cat]);
        });
    });

    test('all defined containers have positive capacity in both units and unique keys', () => {
        const keys = CONTAINERS.map(c => c.key);
        expect(new Set(keys).size).toBe(keys.length);

        CONTAINERS.forEach(c => {
            expect(c.gallons).toBeGreaterThan(0);
            expect(c.liters).toBeGreaterThan(0);
        });
    });

    test('duration stops start at 1 day and are strictly increasing', () => {
        expect(DURATION_STOPS[0]).toBe(1);
        for (let i = 1; i < DURATION_STOPS.length; i++) {
            expect(DURATION_STOPS[i]).toBeGreaterThan(DURATION_STOPS[i - 1]);
        }
    });
});

describe('realistic scenarios', () => {
    test('typical family of 4 for 14 days using minimum rates + some extra', () => {
        const rates = WATER_PRESETS.minimum.imperial;
        const counts = { men: 1, women: 1, children: 2, pregnant: 0 };
        const extra = 2; // e.g. two large dogs

        const daily = dailyDemand(counts, rates) + extra;
        const total = totalWater(daily, 14);

        // 1.0 + 0.9 + 0.8*2 = 3.5 base + 2 extra = 5.5 gal/day
        expect(daily).toBeCloseTo(5.5, 5);
        expect(total).toBe(77);

        const buckets = containersNeeded(total, 5);
        expect(buckets.count).toBe(16);   // 16 × 5 gal = 80 gal capacity
        expect(buckets.leftover).toBeCloseTo(3, 5);
    });

    test('large household for 90 days in metric using comfortable preset', () => {
        const rates = WATER_PRESETS.comfortable.metric;
        const counts = { men: 2, women: 2, children: 3, pregnant: 1 };

        const daily = dailyDemand(counts, rates);
        const totalLiters = totalWater(daily, 90);

        expect(daily).toBeGreaterThan(30);
        expect(totalLiters).toBeGreaterThan(2700);

        const ibcTotes = containersNeeded(totalLiters, 1041);
        expect(ibcTotes.count).toBeGreaterThanOrEqual(3);
    });
});

describe('realistic user lifecycle', () => {
    test('user changes multiple inputs over time and outputs update correctly', () => {
        // Start: Imperial, Minimum preset, 1 man + 1 woman, 14 days
        let state = {
            metric: false,
            preset: 'minimum',
            counts: { men: '1', women: '1', children: '', pregnant: '' },
            extra: '',
            rates: { ...WATER_PRESETS.minimum.imperial },
            days: 14,
        };

        let outputs = computeStorage(state);
        expect(outputs.daily).toBeCloseTo(1.9, 5);           // 1.0 + 0.9
        expect(outputs.total).toBeCloseTo(26.6, 5);
        expect(outputs.bucket.count).toBe(6);                 // 5-gal buckets

        // User switches to Metric
        state = { ...state, metric: true, rates: { ...WATER_PRESETS.minimum.metric } };
        outputs = computeStorage(state);
        expect(outputs.daily).toBeCloseTo(7.2, 5);           // 3.8 + 3.4 in liters
        expect(outputs.weight).toBeCloseTo(100.8, 5);        // 14 days * 7.2 L ≈ 100.8 kg

        // User adds a child
        state.counts = { ...state.counts, children: '1' };
        outputs = computeStorage(state);
        expect(outputs.daily).toBeCloseTo(10.2, 5);          // +3.0 for child

        // User manually edits the men's rate upward (simulating typing)
        state.rates = { ...state.rates, men: clampNonNegative('5.5') };
        outputs = computeStorage(state);
        // 5.5 (men) + 3.4 (women) + 3.0 (child) = 11.9 base
        expect(outputs.daily).toBeCloseTo(11.9, 5);

        // User adds some extra demand for a dog
        state.extra = clampNonNegative('3');
        outputs = computeStorage(state);
        expect(outputs.daily).toBeCloseTo(14.9, 5);          // 11.9 + 3

        // User changes duration to 90 days via slider
        state.days = 90;
        outputs = computeStorage(state);
        expect(outputs.total).toBeCloseTo(1341, 5);   // 14.9 * 90

        // User switches preset to Comfortable (this would normally reset rates in the component)
        state = {
            ...state,
            preset: 'comfortable',
            rates: { ...WATER_PRESETS.comfortable.metric },
        };
        outputs = computeStorage(state);
        // Comfortable rates are higher, so daily should jump even with same counts + extra
        expect(outputs.daily).toBeGreaterThan(20);

        // Final sanity: still using metric, total water is now quite large
        expect(outputs.total).toBeGreaterThan(1800);
        expect(outputs.ibc.count).toBeGreaterThanOrEqual(2);
    });
});
