import React from "react";
import {Input, Select} from "semantic-ui-react";
import {ALL_UNITS, UNIT_GROUPS} from "./units";

// Renders the correct editor for a single field/value, wiring up keyboard navigation.  The `inputRef` is attached
// to the primary <input> so the parent table can focus the first cell of a new row.
//
// Props:
//   field    - {key, label, type, unit?, options?}
//   value    - the current item value for field.key
//   unitValue- the current unit (for quantity fields; stored under `${key}_unit`)
//   onChange(value)      - value changed
//   onUnitChange(unit)   - quantity unit changed
//   onEnter()            - Enter pressed (submit row)
//   inputRef             - ref attached to the primary input
export function FieldCell({field, value, unitValue, onChange, onUnitChange, onEnter, inputRef, listId}) {
    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && onEnter) {
            e.preventDefault();
            onEnter();
        }
    };

    const common = {
        value: value ?? '',
        onChange: (e, data) => onChange(data ? data.value : e.target.value),
        onKeyDown: handleKeyDown,
        'aria-label': field.label,
        name: field.key,
    };

    if (field.type === 'select') {
        const options = (field.options || []).map(o => ({key: o, value: o, text: o}));
        // Allow clearing.
        return <Select
            fluid search clearable selection
            name={field.key}
            options={options}
            placeholder={field.label}
            value={value ?? ''}
            onChange={(e, data) => onChange(data.value)}
            onKeyDown={handleKeyDown}
            aria-label={field.label}
        />;
    }

    if (field.type === 'date') {
        return <Input {...common} type='date' fluid ref={inputRef}/>;
    }

    if (field.type === 'number' || field.type === 'calories') {
        // `calories` is a number (kcal per unit) that the Summary's ration estimate detects by type.
        return <Input {...common} type='number' fluid ref={inputRef}/>;
    }

    if (field.type === 'quantity') {
        const unitOptions = ALL_UNITS.map(u => ({key: u, value: u, text: u}));
        return <Input
            type='number'
            fluid
            ref={inputRef}
            name={field.key}
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label={field.label}
            label={<Select
                compact
                name={`${field.key}_unit`}
                options={unitOptions}
                value={unitValue ?? field.unit ?? ''}
                onChange={(e, data) => onUnitChange(data.value)}
                aria-label={`${field.label} unit`}
            />}
            labelPosition='right'
        />;
    }

    if (field.type === 'location') {
        // Native datalist autocomplete fed by all inventories' locations (basement, attic, ...).  Using a datalist
        // (rather than a Dropdown) keeps it a real text input, so the Tab/Enter row-entry flow still works.
        return <Input {...common} fluid ref={inputRef} list={listId}/>;
    }

    // text / fallback (supports a datalist via listId, e.g. catalog name suggestions on the Name field).
    return <Input {...common} fluid ref={inputRef} list={listId}/>;
}

// The list of selectable unit groups, re-exported for the field editor.
export {UNIT_GROUPS};
