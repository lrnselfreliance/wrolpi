import React, {useState} from "react";
import {Input, Select, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {Button, Header, Icon, Modal, Table} from "../Theme";
import {ALL_UNITS} from "./units";

const UNIT_OPTIONS = [{key: '', value: '', text: '—'}, ...ALL_UNITS.map(u => ({key: u, value: u, text: u}))];

const COLUMNS = [
    {key: 'name', label: 'Name', width: 4},
    {key: 'category', label: 'Category', width: 3},
    {key: 'subcategory', label: 'Subcategory', width: 3},
    {key: 'item_size', label: 'Size', width: 2},
    {key: 'item_size_unit', label: 'Unit', width: 2},
    {key: 'calories', label: 'kcal', width: 2},
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

    return <Modal open={open} onClose={onClose} closeIcon size='fullscreen'>
        <Modal.Header>Food Catalog</Modal.Header>
        <Modal.Content scrolling>
            <p style={{opacity: 0.8}}>
                Known items used to autocomplete and pre-fill the entry form. <strong>kcal</strong> is the total
                calories for one package of the given size.
            </p>
            <Button onClick={add} style={{marginBottom: '0.5em'}}><Icon name='plus'/>Add Item</Button>
            <Table celled unstackable compact>
                <TableHeader>
                    <TableRow>
                        {COLUMNS.map(c => <TableHeaderCell key={c.key} width={c.width}>{c.label}</TableHeaderCell>)}
                        <TableHeaderCell collapsing/>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {draft.map((entry, index) => {
                        const aria = (col) => `${entry.name || 'new item'} ${col}`;
                        return <TableRow key={entry.id ?? `new-${index}`}>
                        <TableCell>
                            <Input fluid name='catalog-name' aria-label={aria('name')} value={entry.name || ''}
                                   placeholder='Name' onChange={e => update(index, 'name', e.target.value)}/>
                        </TableCell>
                        <TableCell>
                            <Input fluid name='catalog-category' aria-label={aria('category')}
                                   value={entry.category || ''}
                                   onChange={e => update(index, 'category', e.target.value)}/>
                        </TableCell>
                        <TableCell>
                            <Input fluid name='catalog-subcategory' aria-label={aria('subcategory')}
                                   value={entry.subcategory || ''}
                                   onChange={e => update(index, 'subcategory', e.target.value)}/>
                        </TableCell>
                        <TableCell>
                            <Input fluid type='number' name='catalog-size' aria-label={aria('size')}
                                   value={entry.item_size || ''}
                                   onChange={e => update(index, 'item_size', e.target.value)}/>
                        </TableCell>
                        <TableCell>
                            <Select compact search name='catalog-unit' aria-label={aria('unit')} options={UNIT_OPTIONS}
                                    value={entry.item_size_unit || ''}
                                    onChange={(e, data) => update(index, 'item_size_unit', data.value)}/>
                        </TableCell>
                        <TableCell>
                            <Input fluid type='number' name='catalog-calories' aria-label={aria('calories')}
                                   value={entry.calories || ''}
                                   onChange={e => update(index, 'calories', e.target.value)}/>
                        </TableCell>
                        <TableCell collapsing>
                            <Button color='red' icon size='mini' aria-label='Remove'
                                    onClick={() => remove(index)}><Icon name='trash'/></Button>
                        </TableCell>
                    </TableRow>;
                    })}
                </TableBody>
            </Table>
        </Modal.Content>
        <Modal.Actions>
            <Button onClick={onClose}>Cancel</Button>
            <Button primary onClick={save}>Save Catalog</Button>
        </Modal.Actions>
    </Modal>;
}
