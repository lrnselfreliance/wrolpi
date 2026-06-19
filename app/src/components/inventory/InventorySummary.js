import React, {useMemo, useState} from "react";
import {Select, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {Header, Segment, Table} from "../Theme";
import {RationEstimatePanel} from "../calculators/RationCalculator";
import {
    defaultGroupKey, defaultSumKey, findCaloriesKey, findCountKey, groupFieldsOf, sortSummaryRows,
    summableFieldsOf, summarizeInventory,
} from "./summarize";
import {ThemeContext} from "../../contexts/contexts";

// Aggregate the inventory client-side: group items by a chosen text/select field and sum a chosen quantity, number,
// or calories field.  When the inventory has a `calories` field, a ration estimate is shown below the summary table.
// The grouping math lives in summarize.js (shared with the PDF export).
export function InventorySummary({fields, items}) {
    const groupFields = groupFieldsOf(fields);
    const summableFields = summableFieldsOf(fields);
    const caloriesKey = findCaloriesKey(fields);
    const countKey = findCountKey(fields);
    const {t} = React.useContext(ThemeContext);

    // Default to grouping by Category (easier to see grains/dairy/etc.), falling back to the first group field.
    const [groupKey, setGroupKey] = useState(defaultGroupKey(fields));
    const [sumKey, setSumKey] = useState(defaultSumKey(fields));
    const [sort, setSort] = useState({key: 'name', dir: 'asc'});

    const toggleSort = (key) => setSort(prev =>
        prev.key === key
            ? {key, dir: prev.dir === 'asc' ? 'desc' : 'asc'}
            : {key, dir: key === 'name' ? 'asc' : 'desc'});

    const rows = useMemo(() => {
        const summarized = summarizeInventory(items, {fields, groupKey, sumKey, countKey, caloriesKey});
        return sortSummaryRows(summarized, sort);
    }, [items, fields, groupKey, sumKey, countKey, caloriesKey, sort]);

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
            {summableFields.length > 0 &&
                <span>
                    Sum:{' '}
                    <Select clearable options={fieldOptions(summableFields)} value={sumKey || ''}
                            onChange={(e, data) => setSumKey(data.value || undefined)}/>
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
                    {sumKey && <TableHeaderCell sorted={sortDir('total')} onClick={() => toggleSort('total')}
                                                style={{cursor: 'pointer'}}>Total</TableHeaderCell>}
                    {caloriesKey && <TableHeaderCell sorted={sortDir('calories')} onClick={() => toggleSort('calories')}
                                                     style={{cursor: 'pointer'}}>Calories</TableHeaderCell>}
                </TableRow>
            </TableHeader>
            <TableBody>
                {rows.map(row => <TableRow key={row.name}>
                    <TableCell>{row.name}</TableCell>
                    <TableCell>{row.count}</TableCell>
                    {sumKey && <TableCell>{row.total}</TableCell>}
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
