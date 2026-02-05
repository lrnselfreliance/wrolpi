import React, {useCallback, useEffect, useState} from 'react';
import {Button as SButton, Grid, Icon, Label, Progress} from 'semantic-ui-react';
import Message from 'semantic-ui-react/dist/commonjs/collections/Message';
import {Button, Modal, Table} from '../Theme';
import {APIButton} from '../Common';
import {
    executeCollectionReorganization,
    fetchCollectionConflicts,
    getReorganizationStatus,
    previewCollectionReorganization
} from '../../api';
import {useReorganizationStatus} from '../../contexts/FileWorkerStatusContext';
import {ConflictResolutionModal} from './ConflictResolutionModal';

/**
 * Modal component for previewing and executing collection file reorganization.
 *
 * Shows a preview of files that will be moved when the file_name_format changes,
 * allows user to execute the reorganization, and tracks progress.
 *
 * @param {boolean} open - Whether the modal is open
 * @param {Function} onClose - Callback when modal is closed
 * @param {number} collectionId - ID of the collection to reorganize
 * @param {string} collectionName - Name of the collection for display
 * @param {Function} onComplete - Optional callback when reorganization completes
 * @param {boolean} needsReorganization - Whether the collection.needs_reorganization flag is true
 * @param {string} collectionKind - 'channel' or 'domain' for conflict resolution modal
 */
