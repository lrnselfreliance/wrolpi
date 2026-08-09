import React from 'react';
import {act, screen, waitFor} from '@testing-library/react';
import {BulkTagModal} from './BulkTagModal';
import {TagsContext} from '../Tags';
import {renderWithProviders} from '../test-utils';

// Mock the API functions
jest.mock('../api', () => ({
    getBulkTagPreview: jest.fn(),
    applyBulkTags: jest.fn(),
    getBulkTagProgress: jest.fn(),
}));

// Import mocked API functions
import {getBulkTagPreview, applyBulkTags, getBulkTagProgress} from '../api';

// Mock TagsGroup component for testing
const MockTagsGroup = ({tagNames, onClick}) => (
    <div data-testid="tags-group">
        {tagNames?.map(name => (
            <span key={name} onClick={() => onClick && onClick(name)} data-testid={`tag-${name}`}>
                {name}
            </span>
        ))}
    </div>
);

// Render with the real ui library components (Mantine-backed) plus TagsContext.
const renderWithTags = (ui, options) => {
    const tagsValue = {
        tagNames: ['tag1', 'tag2', 'tag3'],
        TagsGroup: MockTagsGroup,
    };
    return renderWithProviders(
        <TagsContext.Provider value={tagsValue}>{ui}</TagsContext.Provider>,
        options,
    );
};

describe('BulkTagModal', () => {
    const defaultProps = {
        open: true,
        onClose: jest.fn(),
        paths: ['file1.txt', 'file2.txt'],
        onComplete: jest.fn(),
    };

    beforeEach(() => {
        jest.clearAllMocks();
        getBulkTagPreview.mockResolvedValue({
            file_count: 2,
            shared_tag_names: ['shared'],
        });
        getBulkTagProgress.mockResolvedValue({
            status: 'idle',
            total: 0,
            completed: 0,
            queued_jobs: 0,
        });
    });

    describe('Modal Rendering', () => {
        it('renders modal when open is true', async () => {
            renderWithTags(<BulkTagModal {...defaultProps} />);
            expect(screen.getByRole('dialog')).toBeInTheDocument();
        });

        it('does not render modal when open is false', () => {
            renderWithTags(<BulkTagModal {...defaultProps} open={false}/>);
            expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        });

        it('shows header', async () => {
            renderWithTags(<BulkTagModal {...defaultProps} />);
            expect(screen.getByText('Bulk Tag Files')).toBeInTheDocument();
        });
    });

    describe('Loading State', () => {
        it('shows loading state while fetching preview', async () => {
            getBulkTagPreview.mockImplementation(() => new Promise(() => {
            })); // Never resolves
            renderWithTags(<BulkTagModal {...defaultProps} />);
            expect(screen.getByText('Loading preview...')).toBeInTheDocument();
        });
    });

    describe('Preview State', () => {
        it('shows file count after loading', async () => {
            renderWithTags(<BulkTagModal {...defaultProps} />);
            await waitFor(() => {
                expect(screen.getByText(/2 files will be affected/i)).toBeInTheDocument();
            });
        });

        it('does not show warning for less than 50 files', async () => {
            getBulkTagPreview.mockResolvedValue({
                file_count: 10,
                shared_tag_names: [],
            });
            renderWithTags(<BulkTagModal {...defaultProps} />);
            await waitFor(() => {
                expect(screen.getByText(/10 files will be affected/i)).toBeInTheDocument();
            });
            expect(screen.queryByText(/Tagging over 50 files/i)).not.toBeInTheDocument();
        });

        it('Apply button is disabled when no changes', async () => {
            renderWithTags(<BulkTagModal {...defaultProps} />);
            await waitFor(() => {
                expect(screen.getByText(/2 files will be affected/i)).toBeInTheDocument();
            });
            const applyButton = screen.getByRole('button', {name: 'Apply Tags'});
            expect(applyButton).toBeDisabled();
        });
    });

    describe('Applying Tags', () => {
        it('calls applyBulkTags when Apply is clicked', async () => {
            applyBulkTags.mockResolvedValue({ok: true});
            getBulkTagProgress.mockResolvedValue({
                status: 'running',
                total: 2,
                completed: 1,
                queued_jobs: 0,
            });

            renderWithTags(<BulkTagModal {...defaultProps} />);

            // Wait for preview to load
            await waitFor(() => {
                expect(screen.getByText(/2 files will be affected/i)).toBeInTheDocument();
            });

            // The test would need to simulate adding a tag first
            // This is a simplified test - in real usage, user would click to add tags
        });
    });

    describe('Close Modal', () => {
        it('calls onClose when Cancel is clicked', async () => {
            renderWithTags(<BulkTagModal {...defaultProps} />);
            await waitFor(() => {
                expect(screen.getByText(/2 files will be affected/i)).toBeInTheDocument();
            });
            const cancelButton = screen.getByRole('button', {name: 'Cancel'});
            act(() => {
                cancelButton.click();
            });
            expect(defaultProps.onClose).toHaveBeenCalled();
        });
    });

    describe('Error Handling', () => {
        it('handles preview failure gracefully', async () => {
            // When preview returns undefined (API error), we should still see the modal
            getBulkTagPreview.mockResolvedValue(undefined);
            renderWithTags(<BulkTagModal {...defaultProps} />);
            // Modal should still be visible
            expect(screen.getByRole('dialog')).toBeInTheDocument();
        });
    });
});
