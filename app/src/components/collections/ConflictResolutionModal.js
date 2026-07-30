import React, {useEffect, useState} from 'react';
import {IconVideo} from '@tabler/icons-react';
import {Button, Icon, IconButton, Label, Message, Modal, Panel, Stack} from '../ui';
import {deleteFileGroups} from '../../api';
import {humanFileSize, isoDatetimeToString} from '../Common';
import {TaggedDeleteConfirmModal} from '../TaggedDeleteConfirmModal';

/**
 * Card component for a single conflicting file.
 *
 * Manages its own loading and error state for deletion.
 * Only calls onDelete when deletion succeeds.
 *
 * @param {Object} file - File info object from backend containing:
 *   - file_group_id: number - ID of the FileGroup
 *   - current_path: string - Current file path
 *   - title: string - File title
 *   - model_type: 'video'|'archive' - Type of content
 *   - size: number - File size in bytes
 *   - archive_id: number|null - Archive ID if model_type is 'archive'
 *   - poster_path: string|null - Path to thumbnail/poster image
 *   - published_datetime: string|null - ISO datetime string
 *   - source_id: string|null - External source identifier
 *   - quality_rank: number|null - Quality score for recommendations
 * @param {Function} onDelete - Called with (file) when deletion succeeds
 * @param {boolean} isRecommended - Whether this file is recommended to keep
 */
function ConflictFileCard({file, onDelete, isRecommended}) {
    const [isDeleting, setIsDeleting] = useState(false);
    const [localError, setLocalError] = useState(null);
    const [taggedFileGroups, setTaggedFileGroups] = useState(null);

    const performDelete = async (force) => {
        if (file.file_group_id) {
            return await deleteFileGroups([file.file_group_id], force);
        }
        return null;
    };

    const handleDelete = async (force = false) => {
        setIsDeleting(true);
        setLocalError(null);

        try {
            const result = await performDelete(force);
            if (result && result.tagged) {
                setTaggedFileGroups(result.file_groups);
                return;
            }
            onDelete(file);
        } catch (err) {
            setLocalError(err.message || 'Failed to delete');
        } finally {
            setIsDeleting(false);
        }
    };

    return (
        <Panel style={{marginBottom: '0.5em'}}>
            {localError && (
                <div style={{marginBottom: '0.5em'}}>
                    <Message kind='error' icon='warning'>
                        {localError}
                    </Message>
                </div>
            )}
            <div style={{display: 'flex', gap: '1em', alignItems: 'center'}}>
                {/* Poster/Thumbnail column */}
                <div style={{flex: '0 0 100px'}}>
                    {file.poster_path ? (
                        <img
                            src={`/media/${file.poster_path}`}
                            alt=''
                            style={{width: '100%', height: '80px', objectFit: 'cover'}}
                        />
                    ) : (
                        <div style={{
                            height: '80px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            border: '1px solid var(--border)',
                            color: 'var(--muted)',
                        }}>
                            {file.model_type === 'video'
                                ? <Icon component={IconVideo} size='large'/>
                                : <Icon name='file' size='large'/>}
                        </div>
                    )}
                </div>

                {/* File info column */}
                <div style={{flex: '1 1 auto', minWidth: 0}}>
                    <div style={{marginBottom: '0.5em', fontWeight: 600}}>
                        {file.title || 'Untitled'}
                        {isRecommended && (
                            <Label color='green' style={{marginLeft: '0.5em'}}>
                                <Icon name='star'/> Recommended to Keep
                            </Label>
                        )}
                    </div>
                    <div style={{wordBreak: 'break-all', color: 'var(--muted)', fontSize: '0.9em'}}>
                        <Icon name='folder open outline'/> {file.current_path}
                    </div>
                    <div style={{marginTop: '0.5em', display: 'flex', flexWrap: 'wrap', gap: '0.4em'}}>
                        {file.size > 0 && (
                            <Label>
                                <Icon name='hdd'/> {humanFileSize(file.size)}
                            </Label>
                        )}
                        {file.published_datetime && (
                            <Label>
                                <Icon name='calendar'/> {isoDatetimeToString(file.published_datetime)}
                            </Label>
                        )}
                        {file.source_id && (
                            <Label>
                                <Icon name='linkify'/> {file.source_id}
                            </Label>
                        )}
                        {file.quality_rank !== null && file.quality_rank !== undefined && (
                            <Label color='violet'>
                                <Icon name='star outline'/> {file.quality_rank}
                            </Label>
                        )}
                        <Label color={file.model_type === 'video' ? 'blue' : 'orange'}>
                            {file.model_type}
                        </Label>
                    </div>
                </div>

                {/* Delete button column */}
                <div style={{flex: '0 0 auto'}}>
                    <IconButton
                        role='danger'
                        icon='trash'
                        label='Delete this file'
                        loading={isDeleting}
                        disabled={isDeleting}
                        onClick={() => handleDelete(false)}
                    />
                </div>
            </div>
            <TaggedDeleteConfirmModal
                open={taggedFileGroups !== null}
                taggedFileGroups={taggedFileGroups}
                onCancel={() => setTaggedFileGroups(null)}
                onConfirm={async () => {
                    setTaggedFileGroups(null);
                    await handleDelete(true);
                }}
            />
        </Panel>
    );
}

