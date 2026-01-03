import React from 'react';
import {act, render, screen, waitFor} from '../../test-utils';
import userEvent from '@testing-library/user-event';
import {CollectionReorganizeModal} from './CollectionReorganizeModal';
import * as api from '../../api';

// Mock the api module
jest.mock('../../api', () => ({
    reorganizeCollection: jest.fn(),
}));

// Mock Theme components
jest.mock('../Theme', () => {
    const MockModal = ({open, onClose, children, closeIcon, size}) => {
        if (!open) return null;
        return (
            <div data-testid="modal" data-size={size}>
                {closeIcon && <button data-testid="close-icon" onClick={onClose}>×</button>}
                {children}
            </div>
        );
    };
    MockModal.Header = ({children}) => <div data-testid="modal-header">{children}</div>;
    MockModal.Content = ({children, scrolling}) => <div data-testid="modal-content">{children}</div>;
    MockModal.Actions = ({children}) => <div data-testid="modal-actions">{children}</div>;

    return {
        ...jest.requireActual('../Theme'),
        Modal: MockModal,
        Button: ({children, onClick, disabled, ...props}) => (
            <button onClick={onClick} disabled={disabled} data-testid={`button-${children}`} {...props}>{children}</button>
        ),
    };
});

// Mock Common components
jest.mock('../Common', () => ({
    ...jest.requireActual('../Common'),
    APIButton: ({children, onClick, disabled, ...props}) => (
        <button onClick={onClick} disabled={disabled} data-testid={`api-button-${children}`} {...props}>{children}</button>
    ),
}));

