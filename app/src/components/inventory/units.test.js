import {convert, countByWeight, formatTotals, sumQuantities} from "./units";

describe('countByWeight', () => {
    test('divides total by unit weight and rounds to a whole number', () => {
        expect(countByWeight('1000', 'g', '5', 'g')).toBe(200);
        // 403.7 nails -> 404 (rounded to a whole number).
        expect(countByWeight('1009.25', 'g', '2.5', 'g')).toBe(404);
    });

    test('converts mismatched units before dividing', () => {
        expect(countByWeight('2', 'kg', '5', 'g')).toBe(400);   // 2 kg / 5 g
        expect(countByWeight('1', 'lb', '1', 'oz')).toBe(16);
    });

    test('a sub-unit or zero total yields a count of 0 (not null)', () => {
        expect(countByWeight('1', 'g', '5', 'g')).toBe(0);    // round(0.2) = 0
        expect(countByWeight('0', 'g', '5', 'g')).toBe(0);
    });

    test('returns null when a weight is missing, zero, or incompatible', () => {
        expect(countByWeight('', 'g', '5', 'g')).toBeNull();
        expect(countByWeight('1000', 'g', '', 'g')).toBeNull();
        expect(countByWeight('1000', 'g', '0', 'g')).toBeNull();
        expect(countByWeight('1000', 'lb', '5', 'gallon')).toBeNull();   // incompatible dimensions
    });

    test('refuses to divide when only one side has a unit', () => {
        expect(countByWeight('2', '', '1', 'oz')).toBeNull();
        expect(countByWeight('2', 'oz', '1', '')).toBeNull();
        // Both unitless divides the raw magnitudes.
        expect(countByWeight('100', '', '4', '')).toBe(25);
    });
});

describe('convert', () => {
    test('converts within mass', () => {
        expect(convert(16, 'oz', 'lb')).toBeCloseTo(1, 5);
        expect(convert(2000, 'lb', 'ton')).toBeCloseTo(1, 5);
    });

    test('converts within volume', () => {
        expect(convert(1, 'gallon', 'quart')).toBeCloseTo(4, 5);
    });

    test('returns null for incompatible or unparseable units', () => {
        expect(convert(1, 'lb', 'gallon')).toBeNull();
        expect(convert(1, 'each', 'lb')).toBeNull();
        expect(convert('', 'lb', 'oz')).toBeNull();
    });
});

describe('sumQuantities', () => {
    test('sums compatible units and compacts', () => {
        const result = sumQuantities([
            {value: '16', unit: 'oz'},
            {value: '1', unit: 'lb'},
        ]);
        expect(result.totals).toHaveLength(1);
        expect(result.totals[0].unit).toBe('lb');
        expect(result.totals[0].magnitude).toBeCloseTo(2, 5);
        expect(result.unitlessCount).toBeNull();
    });

    test('compacts pounds to tons past the threshold', () => {
        const result = sumQuantities([{value: '2000', unit: 'lb'}]);
        expect(result.totals[0].unit).toBe('ton');
        expect(result.totals[0].magnitude).toBeCloseTo(1, 5);
    });

    test('keeps incompatible dimensions in separate buckets', () => {
        const result = sumQuantities([
            {value: '1', unit: 'lb'},
            {value: '1', unit: 'gallon'},
        ]);
        expect(result.totals).toHaveLength(2);
        const unitNames = result.totals.map(t => t.unit).sort();
        expect(unitNames).toEqual(['gallon', 'lb']);
    });

    test('counts unitless / non-standard-unit entries separately', () => {
        const result = sumQuantities([
            {value: '5', unit: 'each'},
            {value: '3', unit: ''},
            {value: '1', unit: 'lb'},
        ]);
        expect(result.unitlessCount).toBeCloseTo(8, 5);
        expect(result.totals).toHaveLength(1);
        expect(result.totals[0].unit).toBe('lb');
    });
});

describe('formatTotals', () => {
    test('joins totals and unitless count', () => {
        const summed = {totals: [{magnitude: 1.5, unit: 'lb'}, {magnitude: 2, unit: 'gallon'}], unitlessCount: 3};
        expect(formatTotals(summed)).toBe('1.5 lb + 2 gallon + 3 unitless');
    });

    test('em-dash when empty', () => {
        expect(formatTotals({totals: [], unitlessCount: null})).toBe('—');
    });
});
