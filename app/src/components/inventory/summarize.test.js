import {
    defaultGroupKey, defaultSumKey, findCaloriesKey, findCountKey, findNameKey, groupFieldsOf, planSupplyPurchase,
    sortSummaryRows, summableFieldsOf, summarizeInventory,
} from "./summarize";

const FIELDS = [
    {key: 'name', label: 'Name', type: 'text', order: 0},
    {key: 'category', label: 'Category', type: 'select', order: 1},
    {key: 'item_size', label: 'Size', type: 'quantity', unit: 'lb', order: 2},
    {key: 'count', label: 'Count', type: 'number', order: 3},
    {key: 'calories', label: 'kcal', type: 'calories', order: 4},
];

const ITEMS = [
    {id: 1, name: 'White Rice', category: 'grains', item_size: '30', item_size_unit: 'lb', count: '3', calories: '100'},
    {id: 2, name: 'Oats', category: 'grains', item_size: '10', item_size_unit: 'lb', count: '2', calories: '50'},
    {id: 3, name: 'Beans', category: 'legumes', item_size: '25', item_size_unit: 'lb', count: '1', calories: '0'},
];

describe('field-role helpers', () => {
    test('groupFieldsOf picks categorical (text/select/location) fields', () => {
        expect(groupFieldsOf(FIELDS).map(f => f.key)).toEqual(['name', 'category']);
    });

    test('summableFieldsOf includes quantity, number, and calories fields', () => {
        expect(summableFieldsOf(FIELDS).map(f => f.key)).toEqual(['item_size', 'count', 'calories']);
    });

    test('defaults: group by Category, sum the first quantity field', () => {
        expect(defaultGroupKey(FIELDS)).toBe('category');
        expect(defaultSumKey(FIELDS)).toBe('item_size');
    });

    test('defaultGroupKey falls back to the first group field when no Category', () => {
        const noCat = [{key: 'fuel_type', label: 'Fuel', type: 'select', order: 0}];
        expect(defaultGroupKey(noCat)).toBe('fuel_type');
    });

    test('defaultSumKey falls back to a number field when there is no quantity field', () => {
        const noQty = [{key: 'qty', label: 'Qty', type: 'number', order: 0}];
        expect(defaultSumKey(noQty)).toBe('qty');
    });

    test('findCaloriesKey / findCountKey detect by type/key', () => {
        expect(findCaloriesKey(FIELDS)).toBe('calories');
        expect(findCountKey(FIELDS)).toBe('count');
    });

    test('findNameKey prefers a "name" field, else the first text field', () => {
        expect(findNameKey(FIELDS)).toBe('name');
        expect(findNameKey([{key: 'label', type: 'text'}, {key: 'note', type: 'text'}])).toBe('label');
        expect(findNameKey([{key: 'qty', type: 'number'}])).toBe(null);
    });
});

describe('planSupplyPurchase', () => {
    const opts = (scale) => ({countKey: 'count', nameKey: 'name', caloriesKey: 'calories', scale});

    test('the canonical example: 100 cans lasting 2 months, extend to 3 → buy 50 more', () => {
        const items = [{name: 'Beans', count: '100', calories: '370'}];
        const {rows} = planSupplyPurchase(items, opts(3 / 2));
        expect(rows).toEqual([{name: 'Beans', current: 100, target: 150, additional: 50}]);
    });

    test('rounds a split package UP to a whole one', () => {
        // One 50 lb bucket extrapolating to ~1.6 buckets → recommend buying 1 (not 0).
        const items = [{name: 'Wheat', count: '1', calories: '7500'}];
        expect(planSupplyPurchase(items, opts(1.6)).rows).toEqual(
            [{name: 'Wheat', current: 1, target: 2, additional: 1}]);
        // Even a small fraction rounds up.
        expect(planSupplyPurchase(items, opts(1.05)).rows[0].additional).toBe(1);
    });

    test('scales every item proportionally (balanced restock) and reports added calories', () => {
        const items = [
            {name: 'Rice', count: '14', calories: '8040'},
            {name: 'Beans', count: '96', calories: '370'},
            {name: 'Salt', count: '6', calories: '0'},   // zero-calorie items still scale
        ];
        const {rows, addedCalories} = planSupplyPurchase(items, opts(1.25));
        const byName = Object.fromEntries(rows.map(r => [r.name, r]));
        expect(byName.Rice.additional).toBe(4);    // ceil(14×1.25)=18
        expect(byName.Beans.additional).toBe(24);  // ceil(96×1.25)=120
        expect(byName.Salt.additional).toBe(2);    // ceil(6×1.25)=8, still listed
        // Added calories ignore the zero-calorie salt: 8040×4 + 370×24.
        expect(addedCalories).toBe(8040 * 4 + 370 * 24);
        // Sorted by largest purchase first.
        expect(rows.map(r => r.name)).toEqual(['Beans', 'Rice', 'Salt']);
    });

    test('a scale of 1 or less yields no purchases', () => {
        const items = [{name: 'Rice', count: '14', calories: '8040'}];
        expect(planSupplyPurchase(items, opts(1)).rows).toEqual([]);
        expect(planSupplyPurchase(items, opts(0.5)).rows).toEqual([]);
    });

    test('items with no positive count are skipped (no basis to scale)', () => {
        const items = [{name: 'Mystery', count: '', calories: '500'}, {name: 'Rice', count: '0', calories: '8040'}];
        expect(planSupplyPurchase(items, opts(2)).rows).toEqual([]);
    });
});

