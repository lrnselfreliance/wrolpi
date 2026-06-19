import React from "react";
import {fireEvent, render, screen, within} from "@testing-library/react";
import {
    dailyCalorieDemand, daysOfFood, findCaloriesKey, findCountKey, RationEstimatePanel, totalCalories,
} from "./RationCalculator";

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

describe('RationEstimatePanel supply plan', () => {
    const FIELDS = [
        {key: 'name', label: 'Name', type: 'text', order: 0},
        {key: 'count', label: 'Count', type: 'number', order: 1},
        {key: 'calories', label: 'kcal', type: 'calories', order: 2},
    ];
    // 100 cans × 450 kcal = 45,000 kcal; with a survival ration for one man (1,500/day) that lasts exactly 30 days.
    const ITEMS = [{name: 'Beans', count: '100', calories: '450'}];

    beforeEach(() => {
        window.localStorage.clear();
        // Deterministic household: one man on the Survival preset → 1,500 kcal/day.
        window.localStorage.setItem('ration_preset', JSON.stringify('survival'));
        window.localStorage.setItem('ration_counts', JSON.stringify({men: '1', women: '', children: ''}));
    });

    test('dragging the target slider produces a round-up shopping list', () => {
        render(<RationEstimatePanel items={ITEMS} fields={FIELDS} caloriesKey='calories' countKey='count'/>);

        // Current estimate is 1 month, so the slider starts there with no purchases yet.
        expect(screen.getByText(/drag the slider/i)).toBeTruthy();

        // Drag to a 2-month target: scale ×2 → 100 → 200 cans, buy 100.
        fireEvent.change(screen.getByLabelText(/target duration/i), {target: {value: '2'}});

        // Scope to the on-screen table (the hidden print block duplicates these texts in the DOM).
        const plan = within(document.querySelector('table.sortable'));
        expect(plan.getByText('Beans')).toBeTruthy();
        expect(plan.getByText('+100')).toBeTruthy();
        // Summary line reports the total to buy.
        expect(screen.getByText(/additional packages/).textContent).toMatch(/100 additional packages/);
    });

    test('clicking a column header re-sorts the shopping list', () => {
        const items = [
            {name: 'Apples', count: '10', calories: '100'},
            {name: 'Beans', count: '200', calories: '100'},
        ];
        render(<RationEstimatePanel items={items} fields={FIELDS} caloriesKey='calories' countKey='count'/>);
        fireEvent.change(screen.getByLabelText(/target duration/i), {target: {value: '2'}});

        const itemNames = () =>
            [...document.querySelectorAll('table.sortable tbody tr td:first-child')].map(td => td.textContent);
        // Default sort is largest purchase first (Beans buys far more than Apples).
        expect(itemNames()).toEqual(['Beans', 'Apples']);

        // Sorting by Item ascending flips to alphabetical (scope to the sortable table; the print block also has an
        // "Item" header).
        fireEvent.click(within(document.querySelector('table.sortable')).getByText('Item'));
        expect(itemNames()).toEqual(['Apples', 'Beans']);
    });

    test('a populated plan offers CSV and PDF export, and printing scopes to the shopping list', () => {
        const printSpy = jest.spyOn(window, 'print').mockImplementation(() => {});
        render(<RationEstimatePanel name='Food Storage' items={ITEMS} fields={FIELDS}
                                    caloriesKey='calories' countKey='count'/>);
        fireEvent.change(screen.getByLabelText(/target duration/i), {target: {value: '2'}});

        expect(screen.getByText(/Download CSV/i)).toBeTruthy();

        // Printing toggles the body class the @media print rules use to show only the shopping list.
        fireEvent.click(screen.getByText(/Print/i));
        expect(printSpy).toHaveBeenCalled();
        expect(document.body.classList.contains('printing-shopping')).toBe(true);
        printSpy.mockRestore();
    });

    test('without a count field, the plan asks for one instead of a list', () => {
        render(<RationEstimatePanel items={ITEMS} fields={FIELDS} caloriesKey='calories' countKey={null}/>);
        expect(screen.getByText(/add a/i).textContent.toLowerCase()).toContain('count');
    });
});
