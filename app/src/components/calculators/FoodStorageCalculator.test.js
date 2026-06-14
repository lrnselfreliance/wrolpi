import {adultEquivalents, amountNeeded, convertAmounts, DEFAULT_SHARES, formatMonths, totalPeople} from "./FoodStorageCalculator";

describe('convertAmounts', () => {
    test('converts lb to kg and back, preserving blanks', () => {
        const lb = {grains: '300', aux: ''};
        const kg = convertAmounts(lb, true);
        expect(Number(kg.grains)).toBeCloseTo(136.08, 1);  // 300 lb -> ~136 kg
        expect(kg.aux).toBe('');
        const back = convertAmounts(kg, false);
        expect(Number(back.grains)).toBeCloseTo(300, 0);
    });
});

describe('adultEquivalents', () => {
    test('weights women and children below an adult man', () => {
        // 1 man (100%) + 1 woman (77%) + 1 child (69%) = 2.46 adult-equivalents.
        expect(adultEquivalents({men: '1', women: '1', children: '1'}, DEFAULT_SHARES)).toBeCloseTo(2.46, 5);
    });
    test('a household of adult men equals the head count', () => {
        expect(adultEquivalents({men: '3', women: '', children: ''}, DEFAULT_SHARES)).toBe(3);
    });
    test('custom shares are respected', () => {
        expect(adultEquivalents({men: '0', women: '2', children: '0'}, {men: 100, women: 50, children: 69}))
            .toBeCloseTo(1, 5);
    });
});

describe('totalPeople', () => {
    test('sums men, women, and children', () => {
        expect(totalPeople({men: '2', women: '1', children: '3'})).toBe(6);
    });
    test('ignores blank/negative counts', () => {
        expect(totalPeople({men: '1', women: '', children: '-2'})).toBe(1);
    });
});

describe('amountNeeded', () => {
    test('scales per-person-per-year by people and duration (one man, one year)', () => {
        expect(amountNeeded(300, 1, 12)).toBe(300);   // grains, 1 man, 1 year
    });
    test('scales by household and partial year', () => {
        expect(amountNeeded(300, 4, 6)).toBe(600);     // 300 * 4 people * 0.5 year
    });
    test('zero for impossible inputs', () => {
        expect(amountNeeded(0, 4, 12)).toBe(0);
        expect(amountNeeded(300, 0, 12)).toBe(0);
        expect(amountNeeded(300, 4, 0)).toBe(0);
    });
});

describe('formatMonths', () => {
    test('whole years read as years', () => {
        expect(formatMonths(12)).toBe('1 year');
        expect(formatMonths(24)).toBe('2 years');
    });
    test('otherwise months', () => {
        expect(formatMonths(3)).toBe('3 months');
        expect(formatMonths(1)).toBe('1 month');
    });
});
