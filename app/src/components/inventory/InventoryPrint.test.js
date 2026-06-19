import React from "react";
import {render} from "@testing-library/react";
import {InventoryPrint} from "./InventoryPrint";

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
    {id: 3, name: 'Beans', category: 'legumes', item_size: '25', item_size_unit: 'lb', count: '1'},
];

describe('InventoryPrint', () => {
    const tables = (container) => [...container.querySelectorAll('table')];

    test('renders the full items table and a summary grouped by the chosen field', () => {
        const {container} = render(
            <InventoryPrint name='Food Storage' fields={FIELDS} items={ITEMS}
                            groupKey='category' sumKey='item_size'/>);

        expect(container.querySelector('h1').textContent).toBe('Food Storage');
        expect(container.querySelector('.inventory-print-meta').textContent).toMatch(/3 items/);

        // Two tables: items, then summary.
        const [itemsTable, summaryTable] = tables(container);
        expect(itemsTable.querySelectorAll('tbody tr').length).toBe(3);

        // Summary section header + grouped rows.
        expect(container.querySelector('h2').textContent).toBe('Summary by Category');
        const summaryRows = [...summaryTable.querySelectorAll('tbody tr')]
            .map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent));
        // grains: 2 items, 110 lb, 400 kcal; legumes: 1 item, 25 lb, no calories.
        expect(summaryRows).toEqual([
            ['grains', '2', '110 lb', '400 kcal'],
            ['legumes', '1', '25 lb', '—'],
        ]);
    });

    test('summing a number field shows a plain column total', () => {
        const {container} = render(
            <InventoryPrint name='Food Storage' fields={FIELDS} items={ITEMS}
                            groupKey='category' sumKey='count'/>);
        const summaryRows = [...tables(container)[1].querySelectorAll('tbody tr')]
            .map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent));
        // grains: 2 items, count 3+2=5; legumes: 1 item, count 1.
        expect(summaryRows).toEqual([
            ['grains', '2', '5', '400 kcal'],
            ['legumes', '1', '1', '—'],
        ]);
    });

    test('omits the summary when there is no group key', () => {
        const {container} = render(
            <InventoryPrint name='X' fields={FIELDS} items={ITEMS} groupKey={undefined} sumKey='item_size'/>);
        expect(container.querySelector('h2')).toBeNull();
        expect(tables(container).length).toBe(1);
    });
});
