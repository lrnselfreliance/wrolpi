import React, {useCallback, useEffect, useState} from 'react';
import {Link} from 'react-router';
import {Grid, Icon, Label, Progress, Button as SButton} from 'semantic-ui-react';
import Message from 'semantic-ui-react/dist/commonjs/collections/Message';
import {Button, Modal, Table} from '../Theme';
import {APIButton} from '../Common';
import {
    executeBatchReorganization,
    getBatchReorganizationStatus,
    previewBatchReorganization
} from '../../api';
import {useReorganizationStatus, useFileWorkerStatus} from '../../contexts/FileWorkerStatusContext';

/**
 * Modal component for previewing and executing batch collection file reorganization.
 *
 * Shows a list of collections that need reorganization, allows user to execute
 * batch reorganization, and tracks progress with dual progress bars (overall and per-collection).
 *
 * @param {boolean} open - Whether the modal is open
 * @param {Function} onClose - Callback when modal is closed
 * @param {string} kind - 'channel' or 'domain'
 * @param {Function} onComplete - Optional callback when reorganization completes
 */
export function BatchReorganizeModal({
                                         open,
                                         onClose,
                                         kind,
                                         onComplete,
                                     }) {
    const [loading, setLoading] = useState(false);
    const [preview, setPreview] = useState(null);
    const [error, setError] = useState(null);
    const [batchJobId, setBatchJobId] = useState(null);
    const [status, setStatus] = useState(null);
    const [polling, setPolling] = useState(false);

    const kindLabel = kind === 'channel' ? 'Channel' : 'Domain';
    const kindLabelPlural = kind === 'channel' ? 'Channels' : 'Domains';

    // Check if batch reorganization is currently active
    const {
        isReorganizing,
        taskType,
        collectionKind,
        batchStatus: workerBatchStatus,
        workerStatus,
    } = useReorganizationStatus();
    const {setFastPolling} = useFileWorkerStatus();

    // Enable fast polling when modal is open
    useEffect(() => {
        if (open) {
            setFastPolling(true);
        }
        return () => setFastPolling(false);
    }, [open, setFastPolling]);

    // Load preview when modal opens, or resume if already reorganizing
    useEffect(() => {
        if (open && kind) {
            // Check if batch_status has an active job for this kind
            // This is the primary indicator since worker status can briefly show
            // 'reorganizing'/'reorganize' during individual collection processing
            const hasActiveBatchJob = workerBatchStatus?.batch_job_id &&
                                     collectionKind === kind;

            // Worker is actively doing something (taskType is set)
            // After batch completes, taskType becomes null, so this distinguishes
            // "batch in progress" from "batch completed but batch_job_id still cached"
            const workerIsActive = taskType != null;

            // Use either the standard detection OR the batch_status fallback (only when worker is active)
            const isThisActive = (isReorganizing && taskType === 'batch_reorganize' && collectionKind === kind) ||
                                (hasActiveBatchJob && workerIsActive);

            if (isThisActive && workerBatchStatus) {
                // Resume: start polling API immediately for accurate progress
                // Don't use workerBatchStatus.current_collection directly as it may have stale
                // percent/total/completed values. The batch status API returns fresh values
                // by copying operation_percent into current_collection.percent.
                setLoading(false);
                setPreview(null);
                setBatchJobId(workerBatchStatus.batch_job_id || null);
                // Don't setStatus from workerBatchStatus - let the first poll populate it
                // with accurate values from the batch status API
                setPolling(true);
            } else if (!polling && !batchJobId) {
                // Normal: fetch preview (only if not already polling/resuming)
                setLoading(true);
                setError(null);
                setPreview(null);
                setBatchJobId(null);
                setStatus(null);

                previewBatchReorganization(kind)
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
    }, [open, kind, isReorganizing, taskType, collectionKind]);

    // Poll for status when we have a batch job ID
    useEffect(() => {
        if (!batchJobId || !polling) {
            return;
        }

        let timeoutId = null;
        let cancelled = false;

        const pollStatus = async () => {
            if (cancelled) {
                return;
            }

            try {
                const statusData = await getBatchReorganizationStatus(batchJobId);
                if (cancelled) return;

                setStatus(statusData);

                if (statusData.status === 'complete') {
                    setPolling(false);
                    if (onComplete) {
                        onComplete();
                    }
                } else if (statusData.status === 'failed' || statusData.error) {
                    setPolling(false);
                    setError(statusData.error || 'Batch reorganization failed');
                } else {
                    // Schedule next poll after this one completes
                    timeoutId = setTimeout(pollStatus, 500);
                }
            } catch (err) {
                console.error('Failed to get batch reorganization status', err);
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
    }, [batchJobId, polling, onComplete]);

    const handleClose = useCallback(() => {
        // Allow closing - user can reopen to resume if needed
        setPreview(null);
        setError(null);
        setBatchJobId(null);
        setStatus(null);
        setPolling(false);
        onClose();
    }, [onClose]);

    const handleReorganize = useCallback(async () => {
        try {
            setError(null);
            const result = await executeBatchReorganization(kind);
            if (result.batch_job_id) {
                setBatchJobId(result.batch_job_id);
                setPolling(true);
                setStatus({
                    status: 'pending',
                    total_collections: result.collection_count,
                    completed_collections: 0,
                    current_collection: null,
                    overall_percent: 0,
                    failed_collection: null,
                    error: null,
                });
            } else {
                // No collections needed reorganization
                if (onComplete) {
                    onComplete();
                }
                handleClose();
            }
        } catch (err) {
            setError(err.message);
        }
    }, [kind, onComplete, handleClose]);

    const renderPreview = () => {
        if (!preview) return null;

        return (
            <Grid columns={1}>
                <Grid.Row>
                    <Grid.Column>
                        <p>
                            <strong>{preview.total_collections}</strong> {kindLabelPlural.toLowerCase()} need reorganization,
                            with <strong>{preview.total_files_needing_move}</strong> total files to move.
                        </p>
                        <p>
                            <strong>New format:</strong> <Label>{preview.new_file_format}</Label>
                        </p>
                    </Grid.Column>
                </Grid.Row>

                {preview.collections && preview.collections.length > 0 && (
                    <Grid.Row>
                        <Grid.Column>
                            <strong>{kindLabelPlural} to reorganize:</strong>
                            <Table basic='very' compact size='small'>
                                <Table.Header>
                                    <Table.Row>
                                        <Table.HeaderCell>{kindLabel}</Table.HeaderCell>
                                        <Table.HeaderCell>Files to Move</Table.HeaderCell>
                                        <Table.HeaderCell>Sample</Table.HeaderCell>
                                    </Table.Row>
                                </Table.Header>
                                <Table.Body>
                                    {preview.collections.slice(0, 10).map((collection, idx) => (
                                        <Table.Row key={idx}>
                                            <Table.Cell>{collection.collection_name}</Table.Cell>
                                            <Table.Cell>
                                                {collection.total_files}
                                            </Table.Cell>
                                            <Table.Cell style={{wordBreak: 'break-all', fontSize: '0.9em'}}>
                                                {collection.sample_move ? (
                                                    <>
                                                        <span style={{color: '#888'}}>{collection.sample_move.old_path}</span>
                                                        <br/>
                                                        <Icon name='arrow right' size='small'/>
                                                        <span>{collection.sample_move.new_path}</span>
                                                    </>
                                                ) : '-'}
                                            </Table.Cell>
                                        </Table.Row>
                                    ))}
                                </Table.Body>
                            </Table>
                            {preview.collections.length > 10 && (
                                <p style={{fontStyle: 'italic'}}>
                                    ...and {preview.collections.length - 10} more {kindLabelPlural.toLowerCase()}
                                </p>
                            )}
                        </Grid.Column>
                    </Grid.Row>
                )}

                {preview.total_collections === 0 && (
                    <Grid.Row>
                        <Grid.Column>
                            <Message info>
                                <Message.Header>No {kindLabelPlural} Need Reorganization</Message.Header>
                                <p>All {kindLabelPlural.toLowerCase()} are already organized according to the current format.</p>
                            </Message>
                        </Grid.Column>
                    </Grid.Row>
                )}
            </Grid>
        );
    };

    const renderProgress = () => {
        if (!status) return null;

        const currentCollection = status.current_collection;

        return (
            <Grid columns={1}>
                <Grid.Row>
                    <Grid.Column>
                        <p>
                            <strong>Overall Status:</strong> {status.status}
                        </p>
                        <strong>Overall Progress:</strong>
                        <Progress
                            percent={status.overall_percent || 0}
                            progress
                            indicating={status.status !== 'complete' && status.status !== 'failed'}
                            success={status.status === 'complete'}
                            error={status.status === 'failed'}
                        />
                        <p>
                            {status.completed_collections || 0} of {status.total_collections || 0} {kindLabelPlural.toLowerCase()} completed
                        </p>
                    </Grid.Column>
                </Grid.Row>

                {currentCollection && (
                    <Grid.Row>
                        <Grid.Column>
                            <strong>Currently Processing:</strong> {currentCollection.name}
                            <Progress
                                percent={currentCollection.percent || 0}
                                progress
                                indicating
                                size='small'
                                color='blue'
                            />
                            <p style={{fontSize: '0.9em'}}>
                                {currentCollection.completed || 0} of {currentCollection.total || 0} files
                            </p>
                        </Grid.Column>
                    </Grid.Row>
                )}

                {status.status === 'complete' && (
                    <Grid.Row>
                        <Grid.Column>
                            <Message success>
                                <Message.Header>Batch Reorganization Complete</Message.Header>
                                <p>All {kindLabelPlural.toLowerCase()} have been reorganized successfully.</p>
                            </Message>
                        </Grid.Column>
                    </Grid.Row>
                )}

                {status.status === 'failed' && status.failed_collection && (
                    <Grid.Row>
                        <Grid.Column>
                            <Message negative>
                                <Message.Header>Reorganization Failed</Message.Header>
                                <p>
                                    Failed on {kindLabel.toLowerCase()}: <strong>{status.failed_collection.name}</strong>
                                </p>
                                <SButton
                                    as={Link}
                                    to={kind === 'channel'
                                        ? `/videos/channel/${status.failed_collection.channel_id || status.failed_collection.id}/edit`
                                        : `/archive/domain/${status.failed_collection.id}/edit`
                                    }
                                    size='small'
                                >
                                    <Icon name='eye'/> View {kindLabel}
                                </SButton>
                                {status.error && (
                                    <p style={{whiteSpace: 'pre-wrap'}}>Error: {status.error}</p>
                                )}
                            </Message>
                        </Grid.Column>
                    </Grid.Row>
                )}
            </Grid>
        );
    };

    const isInProgress = polling || (status && status.status !== 'complete' && status.status !== 'failed');
    const canReorganize = preview && preview.total_collections > 0 && !isInProgress && !batchJobId;

    return (
        <Modal
            open={open}
            onClose={handleClose}
            closeIcon={true}
            closeOnDimmerClick={!isInProgress}
            closeOnEscape={!isInProgress}
            size='large'
        >
            <Modal.Header>
                Reorganize All {kindLabelPlural}
            </Modal.Header>
            <Modal.Content scrolling>
                {loading && (
                    <Message icon>
                        <Icon name='circle notched' loading/>
                        <Message.Content>
                            <Message.Header>Loading Preview</Message.Header>
                            Analyzing {kindLabelPlural.toLowerCase()}...
                        </Message.Content>
                    </Message>
                )}

                {error && !status?.failed_collection && (
                    <Message negative>
                        <Message.Header>Error</Message.Header>
                        <p>{error}</p>
                    </Message>
                )}

                {!loading && !batchJobId && renderPreview()}
                {batchJobId && renderProgress()}
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
                        Reorganize All {kindLabelPlural}
                    </APIButton>
                )}
            </Modal.Actions>
        </Modal>
    );
}
