import React, {useMemo, useState} from "react";
import {Group, Header, Select, Table, Text} from "../ui";
import {
    defaultGroupKey, defaultSumKey, findCaloriesKey, findCountKey, groupFieldsOf, sortSummaryRows,
    summableFieldsOf, summarizeInventory,
} from "./summarize";

// Aggregate the inventory client-side: group items by a chosen text/select field and sum a chosen quantity, number,
// or calories field.  The grouping math lives in summarize.js (shared with the PDF export).  The ration estimate
// lives in its own "Ration" tab (see RationEstimatePanel).
export function InventorySummary({fields, items}) {
    const groupFields = groupFieldsOf(fields);
    const summableFields = summableFieldsOf(fields);
    const caloriesKey = findCaloriesKey(fields);
    const countKey = findCountKey(fields);

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
        return <Text>No items to summarize yet.</Text>;
    }

    const fieldOptions = (fs) => fs.map(f => ({value: f.key, label: f.label}));

    return <>
        <Header as='h3'>Summary</Header>
        <Group mb='1em' gap='1em' wrap='wrap'>
            <span>
                Group by:{' '}
                <Select data={fieldOptions(groupFields)} value={groupKey}
                        onChange={value => setGroupKey(value)}/>
            </span>
            {summableFields.length > 0 &&
                <span>
                    Sum:{' '}
                    <Select clearable data={fieldOptions(summableFields)} value={sumKey || ''}
                            onChange={value => setSumKey(value || undefined)}/>
                </span>}
        </Group>
        <Table>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell sorted={sortDir('name')} onSort={() => toggleSort('name')}>
                        {groupFields.find(f => f.key === groupKey)?.label || 'Group'}
                    </Table.HeaderCell>
                    <Table.HeaderCell sorted={sortDir('count')} onSort={() => toggleSort('count')}>
                        Items
                    </Table.HeaderCell>
                    {sumKey && <Table.HeaderCell sorted={sortDir('total')} onSort={() => toggleSort('total')}>
                        Total
                    </Table.HeaderCell>}
                    {caloriesKey && <Table.HeaderCell sorted={sortDir('calories')}
                                                       onSort={() => toggleSort('calories')}>
                        Calories
                    </Table.HeaderCell>}
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {rows.map(row => <Table.Row key={row.name}>
                    <Table.Cell>{row.name}</Table.Cell>
                    <Table.Cell>{row.count}</Table.Cell>
                    {sumKey && <Table.Cell>{row.total}</Table.Cell>}
                    {caloriesKey &&
                        <Table.Cell>{row.calories > 0 ? `${row.calories.toLocaleString()} kcal` : '—'}</Table.Cell>}
                </Table.Row>)}
            </Table.Body>
        </Table>
    </>;
}
