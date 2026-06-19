import React from "react";
import {Input, Select} from "semantic-ui-react";
import {ALL_UNITS, evaluateExpression, NUMERIC_TYPES, UNIT_GROUPS} from "./units";

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
//   autoFocus            - on mount, focus the input and select its contents (for rapid inline edits)
export function FieldCell({field, value, unitValue, onChange, onUnitChange, onEnter, inputRef, listId, autoFocus}) {
    // Merge the parent's `inputRef` (used to focus the draft row's first field) with a local ref we use to
    // focus + select this cell's contents when the user clicks it to edit.
    const localRef = React.useRef(null);
    const setRef = React.useCallback((node) => {
        localRef.current = node;
        if (typeof inputRef === 'function') {
            inputRef(node);
        } else if (inputRef) {
            inputRef.current = node;
        }
    }, [inputRef]);

    React.useEffect(() => {
        if (!autoFocus) {
            return;
        }
        const node = localRef.current;
        // Semantic's Input exposes the DOM <input> via `inputRef`; selecting its contents lets the user type over
        // the value immediately.  Other editors (e.g. Select) just take focus.
        const dom = node && node.inputRef && node.inputRef.current;
        if (dom) {
            dom.focus();
            if (dom.select) {
                dom.select();
            }
        } else if (node && node.focus) {
            node.focus();
        }
    }, [autoFocus]);

    const numeric = NUMERIC_TYPES.includes(field.type);

    // Evaluate an arithmetic expression in this field and swap in the result (no-op for a plain number).  Routed
    // through onChange so dependent logic (e.g. count-by-weight) recomputes from the resolved value.
    const resolveExpression = () => {
        const evaluated = evaluateExpression(value);
        // Compare against the raw value: evaluateExpression returns its input unchanged when there's no expression,
        // so a null/undefined backing value (an unfilled item field) compares equal and never spuriously fires.
        if (evaluated !== value) {
            onChange(evaluated);
            return true;
        }
        return false;
    };

    const handleKeyDown = (e) => {
        if (e.key !== 'Enter') {
            return;
        }
        // In a numeric field, the first Enter resolves a pending expression ("400 - 20" -> "380"); a second Enter
        // (now a plain number) submits the row as usual.
        if (numeric && resolveExpression()) {
            e.preventDefault();
            return;
        }
        if (onEnter) {
            e.preventDefault();
            onEnter();
        }
    };

    // Numeric fields accept arithmetic, so they are text inputs that evaluate on blur (Tab/click-away) and Enter.
    const onBlur = numeric ? resolveExpression : undefined;

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
            ref={setRef}
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
        return <Input {...common} type='date' fluid ref={setRef}/>;
    }

    if (field.type === 'number' || field.type === 'calories') {
        // `calories` is a number (kcal per unit) that the Summary's ration estimate detects by type.  Text (not
        // number) input so arithmetic expressions can be typed; evaluated on blur/Enter.
        return <Input {...common} type='text' inputMode='decimal' fluid ref={setRef} onBlur={onBlur}/>;
    }

    if (field.type === 'quantity') {
        const unitOptions = ALL_UNITS.map(u => ({key: u, value: u, text: u}));
        return <Input
            type='text'
            inputMode='decimal'
            fluid
            ref={setRef}
            name={field.key}
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={onBlur}
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
        return <Input {...common} fluid ref={setRef} list={listId}/>;
    }

    // text / fallback (supports a datalist via listId, e.g. catalog name suggestions on the Name field).
    return <Input {...common} fluid ref={setRef} list={listId}/>;
}

// The list of selectable unit groups, re-exported for the field editor.
export {UNIT_GROUPS};
