import React from 'react';
import {act, render, screen, waitFor} from '../../test-utils';
import userEvent from '@testing-library/user-event';
import {CollectionTagModal} from './CollectionTagModal';

// Mock Theme components
jest.mock('../Theme', () => ({
    ...jest.requireActual('../Theme'),
    Modal: ({open, onClose, children, closeIcon}) => {
        if (!open) return null;
        return (
            <div data-testid="modal">
                {closeIcon && <button data-testid="close-icon" onClick={onClose}>×</button>}
                {children}
            </div>
        );
    },
    ModalHeader: ({children}) => <div data-testid="modal-header">{children}</div>,
    ModalContent: ({children}) => <div data-testid="modal-content">{children}</div>,
    ModalActions: ({children}) => <div data-testid="modal-actions">{children}</div>,
    Button: ({children, onClick, ...props}) => (
        <button onClick={onClick} data-testid={`button-${children}`} {...props}>{children}</button>
    ),
}));

// Mock Common components
jest.mock('../Common', () => ({
    ...jest.requireActual('../Common'),
    Toggle: ({label, checked, onChange}) => (
        <label data-testid="toggle">
            <input
                type="checkbox"
                checked={checked}
                onChange={(e) => onChange(e.target.checked)}
                data-testid="toggle-checkbox"
            />
            {label}
        </label>
    ),
    APIButton: ({children, onClick, ...props}) => (
        <button onClick={onClick} data-testid={`api-button-${children}`} {...props}>{children}</button>
    ),
}));

// Mock TagsSelector
jest.mock('../../Tags', () => ({
    TagsSelector: ({selectedTagNames, onAdd, onRemove, limit}) => (
        <div data-testid="tags-selector">
            <span data-testid="selected-tags">{selectedTagNames?.join(', ') || 'none'}</span>
            <button data-testid="add-tag" onClick={() => onAdd('test-tag')}>Add Tag</button>
            <button data-testid="remove-tag" onClick={() => onRemove('test-tag')}>Remove Tag</button>
        </div>
    ),
}));