/**
 * Modal component for resolving reorganization conflicts.
 *
 * Shows files that would have the same destination path and allows users
 * to delete duplicates before proceeding with reorganization.
 *
 * @param {boolean} open - Whether the modal is open
 * @param {Function} onClose - Callback when modal is closed
 * @param {Array} conflicts - Array of ConflictDetail objects from the backend
 * @param {string} collectionKind - 'channel' or 'domain'
 * @param {Function} onResolved - Callback when a file is deleted (to refresh preview)
 */
export function ConflictResolutionModal({
                                            open,
                                            onClose,
                                            conflicts = [],
                                            collectionKind,
                                            onResolved,
                                        }) {
    const [localConflicts, setLocalConflicts] = useState(conflicts);
    const [hasChanges, setHasChanges] = useState(false);

    // Sync local conflicts with props when they change (e.g., when modal opens with new data)
    useEffect(() => {
        setLocalConflicts(conflicts);
        setHasChanges(false);
    }, [conflicts]);

    /**
     * Handle successful file deletion from a ConflictFileCard.
     * Only called when deletion succeeds (errors are handled in the card).
     * @param {Object} file - The file that was deleted
     */
    const handleFileDelete = (file) => {
        // Update local conflicts: remove the deleted file
        setLocalConflicts(prev => {
            const updated = prev.map(conflict => ({
                ...conflict,
                conflicting_files: conflict.conflicting_files.filter(
                    f => f.file_group_id !== file.file_group_id
                ),
            })).filter(conflict => conflict.conflicting_files.length > 1);
            // Keep conflicts that still have 2+ files
            return updated;
        });
        setHasChanges(true);
    };

    const handleClose = () => {
        if (hasChanges && onResolved) {
            onResolved();
        }
        onClose();
    };

    const totalConflicts = localConflicts.length;

    return (
        <Modal
            open={open}
            onClose={handleClose}
            closeIcon={true}
            size='fullscreen'
        >
            <Modal.Header>
                <Icon name='warning sign'/> Resolve Conflicts Before Reorganizing
            </Modal.Header>
            <Modal.Content scrolling>
                <Message kind='warning' title='Destination Path Conflicts Detected'>
                    <p>
                        {totalConflicts} destination {totalConflicts === 1 ? 'path has' : 'paths have'}{' '}
                        multiple files that would be moved there. This typically happens when the same{' '}
                        {collectionKind === 'channel' ? 'video' : 'page'} was downloaded multiple times.
                    </p>
                    <p>
                        <strong>Delete the duplicates you don't want to keep</strong> before reorganizing.
                        For each conflict, keep only one file.
                    </p>
                </Message>

                <Stack>
                    {localConflicts.map((conflict, idx) => {
                        // Find the highest quality rank in this conflict (for video recommendations)
                        const hasRanks = conflict.conflicting_files.some(
                            f => f.quality_rank !== null && f.quality_rank !== undefined
                        );
                        const highestRank = hasRanks
                            ? Math.max(...conflict.conflicting_files.map(f => f.quality_rank || 0))
                            : null;
                        // Check if there are multiple files with the same highest rank
                        const highestRankCount = hasRanks
                            ? conflict.conflicting_files.filter(f => f.quality_rank === highestRank).length
                            : 0;

                        return (
                            <Panel key={idx}>
                                <div style={{display: 'flex', alignItems: 'center', gap: '0.5em', marginBottom: '1em'}}>
                                    <Icon name='folder'/>
                                    <strong>Destination: {conflict.destination_path}</strong>
                                    <Label>{conflict.conflicting_files.length} files</Label>
                                </div>

                                <div>
                                    {conflict.conflicting_files.map((file, fileIdx) => {
                                        // Only show "Recommended" if there's a clear winner (one file with highest rank)
                                        const isRecommended = hasRanks &&
                                            highestRankCount === 1 &&
                                            file.quality_rank === highestRank;

                                        return (
                                            <ConflictFileCard
                                                key={file.file_group_id}
                                                file={file}
                                                onDelete={handleFileDelete}
                                                isRecommended={isRecommended}
                                            />
                                        );
                                    })}
                                </div>
                            </Panel>
                        );
                    })}
                </Stack>

                {localConflicts.length === 0 && (
                    <Message kind='success' title='All Conflicts Resolved'>
                        <p>You can now proceed with the reorganization.</p>
                    </Message>
                )}
            </Modal.Content>
            <Modal.Actions>
                <Button role='cancel' onClick={handleClose}>
                    {localConflicts.length === 0 ? 'Done' : 'Close'}
                </Button>
            </Modal.Actions>
        </Modal>
    );
}
