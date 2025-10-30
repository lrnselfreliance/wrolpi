import React from 'react';
import {render, renderInDarkMode, renderInLightMode, hasInvertedStyling, screen, waitFor, createTestForm} from '../../test-utils';
import {CollectionEditForm} from './CollectionEditForm';
import {createMockMetadata, createMockDomain} from '../../test-utils';

// Mock the TagsSelector component and TagsContext
jest.mock('../../Tags', () => ({
    TagsSelector: ({selectedTagNames, onChange, disabled}) => (
        <div data-testid="tags-selector" data-disabled={disabled}>
            <input
                data-testid="tags-input"
                value={selectedTagNames?.join(',') || ''}
                onChange={(e) => onChange(e.target.value ? [e.target.value] : [])}
                disabled={disabled}
            />
        </div>
    ),
    TagsContext: {
        _currentValue: {
            SingleTag: ({name}) => <span data-testid="applied-tag">{name}</span>
        }
    },
}));

// Mock Common components
jest.mock('../Common', () => ({
    ...jest.requireActual('../Common'),
    WROLModeMessage: () => <div data-testid="wrol-mode-message" />,
}));

// Mock DestinationForm (used for directory field)
jest.mock('../Download', () => ({
    DestinationForm: ({form, label, name}) => (
        <div data-testid="directory-search">
            <label>{label}</label>
            <input
                value={form.formData[name] || ''}
                onChange={(e) => form.setValue(name, e.target.value)}
            />
        </div>
    ),
}));

// Mock InputForm (used for text fields)
jest.mock('../../hooks/useForm', () => ({
    ...jest.requireActual('../../hooks/useForm'),
    InputForm: ({form, label, name}) => (
        <div data-testid={`input-${name}`}>
            <label>{label}</label>
            <input
                value={form.formData[name] || ''}
                onChange={(e) => form.setValue(name, e.target.value)}
            />
        </div>
    ),
}));

