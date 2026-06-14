import React, {useMemo, useState} from "react";
import {Select, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {Header, Segment, Table} from "../Theme";
import {formatTotals, sumQuantities} from "./units";
import {findCaloriesKey, findCountKey, RationEstimatePanel} from "../calculators/RationCalculator";
import {ThemeContext} from "../../contexts/contexts";

// Aggregate the inventory client-side: group items by a chosen text/select field and sum a chosen quantity field.
// When the inventory has a `calories` field, a ration estimate is shown below the summary table.
export function InventorySummary({fields, items}) {
    const groupFields = fields.filter(f => ['text', 'select', 'location'].includes(f.type));
    const quantityFields = fields.filter(f => f.type === 'quantity');
    const caloriesKey = findCaloriesKey(fields);
    const countKey = findCountKey(fields);
    const {t} = React.useContext(ThemeContext);

    // Default to grouping by Category (easier to see grains/dairy/etc.), falling back to the first group field.
    const [groupKey, setGroupKey] = useState((groupFields.find(f => f.key === 'category') || groupFields[0])?.key);
    const [quantityKey, setQuantityKey] = useState(quantityFields[0]?.key);
    const [sort, setSort] = useState({key: 'name', dir: 'asc'});

    const toggleSort = (key) => setSort(prev =>
        prev.key === key
            ? {key, dir: prev.dir === 'asc' ? 'desc' : 'asc'}
            : {key, dir: key === 'name' ? 'asc' : 'desc'});

    const rows = useMemo(() => {
        if (!groupKey) {
            return [];
        }
        // A blank/zero count means a single unit (matches the ration estimate's convention).
        const unitsOf = (item) => {
            const c = countKey ? Number(item[countKey]) : 1;
            return c > 0 ? c : 1;
        };
        const groups = {};
        (items || []).forEach(item => {
            const key = item[groupKey] || '(none)';
            if (!groups[key]) {
                groups[key] = {entries: [], count: 0, calories: 0};
            }
            const group = groups[key];
            group.count += 1;
            const units = unitsOf(item);
            if (quantityKey) {
                // Total size = per-container size × count (the count field), so the summary matches reality.
                const size = Number(item[quantityKey]);
                group.entries.push({
                    value: (size > 0 ? size : 0) * units,
                    unit: item[`${quantityKey}_unit`],
                });
            }
            if (caloriesKey) {
                const cal = Number(item[caloriesKey]);
                if (cal > 0) {
                    group.calories += cal * units;
                }
            }
        });
        const mapped = Object.entries(groups).map(([name, g]) => {
            const summed = sumQuantities(g.entries);
            // "Total" is a multi-unit string; keep a numeric proxy (sum of magnitudes + unitless) for sorting.
            const totalSort = (summed.totals || []).reduce((s, x) => s + x.magnitude, 0) + (summed.unitlessCount || 0);
            return {name, count: g.count, total: formatTotals(summed), totalSort, calories: g.calories};
        });
        const compare = (a, b) => {
            const r = sort.key === 'name' ? a.name.localeCompare(b.name)
                : sort.key === 'count' ? a.count - b.count
                    : sort.key === 'total' ? a.totalSort - b.totalSort
                        : a.calories - b.calories;
            return sort.dir === 'desc' ? -r : r;
        };
        return mapped.sort(compare);
    }, [items, groupKey, quantityKey, countKey, caloriesKey, sort]);

    const sortDir = (key) => sort.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined;

    if (!items || items.length === 0) {
        return <p {...t}>No items to summarize yet.</p>;
    }

    const fieldOptions = (fs) => fs.map(f => ({key: f.key, value: f.key, text: f.label}));

    return <>
        <Header as='h3'>Summary</Header>
        <div style={{marginBottom: '1em', display: 'flex', gap: '1em', flexWrap: 'wrap'}}>
            <span {...t}>
                Group by:{' '}
                <Select options={fieldOptions(groupFields)} value={groupKey}
                        onChange={(e, data) => setGroupKey(data.value)}/>
            </span>
            {quantityFields.length > 0 &&
                <span>
                    Sum:{' '}
                    <Select clearable options={fieldOptions(quantityFields)} value={quantityKey}
                            onChange={(e, data) => setQuantityKey(data.value)}/>
                </span>}
        </div>
        <Table celled unstackable sortable>
            <TableHeader>
                <TableRow>
                    <TableHeaderCell sorted={sortDir('name')} onClick={() => toggleSort('name')}
                                     style={{cursor: 'pointer'}}>
                        {groupFields.find(f => f.key === groupKey)?.label || 'Group'}
                    </TableHeaderCell>
                    <TableHeaderCell sorted={sortDir('count')} onClick={() => toggleSort('count')}
                                     style={{cursor: 'pointer'}}>Items</TableHeaderCell>
                    {quantityKey && <TableHeaderCell sorted={sortDir('total')} onClick={() => toggleSort('total')}
                                                     style={{cursor: 'pointer'}}>Total</TableHeaderCell>}
                    {caloriesKey && <TableHeaderCell sorted={sortDir('calories')} onClick={() => toggleSort('calories')}
                                                     style={{cursor: 'pointer'}}>Calories</TableHeaderCell>}
                </TableRow>
            </TableHeader>
            <TableBody>
                {rows.map(row => <TableRow key={row.name}>
                    <TableCell>{row.name}</TableCell>
                    <TableCell>{row.count}</TableCell>
                    {quantityKey && <TableCell>{row.total}</TableCell>}
                    {caloriesKey &&
                        <TableCell>{row.calories > 0 ? `${row.calories.toLocaleString()} kcal` : '—'}</TableCell>}
                </TableRow>)}
            </TableBody>
        </Table>

        {caloriesKey &&
            <Segment style={{marginTop: '2em'}}>
                <Header as='h3'>Ration Estimate</Header>
                <RationEstimatePanel items={items} caloriesKey={caloriesKey} countKey={countKey}/>
            </Segment>}
    </>;
}
