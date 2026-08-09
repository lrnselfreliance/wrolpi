import React from 'react';
import {
    createMockDomain,
    createTestForm,
    render,
    renderInDarkMode,
    renderInLightMode,
    screen
} from '../../test-utils';
import {CollectionEditForm} from './CollectionEditForm';

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
        // Panel/Header are token-driven (see ui/Surfaces.tsx): their colors come from CSS
        // variables scoped on `[data-theme]`, not from JS branching on the theme. There is
        // no more "inverted" prop/class to assert on -- just that the same markup renders
        // in both modes.
        it('renders a token-driven Panel in dark mode', () => {
            const form = createTestForm(mockCollection);

            const {container} = renderInDarkMode(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(container.querySelector('.wrolpi-panel')).toBeInTheDocument();
        });

        it('renders a token-driven Panel in light mode', () => {
            const form = createTestForm(mockCollection);

            const {container} = renderInLightMode(
                <CollectionEditForm form={form}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            expect(container.querySelector('.wrolpi-panel')).toBeInTheDocument();
        });

        it('renders a token-driven Header for the title', () => {
            const form = createTestForm(mockCollection);

            const {container} = renderInDarkMode(
                <CollectionEditForm form={form} title="Test Collection">
                    <div>Form content</div>
                </CollectionEditForm>
            );

            const header = container.querySelector('.wrolpi-header');
            expect(header).toBeInTheDocument();
            expect(header).toHaveTextContent('Test Collection');
        });
    });

    describe('CSS Classes', () => {
        it('puts its actions in a button row, and leaves their margins alone', () => {
            /*
             * `action-button-spacing` was `margin-top: 1em` on Cancel alone, matching the same
             * margin the three calling pages stamped on each of their action buttons -- so every
             * button in this row sat 1em below the Save beside it, which has none.  The row spaces
             * and wraps them now, and nothing in it carries a margin of its own.
             */
            const form = createTestForm(mockCollection);
            const mockOnCancel = jest.fn();

            const {container} = render(
                <CollectionEditForm form={form} onCancel={mockOnCancel}>
                    <div>Form content</div>
                </CollectionEditForm>
            );

            const cancelButton = screen.getByRole('button', {name: /cancel/i});
            const row = container.querySelector('.wrolpi-button-row');
            expect(row).toBeInTheDocument();
            expect(row).toContainElement(cancelButton);
            expect(row).toContainElement(screen.getByRole('button', {name: /save/i}));
            expect(cancelButton).not.toHaveClass('action-button-spacing');
        });
    });
});