describe('CollectionEditForm', () => {
    const mockMetadata = createMockMetadata();
    const mockCollection = createMockDomain();

    describe('Form Rendering', () => {
        it('renders all configured fields', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            // Check that all fields from metadata are rendered
            expect(screen.getByTestId('directory-search')).toBeInTheDocument();
            expect(screen.getByTestId('tags-selector')).toBeInTheDocument();
            expect(screen.getByPlaceholderText(/optional description/i)).toBeInTheDocument();

            // Verify Save button exists
            expect(screen.getByRole('button', {name: /save/i})).toBeInTheDocument();
        });

        it('loads initial values into form', () => {
            const collectionWithData = createMockDomain({
                description: 'Test description',
                directory: 'archive/example.com'
            });

            const form = createTestForm(collectionWithData);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            // Check description is loaded
            expect(screen.getByPlaceholderText(/optional description/i)).toHaveValue('Test description');
            // Check directory field is rendered with the value
            const directoryField = screen.getByTestId('directory-search');
            expect(directoryField).toBeInTheDocument();
            // The mocked DestinationForm renders an input inside the container
            const directoryInput = directoryField.querySelector('input');
            expect(directoryInput).toHaveValue('archive/example.com');
        });

        it('renders without errors when form is provided', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            expect(screen.getByRole('button', {name: /save/i})).toBeInTheDocument();
        });
    });

    describe('Field Types', () => {
        it('renders textarea for description field', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            const descriptionField = screen.getByPlaceholderText(/optional description/i);
            expect(descriptionField.tagName).toBe('TEXTAREA');
        });

        it('renders directory field using DestinationForm', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            expect(screen.getByTestId('directory-search')).toBeInTheDocument();
        });

        it('renders tag selector for tag_name field', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            expect(screen.getByTestId('tags-selector')).toBeInTheDocument();
        });
    });

    describe('Field Dependencies (tag requires directory)', () => {
        it('disables tag field when directory is empty', () => {
            const collectionWithoutDirectory = createMockDomain({
                directory: '',
                can_be_tagged: false
            });

            const form = createTestForm(collectionWithoutDirectory);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            // Should show dependency warning
            expect(screen.getByText(/set a directory to enable tagging/i)).toBeInTheDocument();

            // Tag selector should be disabled
            const tagSelector = screen.getByTestId('tags-selector');
            expect(tagSelector).toHaveAttribute('data-disabled', 'true');
        });

        it('enables tag field when directory is set', () => {
            const collectionWithDirectory = createMockDomain({
                directory: 'archive/example.com',
                can_be_tagged: true
            });

            const form = createTestForm(collectionWithDirectory);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            // Dependency warning should not be shown
            expect(screen.queryByText(/set a directory to enable tagging/i)).not.toBeInTheDocument();

            // Tag selector should not be disabled
            const tagSelector = screen.getByTestId('tags-selector');
            expect(tagSelector).toHaveAttribute('data-disabled', 'false');
        });

        it('shows warning when tag is set with directory', () => {
            const collectionWithDirectoryAndTag = createMockDomain({
                directory: 'archive/example.com',
                tag_name: 'News',
                can_be_tagged: true
            });

            const form = createTestForm(collectionWithDirectoryAndTag);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            // Should show tag warning
            expect(screen.getByText(/tagging will move files/i)).toBeInTheDocument();
        });
    });

    describe('Save/Cancel Actions', () => {
        it('shows Cancel button when onCancel provided', () => {
            const form = createTestForm(mockCollection);
            const mockOnCancel = jest.fn();

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                    onCancel={mockOnCancel}
                />
            );

            expect(screen.getByRole('button', {name: /cancel/i})).toBeInTheDocument();
        });

        it('disables form during loading', () => {
            const form = createTestForm(mockCollection, {
                overrides: {loading: true, disabled: true}
            });

            render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            // Save button should be disabled during loading
            const saveButton = screen.getByRole('button', {name: /save/i});
            expect(saveButton).toBeDisabled();
        });
    });

    describe('Error States', () => {
        it('handles missing metadata gracefully', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm
                    form={form}
                    metadata={null}
                />
            );

            // Should show warning about missing metadata
            expect(screen.getByText(/no metadata available/i)).toBeInTheDocument();
        });
    });

    describe('Theme Integration', () => {
        it('applies inverted styling to Segment in dark mode', () => {
            const form = createTestForm(mockCollection);

            const {container} = renderInDarkMode(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            // Segment should have inverted class in dark mode
            const segment = container.querySelector('.ui.segment');
            expect(segment).toBeInTheDocument();
            expect(hasInvertedStyling(segment)).toBe(true);
        });

        it('does not apply inverted styling in light mode', () => {
            const form = createTestForm(mockCollection);

            const {container} = renderInLightMode(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            // Segment should NOT have inverted class in light mode
            const segment = container.querySelector('.ui.segment');
            expect(segment).toBeInTheDocument();
            expect(hasInvertedStyling(segment)).toBe(false);
        });

        it('applies dark theme styling to Header in dark mode', () => {
            const form = createTestForm(mockCollection);

            const {container} = renderInDarkMode(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                    title="Test Collection"
                />
            );

            // Header should have dark text color inline style in dark mode
            const header = container.querySelector('.ui.header');
            expect(header).toBeInTheDocument();
            expect(header.style.color).toBe('rgb(238, 238, 238)');  // #eeeeee
        });

        it('uses theme context from provider', () => {
            const form = createTestForm(mockCollection);

            const {container} = render(
                <CollectionEditForm
                    form={form}
                    metadata={mockMetadata}
                />
            );

            const segment = container.querySelector('.ui.segment');
            expect(segment).toBeInTheDocument();
            // Should not be inverted by default
            expect(hasInvertedStyling(segment)).toBe(false);
        });
    });
});
