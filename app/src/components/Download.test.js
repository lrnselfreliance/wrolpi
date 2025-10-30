import React from 'react';
import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {DestinationForm} from './Download';
import {createTestForm} from '../test-utils';

// Mock DirectorySearch component - simplified to avoid useState/useEffect warnings
jest.mock('./Common', () => {
    const React = require('react');
    return {
        ...jest.requireActual('./Common'),
        DirectorySearch: ({value, onSelect, disabled, required, id}) => (
            <div data-testid="directory-search-mock">
                <input
                    data-testid="directory-search-input"
                    defaultValue={value || ''}
                    onChange={(e) => onSelect(e.target.value)}
                    disabled={disabled}
                    required={required}
                    id={id}
                />
            </div>
        ),
        RequiredAsterisk: () => React.createElement('span', null, '*'),
        InfoPopup: ({content}) => React.createElement('span', {'data-testid': 'info-popup'}, content),
    };
});

describe('DestinationForm', () => {
    describe('Form Integration', () => {
        it('renders DirectorySearch with form value', () => {
            const form = createTestForm(
                {destination: 'videos/test'},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} />);

            const input = screen.getByTestId('directory-search-input');
            expect(input).toHaveValue('videos/test');
        });

        it('calls form onChange when directory is selected', async () => {
            const form = createTestForm(
                {destination: ''},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} />);

            const input = screen.getByTestId('directory-search-input');

            // Type a new directory
            await userEvent.type(input, 'archive/new');

            // Form data should be updated
            await waitFor(() => {
                expect(form.formData.destination).toBe('archive/new');
            });
        });


        it('displays required indicator when required=true', () => {
            const form = createTestForm(
                {destination: ''},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} required />);

            const input = screen.getByTestId('directory-search-input');
            expect(input).toHaveAttribute('required');
        });
    });

    describe('Props Handling', () => {
        it('uses custom label when provided', () => {
            const form = createTestForm(
                {destination: ''},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} label="Custom Folder" />);

            expect(screen.getByText(/custom folder/i)).toBeInTheDocument();
        });

        it('uses default label when not provided', () => {
            const form = createTestForm(
                {destination: ''},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} />);

            expect(screen.getByText(/destination/i)).toBeInTheDocument();
        });

        it('uses custom name/path when provided', () => {
            const form = createTestForm(
                {output_dir: 'videos/test'},
                {overrides: {ready: true, loading: false}}
            );

            render(
                <DestinationForm
                    form={form}
                    name="output_dir"
                    path="output_dir"
                />
            );

            const input = screen.getByTestId('directory-search-input');
            expect(input).toHaveValue('videos/test');
        });

        it('shows info popup when infoContent provided', () => {
            const form = createTestForm(
                {destination: ''},
                {overrides: {ready: true, loading: false}}
            );

            render(
                <DestinationForm
                    form={form}
                    infoContent="This is helpful information"
                />
            );

            expect(screen.getByText(/this is helpful information/i)).toBeInTheDocument();
        });
    });

    describe('useForm Integration', () => {
        it('gets correct props from form.getCustomProps', () => {
            const form = createTestForm(
                {destination: 'videos/initial'},
                {overrides: {ready: true, loading: false}}
            );

            const getCustomPropsSpy = jest.spyOn(form, 'getCustomProps');

            render(<DestinationForm form={form} required />);

            expect(getCustomPropsSpy).toHaveBeenCalledWith({
                name: 'destination',
                path: 'destination',
                required: true
            });
        });

        it('updates form data on selection', async () => {
            const form = createTestForm(
                {destination: ''},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} />);

            const input = screen.getByTestId('directory-search-input');

            // Select a directory
            await userEvent.type(input, 'videos/new-folder');

            // Form should be updated
            await waitFor(() => {
                expect(form.formData.destination).toBe('videos/new-folder');
            });
        });

    });

    describe('Edge Cases', () => {

        it('works with nested form paths', () => {
            const form = createTestForm(
                {config: {output: {destination: 'videos/nested'}}},
                {overrides: {ready: true, loading: false}}
            );

            render(
                <DestinationForm
                    form={form}
                    path="config.output.destination"
                    name="destination"
                />
            );

            const input = screen.getByTestId('directory-search-input');
            expect(input).toHaveValue('videos/nested');
        });

        it('handles concurrent field updates', async () => {
            const form = createTestForm(
                {destination: '', title: ''},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} />);

            const input = screen.getByTestId('directory-search-input');

            // Simulate rapid updates
            await userEvent.type(input, 'videos/a');
            form.setValue('title', 'Test Title');
            await userEvent.type(input, 'bc');

            // Destination should have full value
            await waitFor(() => {
                expect(form.formData.destination).toBe('videos/abc');
            });

            // Title should also be set
            expect(form.formData.title).toBe('Test Title');
        });

        it('handles empty string as initial value', () => {
            const form = createTestForm(
                {destination: ''},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} />);

            const input = screen.getByTestId('directory-search-input');
            expect(input).toHaveValue('');
        });

        it('handles null as initial value', () => {
            const form = createTestForm(
                {destination: null},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} />);

            const input = screen.getByTestId('directory-search-input');
            expect(input).toHaveValue('');
        });

        it('handles undefined as initial value', () => {
            const form = createTestForm(
                {},
                {overrides: {ready: true, loading: false}}
            );

            render(<DestinationForm form={form} />);

            const input = screen.getByTestId('directory-search-input');
            expect(input).toHaveValue('');
        });
    });
});
