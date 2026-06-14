import React, {useState} from "react";
import {Input, Select, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {Button, Icon, Modal, Table} from "../Theme";
import {ALL_UNITS} from "./units";

const FIELD_TYPE_OPTIONS = ['text', 'number', 'quantity', 'date', 'select', 'location', 'calories']
    .map(t => ({key: t, value: t, text: t}));

const UNIT_OPTIONS = ALL_UNITS.map(u => ({key: u, value: u, text: u}));

function slugifyKey(label) {
    return (label || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'field';
}

/**
 * Modal editor for an inventory's field schema: add/remove/reorder/retype fields, set a quantity field's default
 * unit, and a select field's options.  Saves via PUT /<slug>/fields.
 */
export function FieldSchemaEditor({fields, open, onClose, onSave}) {
    const [draft, setDraft] = useState(() => fields.map(f => ({...f})));

    React.useEffect(() => {
        if (open) {
            setDraft(fields.map(f => ({...f})));
        }
    }, [open, fields]);

    const update = (index, patch) => setDraft(prev => prev.map((f, i) => i === index ? {...f, ...patch} : f));
    const remove = (index) => setDraft(prev => prev.filter((_, i) => i !== index));
    const move = (index, delta) => setDraft(prev => {
        const next = [...prev];
        const target = index + delta;
        if (target < 0 || target >= next.length) {
            return prev;
        }
        [next[index], next[target]] = [next[target], next[index]];
        return next;
    });
    const add = () => setDraft(prev => [...prev, {key: '', label: '', type: 'text'}]);

    const save = async () => {
        // Fill any missing keys from labels and normalize order.
        const cleaned = draft
            .filter(f => f.label || f.key)
            .map((f, index) => ({
                ...f,
                key: f.key || slugifyKey(f.label),
                label: f.label || f.key,
                order: index,
            }));
        await onSave(cleaned);
        onClose();
    };

    return <Modal open={open} onClose={onClose} closeIcon size='large'>
        <Modal.Header>Customize Fields</Modal.Header>
        <Modal.Content scrolling>
            {/* NOTE: do NOT use `fixed` here — semantic gives fixed-table cells `overflow:hidden`, which clips the
                Type/Unit dropdown menus to the cell height.  The `width` props below size the columns without it. */}
            <Table celled unstackable>
                <TableHeader>
                    <TableRow>
                        <TableHeaderCell width={2}>Order</TableHeaderCell>
                        <TableHeaderCell width={4}>Label</TableHeaderCell>
                        <TableHeaderCell width={4}>Type</TableHeaderCell>
                        <TableHeaderCell width={5}>Unit / Options</TableHeaderCell>
                        <TableHeaderCell width={1}/>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {draft.map((f, index) => <TableRow key={index}>
                        <TableCell collapsing>
                            <Button icon size='mini' onClick={() => move(index, -1)} disabled={index === 0}
                                    aria-label='Move up'><Icon name='arrow up'/></Button>
                            <Button icon size='mini' onClick={() => move(index, 1)}
                                    disabled={index === draft.length - 1}
                                    aria-label='Move down'><Icon name='arrow down'/></Button>
                        </TableCell>
                        <TableCell>
                            <Input fluid value={f.label || ''} placeholder='Label'
                                   onChange={e => update(index, {label: e.target.value})}/>
                        </TableCell>
                        <TableCell>
                            <Select fluid options={FIELD_TYPE_OPTIONS} value={f.type}
                                    onChange={(e, data) => update(index, {type: data.value})}/>
                        </TableCell>
                        <TableCell>
                            {f.type === 'quantity' &&
                                <Select fluid search options={UNIT_OPTIONS} value={f.unit || ''}
                                        placeholder='Default unit'
                                        onChange={(e, data) => update(index, {unit: data.value})}/>}
                            {f.type === 'select' &&
                                <Input fluid placeholder='comma,separated,options'
                                       value={(f.options || []).join(',')}
                                       onChange={e => update(index, {
                                           options: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                                       })}/>}
                        </TableCell>
                        <TableCell collapsing>
                            <Button color='red' icon size='mini' onClick={() => remove(index)}
                                    aria-label='Remove field'><Icon name='trash'/></Button>
                        </TableCell>
                    </TableRow>)}
                </TableBody>
            </Table>
            <Button onClick={add}><Icon name='plus'/>Add Field</Button>
        </Modal.Content>
        <Modal.Actions>
            <Button onClick={onClose}>Cancel</Button>
            <Button primary onClick={save}>Save Fields</Button>
        </Modal.Actions>
    </Modal>;
}
