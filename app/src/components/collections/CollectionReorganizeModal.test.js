import React from 'react';
import {screen, waitFor, fireEvent} from '@testing-library/react';
import {renderWithProviders} from '../../test-utils';
import {CollectionReorganizeModal} from './CollectionReorganizeModal';
import * as api from '../../api';

// Mock the API functions
jest.mock('../../api', () => ({
    previewCollectionReorganization: jest.fn(),
    executeCollectionReorganization: jest.fn(),
    getReorganizationStatus: jest.fn(),
}));

// Mock react-semantic-toasts-2
jest.mock('react-semantic-toasts-2', () => ({
    toast: jest.fn(),
}));

// Mock the FileWorkerStatusContext - default mock returns inactive state
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

describe('CollectionReorganizeModal', () => {
    const defaultProps = {
        open: true,
        onClose: jest.fn(),
        collectionId: 1,
        collectionName: 'Test Channel',
        onComplete: jest.fn(),
        needsReorganization: true,
    };

    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('loads preview when opened', async () => {
        const mockPreview = {
            files_needing_move: 45,
            total_files: 50,
            current_file_format: '%(title)s.%(ext)s',
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [
                {old_path: 'video.mp4', new_path: '2024-01-15/video.mp4'},
            ],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        // Should show loading initially
        expect(screen.getByText(/Loading Preview/i)).toBeInTheDocument();

        // Wait for preview to load
        await waitFor(() => {
            expect(screen.getByText(/45/)).toBeInTheDocument();
            expect(screen.getByText(/50/)).toBeInTheDocument();
        });

        expect(api.previewCollectionReorganization).toHaveBeenCalledWith(1);
    });

    it('shows sample moves in preview', async () => {
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            current_file_format: '%(title)s.%(ext)s',
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [
                {old_path: 'old/video1.mp4', new_path: 'new/video1.mp4'},
                {old_path: 'old/video2.mp4', new_path: 'new/video2.mp4'},
            ],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByText('old/video1.mp4')).toBeInTheDocument();
            expect(screen.getByText('new/video1.mp4')).toBeInTheDocument();
        });
    });

    it('shows "No Files Need Reorganization" message when no files need moving', async () => {
        const mockPreview = {
            files_needing_move: 0,
            total_files: 50,
            current_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByText(/No Files Need Reorganization/i)).toBeInTheDocument();
        });
    });

    it('shows warning when collection appears organized but has files to move', async () => {
        const mockPreview = {
            files_needing_move: 5,
            total_files: 50,
            current_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [{old_path: 'a.mp4', new_path: 'b.mp4'}],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);

        // needsReorganization is false, but there are files to move
        renderWithProviders(
            <CollectionReorganizeModal {...defaultProps} needsReorganization={false} />
        );

        await waitFor(() => {
            expect(screen.getByText(/Collection Appears Organized/i)).toBeInTheDocument();
        });
    });

    it('executes reorganization on button click', async () => {
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);
        api.executeCollectionReorganization.mockResolvedValue({
            job_id: 'reorganize-abc123',
            message: 'Reorganization started',
        });
        api.getReorganizationStatus.mockResolvedValue({
            status: 'complete',
            total: 10,
            completed: 10,
            percent: 100,
        });

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        // Wait for preview to load
        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize Files/i})).toBeInTheDocument();
        });

        // Click the reorganize button
        fireEvent.click(screen.getByRole('button', {name: /Reorganize Files/i}));

        await waitFor(() => {
            expect(api.executeCollectionReorganization).toHaveBeenCalledWith(1);
        });
    });

    it('shows progress bar during execution', async () => {
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);
        api.executeCollectionReorganization.mockResolvedValue({
            job_id: 'reorganize-abc123',
            message: 'Reorganization started',
        });
        api.getReorganizationStatus.mockResolvedValue({
            status: 'running',
            total: 10,
            completed: 5,
            percent: 50,
        });

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize Files/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Reorganize Files/i}));

        await waitFor(() => {
            expect(screen.getByText(/5 of 10 files processed/i)).toBeInTheDocument();
        });
    });

    it('calls onComplete when reorganization finishes', async () => {
        const mockOnComplete = jest.fn();
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);
        api.executeCollectionReorganization.mockResolvedValue({
            job_id: 'reorganize-abc123',
            message: 'Reorganization started',
        });
        api.getReorganizationStatus.mockResolvedValue({
            status: 'complete',
            total: 10,
            completed: 10,
            percent: 100,
        });

        renderWithProviders(
            <CollectionReorganizeModal {...defaultProps} onComplete={mockOnComplete} />
        );

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize Files/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Reorganize Files/i}));

        await waitFor(() => {
            expect(mockOnComplete).toHaveBeenCalled();
        });
    });

    it('displays error message on API failure', async () => {
        api.previewCollectionReorganization.mockRejectedValue(new Error('Network error'));

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByText(/Network error/i)).toBeInTheDocument();
        });
    });

    it('calls onClose when cancel button is clicked', async () => {
        const mockOnClose = jest.fn();
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);

        renderWithProviders(
            <CollectionReorganizeModal {...defaultProps} onClose={mockOnClose} />
        );

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Cancel/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Cancel/i}));

        expect(mockOnClose).toHaveBeenCalled();
    });

    it('shows completion message when reorganization completes', async () => {
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);
        api.executeCollectionReorganization.mockResolvedValue({
            job_id: 'reorganize-abc123',
            message: 'Reorganization started',
        });
        api.getReorganizationStatus.mockResolvedValue({
            status: 'complete',
            total: 10,
            completed: 10,
            percent: 100,
        });

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize Files/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Reorganize Files/i}));

        await waitFor(() => {
            expect(screen.getByText(/Reorganization Complete/i)).toBeInTheDocument();
        });
    });

    it('handles execution error gracefully', async () => {
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);
        api.executeCollectionReorganization.mockRejectedValue(new Error('Permission denied'));

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize Files/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Reorganize Files/i}));

        await waitFor(() => {
            expect(screen.getByText(/Permission denied/i)).toBeInTheDocument();
        });
    });

    it('does not fetch preview when modal is closed', () => {
        renderWithProviders(<CollectionReorganizeModal {...defaultProps} open={false} />);

        expect(api.previewCollectionReorganization).not.toHaveBeenCalled();
    });

    it('changes button text based on state', async () => {
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);
        api.executeCollectionReorganization.mockResolvedValue({
            job_id: 'reorganize-abc123',
            message: 'Reorganization started',
        });
        api.getReorganizationStatus.mockResolvedValue({
            status: 'complete',
            total: 10,
            completed: 10,
            percent: 100,
        });

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        // Wait for preview to load and button to appear
        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize Files/i})).toBeInTheDocument();
        });

        // Should show "Cancel" initially (when not in progress)
        expect(screen.getByRole('button', {name: /Cancel/i})).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: /Reorganize Files/i}));

        // Should show "Close" after completion
        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Close/i})).toBeInTheDocument();
        });
    });

    it('polls for status with real job ID, not with "active"', async () => {
        // This test verifies the bug fix: the component should poll using
        // the real job_id returned from executeCollectionReorganization,
        // not a hardcoded string like 'active'
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);
        api.executeCollectionReorganization.mockResolvedValue({
            job_id: 'reorganize-real-job-id-123',
            message: 'Reorganization started',
        });
        api.getReorganizationStatus.mockResolvedValue({
            status: 'running',
            total: 10,
            completed: 3,
            percent: 30,
        });

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize Files/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Reorganize Files/i}));

        // Wait for status polling to start
        await waitFor(() => {
            expect(api.getReorganizationStatus).toHaveBeenCalled();
        });

        // CRITICAL: Verify that getReorganizationStatus was called with the real job ID
        // NOT with 'active' which was the bug
        expect(api.getReorganizationStatus).toHaveBeenCalledWith(1, 'reorganize-real-job-id-123');
        expect(api.getReorganizationStatus).not.toHaveBeenCalledWith(1, 'active');
    });

    it('handles status polling error and retries', async () => {
        const mockPreview = {
            files_needing_move: 10,
            total_files: 20,
            new_file_format: '%(upload_date)s/%(title)s.%(ext)s',
            sample_moves: [],
        };

        api.previewCollectionReorganization.mockResolvedValue(mockPreview);
        api.executeCollectionReorganization.mockResolvedValue({
            job_id: 'reorganize-abc123',
            message: 'Reorganization started',
        });

        // First call fails, second call succeeds
        api.getReorganizationStatus
            .mockRejectedValueOnce(new Error('Network error'))
            .mockResolvedValue({
                status: 'complete',
                total: 10,
                completed: 10,
                percent: 100,
            });

        const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

        renderWithProviders(<CollectionReorganizeModal {...defaultProps} />);

        await waitFor(() => {
            expect(screen.getByRole('button', {name: /Reorganize Files/i})).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', {name: /Reorganize Files/i}));

        // Wait for retry and completion
        await waitFor(() => {
            expect(screen.getByText(/Reorganization Complete/i)).toBeInTheDocument();
        }, {timeout: 3000});

        // Should have retried after initial error
        expect(api.getReorganizationStatus.mock.calls.length).toBeGreaterThanOrEqual(2);

        consoleSpy.mockRestore();
    });
});