describe('CollectionReorganizeModal', () => {
    const mockPreview = {
        preview: {
            total_files: 10,
            files_to_move: 8,
            files_unchanged: 2,
            moves: [
                {from: '2024-01-15_Article.html', to: '2024/2024-01-15_Article.html'},
                {from: '2024-02-20_Another.html', to: '2024/2024-02-20_Another.html'},
            ]
        },
        new_file_format: '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s',
        reorganized: false,
    };

    const defaultProps = {
        open: true,
        onClose: jest.fn(),
        collectionId: 1,
        collectionName: 'Domain',
        onSuccess: jest.fn(),
    };

    beforeEach(() => {
        jest.clearAllMocks();
        api.reorganizeCollection.mockResolvedValue(mockPreview);
    });

    describe('Modal Rendering', () => {
        it('renders modal when open is true', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);
            await waitFor(() => {
                expect(screen.getByTestId('modal')).toBeInTheDocument();
            });
        });

        it('does not render modal when open is false', () => {
            render(<CollectionReorganizeModal {...defaultProps} open={false}/>);
            expect(screen.queryByTestId('modal')).not.toBeInTheDocument();
        });

        it('shows correct header with collection name', async () => {
            render(<CollectionReorganizeModal {...defaultProps} collectionName="Domain"/>);
            await waitFor(() => {
                expect(screen.getByTestId('modal-header')).toHaveTextContent('Reorganize Domain Files');
            });
        });

        it('shows correct header for Channel', async () => {
            render(<CollectionReorganizeModal {...defaultProps} collectionName="Channel"/>);
            await waitFor(() => {
                expect(screen.getByTestId('modal-header')).toHaveTextContent('Reorganize Channel Files');
            });
        });
    });

    describe('Loading State', () => {
        it('shows loading state while fetching preview', async () => {
            // Don't resolve the promise immediately
            let resolvePreview;
            api.reorganizeCollection.mockImplementation(() => new Promise(resolve => {
                resolvePreview = resolve;
            }));

            render(<CollectionReorganizeModal {...defaultProps} />);

            expect(screen.getByText(/loading preview/i)).toBeInTheDocument();

            // Resolve the promise
            await act(async () => {
                resolvePreview(mockPreview);
            });

            await waitFor(() => {
                expect(screen.queryByText(/loading preview/i)).not.toBeInTheDocument();
            });
        });

        it('fetches preview with dry_run=true on mount', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(api.reorganizeCollection).toHaveBeenCalledWith(1, true);
            });
        });
    });

    describe('Preview Display', () => {
        it('displays files to move count', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(screen.getByText(/files will be moved/i)).toBeInTheDocument();
            });
        });

        it('displays files unchanged count', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(screen.getByText(/files are already in the correct location/i)).toBeInTheDocument();
            });
        });

        it('displays new file format', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(screen.getByText(/New File Format/i)).toBeInTheDocument();
                expect(screen.getByText(/%\(download_year\)s/)).toBeInTheDocument();
            });
        });

        it('displays move paths in table', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(screen.getByText('2024-01-15_Article.html')).toBeInTheDocument();
                expect(screen.getByText('2024/2024-01-15_Article.html')).toBeInTheDocument();
            });
        });

        it('truncates moves list if more than 50 items', async () => {
            const manyMoves = Array.from({length: 75}, (_, i) => ({
                from: `file_${i}.html`,
                to: `2024/file_${i}.html`,
            }));
            api.reorganizeCollection.mockResolvedValue({
                ...mockPreview,
                preview: {
                    ...mockPreview.preview,
                    files_to_move: 75,
                    moves: manyMoves,
                }
            });

            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(screen.getByText(/and 25 more files/i)).toBeInTheDocument();
            });
        });

        it('does not show truncation message for 50 or fewer files', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(screen.queryByText(/more files/i)).not.toBeInTheDocument();
            });
        });
    });

    describe('Error Handling', () => {
        it('displays error message when preview fetch fails', async () => {
            api.reorganizeCollection.mockRejectedValue(new Error('Failed to load preview'));

            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(screen.getByText('Error')).toBeInTheDocument();
                expect(screen.getByText('Failed to load preview')).toBeInTheDocument();
            });
        });

        it('displays error message when reorganize fails', async () => {
            api.reorganizeCollection
                .mockResolvedValueOnce(mockPreview) // First call for preview
                .mockRejectedValueOnce(new Error('Reorganization failed')); // Second call for actual reorganize

            render(<CollectionReorganizeModal {...defaultProps} />);

            // Wait for preview to load
            await waitFor(() => {
                expect(screen.getByText(/files will be moved/i)).toBeInTheDocument();
            });

            // Click reorganize button
            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Reorganize 8 Files'));
            });

            // Check error is displayed
            await waitFor(() => {
                expect(screen.getByText('Reorganization failed')).toBeInTheDocument();
            });
        });
    });

    describe('Reorganize Button', () => {
        it('shows correct file count on button', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(screen.getByTestId('api-button-Reorganize 8 Files')).toBeInTheDocument();
            });
        });

        it('is disabled while loading', async () => {
            let resolvePreview;
            api.reorganizeCollection.mockImplementation(() => new Promise(resolve => {
                resolvePreview = resolve;
            }));

            render(<CollectionReorganizeModal {...defaultProps} />);

            const button = screen.getByTestId('api-button-Reorganize 0 Files');
            expect(button).toBeDisabled();

            await act(async () => {
                resolvePreview(mockPreview);
            });
        });

        it('is disabled when no files to move', async () => {
            api.reorganizeCollection.mockResolvedValue({
                ...mockPreview,
                preview: {
                    ...mockPreview.preview,
                    files_to_move: 0,
                    moves: [],
                }
            });

            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                const button = screen.getByTestId('api-button-Reorganize 0 Files');
                expect(button).toBeDisabled();
            });
        });

        it('is enabled when files to move', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                const button = screen.getByTestId('api-button-Reorganize 8 Files');
                expect(button).not.toBeDisabled();
            });
        });
    });

    describe('Reorganize Action', () => {
        it('calls reorganizeCollection with dry_run=false when button clicked', async () => {
            render(<CollectionReorganizeModal {...defaultProps} />);

            await waitFor(() => {
                expect(screen.getByTestId('api-button-Reorganize 8 Files')).toBeInTheDocument();
            });

            api.reorganizeCollection.mockResolvedValueOnce({...mockPreview, reorganized: true});

            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Reorganize 8 Files'));
            });

            expect(api.reorganizeCollection).toHaveBeenCalledWith(1, false);
        });

        it('calls onClose after successful reorganization', async () => {
            const mockOnClose = jest.fn();
            render(<CollectionReorganizeModal {...defaultProps} onClose={mockOnClose} />);

            await waitFor(() => {
                expect(screen.getByTestId('api-button-Reorganize 8 Files')).toBeInTheDocument();
            });

            api.reorganizeCollection.mockResolvedValueOnce({...mockPreview, reorganized: true});

            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Reorganize 8 Files'));
            });

            expect(mockOnClose).toHaveBeenCalled();
        });

        it('calls onSuccess after successful reorganization', async () => {
            const mockOnSuccess = jest.fn();
            render(<CollectionReorganizeModal {...defaultProps} onSuccess={mockOnSuccess} />);

            await waitFor(() => {
                expect(screen.getByTestId('api-button-Reorganize 8 Files')).toBeInTheDocument();
            });

            api.reorganizeCollection.mockResolvedValueOnce({...mockPreview, reorganized: true});

            await act(async () => {
                await userEvent.click(screen.getByTestId('api-button-Reorganize 8 Files'));
            });

            expect(mockOnSuccess).toHaveBeenCalled();
        });
    });

    describe('Cancel Behavior', () => {
        it('calls onClose when cancel button clicked', async () => {
            const mockOnClose = jest.fn();
            render(<CollectionReorganizeModal {...defaultProps} onClose={mockOnClose} />);

            await waitFor(() => {
                expect(screen.getByTestId('button-Cancel')).toBeInTheDocument();
            });

            await userEvent.click(screen.getByTestId('button-Cancel'));

            expect(mockOnClose).toHaveBeenCalled();
        });
    });

    describe('State Reset on Close', () => {
        it('resets state when modal is closed and reopened', async () => {
            const {rerender} = render(<CollectionReorganizeModal {...defaultProps} />);

            // Wait for preview to load - use more specific selector
            await waitFor(() => {
                expect(screen.getByText(/files will be moved/i)).toBeInTheDocument();
            });

            // Close modal
            await act(async () => {
                rerender(<CollectionReorganizeModal {...defaultProps} open={false} />);
            });

            // Reopen modal
            api.reorganizeCollection.mockResolvedValue({
                ...mockPreview,
                preview: {
                    ...mockPreview.preview,
                    files_to_move: 5,
                }
            });

            await act(async () => {
                rerender(<CollectionReorganizeModal {...defaultProps} open={true} />);
            });

            // Should fetch new preview
            await waitFor(() => {
                expect(api.reorganizeCollection).toHaveBeenCalledTimes(2);
            });
        });
    });
});
