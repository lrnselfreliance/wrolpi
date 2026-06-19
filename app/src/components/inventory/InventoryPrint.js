import React from "react";
import {formatValue} from "./InventoryTable";
import {findCaloriesKey, findCountKey, summarizeInventory} from "./summarize";

/**
 * Printable rendering of a full inventory (every field, every item) plus a summary table grouped by `groupKey`,
 * used for the "PDF" export via the browser's print dialog.  It is hidden on screen
 * (`.inventory-print { display: none }` in App.css) and becomes the only visible content when printing — so the
 * user can "Save as PDF" without the app chrome.
 */
export function InventoryPrint({name, fields, items, groupKey, sumKey}) {
    const cols = [...(fields || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    const list = items || [];
    const printed = new Date().toLocaleString();

    const caloriesKey = findCaloriesKey(fields);
    const countKey = findCountKey(fields);
    const summaryRows = summarizeInventory(list, {fields, groupKey, sumKey, countKey, caloriesKey});
    const groupLabel = cols.find(f => f.key === groupKey)?.label || 'Group';

    return <div className='inventory-print'>
        <h1>{name}</h1>
        <p className='inventory-print-meta'>{list.length} item{list.length === 1 ? '' : 's'} · printed {printed}</p>
        <table>
            <thead>
                <tr>{cols.map(f => <th key={f.key}>{f.label || f.key}</th>)}</tr>
            </thead>
            <tbody>
                {list.map(item => <tr key={item.id}>
                    {cols.map(f => <td key={f.key}>{formatValue(item, f)}</td>)}
                </tr>)}
            </tbody>
        </table>

        {summaryRows.length > 0 && <>
            <h2>Summary by {groupLabel}</h2>
            <table>
                <thead>
                    <tr>
                        <th>{groupLabel}</th>
                        <th>Items</th>
                        {sumKey && <th>Total</th>}
                        {caloriesKey && <th>Calories</th>}
                    </tr>
                </thead>
                <tbody>
                    {summaryRows.map(row => <tr key={row.name}>
                        <td>{row.name}</td>
                        <td>{row.count}</td>
                        {sumKey && <td>{row.total}</td>}
                        {caloriesKey && <td>{row.calories > 0 ? `${row.calories.toLocaleString()} kcal` : '—'}</td>}
                    </tr>)}
                </tbody>
            </table>
        </>}
    </div>;
}
