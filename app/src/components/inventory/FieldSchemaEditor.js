import React, {useState} from "react";
import {Button, Icon, IconButton, Modal, Select, Table, TextInput, Toggle} from "../ui";
import {ALL_UNITS} from "./units";
import {addCountByWeightFields, isCountByWeight} from "./computeFields";

const FIELD_TYPE_OPTIONS = ['text', 'number', 'quantity', 'date', 'select', 'location', 'calories']
    .map(t => ({value: t, label: t}));

const UNIT_OPTIONS = ALL_UNITS.map(u => ({value: u, label: u}));

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
    // Add the "count by weight" fields (Unit Weight, Total Weight, computed Count); links an existing Count field.
    const addCountByWeight = () => setDraft(prev => addCountByWeightFields(prev));

    const save = async () => {
        // Fill any missing keys from labels and normalize order.
        const cleaned = draft
            .filter(f => f.label || f.key)
            .map((f, index) => {
                const field = {
                    ...f,
                    key: f.key || slugifyKey(f.label),
                    label: f.label || f.key,
                    order: index,
                };
                // Clean select options here (not on every keystroke) so commas survive while typing.
                if (f.type === 'select') {
                    field.options = (f.options || []).map(s => s.trim()).filter(Boolean);
                }
                return field;
            });
        await onSave(cleaned);
        onClose();
    };

    return <Modal open={open} onClose={onClose} closeIcon size='large'>
        <Modal.Header>Customize Fields</Modal.Header>
        <Modal.Content scrolling>
            <Table>
                <Table.Header>
                    <Table.Row>
                        <Table.HeaderCell>Order</Table.HeaderCell>
                        <Table.HeaderCell>Label</Table.HeaderCell>
                        <Table.HeaderCell>Type</Table.HeaderCell>
                        <Table.HeaderCell>Unit / Options</Table.HeaderCell>
                        <Table.HeaderCell style={{textAlign: 'center'}}
                                           title='Show this field in the read-only portrait-mobile view'>
                            Mobile
                        </Table.HeaderCell>
                        <Table.HeaderCell/>
                    </Table.Row>
                </Table.Header>
                <Table.Body>
                    {draft.map((f, index) => <Table.Row key={index}>
                        <Table.Cell>
                            <div className='wrolpi-button-row'>
                                <IconButton size='xs' icon='arrow up' onClick={() => move(index, -1)}
                                            disabled={index === 0} label='Move up'/>
                                <IconButton size='xs' icon='arrow down' onClick={() => move(index, 1)}
                                            disabled={index === draft.length - 1} label='Move down'/>
                            </div>
                        </Table.Cell>
                        <Table.Cell>
                            <TextInput value={f.label || ''} placeholder='Label'
                                       onChange={e => update(index, {label: e.currentTarget.value})}/>
                        </Table.Cell>
                        <Table.Cell>
                            <Select data={FIELD_TYPE_OPTIONS} value={f.type}
                                    onChange={value => update(index, {type: value})}/>
                        </Table.Cell>
                        <Table.Cell>
                            {f.type === 'quantity' &&
                                <Select searchable data={UNIT_OPTIONS} value={f.unit || ''}
                                        placeholder='Default unit'
                                        onChange={value => update(index, {unit: value})}/>}
                            {f.type === 'select' &&
                                /* Keep the raw split (no trim/filter) so typing a comma to start the next option
                                   isn't swallowed mid-edit; options are trimmed/cleaned on save(). */
                                <TextInput placeholder='comma,separated,options'
                                           value={(f.options || []).join(',')}
                                           onChange={e => update(index, {options: e.currentTarget.value.split(',')})}/>}
                            {isCountByWeight(f) &&
                                <span style={{opacity: 0.7, fontSize: '0.9em'}}>
                                    <Icon name='calculator'/> Auto-counted: Total Weight ÷ Unit Weight
                                </span>}
                        </Table.Cell>
                        <Table.Cell style={{textAlign: 'center'}}>
                            <Toggle checked={!!f.mobile} aria-label={`Show ${f.label || f.key} on mobile`}
                                    onChange={e => update(index, {mobile: e.currentTarget.checked})}/>
                        </Table.Cell>
                        <Table.Cell>
                            <IconButton role='danger' size='xs' icon='trash' onClick={() => remove(index)}
                                        label='Remove field'/>
                        </Table.Cell>
                    </Table.Row>)}
                </Table.Body>
            </Table>
            <div className='wrolpi-button-row'>
                <Button icon='plus' onClick={add}>Add Field</Button>
                <Button icon='balance scale' onClick={addCountByWeight}
                        title='Add Unit Weight, Total Weight, and an auto-counted Count'>
                    Count by Weight
                </Button>
            </div>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>Cancel</Button>
            <Button role='save' onClick={save}>Save Fields</Button>
        </Modal.Actions>
    </Modal>;
}