describe('CollectionTagModal', () => {
    const defaultProps = {
        open: true,
        onClose: jest.fn(),
        currentTagName: null,
        originalDirectory: '/original/directory',
        getTagInfo: jest.fn(),
        onSave: jest.fn(),
        collectionName: 'Test',
    };

    beforeEach(() => {
        jest.clearAllMocks();
    });

    describe('Modal Rendering', () => {
        it('renders modal when open is true', () => {
            render(<CollectionTagModal {...defaultProps} />);
            expect(screen.getByTestId('modal')).toBeInTheDocument();
        });

        it('does not render modal when open is false', () => {
            render(<CollectionTagModal {...defaultProps} open={false}/>);
            expect(screen.queryByTestId('modal')).not.toBeInTheDocument();
        });

        it('shows "Add Tag" header when no current tag', () => {
            render(<CollectionTagModal {...defaultProps} currentTagName={null}/>);
            expect(screen.getByTestId('modal-header')).toHaveTextContent('Add Tag');
        });

        it('shows "Modify Tag" header when there is a current tag', () => {
            render(<CollectionTagModal {...defaultProps} currentTagName="existing-tag"/>);
            expect(screen.getByTestId('modal-header')).toHaveTextContent('Modify Tag');
        });
    });

    describe('Directory Input', () => {
        it('displays original directory in input field', () => {
            render(<CollectionTagModal {...defaultProps} />);
            const input = screen.getByRole('textbox');
            expect(input).toHaveValue('/original/directory');
        });

        it('updates directory when user types', async () => {
            render(<CollectionTagModal {...defaultProps} />);
            const input = screen.getByRole('textbox');
            await userEvent.clear(input);
            await userEvent.type(input, '/new/directory');
            expect(input).toHaveValue('/new/directory');
        });

        it('disables directory input when move toggle is off', async () => {
            render(<CollectionTagModal {...defaultProps} />);
            const toggleCheckbox = screen.getByTestId('toggle-checkbox');
            await userEvent.click(toggleCheckbox); // Turn off move to directory
            const input = screen.getByRole('textbox');
            expect(input).toBeDisabled();
        });
    });

    describe('Tag Info Fetching', () => {
        it('fetches tag info when tag is added', async () => {
            const mockGetTagInfo = jest.fn().mockResolvedValue({
                suggested_directory: '/suggested/directory',
                conflict: false,
                conflict_message: null,
            });

            render(<CollectionTagModal {...defaultProps} getTagInfo={mockGetTagInfo}/>);

            const addTagButton = screen.getByTestId('add-tag');
            await userEvent.click(addTagButton);

            // Wait for all async state updates to complete by checking the final result
            await waitFor(() => {
                expect(mockGetTagInfo).toHaveBeenCalledWith('test-tag');
                // Also verify the directory was updated (this ensures async call completed)
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/suggested/directory');
            });
        });

        it('updates directory with suggested directory from tag info', async () => {
            const mockGetTagInfo = jest.fn().mockResolvedValue({
                suggested_directory: '/suggested/directory',
                conflict: false,
                conflict_message: null,
            });

            render(<CollectionTagModal {...defaultProps} getTagInfo={mockGetTagInfo}/>);

            const addTagButton = screen.getByTestId('add-tag');
            await userEvent.click(addTagButton);

            await waitFor(() => {
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/suggested/directory');
            });
        });

        it('handles legacy string format from tag info', async () => {
            const mockGetTagInfo = jest.fn().mockResolvedValue('/legacy/directory');

            render(<CollectionTagModal {...defaultProps} getTagInfo={mockGetTagInfo}/>);

            const addTagButton = screen.getByTestId('add-tag');
            await userEvent.click(addTagButton);

            await waitFor(() => {
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/legacy/directory');
            });
        });

        it('fetches tag info when tag is removed', async () => {
            const mockGetTagInfo = jest.fn().mockResolvedValue(null);

            render(<CollectionTagModal {...defaultProps} getTagInfo={mockGetTagInfo} currentTagName="existing-tag"/>);

            const removeTagButton = screen.getByTestId('remove-tag');
            await userEvent.click(removeTagButton);

            // Wait for all async state updates to complete
            await waitFor(() => {
                expect(mockGetTagInfo).toHaveBeenCalledWith(null);
                // Also verify the directory was reset (ensures async call completed)
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/original/directory');
            });
        });

        it('updates directory when tag is removed and backend returns suggestion', async () => {
            const mockGetTagInfo = jest.fn().mockResolvedValue({
                suggested_directory: '/untagged/directory',
                conflict: false,
                conflict_message: null,
            });

            render(<CollectionTagModal {...defaultProps} getTagInfo={mockGetTagInfo} currentTagName="existing-tag"/>);

            const removeTagButton = screen.getByTestId('remove-tag');
            await userEvent.click(removeTagButton);

            await waitFor(() => {
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/untagged/directory');
            });
        });

        it('resets to original directory when tag is removed and no suggestion', async () => {
            const mockGetTagInfo = jest.fn().mockResolvedValue(null);

            render(<CollectionTagModal {...defaultProps} getTagInfo={mockGetTagInfo}
                                       originalDirectory="/original/path"/>);

            // First add a tag - wait for async to complete including state updates
            const addTagButton = screen.getByTestId('add-tag');
            await act(async () => {
                await userEvent.click(addTagButton);
            });

            // Wait for first getTagInfo call to complete AND directory state to settle
            // When getTagInfo returns null, the component sets directory to originalDirectory
            await waitFor(() => {
                expect(mockGetTagInfo).toHaveBeenCalledWith('test-tag');
                const input = screen.getByRole('textbox');
                // After null response, directory is reset to original
                expect(input).toHaveValue('/original/path');
            });

            // Then remove the tag - wrap in act to catch async state updates
            const removeTagButton = screen.getByTestId('remove-tag');
            await act(async () => {
                await userEvent.click(removeTagButton);
            });

            // Verify all state updates completed
            expect(mockGetTagInfo).toHaveBeenCalledWith(null);
            const input = screen.getByRole('textbox');
            expect(input).toHaveValue('/original/path');
        });
    });

    describe('Conflict Handling', () => {
        it('displays conflict warning when tag info indicates conflict', async () => {
            const mockGetTagInfo = jest.fn().mockResolvedValue({
                suggested_directory: '/conflict/directory',
                conflict: true,
                conflict_message: 'Directory already in use',
            });

            render(<CollectionTagModal {...defaultProps} getTagInfo={mockGetTagInfo}/>);

            const addTagButton = screen.getByTestId('add-tag');
            await userEvent.click(addTagButton);

            // Wait for all async state updates including conflict message and directory
            await waitFor(() => {
                expect(screen.getByText('Directory Conflict')).toBeInTheDocument();
                expect(screen.getByText('Directory already in use')).toBeInTheDocument();
                // Also check directory was updated (ensures all state updates complete)
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/conflict/directory');
            });
        });

        it('clears conflict warning when tag is changed', async () => {
            const mockGetTagInfo = jest.fn()
                .mockResolvedValueOnce({
                    suggested_directory: '/conflict/directory',
                    conflict: true,
                    conflict_message: 'Directory already in use',
                })
                .mockResolvedValueOnce({
                    suggested_directory: '/no-conflict/directory',
                    conflict: false,
                    conflict_message: null,
                });

            render(<CollectionTagModal {...defaultProps} getTagInfo={mockGetTagInfo}/>);

            // Add first tag - shows conflict
            const addTagButton = screen.getByTestId('add-tag');
            await userEvent.click(addTagButton);

            // Wait for first async call to complete (conflict message AND directory update)
            await waitFor(() => {
                expect(screen.getByText('Directory Conflict')).toBeInTheDocument();
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/conflict/directory');
            });

            // Add different tag - conflict should clear
            await userEvent.click(addTagButton);

            // Wait for second async call to complete (no conflict AND new directory)
            await waitFor(() => {
                expect(screen.queryByText('Directory Conflict')).not.toBeInTheDocument();
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/no-conflict/directory');
            });
        });
    });

    describe('Modal Close Behavior', () => {
        it('calls onClose when cancel button is clicked', async () => {
            const mockOnClose = jest.fn();
            render(<CollectionTagModal {...defaultProps} onClose={mockOnClose}/>);

            const cancelButton = screen.getByTestId('button-Cancel');
            await userEvent.click(cancelButton);

            expect(mockOnClose).toHaveBeenCalled();
        });

        it('resets directory to original value when modal is closed', async () => {
            const mockOnClose = jest.fn();
            const mockGetTagInfo = jest.fn().mockResolvedValue({
                suggested_directory: '/changed/directory',
                conflict: false,
                conflict_message: null,
            });

            const {rerender} = render(
                <CollectionTagModal
                    {...defaultProps}
                    onClose={mockOnClose}
                    getTagInfo={mockGetTagInfo}
                    originalDirectory="/original/directory"
                />
            );

            // Change directory by adding a tag
            const addTagButton = screen.getByTestId('add-tag');
            await userEvent.click(addTagButton);

            await waitFor(() => {
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/changed/directory');
            });

            // Close the modal
            const cancelButton = screen.getByTestId('button-Cancel');
            await userEvent.click(cancelButton);

            // Reopen modal
            rerender(
                <CollectionTagModal
                    {...defaultProps}
                    open={true}
                    onClose={mockOnClose}
                    getTagInfo={mockGetTagInfo}
                    originalDirectory="/original/directory"
                />
            );

            // Directory should be reset to original
            await waitFor(() => {
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/original/directory');
            });
        });
    });

    describe('Save Behavior', () => {
        it('calls onSave with tag name and directory when move toggle is on', async () => {
            const mockOnClose = jest.fn();
            // Use mockResolvedValue to make onSave async - this helps React batch state updates properly
            const mockOnSave = jest.fn().mockResolvedValue(undefined);
            const mockGetTagInfo = jest.fn().mockResolvedValue({
                suggested_directory: '/suggested/directory',
                conflict: false,
            });

            render(
                <CollectionTagModal
                    {...defaultProps}
                    onSave={mockOnSave}
                    onClose={mockOnClose}
                    getTagInfo={mockGetTagInfo}
                />
            );

            // Add a tag
            const addTagButton = screen.getByTestId('add-tag');
            await userEvent.click(addTagButton);

            // Wait for the directory to be updated from getTagInfo
            await waitFor(() => {
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/suggested/directory');
            });

            // Click save/move button and wait for all async operations to complete
            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Move'));
            });

            // Verify the save was called
            expect(mockOnSave).toHaveBeenCalledWith('test-tag', '/suggested/directory');
            expect(mockOnClose).toHaveBeenCalled();
        });

        it('calls onSave with null directory when move toggle is off', async () => {
            const mockOnClose = jest.fn();
            // Use mockResolvedValue to make onSave async - this helps React batch state updates properly
            const mockOnSave = jest.fn().mockResolvedValue(undefined);
            const mockGetTagInfo = jest.fn().mockResolvedValue({
                suggested_directory: '/suggested/directory',
                conflict: false,
            });

            render(
                <CollectionTagModal
                    {...defaultProps}
                    onSave={mockOnSave}
                    onClose={mockOnClose}
                    getTagInfo={mockGetTagInfo}
                />
            );

            // Add a tag
            const addTagButton = screen.getByTestId('add-tag');
            await userEvent.click(addTagButton);

            // Wait for all async state updates to complete
            await waitFor(() => {
                expect(mockGetTagInfo).toHaveBeenCalled();
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/suggested/directory');
            });

            // Turn off move toggle
            const toggleCheckbox = screen.getByTestId('toggle-checkbox');
            await userEvent.click(toggleCheckbox);

            // Click save button and wait for all async operations to complete
            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Save'));
            });

            // Verify the save was called
            expect(mockOnSave).toHaveBeenCalledWith('test-tag', null);
            expect(mockOnClose).toHaveBeenCalled();
        });
    });

    describe('hasDirectory prop', () => {
        it('hides move toggle and directory input when hasDirectory is false', () => {
            // TDD test - should FAIL initially because hasDirectory prop doesn't exist yet
            render(
                <CollectionTagModal
                    {...defaultProps}
                    hasDirectory={false}
                    originalDirectory={null}
                />
            );

            // Toggle and directory input should be hidden
            expect(screen.queryByTestId('toggle')).not.toBeInTheDocument();
            expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
        });

        it('shows move toggle and directory input when hasDirectory is true', () => {
            render(
                <CollectionTagModal
                    {...defaultProps}
                    hasDirectory={true}
                    originalDirectory="/some/directory"
                />
            );

            // Toggle and directory input should be visible
            expect(screen.getByTestId('toggle')).toBeInTheDocument();
            expect(screen.getByRole('textbox')).toBeInTheDocument();
        });

        it('defaults hasDirectory to true for backward compatibility', () => {
            // When hasDirectory is not specified, it should default to true (show directory UI)
            render(
                <CollectionTagModal
                    {...defaultProps}
                    originalDirectory="/some/directory"
                />
            );

            // Toggle and directory input should be visible by default
            expect(screen.getByTestId('toggle')).toBeInTheDocument();
            expect(screen.getByRole('textbox')).toBeInTheDocument();
        });

        it('calls onSave with null directory when hasDirectory is false', async () => {
            const mockOnClose = jest.fn();
            const mockOnSave = jest.fn().mockResolvedValue(undefined);
            const mockGetTagInfo = jest.fn().mockResolvedValue({
                suggested_directory: null,
                conflict: false,
            });

            render(
                <CollectionTagModal
                    {...defaultProps}
                    hasDirectory={false}
                    originalDirectory={null}
                    onSave={mockOnSave}
                    onClose={mockOnClose}
                    getTagInfo={mockGetTagInfo}
                />
            );

            // Add a tag
            const addTagButton = screen.getByTestId('add-tag');
            await userEvent.click(addTagButton);

            // Wait for getTagInfo to be called
            await waitFor(() => {
                expect(mockGetTagInfo).toHaveBeenCalled();
            });

            // Click save button
            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Save'));
            });

            // Verify onSave was called with null directory
            expect(mockOnSave).toHaveBeenCalledWith('test-tag', null);
            expect(mockOnClose).toHaveBeenCalled();
        });
    });

    describe('Tag Removal Save Behavior', () => {
        it('calls onSave with updated directory after removing tag', async () => {
            const mockOnSave = jest.fn().mockResolvedValue(undefined);
            const mockOnClose = jest.fn();
            const mockGetTagInfo = jest.fn().mockResolvedValue({
                suggested_directory: '/videos/wrolpi.org',  // Untagged directory
                conflict: false,
                conflict_message: null,
            });

            render(
                <CollectionTagModal
                    open={true}
                    onClose={mockOnClose}
                    currentTagName="WROL"  // Currently has a tag
                    originalDirectory='/videos/WROL/wrolpi.org'  // Current tagged directory
                    getTagInfo={mockGetTagInfo}
                    onSave={mockOnSave}
                    collectionName="Channel"
                    hasDirectory={true}
                />
            );

            // Remove the tag - this triggers getTagInfo(null) and should update directory
            await userEvent.click(screen.getByTestId('remove-tag'));

            // Wait for directory to be updated with the untagged directory
            await waitFor(() => {
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/videos/wrolpi.org');
            });

            // Click Move button to save
            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Move'));
            });

            // Verify onSave was called with null tag and NEW directory
            expect(mockOnSave).toHaveBeenCalledWith(null, '/videos/wrolpi.org');
        });

        it('calls onSave with updated directory even when clicking save quickly after removing tag', async () => {
            // This test simulates a potential race condition where user clicks save
            // very quickly after removing the tag, before the async getTagInfo completes
            const mockOnSave = jest.fn().mockResolvedValue(undefined);
            const mockOnClose = jest.fn();

            // Simulate a slow API call
            const mockGetTagInfo = jest.fn().mockImplementation(() => {
                return new Promise(resolve => {
                    setTimeout(() => {
                        resolve({
                            suggested_directory: '/videos/wrolpi.org',
                            conflict: false,
                            conflict_message: null,
                        });
                    }, 100); // 100ms delay
                });
            });

            render(
                <CollectionTagModal
                    open={true}
                    onClose={mockOnClose}
                    currentTagName="WROL"
                    originalDirectory='/videos/WROL/wrolpi.org'
                    getTagInfo={mockGetTagInfo}
                    onSave={mockOnSave}
                    collectionName="Channel"
                    hasDirectory={true}
                />
            );

            // Remove the tag
            await userEvent.click(screen.getByTestId('remove-tag'));

            // Wait for the directory to update (ensures async completed)
            await waitFor(() => {
                const input = screen.getByRole('textbox');
                expect(input).toHaveValue('/videos/wrolpi.org');
            }, {timeout: 500});

            // Click Move button
            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Move'));
            });

            // Verify onSave was called with null tag and NEW directory
            expect(mockOnSave).toHaveBeenCalledWith(null, '/videos/wrolpi.org');
        });

        it('does NOT send stale directory if user clicks save before async completes', async () => {
            // This test checks what happens if user manages to click save BEFORE getTagInfo resolves
            // This would be the actual bug scenario
            const mockOnSave = jest.fn().mockResolvedValue(undefined);
            const mockOnClose = jest.fn();

            // Create a promise that we can control
            let resolveGetTagInfo;
            const mockGetTagInfo = jest.fn().mockImplementation(() => {
                return new Promise(resolve => {
                    resolveGetTagInfo = resolve;
                });
            });

            render(
                <CollectionTagModal
                    open={true}
                    onClose={mockOnClose}
                    currentTagName="WROL"
                    originalDirectory='/videos/WROL/wrolpi.org'
                    getTagInfo={mockGetTagInfo}
                    onSave={mockOnSave}
                    collectionName="Channel"
                    hasDirectory={true}
                />
            );

            // Remove the tag - triggers getTagInfo but doesn't resolve yet
            await userEvent.click(screen.getByTestId('remove-tag'));

            // getTagInfo should have been called
            expect(mockGetTagInfo).toHaveBeenCalledWith(null);

            // At this point, directory is still the old value
            const input = screen.getByRole('textbox');
            expect(input).toHaveValue('/videos/WROL/wrolpi.org');

            // Now resolve the getTagInfo promise
            await act(async () => {
                resolveGetTagInfo({
                    suggested_directory: '/videos/wrolpi.org',
                    conflict: false,
                    conflict_message: null,
                });
            });

            // Wait for directory to update
            await waitFor(() => {
                expect(input).toHaveValue('/videos/wrolpi.org');
            });

            // NOW click save
            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Move'));
            });

            // Verify onSave was called with the CORRECT directory
            expect(mockOnSave).toHaveBeenCalledWith(null, '/videos/wrolpi.org');
        });
    });
});
