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
