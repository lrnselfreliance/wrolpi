import {dailyCalorieDemand, daysOfFood, findCaloriesKey, findCountKey, totalCalories} from "./RationCalculator";

describe('findCaloriesKey', () => {
    test('detects a calories-type field', () => {
        expect(findCaloriesKey([{key: 'kcal', type: 'calories'}, {key: 'name', type: 'text'}])).toBe('kcal');
    });
    test('falls back to a legacy number field keyed "calories"', () => {
        expect(findCaloriesKey([{key: 'calories', type: 'number'}])).toBe('calories');
    });
    test('returns null when no calories field exists', () => {
        expect(findCaloriesKey([{key: 'name', type: 'text'}])).toBeNull();
    });
});

describe('findCountKey', () => {
    test('prefers a number field keyed "count"', () => {
        expect(findCountKey([{key: 'qty', type: 'number'}, {key: 'count', type: 'number'}])).toBe('count');
    });
    test('falls back to the first number field', () => {
        expect(findCountKey([{key: 'qty', type: 'number'}])).toBe('qty');
    });
    test('returns null when no number field exists', () => {
        expect(findCountKey([{key: 'name', type: 'text'}])).toBeNull();
    });
});

describe('totalCalories', () => {
    const items = [
        {calories: '1600', count: '4'},   // 6400
        {calories: '2000', count: '2'},   // 4000
        {calories: '', count: '5'},        // 0 (no calories)
        {calories: '500'},                 // 500 (count defaults to 1)
        {calories: '300', count: '0'},     // 300 (zero count treated as 1)
    ];

    test('sums calories times count', () => {
        expect(totalCalories(items, 'calories', 'count')).toBe(6400 + 4000 + 500 + 300);
    });

    test('treats every item as one unit when no count field is chosen', () => {
        expect(totalCalories(items, 'calories', null)).toBe(1600 + 2000 + 500 + 300);
    });

    test('returns 0 with no items or no calories key', () => {
        expect(totalCalories(null, 'calories', 'count')).toBe(0);
        expect(totalCalories(items, null, 'count')).toBe(0);
    });
});

describe('dailyCalorieDemand', () => {
    test('sums per-category counts times rates', () => {
        const demand = dailyCalorieDemand({men: '2', women: '1', children: '3'},
            {men: 2500, women: 2000, children: 1600});
        expect(demand).toBe(2 * 2500 + 1 * 2000 + 3 * 1600);
    });

    test('ignores blank/zero counts', () => {
        const demand = dailyCalorieDemand({men: '', women: '0', children: '1'},
            {men: 2500, women: 2000, children: 1600});
        expect(demand).toBe(1600);
    });
});

describe('daysOfFood', () => {
    test('divides total by daily demand', () => {
        expect(daysOfFood(14000, 7000)).toBe(2);
    });

    test('null for impossible inputs', () => {
        expect(daysOfFood(0, 2000)).toBeNull();
        expect(daysOfFood(14000, 0)).toBeNull();
    });
});
