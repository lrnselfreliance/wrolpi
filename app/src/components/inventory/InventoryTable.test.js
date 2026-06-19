import React from "react";
import {fireEvent, render, screen} from "@testing-library/react";
import {filterItems, InventoryTable} from "./InventoryTable";

const FIELDS = [
    {key: 'name', label: 'Name', type: 'text', order: 0},
    {key: 'count', label: 'Count', type: 'number', order: 1},
];

describe('InventoryTable keyboard entry', () => {
    test('pressing Enter in the draft row submits the new item via onChange', () => {
        const onChange = jest.fn();
        render(<InventoryTable slug='food-storage' fields={FIELDS} items={[]} locations={[]} onChange={onChange}/>);

        const nameInput = screen.getAllByLabelText('Name')[0];
        fireEvent.change(nameInput, {target: {value: 'Salt'}});
        fireEvent.keyDown(nameInput, {key: 'Enter'});

        expect(onChange).toHaveBeenCalledTimes(1);
        const newItems = onChange.mock.calls[0][0];
        expect(newItems).toHaveLength(1);
        expect(newItems[0].name).toBe('Salt');
        expect(typeof newItems[0].id).toBe('number');
    });

    test('does not submit an empty draft row', () => {
        const onChange = jest.fn();
        render(<InventoryTable slug='food-storage' fields={FIELDS} items={[]} locations={[]} onChange={onChange}/>);

        const nameInput = screen.getAllByLabelText('Name')[0];
        fireEvent.keyDown(nameInput, {key: 'Enter'});

        expect(onChange).not.toHaveBeenCalled();
    });

    test('new item id is unique relative to existing items', () => {
        const onChange = jest.fn();
        const items = [{id: 7, name: 'Salt', count: '5'}];
        render(<InventoryTable slug='food-storage' fields={FIELDS} items={items} locations={[]} onChange={onChange}/>);

        const nameInput = screen.getAllByLabelText('Name').slice(-1)[0];  // the draft row's input
        fireEvent.change(nameInput, {target: {value: 'Rice'}});
        fireEvent.keyDown(nameInput, {key: 'Enter'});

        const newItems = onChange.mock.calls[0][0];
        expect(newItems).toHaveLength(2);
        expect(newItems[1].id).toBe(8);
    });

    test('clicking an existing item cell starts inline edit', () => {
        const items = [{id: 1, name: 'Salt', count: '5'}];
        render(<InventoryTable slug='food-storage' fields={FIELDS} items={items} locations={[]} onChange={jest.fn()}/>);

        fireEvent.click(screen.getByText('Salt'));
        const editInputs = screen.getAllByLabelText('Name').map(i => i.value);
        expect(editInputs).toContain('Salt');
    });
});

describe('InventoryTable sorting', () => {
    const items = [
        {id: 1, name: 'Rice', count: '5'},
        {id: 2, name: 'Beans', count: '20'},
        {id: 3, name: 'Apples', count: '12'},
    ];

    const bodyNames = () =>
        [...document.querySelectorAll('tbody tr')].map(tr => tr.querySelector('td:nth-child(2)').textContent);

    test('clicking a text header sorts ascending then descending', () => {
        render(<InventoryTable slug='s' fields={FIELDS} items={items} locations={[]} onChange={jest.fn()}/>);
        expect(bodyNames()).toEqual(['Rice', 'Beans', 'Apples']);  // entry order

        fireEvent.click(screen.getByText('Name'));
        expect(bodyNames()).toEqual(['Apples', 'Beans', 'Rice']);

        fireEvent.click(screen.getByText('Name'));
        expect(bodyNames()).toEqual(['Rice', 'Beans', 'Apples']);
    });

    test('numeric column sorts numerically, not lexically', () => {
        render(<InventoryTable slug='s' fields={FIELDS} items={items} locations={[]} onChange={jest.fn()}/>);
        fireEvent.click(screen.getByText('Count'));
        // 5 < 12 < 20 numerically (lexical would put '12','20','5').
        expect(bodyNames()).toEqual(['Rice', 'Apples', 'Beans']);
    });
});

describe('InventoryTable catalog pre-fill', () => {
    const CAT_FIELDS = [
        {key: 'name', label: 'Name', type: 'text', order: 0},
        {key: 'category', label: 'Category', type: 'text', order: 1},
        {key: 'item_size', label: 'Size', type: 'quantity', unit: 'lb', order: 2},
        {key: 'calories', label: 'kcal', type: 'calories', order: 3},
    ];
    const CATALOG = [
        {id: 1, name: 'White Rice', category: 'grains', subcategory: 'rice',
         item_size: '5', item_size_unit: 'lb', calories: '8040'},
    ];

    test('selecting a catalog name pre-fills the matching fields', () => {
        render(<InventoryTable slug='s' fields={CAT_FIELDS} items={[]} locations={[]} catalog={CATALOG}
                               onChange={jest.fn()}/>);
        // The catalog datalist is present.
        expect(document.querySelector('#inventory-catalog-names option[value="White Rice"]')).toBeTruthy();

        fireEvent.change(screen.getByLabelText('Name'), {target: {value: 'White Rice'}});

        expect(screen.getByLabelText('Category').value).toBe('grains');
        expect(screen.getByLabelText('Size').value).toBe('5');
        expect(screen.getByLabelText('kcal').value).toBe('8040');
    });

    test('a non-catalog name leaves other fields untouched', () => {
        render(<InventoryTable slug='s' fields={CAT_FIELDS} items={[]} locations={[]} catalog={CATALOG}
                               onChange={jest.fn()}/>);
        fireEvent.change(screen.getByLabelText('Name'), {target: {value: 'Homemade Jerky'}});
        expect(screen.getByLabelText('Category').value).toBe('');
        expect(screen.getByLabelText('kcal').value).toBe('');
    });
});

