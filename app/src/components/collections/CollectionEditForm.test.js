import React from 'react';
import {render, renderInDarkMode, renderInLightMode, hasInvertedStyling, screen, createTestForm} from '../../test-utils';
import {CollectionEditForm} from './CollectionEditForm';
import {createMockDomain} from '../../test-utils';

// Mock the TagsContext
jest.mock('../../Tags', () => ({
    TagsContext: {
        _currentValue: {
            SingleTag: ({name}) => <span data-testid="applied-tag">{name}</span>
        }
    },
}));

// Mock Common components
jest.mock('../Common', () => ({
    ...jest.requireActual('../Common'),
    WROLModeMessage: ({content}) => <div data-testid="wrol-mode-message">{content}</div>,
}));

describe('CollectionEditForm', () => {
    const mockCollection = createMockDomain();

    describe('Form Rendering', () => {
        it('renders children and Save button', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm form={form}>
                    <div data-testid="child-content">Form fields here</div>
                </CollectionEditForm>
            );

            expect(screen.getByTestId('child-content')).toBeInTheDocument();
            expect(screen.getByRole('button', {name: /save/i})).toBeInTheDocument();
        });

        it('renders title when provided', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm form={form} title="Edit Domain: example.com">
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('Edit Domain: example.com');
        });

        it('renders WROL mode message when provided', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm
                    form={form}
                    wrolModeContent="Editing disabled in WROL Mode"
                >
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.getByTestId('wrol-mode-message')).toHaveTextContent('Editing disabled in WROL Mode');
        });

        it('renders action buttons when provided', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm
                    form={form}
                    actionButtons={<button data-testid="delete-button">Delete</button>}
                >
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.getByTestId('delete-button')).toBeInTheDocument();
        });

        it('renders appliedTagName when provided', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm form={form} appliedTagName="News">
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.getByTestId('applied-tag')).toHaveTextContent('News');
        });

        it('does not render appliedTagName when not provided', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.queryByTestId('applied-tag')).not.toBeInTheDocument();
        });
    });

    describe('Save/Cancel Actions', () => {
        it('shows Cancel button when onCancel provided', () => {
            const form = createTestForm(mockCollection);
            const mockOnCancel = jest.fn();

            render(
                <CollectionEditForm form={form} onCancel={mockOnCancel}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.getByRole('button', {name: /cancel/i})).toBeInTheDocument();
        });

        it('does not show Cancel button when onCancel not provided', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.queryByRole('button', {name: /cancel/i})).not.toBeInTheDocument();
        });

        it('disables Save button when form is disabled', () => {
            const form = createTestForm(mockCollection, {
                overrides: {disabled: true}
            });

            render(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.getByRole('button', {name: /save/i})).toBeDisabled();
        });

        it('disables Cancel button when form is disabled', () => {
            const form = createTestForm(mockCollection, {
                overrides: {disabled: true}
            });
            const mockOnCancel = jest.fn();

            render(
                <CollectionEditForm form={form} onCancel={mockOnCancel}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.getByRole('button', {name: /cancel/i})).toBeDisabled();
        });
    });

    describe('Error States', () => {
        it('displays form-level errors', () => {
            const form = createTestForm(mockCollection, {
                overrides: {error: 'Something went wrong'}
            });

            render(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
        });

        it('does not display error message when no error', () => {
            const form = createTestForm(mockCollection);

            render(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
        });
    });

    describe('Form Submission', () => {
        it('calls form.onSubmit when Save button is clicked', () => {
            const form = createTestForm(mockCollection);
            form.onSubmit = jest.fn();

            render(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            screen.getByRole('button', {name: /save/i}).click();
            expect(form.onSubmit).toHaveBeenCalled();
        });
    });

    describe('Theme Integration', () => {
        it('applies inverted styling to Segment in dark mode', () => {
            const form = createTestForm(mockCollection);

            const {container} = renderInDarkMode(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            const segment = container.querySelector('.ui.segment');
            expect(segment).toBeInTheDocument();
            expect(hasInvertedStyling(segment)).toBe(true);
        });

        it('does not apply inverted styling in light mode', () => {
            const form = createTestForm(mockCollection);

            const {container} = renderInLightMode(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            const segment = container.querySelector('.ui.segment');
            expect(segment).toBeInTheDocument();
            expect(hasInvertedStyling(segment)).toBe(false);
        });

        it('applies dark theme styling to Header in dark mode', () => {
            const form = createTestForm(mockCollection);

            const {container} = renderInDarkMode(
                <CollectionEditForm form={form} title="Test Collection">
                    <div>Form content</div>
                </CollectionEditForm>
            );

            const header = container.querySelector('.ui.header');
            expect(header).toBeInTheDocument();
            expect(header.style.color).toBe('rgb(238, 238, 238)');  // #eeeeee
        });
    });

    describe('CSS Classes', () => {
        it('uses action-button-spacing class for cancel button', () => {
            const form = createTestForm(mockCollection);
            const mockOnCancel = jest.fn();

            render(
                <CollectionEditForm form={form} onCancel={mockOnCancel}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            const cancelButton = screen.getByRole('button', {name: /cancel/i});
            expect(cancelButton).toHaveClass('action-button-spacing');
        });
    });
});
