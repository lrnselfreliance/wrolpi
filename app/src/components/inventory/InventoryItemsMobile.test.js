import React from "react";
import {render, screen} from "@testing-library/react";
import {InventoryItemsMobile} from "./InventoryItemsMobile";

const FIELDS = [
    {key: 'name', label: 'Name', type: 'text', order: 0},
    {key: 'category', label: 'Category', type: 'text', order: 1},
    {key: 'subcategory', label: 'Sub-category', type: 'text', order: 2},
    {key: 'item_size', label: 'Size', type: 'quantity', unit: 'lb', order: 3},
    {key: 'count', label: 'Count', type: 'number', order: 4},
    {key: 'expiration_date', label: 'Expires', type: 'date', order: 5},
];

describe('InventoryItemsMobile', () => {
    test('shows the fields flagged `mobile`, in field order', () => {
        const flagged = [
            {key: 'name', label: 'Name', type: 'text', order: 0, mobile: true},
            {key: 'category', label: 'Category', type: 'text', order: 1},
            {key: 'count', label: 'Count', type: 'number', order: 2, mobile: true},
            {key: 'expiration_date', label: 'Expires', type: 'date', order: 3, mobile: true},
        ];
        render(<InventoryItemsMobile fields={flagged} items={[{id: 1, name: 'Rice'}]}/>);

        const headers = [...document.querySelectorAll('thead th')].map(th => th.textContent);
        expect(headers).toEqual(['Name', 'Count', 'Expires']);
        // An unflagged field is not shown.
        expect(screen.queryByText('Category')).toBeNull();
    });

    test('falls back to default columns when no field is flagged mobile', () => {
        render(<InventoryItemsMobile fields={FIELDS} items={[{id: 1, name: 'Rice'}]}/>);

        const headers = [...document.querySelectorAll('thead th')].map(th => th.textContent);
        expect(headers).toEqual(['Name', 'Sub-category', 'Size', 'Count']);
        expect(screen.queryByText('Category')).toBeNull();
        expect(screen.queryByText('Expires')).toBeNull();
    });

    test('falls back to the first four fields when no preferred keys are present', () => {
        const fields = [
            {key: 'fuel_type', label: 'Fuel', type: 'text', order: 0},
            {key: 'container', label: 'Container', type: 'text', order: 1},
            {key: 'volume', label: 'Volume', type: 'quantity', order: 2},
            {key: 'purchase_date', label: 'Purchased', type: 'date', order: 3},
            {key: 'location', label: 'Location', type: 'location', order: 4},
        ];
        render(<InventoryItemsMobile fields={fields} items={[{id: 1, fuel_type: 'Diesel'}]}/>);
        const headers = [...document.querySelectorAll('thead th')].map(th => th.textContent);
        expect(headers).toEqual(['Fuel', 'Container', 'Volume', 'Purchased']);
    });

    test('renders quantity values with their unit and flags expired rows', () => {
        const items = [
            {id: 1, name: 'Old', subcategory: 'rice', item_size: '5', item_size_unit: 'lb', count: '2',
             expiration_date: '2000-01-01'},
            {id: 2, name: 'Fresh', subcategory: 'beans', item_size: '10', item_size_unit: 'lb', count: '4',
             expiration_date: '2999-01-01'},
        ];
        const {container} = render(<InventoryItemsMobile fields={FIELDS} items={items}/>);

        expect(screen.getByText('5 lb')).toBeTruthy();
        const rowOf = (name) => screen.getByText(name).closest('tr');
        expect(rowOf('Old').className).toContain('negative');
        expect(rowOf('Fresh').className).not.toContain('negative');
        expect(container.querySelectorAll('i.warning.sign.icon').length).toBe(1);
    });

    test('shows an empty state when there are no items', () => {
        render(<InventoryItemsMobile fields={FIELDS} items={[]}/>);
        expect(screen.getByText('No items yet.')).toBeTruthy();
    });
});
