import {addCountByWeightFields, applyComputedCounts, computedCountConfigs, isCountByWeight} from "./computeFields";

describe('addCountByWeightFields', () => {
    test('adds Unit Weight, Total Weight, and a computed Count to a schema with no count', () => {
        const result = addCountByWeightFields([{key: 'name', label: 'Name', type: 'text'}]);
        const byKey = Object.fromEntries(result.map(f => [f.key, f]));
        expect(byKey.unit_weight).toMatchObject({type: 'quantity', unit: 'g'});
        expect(byKey.total_weight).toMatchObject({type: 'quantity', unit: 'g'});
        expect(byKey.count.type).toBe('number');
        expect(byKey.count.compute).toEqual({kind: 'count_by_weight', total: 'total_weight', unit: 'unit_weight'});
    });

    test('links an existing count field instead of duplicating it', () => {
        const fields = [
            {key: 'name', label: 'Name', type: 'text'},
            {key: 'count', label: 'Count', type: 'number'},
        ];
        const result = addCountByWeightFields(fields);
        expect(result.filter(f => f.key === 'count')).toHaveLength(1);
        expect(isCountByWeight(result.find(f => f.key === 'count'))).toBe(true);
        // The two weight fields were appended.
        expect(result.map(f => f.key)).toEqual(['name', 'count', 'unit_weight', 'total_weight']);
    });

    test('does not duplicate existing weight fields', () => {
        const fields = [{key: 'unit_weight', type: 'quantity', unit: 'oz'}];
        const result = addCountByWeightFields(fields);
        expect(result.filter(f => f.key === 'unit_weight')).toHaveLength(1);
        expect(result.find(f => f.key === 'unit_weight').unit).toBe('oz');   // left untouched
    });
});

describe('computedCountConfigs', () => {
    const FIELDS = [
        {key: 'unit_weight', type: 'quantity', unit: 'g'},
        {key: 'total_weight', type: 'quantity', unit: 'g'},
        {key: 'count', type: 'number', compute: {kind: 'count_by_weight', total: 'total_weight', unit: 'unit_weight'}},
    ];

    test('resolves the weight keys and their default units', () => {
        expect(computedCountConfigs(FIELDS)).toEqual([
            {countKey: 'count', totalKey: 'total_weight', unitKey: 'unit_weight', totalUnit: 'g', unitUnit: 'g'},
        ]);
    });

    test('skips a config whose referenced weight field is missing', () => {
        const broken = [{key: 'count', type: 'number',
            compute: {kind: 'count_by_weight', total: 'gone', unit: 'unit_weight'}}];
        expect(computedCountConfigs(broken)).toEqual([]);
    });
});

describe('applyComputedCounts', () => {
    const configs = [{countKey: 'count', totalKey: 'total_weight', unitKey: 'unit_weight',
        totalUnit: 'g', unitUnit: 'g'}];

    test('fills the count when a weight changes', () => {
        const item = {total_weight: '1000', unit_weight: '5'};
        applyComputedCounts(item, configs, 'total_weight');
        expect(item.count).toBe('200');
    });

    test('uses the per-item unit override when present', () => {
        const item = {total_weight: '2', total_weight_unit: 'kg', unit_weight: '5', unit_weight_unit: 'g'};
        applyComputedCounts(item, configs, 'unit_weight');
        expect(item.count).toBe('400');
    });

    test('does not recompute when an unrelated field changes (manual count survives)', () => {
        const item = {total_weight: '1000', unit_weight: '5', count: '999', name: 'Screws'};
        applyComputedCounts(item, configs, 'name');
        expect(item.count).toBe('999');
    });

    test('reducing a weight to a sub-unit total recomputes the count to 0 (no stale value)', () => {
        const item = {total_weight: '1', unit_weight: '5', count: '200'};
        applyComputedCounts(item, configs, 'total_weight');
        expect(item.count).toBe('0');
    });

    test('clearing a weight clears the count so a stale value cannot persist', () => {
        const item = {total_weight: '', unit_weight: '5', count: '200'};
        applyComputedCounts(item, configs, 'total_weight');
        expect(item.count).toBe('');
    });

    test('a fresh draft (no count yet) stays blank while only one weight is entered', () => {
        const item = {total_weight: '', unit_weight: '5', count: ''};
        applyComputedCounts(item, configs, 'unit_weight');
        expect(item.count).toBe('');
    });
});
