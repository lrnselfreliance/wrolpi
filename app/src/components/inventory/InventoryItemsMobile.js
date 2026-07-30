import React from "react";
import {Icon, Table, Text} from "../ui";
import {formatValue, isItemExpired} from "./InventoryTable";

// Fallback columns for inventories whose schema predates the per-field `mobile` flag: these preferred keys in
// order, else the first few fields.
const FALLBACK_COLUMN_KEYS = ['name', 'subcategory', 'item_size', 'count'];

// The condensed columns for portrait mobile: fields the user flagged `mobile`, falling back to a sensible default
// when an older schema has none flagged.
export function mobileColumns(fields) {
    const ordered = [...(fields || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    const flagged = ordered.filter(f => f.mobile);
    if (flagged.length) {
        return flagged;
    }
    const preferred = ordered.filter(f => FALLBACK_COLUMN_KEYS.includes(f.key));
    if (preferred.length >= 4) {
        return preferred;
    }
    // Fewer than 4 preferred keys (e.g. old tool/fuel schemas) — show the first four fields instead.
    return ordered.slice(0, 4);
}

/**
 * Read-only, condensed inventory view for portrait mobile.  Shows only the fields flagged `mobile` (configurable in
 * the field-schema editor) and highlights expired rows; editing/sorting/adding happen in the full InventoryTable
 * (landscape / tablet+).
 */
export function InventoryItemsMobile({fields, items}) {
    const columns = mobileColumns(fields);

    return <>
        <Text size='sm' c='dimmed' mb='0.5em'>
            Read-only — rotate to landscape to edit.
        </Text>
        {(items || []).length === 0
            ? <Text>No items yet.</Text>
            : <Table>
                <Table.Header>
                    <Table.Row>
                        {columns.map(f => <Table.HeaderCell key={f.key}>{f.label}</Table.HeaderCell>)}
                    </Table.Row>
                </Table.Header>
                <Table.Body>
                    {items.map(item => {
                        const expired = isItemExpired(item, fields);
                        return <Table.Row key={item.id} failed={expired}>
                            {columns.map((f, idx) => <Table.Cell key={f.key}>
                                {idx === 0 && expired &&
                                    <Icon name='warning sign' label='Expired'
                                          style={{color: 'var(--red)', marginRight: '0.4em'}}/>}
                                {formatValue(item, f)}
                            </Table.Cell>)}
                        </Table.Row>;
                    })}
                </Table.Body>
            </Table>}
    </>;
}
