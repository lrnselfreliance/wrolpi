import React from 'react';
import {screen, waitFor, fireEvent} from '@testing-library/react';
import {renderWithProviders} from '../../test-utils';
import {ConflictResolutionModal} from './ConflictResolutionModal';
import * as api from '../../api';

// Mock the API functions
jest.mock('../../api', () => ({
    deleteVideos: jest.fn(),
    deleteArchives: jest.fn(),
}));

// Mock react-semantic-toasts-2
jest.mock('react-semantic-toasts-2', () => ({
    toast: jest.fn(),
}));

describe('ConflictResolutionModal', () => {
    const mockConflicts = [
        {
            destination_path: 'videos/2024-01-15/My Video.mp4',
            conflicting_files: [
                {
                    file_group_id: 1,
                    current_path: 'videos/old/My Video.mp4',
                    title: 'My Video',
                    model_type: 'video',
                    size: 1024000,
                    video_id: 101,
                    archive_id: null,
                    poster_path: 'videos/old/My Video.jpg',
                    published_datetime: '2024-01-15T10:00:00Z',
                    source_id: 'abc123',
                },
                {
                    file_group_id: 2,
                    current_path: 'videos/new/My Video.mp4',
                    title: 'My Video',
                    model_type: 'video',
                    size: 2048000,
                    video_id: 102,
                    archive_id: null,
                    poster_path: null,
                    published_datetime: '2024-01-15T10:00:00Z',
                    source_id: 'abc123',
                },
            ],
        },
    ];

    const defaultProps = {
        open: true,
        onClose: jest.fn(),
        conflicts: mockConflicts,
        collectionKind: 'channel',
        onResolved: jest.fn(),
    };

    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('renders the modal with conflicts', () => {
        renderWithProviders(<ConflictResolutionModal {...defaultProps} />);

        expect(screen.getByText(/Resolve Conflicts Before Reorganizing/i)).toBeInTheDocument();
        expect(screen.getByText(/Destination Path Conflicts Detected/i)).toBeInTheDocument();
        expect(screen.getByText(/1 destination path has/i)).toBeInTheDocument();
    });

    it('shows conflict destination path', () => {
        renderWithProviders(<ConflictResolutionModal {...defaultProps} />);

        expect(screen.getByText(/videos\/2024-01-15\/My Video.mp4/)).toBeInTheDocument();
    });

    it('shows file details for conflicting files', () => {
        renderWithProviders(<ConflictResolutionModal {...defaultProps} />);

        // Should show both file paths
        expect(screen.getByText('videos/old/My Video.mp4')).toBeInTheDocument();
        expect(screen.getByText('videos/new/My Video.mp4')).toBeInTheDocument();

        // Should show title
        const titles = screen.getAllByText('My Video');
        expect(titles.length).toBeGreaterThanOrEqual(2);

        // Should show source_id
        const sourceIds = screen.getAllByText('abc123');
        expect(sourceIds.length).toBe(2);
    });

    it('shows file size in human-readable format', () => {
        renderWithProviders(<ConflictResolutionModal {...defaultProps} />);

        // 1024000 bytes = ~1000 kB (uses humanFileSize from Common.js)
        expect(screen.getByText('1000.0 kB')).toBeInTheDocument();
        // 2048000 bytes = ~2 MB
        expect(screen.getByText('2.0 MB')).toBeInTheDocument();
    });

    it('calls deleteVideos when delete button is clicked for video', async () => {
        api.deleteVideos.mockResolvedValue({});

        renderWithProviders(<ConflictResolutionModal {...defaultProps} />);

        // Find and click the first delete button
        const deleteButtons = screen.getAllByTitle('Delete this file');
        fireEvent.click(deleteButtons[0]);

        await waitFor(() => {
            expect(api.deleteVideos).toHaveBeenCalledWith([101]);
        });

        // File should be removed from UI (conflict resolved since only 1 file remains)
        await waitFor(() => {
            expect(screen.getByText(/All Conflicts Resolved/i)).toBeInTheDocument();
        });

        // onResolved is NOT called until modal is closed
        expect(defaultProps.onResolved).not.toHaveBeenCalled();

        // Click Close/Done button - now onResolved should be called
        fireEvent.click(screen.getByRole('button', {name: /Done/i}));
        expect(defaultProps.onResolved).toHaveBeenCalled();
    });

    it('calls deleteArchives when delete button is clicked for archive', async () => {
        const archiveConflicts = [
            {
                destination_path: 'archives/example.com/page.html',
                conflicting_files: [
                    {
                        file_group_id: 10,
                        current_path: 'archives/old/page.html',
                        title: 'Example Page',
                        model_type: 'archive',
                        size: 50000,
                        video_id: null,
                        archive_id: 201,
                        poster_path: null,
                        published_datetime: null,
                        source_id: null,
                    },
                ],
            },
        ];

        api.deleteArchives.mockResolvedValue({});

        renderWithProviders(
            <ConflictResolutionModal
                {...defaultProps}
                conflicts={archiveConflicts}
                collectionKind='domain'
            />
        );

        const deleteButton = screen.getByTitle('Delete this file');
        fireEvent.click(deleteButton);

        await waitFor(() => {
            expect(api.deleteArchives).toHaveBeenCalledWith([201]);
        });
    });

    it('shows success message when no conflicts remain', () => {
        renderWithProviders(
            <ConflictResolutionModal {...defaultProps} conflicts={[]} />
        );

        expect(screen.getByText(/All Conflicts Resolved/i)).toBeInTheDocument();
        expect(screen.getByText(/You can now proceed with the reorganization/i)).toBeInTheDocument();
    });

    it('shows Done button when no conflicts', () => {
        renderWithProviders(
            <ConflictResolutionModal {...defaultProps} conflicts={[]} />
        );

        expect(screen.getByRole('button', {name: /Done/i})).toBeInTheDocument();
    });

    it('shows Close button when conflicts exist', () => {
        renderWithProviders(<ConflictResolutionModal {...defaultProps} />);

        expect(screen.getByRole('button', {name: /Close/i})).toBeInTheDocument();
    });

    it('calls onClose when Close button is clicked (without changes)', () => {
        renderWithProviders(<ConflictResolutionModal {...defaultProps} />);

        fireEvent.click(screen.getByRole('button', {name: /Close/i}));

        // onClose is called, but onResolved is NOT called since no changes were made
        expect(defaultProps.onClose).toHaveBeenCalled();
        expect(defaultProps.onResolved).not.toHaveBeenCalled();
    });

    it('displays multiple conflicts', () => {
        const multipleConflicts = [
            {
                destination_path: 'videos/path1.mp4',
                conflicting_files: [
                    {file_group_id: 1, current_path: 'a.mp4', title: 'Video 1', model_type: 'video', video_id: 1},
                    {file_group_id: 2, current_path: 'b.mp4', title: 'Video 1', model_type: 'video', video_id: 2},
                ],
            },
            {
                destination_path: 'videos/path2.mp4',
                conflicting_files: [
                    {file_group_id: 3, current_path: 'c.mp4', title: 'Video 2', model_type: 'video', video_id: 3},
                    {file_group_id: 4, current_path: 'd.mp4', title: 'Video 2', model_type: 'video', video_id: 4},
                ],
            },
        ];

        renderWithProviders(
            <ConflictResolutionModal {...defaultProps} conflicts={multipleConflicts} />
        );

        expect(screen.getByText(/2 destination paths have/i)).toBeInTheDocument();
        expect(screen.getByText(/videos\/path1.mp4/)).toBeInTheDocument();
        expect(screen.getByText(/videos\/path2.mp4/)).toBeInTheDocument();
    });

    it('shows video type label for videos', () => {
        renderWithProviders(<ConflictResolutionModal {...defaultProps} />);

        const videoLabels = screen.getAllByText('video');
        expect(videoLabels.length).toBe(2);
    });

    it('shows archive type label for archives', () => {
        const archiveConflicts = [
            {
                destination_path: 'archives/page.html',
                conflicting_files: [
                    {file_group_id: 1, current_path: 'old.html', title: 'Page', model_type: 'archive', archive_id: 1},
                ],
            },
        ];

        renderWithProviders(
            <ConflictResolutionModal {...defaultProps} conflicts={archiveConflicts} collectionKind='domain' />
        );

        expect(screen.getByText('archive')).toBeInTheDocument();
    });

    it('does not render when closed', () => {
        renderWithProviders(
            <ConflictResolutionModal {...defaultProps} open={false} />
        );

        expect(screen.queryByText(/Resolve Conflicts Before Reorganizing/i)).not.toBeInTheDocument();
    });

    it('displays quality rank for videos', () => {
        const conflictsWithRank = [
            {
                destination_path: 'videos/2024-01-15/My Video.mp4',
                conflicting_files: [
                    {
                        file_group_id: 1,
                        current_path: 'videos/old/My Video.mp4',
                        title: 'My Video',
                        model_type: 'video',
                        size: 1024000,
                        video_id: 101,
                        quality_rank: 12,
                    },
                    {
                        file_group_id: 2,
                        current_path: 'videos/new/My Video.mp4',
                        title: 'My Video',
                        model_type: 'video',
                        size: 2048000,
                        video_id: 102,
                        quality_rank: 5,
                    },
                ],
            },
        ];

        renderWithProviders(
            <ConflictResolutionModal {...defaultProps} conflicts={conflictsWithRank} />
        );

        // Should show quality ranks
        expect(screen.getByText('12')).toBeInTheDocument();
        expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('shows recommended badge on highest ranked video', () => {
        const conflictsWithRank = [
            {
                destination_path: 'videos/2024-01-15/My Video.mp4',
                conflicting_files: [
                    {
                        file_group_id: 1,
                        current_path: 'videos/old/My Video.mp4',
                        title: 'My Video',
                        model_type: 'video',
                        video_id: 101,
                        quality_rank: 15,
                    },
                    {
                        file_group_id: 2,
                        current_path: 'videos/new/My Video.mp4',
                        title: 'My Video',
                        model_type: 'video',
                        video_id: 102,
                        quality_rank: 8,
                    },
                ],
            },
        ];

        renderWithProviders(
            <ConflictResolutionModal {...defaultProps} conflicts={conflictsWithRank} />
        );

        // Should show "Recommended to Keep" badge (only on the first/highest ranked)
        expect(screen.getByText(/Recommended to Keep/i)).toBeInTheDocument();
    });

    it('does not show rank display for archives', () => {
        const archiveConflicts = [
            {
                destination_path: 'archives/page.html',
                conflicting_files: [
                    {
                        file_group_id: 1,
                        current_path: 'old.html',
                        title: 'Page',
                        model_type: 'archive',
                        archive_id: 1,
                        quality_rank: null,
                    },
                    {
                        file_group_id: 2,
                        current_path: 'new.html',
                        title: 'Page',
                        model_type: 'archive',
                        archive_id: 2,
                        quality_rank: null,
                    },
                ],
            },
        ];

        renderWithProviders(
            <ConflictResolutionModal {...defaultProps} conflicts={archiveConflicts} collectionKind='domain' />
        );

        // Should NOT show "Recommended to Keep" badge for archives
        expect(screen.queryByText(/Recommended to Keep/i)).not.toBeInTheDocument();
    });
});
