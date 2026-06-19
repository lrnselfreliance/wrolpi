import React, {useMemo, useRef, useState} from "react";
import {Checkbox, TableBody, TableCell, TableFooter, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {Button, Icon, Table} from "../Theme";
import {FieldCell} from "./FieldCell";

const LOCATION_LIST_ID = 'inventory-location-suggestions';
const CATALOG_LIST_ID = 'inventory-catalog-names';
const NUMERIC_TYPES = ['number', 'quantity', 'calories'];
// Fields copied from a catalog entry onto the new-item row when its name matches a catalog entry.
const CATALOG_KEYS = ['name', 'category', 'subcategory', 'item_size', 'item_size_unit', 'calories'];

// Build an empty item keyed by the field schema (quantity fields seed their default unit).
function emptyItem(fields) {
    const item = {};
    fields.forEach(f => {
        item[f.key] = '';
        if (f.type === 'quantity') {
            item[`${f.key}_unit`] = f.unit || '';
        }
    });
    return item;
}

function nextId(items) {
    return items.reduce((max, i) => (typeof i.id === 'number' && i.id > max ? i.id : max), 0) + 1;
}

// Type-aware comparison for sorting: numeric for number/quantity/calories, chronological for date, locale string
// otherwise.  Blank values sort last (ascending).
function compareByField(a, b, field) {
    const av = a[field.key], bv = b[field.key];
    const aBlank = av === '' || av == null;
    const bBlank = bv === '' || bv == null;
    if (aBlank || bBlank) {
        return aBlank === bBlank ? 0 : (aBlank ? 1 : -1);
    }
    if (NUMERIC_TYPES.includes(field.type)) {
        return (Number(av) || 0) - (Number(bv) || 0);
    }
    if (field.type === 'date') {
        return (Date.parse(av) || 0) - (Date.parse(bv) || 0);
    }
    return String(av).localeCompare(String(bv));
}

/**
 * Spreadsheet-style item table.  All edits happen on the in-memory items; `onChange(newItems)` persists the whole
 * inventory (the page holds every inventory and saves the changed one).  A persistent "new item" row sits at the
 * bottom: Tab moves between fields and Enter submits the item then refocuses the first field.
 */
export function InventoryTable({slug, fields, items, locations, catalog, search, onChange}) {
    const [draft, setDraft] = useState(() => emptyItem(fields));
    const [edits, setEdits] = useState({});       // itemId -> edited copy
    const [selected, setSelected] = useState(new Set());
    const [sort, setSort] = useState(null);       // {key, dir: 'asc'|'desc'} or null for entry order
    const firstInputRef = useRef(null);

    const hasLocationField = fields.some(f => f.type === 'location');
    const hasNameField = fields.some(f => f.key === 'name');

    // Catalog lookup by lower-cased name, and the set of field keys this inventory actually has (so pre-fill only
    // touches existing fields).  Catalog integration only applies when the inventory has a `name` field.
    const catalogByName = useMemo(() => {
        const map = {};
        (catalog || []).forEach(e => {
            if (e.name) {
                map[e.name.trim().toLowerCase()] = e;
            }
        });
        return map;
    }, [catalog]);
    const fieldKeySet = useMemo(() => {
        const keys = new Set();
        fields.forEach(f => {
            keys.add(f.key);
            if (f.type === 'quantity') {
                keys.add(`${f.key}_unit`);
            }
        });
        return keys;
    }, [fields]);

    const listIdFor = (field) => {
        if (field.type === 'location') {
            return LOCATION_LIST_ID;
        }
        if (field.key === 'name' && (catalog || []).length) {
            return CATALOG_LIST_ID;
        }
        return undefined;
    };

    // Re-seed local editing state when the inventory or its schema changes.
    React.useEffect(() => {
        setDraft(emptyItem(fields));
        setEdits({});
        setSelected(new Set());
        setSort(null);
    }, [slug, fields]);

    // Expired = any date-type field strictly before the start of today (shared with the mobile view).
    const isExpired = (item) => isItemExpired(item, fields);

    const toggleSort = (key) => setSort(prev =>
        prev && prev.key === key
            ? {key, dir: prev.dir === 'asc' ? 'desc' : 'asc'}
            : {key, dir: 'asc'});

    // Rows are sorted for display only; the persistent entry row lives in the footer and is unaffected.
    const displayItems = useMemo(() => {
        const list = items || [];
        if (!sort) {
            return list;
        }
        const field = fields.find(f => f.key === sort.key);
        if (!field) {
            return list;
        }
        const sorted = [...list].sort((a, b) => compareByField(a, b, field));
        return sort.dir === 'desc' ? sorted.reverse() : sorted;
    }, [items, fields, sort]);

    // The search filters which rows are shown; mutations below still operate on the full `items` prop.
    const visibleItems = useMemo(() => filterItems(displayItems, fields, search), [displayItems, fields, search]);

    const focusFirst = () => {
        const node = firstInputRef.current;
        if (node && node.focus) {
            node.focus();
        } else if (node && node.inputRef && node.inputRef.current) {
            node.inputRef.current.focus();
        }
    };

    const setDraftValue = (key, value) => setDraft(prev => {
        const next = {...prev, [key]: value};
        // When the Name matches a catalog entry, pre-fill the matching fields (category, size, calories, ...).
        if (key === 'name' && hasNameField) {
            const entry = catalogByName[String(value).trim().toLowerCase()];
            if (entry) {
                CATALOG_KEYS.forEach(k => {
                    if (k !== 'name' && fieldKeySet.has(k) && entry[k] != null && entry[k] !== '') {
                        next[k] = entry[k];
                    }
                });
            }
        }
        return next;
    });

    const submitDraft = () => {
        const hasValue = Object.entries(draft).some(([k, v]) => !k.endsWith('_unit') && v !== '' && v != null);
        if (!hasValue) {
            return;
        }
        onChange([...items, {...draft, id: nextId(items)}]);
        setDraft(emptyItem(fields));
        focusFirst();
    };

    const startEdit = (item) => setEdits(prev => ({...prev, [item.id]: {...item}}));
    const setEditValue = (id, key, value) =>
        setEdits(prev => ({...prev, [id]: {...prev[id], [key]: value}}));

    const saveEdit = (id) => {
        onChange(items.map(i => i.id === id ? edits[id] : i));
        setEdits(prev => {
            const next = {...prev};
            delete next[id];
            return next;
        });
    };

    const toggleSelected = (id) => setSelected(prev => {
        const next = new Set(prev);
        next.has(id) ? next.delete(id) : next.add(id);
        return next;
    });

    const removeSelected = () => {
        if (selected.size === 0) {
            return;
        }
        onChange(items.filter(i => !selected.has(i.id)));
        setSelected(new Set());
    };

    const sortedFields = [...fields].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

    return <>
        {/* Shared location suggestions (pooled across all inventories), referenced by location-field inputs. */}
        {hasLocationField &&
            <datalist id={LOCATION_LIST_ID}>
                {(locations || []).map(l => <option key={l} value={l}/>)}
            </datalist>}
        {/* Food-catalog name suggestions; selecting one pre-fills the matching fields. */}
        {hasNameField && (catalog || []).length > 0 &&
            <datalist id={CATALOG_LIST_ID}>
                {catalog.map(e => <option key={e.id ?? e.name} value={e.name}/>)}
            </datalist>}
        {selected.size > 0 &&
            <Button color='red' onClick={removeSelected} style={{marginBottom: '0.5em'}}>
                Delete {selected.size} selected
            </Button>}
        <Table celled unstackable sortable>
            <TableHeader>
                <TableRow>
                    <TableHeaderCell collapsing/>
                    {sortedFields.map(f => <TableHeaderCell
                        key={f.key}
                        sorted={sort && sort.key === f.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                        onClick={() => toggleSort(f.key)}
                        style={{cursor: 'pointer'}}>
                        {f.label}
                    </TableHeaderCell>)}
                </TableRow>
            </TableHeader>
            <TableBody>
                {visibleItems.map(item => {
                    const editing = edits[item.id];
                    const expired = isExpired(item);
                    return <TableRow key={item.id} negative={expired}>
                        <TableCell collapsing>
                            <Checkbox checked={selected.has(item.id)} onChange={() => toggleSelected(item.id)}/>
                            {expired && <Icon name='warning sign' color='red' title='Expired'
                                              style={{marginLeft: '0.4em'}}/>}
                        </TableCell>
                        {sortedFields.map(f => <TableCell key={f.key}>
                            {editing
                                ? <FieldCell
                                    field={f}
                                    value={editing[f.key]}
                                    unitValue={editing[`${f.key}_unit`]}
                                    onChange={v => setEditValue(item.id, f.key, v)}
                                    onUnitChange={v => setEditValue(item.id, `${f.key}_unit`, v)}
                                    onEnter={() => saveEdit(item.id)}
                                    listId={listIdFor(f)}
                                />
                                : <span onClick={() => startEdit(item)} style={{cursor: 'pointer'}}>
                                    {formatValue(item, f)}
                                </span>}
                        </TableCell>)}
                    </TableRow>;
                })}
                {search && visibleItems.length === 0 && (items || []).length > 0 &&
                    <TableRow>
                        <TableCell colSpan={sortedFields.length + 1} style={{opacity: 0.7}}>
                            No items match "{search}".
                        </TableCell>
                    </TableRow>}
            </TableBody>
            <TableFooter>
                {/* The persistent new-item entry row. */}
                <TableRow>
                    <TableCell collapsing>
                        <Button primary size='mini' onClick={submitDraft} aria-label='Add item'>+</Button>
                    </TableCell>
                    {sortedFields.map((f, index) => <TableCell key={f.key}>
                        <FieldCell
                            field={f}
                            value={draft[f.key]}
                            unitValue={draft[`${f.key}_unit`]}
                            onChange={v => setDraftValue(f.key, v)}
                            onUnitChange={v => setDraftValue(`${f.key}_unit`, v)}
                            onEnter={submitDraft}
                            inputRef={index === 0 ? firstInputRef : undefined}
                            listId={listIdFor(f)}
                        />
                    </TableCell>)}
                </TableRow>
            </TableFooter>
        </Table>
    </>;
}

// Format an item's value for a field for display (shared with the read-only mobile view).
export function formatValue(item, field) {
    const value = item[field.key];
    if (value === '' || value == null) {
        return '';
    }
    if (field.type === 'quantity') {
        const unit = item[`${field.key}_unit`] || field.unit || '';
        return `${value} ${unit}`.trim();
    }
    return String(value);
}

// True when any `date`-type field is before the start of today (item is expired).
export function isItemExpired(item, fields) {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    return (fields || []).some(f => {
        if (f.type !== 'date') {
            return false;
        }
        const t = Date.parse(item[f.key]);
        return !isNaN(t) && t < start.getTime();
    });
}

/**
 * Filter items by a free-text search across every column's displayed value (using the same formatting as the
 * table, so quantities match as "30 lb", dates as "2030-01-01", etc.).  Case-insensitive; whitespace-separated
 * terms are AND-ed.  A blank search returns all items.  Shared by the Items table, Summary, and export views.
 */
export function filterItems(items, fields, search) {
    const query = (search || '').trim().toLowerCase();
    if (!query) {
        return items || [];
    }
    const terms = query.split(/\s+/);
    const cols = [...(fields || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    return (items || []).filter(item => {
        const haystack = cols.map(f => formatValue(item, f)).join(' ').toLowerCase();
        return terms.every(term => haystack.includes(term));
    });
}
