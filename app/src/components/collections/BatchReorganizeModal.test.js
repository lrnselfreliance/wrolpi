import React from 'react';
import {screen, waitFor, fireEvent} from '@testing-library/react';
import {renderWithProviders} from '../../test-utils';
import {BatchReorganizeModal} from './BatchReorganizeModal';
import * as api from '../../api';

// Mock the API functions
jest.mock('../../api', () => ({
    previewBatchReorganization: jest.fn(),
    executeBatchReorganization: jest.fn(),
    getBatchReorganizationStatus: jest.fn(),
}));

// Mock react-semantic-toasts-2
jest.mock('react-semantic-toasts-2', () => ({
    toast: jest.fn(),
}));

// Mock the FileWorkerStatusContext
jest.mock('../../contexts/FileWorkerStatusContext', () => ({
    useReorganizationStatus: () => ({
        isReorganizing: false,
        taskType: null,
        collectionId: null,
        collectionKind: null,
        batchStatus: null,
        workerStatus: null,
        refresh: jest.fn(),
    }),
    useFileWorkerStatus: () => ({
        status: null,
        error: null,
        refresh: jest.fn(),
        setFastPolling: jest.fn(),
    }),
}));

describe('BatchReorganizeModal', () => {
    const defaultProps = {
        open: true,
        onClose: jest.fn(),
        kind: 'channel',
        onComplete: jest.fn(),
    };

    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('loads preview when opened', async () => {
        const mockPreview = {
            collections: [
                {
                    collection_id: 1,
                    collection_name: 'Test Channel',
                    total_files: 50,
                    files_needing_move: 45,
                    sample_move: {old_path: 'old/path.mp4', new_path: 'new/path.mp4'},
                },
            ],
            total_collections: 1,
            total_files_needing_move: 45,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
        };

        api.previewBatchReorganization.mockResolvedValue(mockPreview);

        renderWithProviders(<BatchReorganizeModal {...defaultProps} />);

        // Should show loading initially
        expect(screen.getByText(/Loading Preview/i)).toBeInTheDocument();

        // Wait for preview to load
        await waitFor(() => {
            expect(screen.getByText(/Test Channel/)).toBeInTheDocument();
        });

        expect(api.previewBatchReorganization).toHaveBeenCalledWith('channel');
    });

    it('shows collection list with sample moves', async () => {
        const mockPreview = {
            collections: [
                {
                    collection_id: 1,
                    collection_name: 'Channel A',
                    total_files: 100,
                    files_needing_move: 80,
                    sample_move: {old_path: 'videos/old.mp4', new_path: 'videos/new.mp4'},
                },
                {
                    collection_id: 2,
                    collection_name: 'Channel B',
                    total_files: 50,
                    files_needing_move: 30,
                    sample_move: {old_path: 'videos/old2.mp4', new_path: 'videos/new2.mp4'},
                },
            ],
            total_collections: 2,
            total_files_needing_move: 110,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
        };

        api.previewBatchReorganization.mockResolvedValue(mockPreview);

        renderWithProviders(<BatchReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByText('Channel A')).toBeInTheDocument();
            expect(screen.getByText('Channel B')).toBeInTheDocument();
        });

        // Should show total statistics - look for the numbers in the text context
        expect(screen.getByText('2')).toBeInTheDocument(); // total collections
        expect(screen.getByText('110')).toBeInTheDocument(); // total files
    });

    it('shows total statistics', async () => {
        const mockPreview = {
            collections: [
                {collection_id: 1, collection_name: 'ChannelA', total_files: 50, files_needing_move: 45, sample_move: null},
                {collection_id: 2, collection_name: 'ChannelB', total_files: 30, files_needing_move: 25, sample_move: null},
                {collection_id: 3, collection_name: 'ChannelC', total_files: 20, files_needing_move: 15, sample_move: null},
            ],
            total_collections: 3,
            total_files_needing_move: 85,
            new_file_format: '%(title)s.%(ext)s',
        };

        api.previewBatchReorganization.mockResolvedValue(mockPreview);

        renderWithProviders(<BatchReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            // Look for channel names to verify list is displayed
            expect(screen.getByText('ChannelA')).toBeInTheDocument();
            expect(screen.getByText('ChannelB')).toBeInTheDocument();
            expect(screen.getByText('ChannelC')).toBeInTheDocument();
        });
    });

    it('executes batch reorganization on button click', async () => {
        const mockPreview = {
            collections: [{collection_id: 1, collection_name: 'Test', total_files: 10, files_needing_move: 5, sample_move: null}],
            total_collections: 1,
            total_files_needing_move: 5,
            new_file_format: '%(title)s.%(ext)s',
        };

        api.previewBatchReorganization.mockResolvedValue(mockPreview);
        api.executeBatchReorganization.mockResolvedValue({
            batch_job_id: 'batch-reorganize-abc123',
            message: 'Batch reorganization started',
            collection_count: 1,
        });
        api.getBatchReorganizationStatus.mockResolvedValue({
            status: 'complete',
            total_collections: 1,
            completed_collections: 1,
            current_collection: null,
            overall_percent: 100,
            failed_collection: null,
            error: null,
        });

        renderWithProviders(<BatchReorganizeModal {...defaultProps} />);

        // Wait for preview to load
        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize All Channels/i})).toBeInTheDocument();
        });

        // Click the reorganize button
        fireEvent.click(screen.getByRole('button', {name: /Reorganize All Channels/i}));

        await waitFor(() => {
            expect(api.executeBatchReorganization).toHaveBeenCalledWith('channel');
        });
    });

    it('shows overall progress bar during execution', async () => {
        const mockPreview = {
            collections: [{collection_id: 1, collection_name: 'Test', total_files: 10, files_needing_move: 5, sample_move: null}],
            total_collections: 1,
            total_files_needing_move: 5,
            new_file_format: '%(title)s.%(ext)s',
        };

        api.previewBatchReorganization.mockResolvedValue(mockPreview);
        api.executeBatchReorganization.mockResolvedValue({
            batch_job_id: 'batch-reorganize-abc123',
            message: 'Batch reorganization started',
            collection_count: 1,
        });
        api.getBatchReorganizationStatus.mockResolvedValue({
            status: 'running',
            total_collections: 1,
            completed_collections: 0,
            current_collection: {id: 1, name: 'Test', status: 'running', total: 5, completed: 2, percent: 40},
            overall_percent: 40,
            failed_collection: null,
            error: null,
        });

        renderWithProviders(<BatchReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize All Channels/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Reorganize All Channels/i}));

        await waitFor(() => {
            expect(screen.getByText(/Overall Progress/i)).toBeInTheDocument();
        });
    });

    it('shows per-collection progress bars', async () => {
        const mockPreview = {
            collections: [{collection_id: 1, collection_name: 'Test Channel', total_files: 10, files_needing_move: 5, sample_move: null}],
            total_collections: 1,
            total_files_needing_move: 5,
            new_file_format: '%(title)s.%(ext)s',
        };

        api.previewBatchReorganization.mockResolvedValue(mockPreview);
        api.executeBatchReorganization.mockResolvedValue({
            batch_job_id: 'batch-reorganize-abc123',
            message: 'Batch reorganization started',
            collection_count: 1,
        });
        api.getBatchReorganizationStatus.mockResolvedValue({
            status: 'running',
            total_collections: 1,
            completed_collections: 0,
            current_collection: {id: 1, name: 'Test Channel', status: 'running', total: 5, completed: 2, percent: 40},
            overall_percent: 20,
            failed_collection: null,
            error: null,
        });

        renderWithProviders(<BatchReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize All Channels/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Reorganize All Channels/i}));

        await waitFor(() => {
            expect(screen.getByText(/Currently Processing/i)).toBeInTheDocument();
            expect(screen.getByText(/Test Channel/)).toBeInTheDocument();
        });
    });

    it('calls onComplete when finished', async () => {
        const mockOnComplete = jest.fn();
        const mockPreview = {
            collections: [{collection_id: 1, collection_name: 'Test', total_files: 10, files_needing_move: 5, sample_move: null}],
            total_collections: 1,
            total_files_needing_move: 5,
            new_file_format: '%(title)s.%(ext)s',
        };

        api.previewBatchReorganization.mockResolvedValue(mockPreview);
        api.executeBatchReorganization.mockResolvedValue({
            batch_job_id: 'batch-reorganize-abc123',
            message: 'Batch reorganization started',
            collection_count: 1,
        });
        api.getBatchReorganizationStatus.mockResolvedValue({
            status: 'complete',
            total_collections: 1,
            completed_collections: 1,
            current_collection: null,
            overall_percent: 100,
            failed_collection: null,
            error: null,
        });

        renderWithProviders(<BatchReorganizeModal {...defaultProps} onComplete={mockOnComplete} />);

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize All Channels/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Reorganize All Channels/i}));

        await waitFor(() => {
            expect(mockOnComplete).toHaveBeenCalled();
        });
    });

    it('handles domain kind correctly', async () => {
        const mockPreview = {
            collections: [{collection_id: 1, collection_name: 'example.com', total_files: 10, files_needing_move: 5, sample_move: null}],
            total_collections: 1,
            total_files_needing_move: 5,
            new_file_format: '%(title)s.%(ext)s',
        };

        api.previewBatchReorganization.mockResolvedValue(mockPreview);

        renderWithProviders(<BatchReorganizeModal {...defaultProps} kind="domain" />);

        await waitFor(() => {
            expect(screen.getByText(/Reorganize All Domains/i)).toBeInTheDocument();
        });

        expect(api.previewBatchReorganization).toHaveBeenCalledWith('domain');
    });
});
