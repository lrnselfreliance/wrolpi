import React from 'react';
import {screen, fireEvent} from '@testing-library/react';
import {renderWithProviders} from '../test-utils';
import {Confirm} from './ui';
import {TaggedDeleteConfirmModal} from './TaggedDeleteConfirmModal';

describe('TaggedDeleteConfirmModal', () => {
    const sampleGroups = [
        {id: 1, primary_path: 'videos/foo.mp4', tags: ['favorite', 'review']},
        {id: 2, primary_path: 'archives/bar.html', tags: ['important']},
    ];

    it('renders nothing when closed', () => {
        renderWithProviders(
            <TaggedDeleteConfirmModal
                open={false}
                taggedFileGroups={sampleGroups}
                onConfirm={jest.fn()}
                onCancel={jest.fn()}
            />
        );
        expect(screen.queryByText(/Tagged Files Will Be Deleted/i)).not.toBeInTheDocument();
    });

    it('renders rows for each tagged file group', () => {
        renderWithProviders(
            <TaggedDeleteConfirmModal
                open={true}
                taggedFileGroups={sampleGroups}
                onConfirm={jest.fn()}
                onCancel={jest.fn()}
            />
        );
        expect(screen.getAllByText(/Tagged Files Will Be Deleted/i).length).toBeGreaterThan(0);
        expect(screen.getByText('videos/foo.mp4')).toBeInTheDocument();
        expect(screen.getByText('archives/bar.html')).toBeInTheDocument();
        expect(screen.getByText('favorite, review')).toBeInTheDocument();
        expect(screen.getByText('important')).toBeInTheDocument();
    });

    it('calls onCancel when Cancel button clicked', () => {
        const onCancel = jest.fn();
        renderWithProviders(
            <TaggedDeleteConfirmModal
                open={true}
                taggedFileGroups={sampleGroups}
                onConfirm={jest.fn()}
                onCancel={onCancel}
            />
        );
        fireEvent.click(screen.getByRole('button', {name: /Cancel/i}));
        expect(onCancel).toHaveBeenCalled();
    });

    it('calls onConfirm when Delete button clicked', () => {
        const onConfirm = jest.fn();
        renderWithProviders(
            <TaggedDeleteConfirmModal
                open={true}
                taggedFileGroups={sampleGroups}
                onConfirm={onConfirm}
                onCancel={jest.fn()}
            />
        );
        const deleteButton = screen.getAllByRole('button', {name: /Delete/i})
            .find(b => b.textContent.includes('Delete'));
        fireEvent.click(deleteButton);
        expect(onConfirm).toHaveBeenCalled();
    });

    it('handles empty/null taggedFileGroups gracefully', () => {
        renderWithProviders(
            <TaggedDeleteConfirmModal
                open={true}
                taggedFileGroups={null}
                onConfirm={jest.fn()}
                onCancel={jest.fn()}
            />
        );
        expect(screen.getAllByText(/Tagged Files Will Be Deleted/i).length).toBeGreaterThan(0);
    });

    it('is wider than a one-sentence confirmation, because it lists paths in a table', () => {
        /*
         * Every Confirm in the app was 380px, because Confirm hardcoded `size='tiny'` and
         * accepted no size.  380px is right for the eleven that ask a one-line question and
         * wrong for this one: two columns of file paths, and a path is long.  The table
         * scrolls horizontally inside the modal rather than overflowing it, so the width
         * decides how much of a path is readable without dragging.
         */
        /*
         * Both in one render, and every modal root read: a modal is portalled to
         * `document.body`, so two separate renders both land there and reading only the first
         * root reports one modal's size twice.
         *
         * Paired with a plain confirmation so this cannot pass by Confirm having become wide
         * for everyone -- the point is that this one asked and the rest did not.
         */
        const {baseElement} = renderWithProviders(<>
            <TaggedDeleteConfirmModal
                open={true}
                taggedFileGroups={sampleGroups}
                onConfirm={jest.fn()}
                onCancel={jest.fn()}
            />
            <Confirm open title='Delete?'/>
        </>);

        const sizes = [...baseElement.querySelectorAll('.mantine-Modal-root')]
            .map(root => (root.getAttribute('style') ?? '').match(/--modal-size:\s*([^;]+)/)?.[1]);
        expect(sizes).toEqual(['var(--modal-size-lg)', 'var(--modal-size-sm)']);
    });

    it('falls back to name when primary_path is missing', () => {
        renderWithProviders(
            <TaggedDeleteConfirmModal
                open={true}
                taggedFileGroups={[{id: 5, name: 'fallback-name', tags: ['t']}]}
                onConfirm={jest.fn()}
                onCancel={jest.fn()}
            />
        );
        expect(screen.getByText('fallback-name')).toBeInTheDocument();
    });
});