describe('summarizeInventory', () => {
    test('quantity sum is count-aware and unit-compacted, with grouped calories', () => {
        const rows = summarizeInventory(ITEMS, {
            fields: FIELDS, groupKey: 'category', sumKey: 'item_size', countKey: 'count', caloriesKey: 'calories',
        });
        expect(rows.map(r => r.name)).toEqual(['grains', 'legumes']);

        const grains = rows.find(r => r.name === 'grains');
        expect(grains.count).toBe(2);
        expect(grains.total).toBe('110 lb');   // 30×3 + 10×2
        expect(grains.calories).toBe(400);      // 100×3 + 50×2

        const legumes = rows.find(r => r.name === 'legumes');
        expect(legumes.total).toBe('25 lb');    // 25×1
        expect(legumes.calories).toBe(0);
    });

    test('number sum is a plain column total (NOT multiplied by count)', () => {
        const rows = summarizeInventory(ITEMS, {
            fields: FIELDS, groupKey: 'category', sumKey: 'count', countKey: 'count',
        });
        expect(rows.find(r => r.name === 'grains').total).toBe('5');   // 3 + 2
        expect(rows.find(r => r.name === 'legumes').total).toBe('1');
    });

    test('calories sum is a plain column total of the per-unit values', () => {
        const rows = summarizeInventory(ITEMS, {
            fields: FIELDS, groupKey: 'category', sumKey: 'calories', countKey: 'count',
        });
        expect(rows.find(r => r.name === 'grains').total).toBe('150');  // 100 + 50, not ×count
        expect(rows.find(r => r.name === 'legumes').total).toBe('0');
    });

    test('a large plain total is formatted with grouping separators', () => {
        const fields = [{key: 'g', type: 'select'}, {key: 'count', type: 'number'}];
        const items = [{id: 1, g: 'x', count: '1500'}, {id: 2, g: 'x', count: '2500'}];
        const rows = summarizeInventory(items, {fields, groupKey: 'g', sumKey: 'count'});
        expect(rows[0].total).toBe((4000).toLocaleString());
    });

    test('a plain total with no numeric values shows —', () => {
        const fields = [{key: 'g', type: 'select'}, {key: 'count', type: 'number'}];
        const items = [{id: 1, g: 'x'}, {id: 2, g: 'x', count: ''}];
        const rows = summarizeInventory(items, {fields, groupKey: 'g', sumKey: 'count'});
        expect(rows[0].total).toBe('—');
    });

    test('blank/zero count counts as a single unit for quantity sums', () => {
        const fields = [{key: 'g', type: 'select'}, {key: 'item_size', type: 'quantity', unit: 'lb'},
            {key: 'count', type: 'number'}];
        const items = [{id: 1, g: 'grains', item_size: '5', item_size_unit: 'lb', count: ''}];
        const rows = summarizeInventory(items, {fields, groupKey: 'g', sumKey: 'item_size', countKey: 'count'});
        expect(rows[0].total).toBe('5 lb');
    });

    test('missing group values bucket under "(none)"', () => {
        const fields = [{key: 'name', type: 'text'}, {key: 'category', type: 'select'},
            {key: 'item_size', type: 'quantity', unit: 'lb'}];
        const items = [{id: 1, name: 'x', item_size: '5', item_size_unit: 'lb'}];
        const rows = summarizeInventory(items, {fields, groupKey: 'category', sumKey: 'item_size'});
        expect(rows[0].name).toBe('(none)');
    });

    test('returns [] when there is no group key', () => {
        expect(summarizeInventory(ITEMS, {fields: FIELDS, groupKey: undefined})).toEqual([]);
    });

    test('no sum key yields a — total', () => {
        const rows = summarizeInventory(ITEMS, {fields: FIELDS, groupKey: 'category'});
        expect(rows.every(r => r.total === '—')).toBe(true);
    });
});

describe('sortSummaryRows', () => {
    const rows = [
        {name: 'grains', count: 2, totalSort: 110, calories: 400},
        {name: 'legumes', count: 1, totalSort: 25, calories: 0},
    ];

    test('sorts by count descending', () => {
        expect(sortSummaryRows(rows, {key: 'count', dir: 'desc'}).map(r => r.name)).toEqual(['grains', 'legumes']);
    });

    test('sorts by total ascending', () => {
        expect(sortSummaryRows(rows, {key: 'total', dir: 'asc'}).map(r => r.name)).toEqual(['legumes', 'grains']);
    });

    test('does not mutate the input array', () => {
        const copy = [...rows];
        sortSummaryRows(rows, {key: 'calories', dir: 'desc'});
        expect(rows).toEqual(copy);
    });
});
