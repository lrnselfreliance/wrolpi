import React, {useEffect, useState} from 'react';
import {Card, Grid, Icon, Image, Label, Segment, Button as SButton} from 'semantic-ui-react';
import Message from 'semantic-ui-react/dist/commonjs/collections/Message';
import {Button, Modal} from '../Theme';
import {deleteArchives, deleteVideos} from '../../api';
import {humanFileSize, isoDatetimeToString} from '../Common';

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
 *   - video_id: number|null - Video ID if model_type is 'video'
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

    const handleDelete = async () => {
        setIsDeleting(true);
        setLocalError(null);

        try {
            if (file.model_type === 'video' && file.video_id) {
                await deleteVideos([file.video_id]);
            } else if (file.model_type === 'archive' && file.archive_id) {
                await deleteArchives([file.archive_id]);
            }
            onDelete(file);
        } catch (err) {
            setLocalError(err.message || 'Failed to delete');
        } finally {
            setIsDeleting(false);
        }
    };

    return (
        <Card fluid>
            <Card.Content>
                {localError && (
                    <Message negative size='small' style={{marginBottom: '0.5em'}}>
                        <Icon name='warning'/> {localError}
                    </Message>
                )}
                <Grid>
                    <Grid.Row>
                        {/* Poster/Thumbnail column */}
                        <Grid.Column width={4}>
                            {file.poster_path ? (
                                <Image
                                    src={`/media/${file.poster_path}`}
                                    size='small'
                                    style={{maxHeight: '100px', objectFit: 'cover'}}
                                />
                            ) : (
                                <Segment placeholder style={{height: '80px'}}>
                                    <Icon
                                        name={file.model_type === 'video' ? 'video' : 'file'}
                                        size='large'
                                        disabled
                                    />
                                </Segment>
                            )}
                        </Grid.Column>

                        {/* File info column */}
                        <Grid.Column width={10}>
                            <Card.Header style={{marginBottom: '0.5em'}}>
                                {file.title || 'Untitled'}
                                {isRecommended && (
                                    <Label color='green' size='small' style={{marginLeft: '0.5em'}}>
                                        <Icon name='star'/> Recommended to Keep
                                    </Label>
                                )}
                            </Card.Header>
                            <Card.Meta style={{wordBreak: 'break-all'}}>
                                <Icon name='folder open outline'/> {file.current_path}
                            </Card.Meta>
                            <Card.Description>
                                <div style={{marginTop: '0.5em'}}>
                                    {file.size > 0 && (
                                        <Label size='small'>
                                            <Icon name='hdd'/> {humanFileSize(file.size)}
                                        </Label>
                                    )}
                                    {file.published_datetime && (
                                        <Label size='small'>
                                            <Icon name='calendar'/> {isoDatetimeToString(file.published_datetime)}
                                        </Label>
                                    )}
                                    {file.source_id && (
                                        <Label size='small'>
                                            <Icon name='linkify'/> {file.source_id}
                                        </Label>
                                    )}
                                    {file.quality_rank !== null && file.quality_rank !== undefined && (
                                        <Label size='small' color='purple'>
                                            <Icon name='star outline'/> {file.quality_rank}
                                        </Label>
                                    )}
                                    <Label size='small' color={file.model_type === 'video' ? 'blue' : 'orange'}>
                                        {file.model_type}
                                    </Label>
                                </div>
                            </Card.Description>
                        </Grid.Column>

                        {/* Delete button column */}
                        <Grid.Column width={2} textAlign='center' verticalAlign='middle'>
                            <SButton
                                color='red'
                                icon
                                loading={isDeleting}
                                disabled={isDeleting}
                                onClick={handleDelete}
                                title='Delete this file'
                            >
                                <Icon name='trash'/>
                            </SButton>
                        </Grid.Column>
                    </Grid.Row>
                </Grid>
            </Card.Content>
        </Card>
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
    const totalFiles = localConflicts.reduce((sum, c) => sum + c.conflicting_files.length, 0);

    return (
        <Modal
            open={open}
            onClose={handleClose}
            closeIcon={true}
            size='fullscreen'
        >
            <Modal.Header>
                <Icon name='warning sign' color='yellow'/> Resolve Conflicts Before Reorganizing
            </Modal.Header>
            <Modal.Content scrolling>
                <Message warning>
                    <Message.Header>Destination Path Conflicts Detected</Message.Header>
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
                        <Segment key={idx}>
                            <Label attached='top' color='grey'>
                                <Icon name='folder'/> Destination: {conflict.destination_path}
                                <Label.Detail>{conflict.conflicting_files.length} files</Label.Detail>
                            </Label>

                            <div style={{marginTop: '1em'}}>
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
                        </Segment>
                    );
                })}

                {localConflicts.length === 0 && (
                    <Message success>
                        <Message.Header>All Conflicts Resolved</Message.Header>
                        <p>You can now proceed with the reorganization.</p>
                    </Message>
                )}
            </Modal.Content>
            <Modal.Actions>
                <Button onClick={handleClose}>
                    {localConflicts.length === 0 ? 'Done' : 'Close'}
                </Button>
            </Modal.Actions>
        </Modal>
    );
}
