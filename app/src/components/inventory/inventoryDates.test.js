import {formatInventoryDateValue, localTodayYmd, parseInventoryDateMs} from "./inventoryDates";
import {filterItems, formatValue, isItemExpired} from "./InventoryTable";

describe('inventoryDates', () => {
    test('parseInventoryDateMs accepts ISO dates and epoch seconds', () => {
        expect(parseInventoryDateMs('2030-01-01')).toBe(new Date(2030, 0, 1).getTime());
        expect(parseInventoryDateMs('1893456000')).toBe(1893456000 * 1000);
    });

    test('formatInventoryDateValue renders a calendar date', () => {
        expect(formatInventoryDateValue('2030-01-01')).toBe('2030-01-01');
        expect(formatInventoryDateValue('1893456000')).toBe('2030-01-01');
    });

    test('ambiguous digit strings are not treated as epoch seconds', () => {
        expect(formatInventoryDateValue('2030')).toBe('2030');
        expect(formatInventoryDateValue('20300101')).toBe('20300101');
        expect(parseInventoryDateMs('2030')).toBeNull();
        expect(parseInventoryDateMs('20300101')).toBeNull();
        expect(formatInventoryDateValue('2030')).not.toMatch(/^1970/);
        expect(formatInventoryDateValue('20300101')).not.toMatch(/^1970/);
        // Unquoted YAML numbers display the same as the equivalent string.
        expect(formatInventoryDateValue(2030)).toBe('2030');
        expect(formatInventoryDateValue(20300101)).toBe('20300101');
        expect(formatInventoryDateValue(1893456000)).toBe('2030-01-01');
    });

    test('epoch seconds with a .0 suffix are accepted', () => {
        expect(formatInventoryDateValue('1893456000.0')).toBe('2030-01-01');
        expect(parseInventoryDateMs('1893456000.0')).toBe(1893456000 * 1000);
    });

    test('date-only values round-trip without timezone shift (US Eastern)', () => {
        const samples = ['2030-01-01', '2000-06-15', '2999-01-01'];
        for (const stored of samples) {
            const displayed = formatInventoryDateValue(stored);
            expect(displayed).toBe(stored);
            const fromInput = displayed;
            expect(fromInput).toBe(stored);
            expect(formatInventoryDateValue(fromInput)).toBe(stored);
            const [y, m, d] = stored.split('-').map(Number);
            expect(parseInventoryDateMs(fromInput)).toBe(new Date(y, m - 1, d).getTime());
        }
    });
});

describe('isItemExpired', () => {
    const fields = [{key: 'expiration_date', label: 'Expires', type: 'date', order: 0}];

    afterEach(() => jest.useRealTimers());

    // The local calendar date of the (possibly faked) clock, independent of the process TZ.
    const localYmd = () => {
        const d = new Date();
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    };

    test('a date that is still today or later is not expired late in the evening', () => {
        jest.useFakeTimers();
        // 2030-01-01T02:00:00Z is 9 PM on 2029-12-31 in US Eastern, but already 2030-01-01 in UTC and east of it.
        // Either way 2030-01-01 is not before the local date, so it must not be expired.
        jest.setSystemTime(new Date('2030-01-01T02:00:00.000Z'));
        expect(localTodayYmd()).toBe(localYmd());
        expect(isItemExpired({expiration_date: '2030-01-01'}, fields)).toBe(false);
        expect(isItemExpired({expiration_date: '1893456000'}, fields)).toBe(false);
    });

    test('yesterday\'s calendar date is expired', () => {
        // 2030-01-02T15:00:00Z is 2030-01-02 in every timezone from UTC-9 through UTC+8.
        jest.useFakeTimers();
        jest.setSystemTime(new Date('2030-01-02T15:00:00.000Z'));
        expect(localTodayYmd()).toBe(localYmd());
        expect(isItemExpired({expiration_date: '2030-01-01'}, fields)).toBe(true);
        expect(isItemExpired({expiration_date: '1893456000'}, fields)).toBe(true);
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
