import React from "react";
import {fireEvent, render, screen} from "@testing-library/react";
import {FieldSchemaEditor} from "./FieldSchemaEditor";

const FIELDS = [
    {key: 'name', label: 'Name', type: 'text', order: 0},
    {key: 'category', label: 'Category', type: 'select', options: [], order: 1},
];

describe('FieldSchemaEditor select options', () => {
    test('typing a comma is preserved while editing (does not get swallowed)', () => {
        render(<FieldSchemaEditor fields={FIELDS} open={true} onClose={jest.fn()} onSave={jest.fn()}/>);
        const optionsInput = screen.getByPlaceholderText('comma,separated,options');

        // Typing the comma after the first option must not be stripped — otherwise a second option can't be started.
        fireEvent.change(optionsInput, {target: {value: 'screws,'}});
        expect(optionsInput.value).toBe('screws,');

        fireEvent.change(optionsInput, {target: {value: 'screws,nails'}});
        expect(optionsInput.value).toBe('screws,nails');
    });

    test('"Count by Weight" adds the linked weight + computed-count fields and they persist on save', async () => {
        const onSave = jest.fn();
        render(<FieldSchemaEditor fields={[{key: 'name', label: 'Name', type: 'text'}]}
                                  open={true} onClose={jest.fn()} onSave={onSave}/>);

        fireEvent.click(screen.getByText('Count by Weight'));
        // The note appears on the computed Count row.
        expect(screen.getByText(/Total Weight ÷ Unit Weight/)).toBeTruthy();

        fireEvent.click(screen.getByText('Save Fields'));
        const saved = onSave.mock.calls[0][0];
        const byKey = Object.fromEntries(saved.map(f => [f.key, f]));
        expect(byKey.unit_weight).toMatchObject({type: 'quantity', unit: 'g'});
        expect(byKey.total_weight).toMatchObject({type: 'quantity', unit: 'g'});
        // The compute metadata survives save() so the table can auto-fill the count.
        expect(byKey.count.compute).toEqual({kind: 'count_by_weight', total: 'total_weight', unit: 'unit_weight'});
    });

    test('options are trimmed and emptied-out on save', async () => {
        const onSave = jest.fn();
        render(<FieldSchemaEditor fields={FIELDS} open={true} onClose={jest.fn()} onSave={onSave}/>);
        const optionsInput = screen.getByPlaceholderText('comma,separated,options');

        fireEvent.change(optionsInput, {target: {value: 'screws, nails ,'}});
        fireEvent.click(screen.getByText('Save Fields'));

        const savedFields = onSave.mock.calls[0][0];
        const category = savedFields.find(f => f.key === 'category');
        expect(category.options).toEqual(['screws', 'nails']);
    });
});
