import React from 'react';
import {screen, fireEvent} from '@testing-library/react';
import {renderWithProviders} from '../test-utils';
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
