import React from "react";
import {fireEvent, render, screen} from "@testing-library/react";
import {InventorySummary} from "./InventorySummary";

// Group by the first text field (category); two groups with different item counts and size totals.
const FIELDS = [
    {key: 'category', label: 'Category', type: 'text', order: 0},
    {key: 'item_size', label: 'Size', type: 'quantity', unit: 'lb', order: 1},
    {key: 'count', label: 'Count', type: 'number', order: 2},
];
const ITEMS = [
    {id: 1, category: 'grains', item_size: '10', item_size_unit: 'lb', count: '2'},  // 20 lb
    {id: 2, category: 'grains', item_size: '5', item_size_unit: 'lb', count: '2'},   // 10 lb  -> grains: 2 items, 30 lb
    {id: 3, category: 'beans', item_size: '25', item_size_unit: 'lb', count: '4'},   // beans: 1 item, 100 lb
];

const groupOrder = () =>
    [...document.querySelectorAll('tbody tr')].map(tr => tr.querySelector('td:first-child').textContent);

describe('InventorySummary sortable columns', () => {
    test('defaults to group name ascending', () => {
        render(<InventorySummary fields={FIELDS} items={ITEMS}/>);
        expect(groupOrder()).toEqual(['beans', 'grains']);
    });

    test('sorting by Items uses the numeric count', () => {
        render(<InventorySummary fields={FIELDS} items={ITEMS}/>);
        fireEvent.click(screen.getByText('Items'));       // first click -> descending
        expect(groupOrder()).toEqual(['grains', 'beans']); // grains has 2 items, beans 1
        fireEvent.click(screen.getByText('Items'));       // toggle -> ascending
        expect(groupOrder()).toEqual(['beans', 'grains']);
    });

    test('sorting by Total uses the summed magnitude, not the formatted string', () => {
        render(<InventorySummary fields={FIELDS} items={ITEMS}/>);
        fireEvent.click(screen.getByText('Total'));        // descending
        expect(groupOrder()).toEqual(['beans', 'grains']); // beans 100 lb > grains 30 lb
    });
});