describe('InventoryTable expired highlighting', () => {
    const FIELDS_WITH_DATE = [
        {key: 'name', label: 'Name', type: 'text', order: 0},
        {key: 'expiration_date', label: 'Expires', type: 'date', order: 1},
    ];

    test('rows past a date field are flagged negative with a warning icon', () => {
        const items = [
            {id: 1, name: 'Old', expiration_date: '2000-01-01'},
            {id: 2, name: 'Fresh', expiration_date: '2999-01-01'},
        ];
        const {container} = render(
            <InventoryTable slug='s' fields={FIELDS_WITH_DATE} items={items} locations={[]} onChange={jest.fn()}/>);

        const rowOf = (name) => screen.getByText(name).closest('tr');
        expect(rowOf('Old').className).toContain('negative');
        expect(rowOf('Fresh').className).not.toContain('negative');
        // One expired row -> one warning icon.
        expect(container.querySelectorAll('i.warning.sign.icon').length).toBe(1);
    });
});

describe('filterItems', () => {
    const FIELDS = [
        {key: 'name', label: 'Name', type: 'text', order: 0},
        {key: 'category', label: 'Category', type: 'select', order: 1},
        {key: 'item_size', label: 'Size', type: 'quantity', unit: 'lb', order: 2},
        {key: 'count', label: 'Count', type: 'number', order: 3},
        {key: 'expiration_date', label: 'Expires', type: 'date', order: 4},
    ];
    const ITEMS = [
        {id: 1, name: 'White Rice', category: 'grains', item_size: '30', item_size_unit: 'lb', count: '3',
            expiration_date: '2030-01-01'},
        {id: 2, name: 'Pinto Beans', category: 'legumes', item_size: '25', item_size_unit: 'lb', count: '2',
            expiration_date: '2033-01-01'},
        {id: 3, name: 'Canned Chicken', category: 'meats', item_size: '12.5', item_size_unit: 'oz', count: '12',
            expiration_date: '2030-06-01'},
    ];
    const names = (rows) => rows.map(r => r.name);

    test('blank or whitespace search returns all items', () => {
        expect(filterItems(ITEMS, FIELDS, '')).toHaveLength(3);
        expect(filterItems(ITEMS, FIELDS, '   ')).toHaveLength(3);
    });

    test('matches a text column, case-insensitively', () => {
        expect(names(filterItems(ITEMS, FIELDS, 'rice'))).toEqual(['White Rice']);
        expect(names(filterItems(ITEMS, FIELDS, 'RICE'))).toEqual(['White Rice']);
    });

    test('matches a select column (category)', () => {
        expect(names(filterItems(ITEMS, FIELDS, 'legumes'))).toEqual(['Pinto Beans']);
    });

    test('matches a date column', () => {
        expect(names(filterItems(ITEMS, FIELDS, '2030'))).toEqual(['White Rice', 'Canned Chicken']);
    });

    test('matches a quantity column by its formatted value', () => {
        expect(names(filterItems(ITEMS, FIELDS, '25 lb'))).toEqual(['Pinto Beans']);
    });

    test('whitespace-separated terms are AND-ed', () => {
        expect(names(filterItems(ITEMS, FIELDS, 'canned chicken'))).toEqual(['Canned Chicken']);
        expect(filterItems(ITEMS, FIELDS, 'rice beans')).toEqual([]);
    });

    test('a non-matching search returns nothing', () => {
        expect(filterItems(ITEMS, FIELDS, 'xyzzy')).toEqual([]);
    });
});

describe('InventoryTable search', () => {
    const FIELDS = [
        {key: 'name', label: 'Name', type: 'text', order: 0},
        {key: 'count', label: 'Count', type: 'number', order: 1},
    ];
    const items = [
        {id: 1, name: 'White Rice', count: '3'},
        {id: 2, name: 'Pinto Beans', count: '2'},
    ];

    test('only matching rows are rendered, and the entry row remains', () => {
        render(<InventoryTable slug='s' fields={FIELDS} items={items} locations={[]} search='rice'
                               onChange={jest.fn()}/>);
        expect(screen.getByText('White Rice')).toBeTruthy();
        expect(screen.queryByText('Pinto Beans')).toBeNull();
        // The persistent draft entry row is still present.
        expect(screen.getAllByLabelText('Name').length).toBeGreaterThan(0);
    });

    test('adding from the entry row while filtered preserves the hidden items', () => {
        const onChange = jest.fn();
        render(<InventoryTable slug='s' fields={FIELDS} items={items} locations={[]} search='rice'
                               onChange={onChange}/>);
        const draftName = screen.getAllByLabelText('Name').slice(-1)[0];
        fireEvent.change(draftName, {target: {value: 'Oats'}});
        fireEvent.keyDown(draftName, {key: 'Enter'});
        // onChange gets the FULL inventory (both originals + new), not just the filtered view.
        const newItems = onChange.mock.calls[0][0];
        expect(newItems.map(i => i.name)).toEqual(['White Rice', 'Pinto Beans', 'Oats']);
    });

    test('a non-matching search shows a no-match message', () => {
        render(<InventoryTable slug='s' fields={FIELDS} items={items} locations={[]} search='xyzzy'
                               onChange={jest.fn()}/>);
        expect(screen.getByText(/no items match/i)).toBeTruthy();
    });
});
