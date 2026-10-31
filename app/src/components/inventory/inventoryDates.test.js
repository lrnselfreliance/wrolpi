import {formatInventoryDateValue, parseInventoryDateMs} from "./inventoryDates";
import {filterItems, formatValue} from "./InventoryTable";

describe('inventoryDates', () => {
    test('parseInventoryDateMs accepts ISO dates and epoch seconds', () => {
        expect(parseInventoryDateMs('2030-01-01')).toBe(new Date(2030, 0, 1).getTime());
        expect(parseInventoryDateMs('1893456000')).toBe(1893456000 * 1000);
    });

    test('formatInventoryDateValue renders a calendar date', () => {
        expect(formatInventoryDateValue('2030-01-01')).toBe('2030-01-01');
        expect(formatInventoryDateValue('1893456000')).toBe('2030-01-01');
    });

    test('date-only values round-trip without timezone shift (US Eastern)', () => {
        const samples = ['2030-01-01', '2000-06-15', '2999-01-01'];
        for (const stored of samples) {
            const displayed = formatInventoryDateValue(stored);
            expect(displayed).toBe(stored);
            const fromInput = displayed;
            expect(fromInput).toBe(stored);
            expect(formatInventoryDateValue(fromInput)).toBe(stored);
            expect(formatInventoryDateValue(parseInventoryDateMs(fromInput))).toBe(stored);
        }
    });
});

describe('formatValue date fields', () => {
    const field = {key: 'expiration_date', label: 'Expires', type: 'date', order: 0};

    test('legacy epoch seconds display as YYYY-MM-DD', () => {
        expect(formatValue({expiration_date: '1893456000'}, field)).toBe('2030-01-01');
    });
});

describe('filterItems epoch dates', () => {
    const fields = [
        {key: 'name', label: 'Name', type: 'text', order: 0},
        {key: 'expiration_date', label: 'Expires', type: 'date', order: 1},
    ];
    const items = [{id: 1, name: 'Rice', expiration_date: '1893456000'}];

    test('search matches formatted expiration date', () => {
        expect(filterItems(items, fields, '2030-01-01')).toHaveLength(1);
    });
});