export function CollectionReorganizeModal({
                                              open,
                                              onClose,
                                              collectionId,
                                              collectionName,
                                              onComplete,
                                              needsReorganization,
                                              collectionKind,
                                          }) {
    const [loading, setLoading] = useState(false);
    const [preview, setPreview] = useState(null);
    const [error, setError] = useState(null);
    const [jobId, setJobId] = useState(null);
    const [status, setStatus] = useState(null);
    const [polling, setPolling] = useState(false);
    const [showConflictModal, setShowConflictModal] = useState(false);
    const [loadingConflicts, setLoadingConflicts] = useState(false);

    // Check if this collection is currently being reorganized
    const {
        isReorganizing,
        taskType,
        collectionId: activeCollectionId,
        workerStatus,
    } = useReorganizationStatus();

    // Load preview when modal opens, or resume if already reorganizing
    useEffect(() => {
        if (open && collectionId) {
            // Check if THIS collection is currently being reorganized
            const isThisActive = isReorganizing &&
                taskType === 'reorganize' &&
                activeCollectionId === collectionId;

            if (isThisActive) {
                // Resume: show current progress from worker status
                // Don't set a fake job ID - we'll watch context instead
                setLoading(false);
                setPreview(null);
                setJobId(null);
                setStatus({
                    status: workerStatus.status,
                    total: workerStatus.operation_total,
                    completed: workerStatus.operation_processed,
                    percent: workerStatus.operation_percent,
                });
                setPolling(false);  // Don't poll job endpoint - watch context instead
            } else if (!polling && !jobId) {
                // Normal: fetch preview (only if not already polling/resuming)
                setLoading(true);
                setError(null);
                setPreview(null);
                setJobId(null);
                setStatus(null);

                previewCollectionReorganization(collectionId)
                    .then(data => {
                        setPreview(data);
                        setLoading(false);
                    })
                    .catch(err => {
                        setError(err.message);
                        setLoading(false);
                    });
            }
        }
    }, [open, collectionId, isReorganizing, taskType, activeCollectionId]);

    // Poll for status when we have a job ID
    // Uses setTimeout instead of setInterval to wait for each request to complete
    // before scheduling the next one, preventing request pile-up on slow connections
    useEffect(() => {
        if (!jobId || !polling) return;

        let timeoutId = null;
        let cancelled = false;

        const pollStatus = async () => {
            if (cancelled) return;

            try {
                const statusData = await getReorganizationStatus(collectionId, jobId);
                if (cancelled) return;

                setStatus(statusData);

                if (statusData.status === 'complete') {
                    setPolling(false);
                    if (onComplete) {
                        onComplete();
                    }
                } else if (statusData.status === 'error' || statusData.error) {
                    setPolling(false);
                    setError(statusData.error || 'Reorganization failed');
                } else {
                    // Schedule next poll after this one completes
                    timeoutId = setTimeout(pollStatus, 1000);
                }
            } catch (err) {
                console.error('Failed to get reorganization status', err);
                if (!cancelled) {
                    // Retry after delay even on error
                    timeoutId = setTimeout(pollStatus, 1000);
                }
            }
        };

        // Start polling immediately
        pollStatus();

        return () => {
            cancelled = true;
            if (timeoutId) {
                clearTimeout(timeoutId);
            }
        };
    }, [jobId, polling, collectionId, onComplete]);

    // Watch context for status updates when resuming an active reorganization
    useEffect(() => {
        const isThisActive = isReorganizing &&
            taskType === 'reorganize' &&
            activeCollectionId === collectionId;

        // Only watch when: modal is open, no real job ID, and this collection is active
        if (!open || jobId || !isThisActive) return;

        // Update status from context (only when values actually change)
        const newStatus = workerStatus?.status || 'running';
        const newTotal = workerStatus?.operation_total || 0;
        const newCompleted = workerStatus?.operation_processed || 0;
        const newPercent = workerStatus?.operation_percent || 0;

        setStatus(prev => {
            // Only update if values actually changed to prevent infinite loops
            if (prev &&
                prev.status === newStatus &&
                prev.total === newTotal &&
                prev.completed === newCompleted &&
                prev.percent === newPercent) {
                return prev;  // Return same object to prevent re-render
            }
            return {
                status: newStatus,
                total: newTotal,
                completed: newCompleted,
                percent: newPercent,
            };
        });
    }, [open, jobId, isReorganizing, taskType, activeCollectionId, workerStatus, collectionId]);

    // Detect completion when context indicates reorganization stopped for this collection
    useEffect(() => {
        // Only relevant when we have status but no job ID (resumed from context)
        if (!status || jobId) return;

        const isThisActive = isReorganizing &&
            taskType === 'reorganize' &&
            activeCollectionId === collectionId;

        if (!isThisActive && status.status !== 'complete') {
            // Reorganization completed
            setStatus(prev => ({...prev, status: 'complete', percent: 100}));
            if (onComplete) {
                onComplete();
            }
        }
    }, [isReorganizing, taskType, activeCollectionId, collectionId, status, jobId, onComplete]);

    const handleClose = useCallback(() => {
        // Allow closing - user can reopen to resume if needed
        setPreview(null);
        setError(null);
        setJobId(null);
        setStatus(null);
        setPolling(false);
        setShowConflictModal(false);
        onClose();
    }, [onClose]);

    // Reload preview (used after conflict resolution)
    const reloadPreview = useCallback(() => {
        setLoading(true);
        setError(null);

        previewCollectionReorganization(collectionId)
            .then(data => {
                setPreview(data);
                setLoading(false);
            })
            .catch(err => {
                setError(err.message);
                setLoading(false);
            });
    }, [collectionId]);

    const handleConflictResolved = useCallback(() => {
        // Reload preview to get updated conflicts
        // Note: The conflict modal calls onClose() after onResolved(), which handles closing
        reloadPreview();
    }, [reloadPreview]);

    const handleResolveConflicts = useCallback(async () => {
        setLoadingConflicts(true);
        setError(null);
        try {
            const data = await fetchCollectionConflicts(collectionId);
            // Update preview with fresh conflicts (including updated quality rankings)
            setPreview(prev => ({
                ...prev,
                conflicts: data.conflicts,
                has_conflicts: data.conflicts.length > 0,
            }));
            setShowConflictModal(true);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoadingConflicts(false);
        }
    }, [collectionId]);

    const handleReorganize = useCallback(async () => {
        try {
            setError(null);
            const result = await executeCollectionReorganization(collectionId);
            if (result.job_id) {
                setJobId(result.job_id);
                setPolling(true);
                setStatus({status: 'pending', total: 0, completed: 0, percent: 0});
            } else {
                // No files needed reorganization
                if (onComplete) {
                    onComplete();
                }
                handleClose();
            }
        } catch (err) {
            setError(err.message);
        }
    }, [collectionId, onComplete, handleClose]);

    const renderPreview = () => {
        if (!preview) return null;

        return (
            <Grid columns={1}>
                {/* Warning when collection appears organized but has files to move */}
                {preview.files_needing_move > 0 && !needsReorganization && (
                    <Grid.Row>
                        <Grid.Column>
                            <Message warning>
                                <Message.Header>Collection Appears Organized</Message.Header>
                                <p>
                                    This collection's format matches the current configuration, but
                                    {' '}<strong>{preview.files_needing_move}</strong> files don't match the expected
                                    layout.
                                    This can happen if a previous reorganization was interrupted.
                                </p>
                            </Message>
                        </Grid.Column>
                    </Grid.Row>
                )}
                <Grid.Row>
                    <Grid.Column>
                        <p>
                            <strong>{preview.files_needing_move}</strong> of <strong>{preview.total_files}</strong> files
                            will be reorganized.
                        </p>
                        {preview.current_file_format && (
                            <p>
                                <strong>Current format:</strong> <code>{preview.current_file_format}</code>
                            </p>
                        )}
                        <p>
                            <strong>New format:</strong> <Label>{preview.new_file_format}</Label>
                        </p>
                    </Grid.Column>
                </Grid.Row>

                {/* Conflict warning */}
                {preview.has_conflicts && (
                    <Grid.Row>
                        <Grid.Column>
                            <Message error>
                                <Message.Header>
                                    <Icon name='warning sign'/> Conflicts Detected
                                </Message.Header>
                                <p>
                                    <strong>{preview.conflicts.length}</strong> destination{' '}
                                    {preview.conflicts.length === 1 ? 'path has' : 'paths have'}{' '}
                                    multiple files that would collide.
                                    You must resolve these conflicts before reorganizing.
                                </p>
                                <SButton
                                    color='yellow'
                                    onClick={handleResolveConflicts}
                                    loading={loadingConflicts}
                                    disabled={loadingConflicts}
                                >
                                    <Icon name='wrench'/> Resolve Conflicts
                                </SButton>
                            </Message>
                        </Grid.Column>
                    </Grid.Row>
                )}

                {preview.sample_moves && preview.sample_moves.length > 0 && (
                    <Grid.Row>
                        <Grid.Column>
                            <strong>Sample moves:</strong>
                            <Table basic='very' compact size='small'>
                                <Table.Header>
                                    <Table.Row>
                                        <Table.HeaderCell>Current Path</Table.HeaderCell>
                                        <Table.HeaderCell/>
                                        <Table.HeaderCell>New Path</Table.HeaderCell>
                                    </Table.Row>
                                </Table.Header>
                                <Table.Body>
                                    {preview.sample_moves.map((move, idx) => (
                                        <Table.Row key={idx}>
                                            <Table.Cell style={{wordBreak: 'break-all'}}>
                                                {move.old_path}
                                            </Table.Cell>
                                            <Table.Cell>
                                                <Icon name='arrow right'/>
                                            </Table.Cell>
                                            <Table.Cell style={{wordBreak: 'break-all'}}>
                                                {move.new_path}
                                            </Table.Cell>
                                        </Table.Row>
                                    ))}
                                </Table.Body>
                            </Table>
                            {preview.files_needing_move > preview.sample_moves.length && (
                                <p style={{fontStyle: 'italic'}}>
                                    ...and {preview.files_needing_move - preview.sample_moves.length} more files
                                </p>
                            )}
                        </Grid.Column>
                    </Grid.Row>
                )}

                {preview.files_needing_move === 0 && (
                    <Grid.Row>
                        <Grid.Column>
                            <Message info>
                                <Message.Header>No Files Need Reorganization</Message.Header>
                                <p>All files are already organized according to the current format.</p>
                            </Message>
                        </Grid.Column>
                    </Grid.Row>
                )}
            </Grid>
        );
    };

    const renderProgress = () => {
        if (!status) return null;

        return (
            <Grid columns={1}>
                <Grid.Row>
                    <Grid.Column>
                        <p>
                            <strong>Status:</strong> {status.status}
                        </p>
                        <Progress
                            percent={status.percent || 0}
                            progress
                            indicating={status.status !== 'complete'}
                            success={status.status === 'complete'}
                        />
                        <p>
                            {status.completed || 0} of {status.total || 0} files processed
                        </p>
                    </Grid.Column>
                </Grid.Row>

                {status.status === 'complete' && (
                    <Grid.Row>
                        <Grid.Column>
                            <Message success>
                                <Message.Header>Reorganization Complete</Message.Header>
                                <p>All files have been reorganized successfully.</p>
                            </Message>
                        </Grid.Column>
                    </Grid.Row>
                )}
            </Grid>
        );
    };

    const isInProgress = polling || (status && status.status !== 'complete' && status.status !== 'error');
    const hasConflicts = preview && preview.has_conflicts;
    const canReorganize = preview && preview.files_needing_move > 0 && !isInProgress && !jobId && !hasConflicts;

    return (
        <>
            <Modal
                open={open}
                onClose={handleClose}
                closeIcon={true}
                closeOnDimmerClick={!isInProgress}
                closeOnEscape={!isInProgress}
                size='fullscreen'
            >
                <Modal.Header>
                    Reorganize Files: {collectionName}
                </Modal.Header>
                <Modal.Content>
                    {loading && (
                        <Message icon>
                            <Icon name='circle notched' loading/>
                            <Message.Content>
                                <Message.Header>Loading Preview</Message.Header>
                                Analyzing files...
                            </Message.Content>
                        </Message>
                    )}

                    {error && (
                        <Message negative>
                            <Message.Header>Error</Message.Header>
                            <p style={{whiteSpace: 'pre-wrap'}}>{error}</p>
                        </Message>
                    )}

                    {!loading && !status && renderPreview()}
                    {status && renderProgress()}
                </Modal.Content>
                <Modal.Actions>
                    <Button onClick={handleClose}>
                        {status?.status === 'complete' ? 'Close' : isInProgress ? 'Hide' : 'Cancel'}
                    </Button>
                    {canReorganize && (
                        <APIButton
                            color='violet'
                            onClick={handleReorganize}
                            obeyWROLMode={true}
                        >
                            Reorganize Files
                        </APIButton>
                    )}
                </Modal.Actions>
            </Modal>

            {/* Conflict Resolution Modal */}
            <ConflictResolutionModal
                open={showConflictModal}
                onClose={() => setShowConflictModal(false)}
                conflicts={preview?.conflicts || []}
                collectionKind={collectionKind}
                onResolved={handleConflictResolved}
            />
        </>
    );
}
