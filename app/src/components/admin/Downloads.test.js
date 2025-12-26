import React from 'react';
import {fireEvent, screen, waitFor} from '@testing-library/react';
import {OnceDownloadsTable} from './Downloads';
import {renderWithProviders} from '../../test-utils';

// Mock the API functions
jest.mock('../../api', () => ({
    batchClearDownloads: jest.fn(() => Promise.resolve({ok: true})),
    batchDeleteDownloads: jest.fn(() => Promise.resolve({ok: true})),
    batchRetryDownloads: jest.fn(() => Promise.resolve({ok: true})),
    clearCompletedDownloads: jest.fn(() => Promise.resolve({ok: true})),
    deleteDownload: jest.fn(() => Promise.resolve({ok: true})),
    deleteOnceDownloads: jest.fn(() => Promise.resolve({ok: true})),
    killDownload: jest.fn(() => Promise.resolve({ok: true})),
    restartDownload: jest.fn(() => Promise.resolve({ok: true})),
    retryOnceDownloads: jest.fn(() => Promise.resolve({ok: true})),
}));

import {
    batchClearDownloads,
    batchDeleteDownloads,
    batchRetryDownloads,
    clearCompletedDownloads,
    deleteOnceDownloads,
    retryOnceDownloads,
} from '../../api';

describe('OnceDownloadsTable', () => {
    const mockDownloads = [
        {id: 1, url: 'https://example.com/1', status: 'complete', last_successful_download: '2024-01-01T00:00:00Z', location: '/videos/1'},
        {id: 2, url: 'https://example.com/2', status: 'failed', error: 'Download failed'},
        {id: 3, url: 'https://example.com/3', status: 'pending'},
    ];

    const mockFetchDownloads = jest.fn();

    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('renders downloads table with checkboxes', () => {
        renderWithProviders(
            <OnceDownloadsTable downloads={mockDownloads} fetchDownloads={mockFetchDownloads}/>
        );

        // Should render all downloads
        expect(screen.getByText('https://example.com/1')).toBeInTheDocument();
        expect(screen.getByText('https://example.com/2')).toBeInTheDocument();
        expect(screen.getByText('https://example.com/3')).toBeInTheDocument();

        // Should have checkboxes (4 = 1 header + 3 rows)
        const checkboxes = screen.getAllByRole('checkbox');
        expect(checkboxes).toHaveLength(4);
    });

    it('renders empty state when no downloads', () => {
        renderWithProviders(
            <OnceDownloadsTable downloads={[]} fetchDownloads={mockFetchDownloads}/>
        );

        expect(screen.getByText('No downloads are scheduled.')).toBeInTheDocument();
    });

    it('toggles selection when checkbox clicked', async () => {
        renderWithProviders(
            <OnceDownloadsTable downloads={mockDownloads} fetchDownloads={mockFetchDownloads}/>
        );

        const checkboxes = screen.getAllByRole('checkbox');
        // First checkbox is select-all, so click the second one (first row)
        fireEvent.click(checkboxes[1]);

        // Button labels should show count
        await waitFor(() => {
            expect(screen.getByText('Clear (1)')).toBeInTheDocument();
            expect(screen.getByText('Retry (1)')).toBeInTheDocument();
            expect(screen.getByText('Delete (1)')).toBeInTheDocument();
        });
    });

    it('selects all when header checkbox clicked', async () => {
        renderWithProviders(
            <OnceDownloadsTable downloads={mockDownloads} fetchDownloads={mockFetchDownloads}/>
        );

        const checkboxes = screen.getAllByRole('checkbox');
        // Click the select-all checkbox (first one)
        fireEvent.click(checkboxes[0]);

        // Button labels should show count of all downloads
        await waitFor(() => {
            expect(screen.getByText('Clear (3)')).toBeInTheDocument();
            expect(screen.getByText('Retry (3)')).toBeInTheDocument();
            expect(screen.getByText('Delete (3)')).toBeInTheDocument();
        });
    });

    it('deselects all when header checkbox clicked again', async () => {
        renderWithProviders(
            <OnceDownloadsTable downloads={mockDownloads} fetchDownloads={mockFetchDownloads}/>
        );

        const checkboxes = screen.getAllByRole('checkbox');
        // Click select-all twice
        fireEvent.click(checkboxes[0]);
        fireEvent.click(checkboxes[0]);

        // Button labels should show no count
        await waitFor(() => {
            expect(screen.getByText('Clear')).toBeInTheDocument();
            expect(screen.getByText('Retry')).toBeInTheDocument();
            expect(screen.getByText('Delete')).toBeInTheDocument();
        });
    });

    it('calls batch API when items selected and Clear clicked', async () => {
        renderWithProviders(
            <OnceDownloadsTable downloads={mockDownloads} fetchDownloads={mockFetchDownloads}/>
        );

        const checkboxes = screen.getAllByRole('checkbox');
        // Select first two downloads
        fireEvent.click(checkboxes[1]);
        fireEvent.click(checkboxes[2]);

        // Click Clear button
        const clearButton = screen.getByText('Clear (2)');
        fireEvent.click(clearButton);

        await waitFor(() => {
            expect(batchClearDownloads).toHaveBeenCalledWith([1, 2]);
            expect(clearCompletedDownloads).not.toHaveBeenCalled();
        });
    });

    it('calls all-downloads API when no items selected', async () => {
        renderWithProviders(
            <OnceDownloadsTable downloads={mockDownloads} fetchDownloads={mockFetchDownloads}/>
        );

        // Click Clear button without selecting any items
        const clearButton = screen.getByText('Clear');
        fireEvent.click(clearButton);

        await waitFor(() => {
            expect(clearCompletedDownloads).toHaveBeenCalled();
            expect(batchClearDownloads).not.toHaveBeenCalled();
        });
    });

    it('clears selection after successful operation', async () => {
        renderWithProviders(
            <OnceDownloadsTable downloads={mockDownloads} fetchDownloads={mockFetchDownloads}/>
        );

        const checkboxes = screen.getAllByRole('checkbox');
        // Select first download
        fireEvent.click(checkboxes[1]);

        // Click Clear button
        const clearButton = screen.getByText('Clear (1)');
        fireEvent.click(clearButton);

        await waitFor(() => {
            // Button label should revert to no count
            expect(screen.getByText('Clear')).toBeInTheDocument();
        });
    });
});
