import {inventoryExportFilename, shoppingListCSV, toCSV} from "./inventoryExport";

const FIELDS = [
    {key: 'name', label: 'Name', type: 'text', order: 0},
    {key: 'item_size', label: 'Size', type: 'quantity', unit: 'lb', order: 1},
    {key: 'count', label: 'Count', type: 'number', order: 2},
];

describe('toCSV', () => {
    test('emits a header row of labels then one row per item, in field order', () => {
        const items = [
            {id: 1, name: 'White Rice', item_size: '30', item_size_unit: 'lb', count: '3'},
            {id: 2, name: 'Honey', item_size: '12', item_size_unit: 'lb', count: '1'},
        ];
        expect(toCSV(FIELDS, items)).toBe(
            'Name,Size,Count\r\n' +
            'White Rice,30 lb,3\r\n' +
            'Honey,12 lb,1'
        );
    });

    test('orders columns by field order, not array order', () => {
        const unordered = [
            {key: 'count', label: 'Count', type: 'number', order: 2},
            {key: 'name', label: 'Name', type: 'text', order: 0},
        ];
        const csv = toCSV(unordered, [{id: 1, name: 'Salt', count: '5'}]);
        expect(csv.split('\r\n')[0]).toBe('Name,Count');
        expect(csv.split('\r\n')[1]).toBe('Salt,5');
    });

    test('quotes values containing commas, quotes, or newlines (RFC 4180)', () => {
        const fields = [{key: 'name', label: 'Name', type: 'text', order: 0}];
        expect(toCSV(fields, [{id: 1, name: 'Beans, dried'}]).split('\r\n')[1])
            .toBe('"Beans, dried"');
        expect(toCSV(fields, [{id: 1, name: 'Bob\'s "Best"'}]).split('\r\n')[1])
            .toBe('"Bob\'s ""Best"""');
        expect(toCSV(fields, [{id: 1, name: 'line1\nline2'}]).split('\r\n').slice(1).join('\r\n'))
            .toBe('"line1\nline2"');
    });

    test('blank/missing values render as empty cells', () => {
        expect(toCSV(FIELDS, [{id: 1, name: 'Salt'}])).toBe('Name,Size,Count\r\nSalt,,');
    });

    test('no items yields just the header row', () => {
        expect(toCSV(FIELDS, [])).toBe('Name,Size,Count');
    });
});

describe('shoppingListCSV', () => {
    test('emits the Item/Have/Buy/New Total columns for each plan row', () => {
        const rows = [
            {name: 'Canned Beans', current: 96, additional: 29, target: 125},
            {name: 'Mixed Vegetables', current: 180, additional: 55, target: 235},
        ];
        expect(shoppingListCSV(rows)).toBe(
            'Item,Have,Buy,New Total\r\n' +
            'Canned Beans,96,29,125\r\n' +
            'Mixed Vegetables,180,55,235'
        );
    });

    test('quotes a name containing a comma, and handles no rows', () => {
        expect(shoppingListCSV([{name: 'Beans, dried', current: 1, additional: 1, target: 2}]).split('\r\n')[1])
            .toBe('"Beans, dried",1,1,2');
        expect(shoppingListCSV([])).toBe('Item,Have,Buy,New Total');
    });
});

describe('inventoryExportFilename', () => {
    test('slugifies the inventory name with the given extension', () => {
        expect(inventoryExportFilename('Food Storage', 'csv')).toBe('food-storage.csv');
        expect(inventoryExportFilename('  My Tools!! ', 'csv')).toBe('my-tools.csv');
    });

    test('falls back to "inventory" for an empty name', () => {
        expect(inventoryExportFilename('', 'csv')).toBe('inventory.csv');
        expect(inventoryExportFilename(null, 'csv')).toBe('inventory.csv');
    });
});
