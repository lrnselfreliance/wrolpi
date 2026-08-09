import React, {useState} from "react";
import {Button, IconButton, Modal, Select, Table, Text, TextInput} from "../ui";
import {ALL_UNITS} from "./units";

const UNIT_OPTIONS = [{value: '', label: '—'}, ...ALL_UNITS.map(u => ({value: u, label: u}))];

const COLUMNS = [
    {key: 'name', label: 'Name'},
    {key: 'category', label: 'Category'},
    {key: 'subcategory', label: 'Subcategory'},
    {key: 'item_size', label: 'Size'},
    {key: 'item_size_unit', label: 'Unit'},
    {key: 'calories', label: 'kcal'},
];

function blankEntry() {
    return {name: '', category: '', subcategory: '', item_size: '', item_size_unit: '', calories: ''};
}

/**
 * Manage the shared food catalog: a scrollable, editable table (add/edit/delete) saved as a whole list.  Each
 * entry's `calories` is the total for one `item_size` package — the value pre-filled onto inventory items.
 */
export function CatalogEditor({catalog, open, onClose, onSave}) {
    const [draft, setDraft] = useState([]);

    React.useEffect(() => {
        if (open) {
            setDraft((catalog || []).map(e => ({...e})));
        }
    }, [open, catalog]);

    const update = (index, key, value) =>
        setDraft(prev => prev.map((e, i) => i === index ? {...e, [key]: value} : e));
    const remove = (index) => setDraft(prev => prev.filter((_, i) => i !== index));
    const add = () => setDraft(prev => [blankEntry(), ...prev]);

    const save = async () => {
        // Drop fully-empty rows.
        const cleaned = draft.filter(e => (e.name || '').trim());
        await onSave(cleaned);
        onClose();
    };

    return <Modal open={open} onClose={onClose} size='fullscreen'>
        <Modal.Header>Food Catalog</Modal.Header>
        <Modal.Content>
            <Text size='sm' c='dimmed' mb='sm'>
                Known items used to autocomplete and pre-fill the entry form. <strong>kcal</strong> is the total
                calories for one package of the given size.
            </Text>
            <Button onClick={add} icon='plus' style={{marginBottom: '0.5em'}}>Add Item</Button>
            <Table>
                <Table.Header>
                    <Table.Row>
                        {COLUMNS.map(c => <Table.HeaderCell key={c.key}>{c.label}</Table.HeaderCell>)}
                        <Table.HeaderCell/>
                    </Table.Row>
                </Table.Header>
                <Table.Body>
                    {draft.map((entry, index) => {
                        const aria = (col) => `${entry.name || 'new item'} ${col}`;
                        return <Table.Row key={entry.id ?? `new-${index}`}>
                        <Table.Cell>
                            <TextInput name='catalog-name' aria-label={aria('name')} value={entry.name || ''}
                                   placeholder='Name' onChange={e => update(index, 'name', e.currentTarget.value)}/>
                        </Table.Cell>
                        <Table.Cell>
                            <TextInput name='catalog-category' aria-label={aria('category')}
                                   value={entry.category || ''}
                                   onChange={e => update(index, 'category', e.currentTarget.value)}/>
                        </Table.Cell>
                        <Table.Cell>
                            <TextInput name='catalog-subcategory' aria-label={aria('subcategory')}
                                   value={entry.subcategory || ''}
                                   onChange={e => update(index, 'subcategory', e.currentTarget.value)}/>
                        </Table.Cell>
                        <Table.Cell>
                            <TextInput type='number' name='catalog-size' aria-label={aria('size')}
                                   value={entry.item_size || ''}
                                   onChange={e => update(index, 'item_size', e.currentTarget.value)}/>
                        </Table.Cell>
                        <Table.Cell>
                            <Select searchable name='catalog-unit' aria-label={aria('unit')} data={UNIT_OPTIONS}
                                    value={entry.item_size_unit || ''}
                                    onChange={value => update(index, 'item_size_unit', value)}/>
                        </Table.Cell>
                        <Table.Cell>
                            <TextInput type='number' name='catalog-calories' aria-label={aria('calories')}
                                   value={entry.calories || ''}
                                   onChange={e => update(index, 'calories', e.currentTarget.value)}/>
                        </Table.Cell>
                        <Table.Cell>
                            <IconButton role='danger' icon='trash' label='Remove'
                                    onClick={() => remove(index)}/>
                        </Table.Cell>
                    </Table.Row>;
                    })}
                </Table.Body>
            </Table>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>Cancel</Button>
            <Button role='save' onClick={save}>Save Catalog</Button>
        </Modal.Actions>
    </Modal>;
}
