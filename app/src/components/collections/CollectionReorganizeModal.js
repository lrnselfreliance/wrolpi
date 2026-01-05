import React, {useEffect, useState} from 'react';
import {Grid, Table, Loader} from 'semantic-ui-react';
import Message from 'semantic-ui-react/dist/commonjs/collections/Message';
import {Button, Modal} from '../Theme';
import {APIButton} from '../Common';
import {reorganizeCollection} from '../../api';

/**
 * Modal for previewing and executing collection file reorganization.
 * Shows files that will be moved and allows user to confirm or cancel.
 *
 * @param {boolean} open - Whether the modal is open
 * @param {Function} onClose - Callback when modal is closed
 * @param {number} collectionId - Collection ID to reorganize
 * @param {string} collectionName - Display name (e.g., "Domain", "Channel")
 * @param {Function} onSuccess - Callback after successful reorganization
 */
export function CollectionReorganizeModal({
    open,
    onClose,
    collectionId,
    collectionName = 'Collection',
    onSuccess,
}) {
    const [loading, setLoading] = useState(false);
    const [preview, setPreview] = useState(null);
    const [newFormat, setNewFormat] = useState('');
    const [error, setError] = useState(null);

    // Fetch preview when modal opens
    useEffect(() => {
        if (open && collectionId) {
            fetchPreview();
        } else {
            // Reset state when closing
            setPreview(null);
            setNewFormat('');
            setError(null);
        }
    }, [open, collectionId]);

    const fetchPreview = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await reorganizeCollection(collectionId, true);
            setPreview(data.preview);
            setNewFormat(data.new_file_format);
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const handleReorganize = async () => {
        try {
            await reorganizeCollection(collectionId, false);
            onClose();
            if (onSuccess) {
                onSuccess();
            }
        } catch (e) {
            setError(e.message);
        }
    };

    return (
        <Modal open={open} onClose={onClose} closeIcon size='large'>
            <Modal.Header>Reorganize {collectionName} Files</Modal.Header>
            <Modal.Content scrolling>
                {loading && <Loader active>Loading preview...</Loader>}

                {error && (
                    <Message negative>
                        <Message.Header>Error</Message.Header>
                        <p>{error}</p>
                    </Message>
                )}

                {preview && !loading && (
                    <Grid columns={1}>
                        <Grid.Row>
                            <Grid.Column>
                                <Message info>
                                    <Message.Header>New File Format</Message.Header>
                                    <p><code>{newFormat}</code></p>
                                </Message>
                            </Grid.Column>
                        </Grid.Row>
                        <Grid.Row>
                            <Grid.Column>
                                <p>
                                    <strong>{preview.files_to_move}</strong> files will be moved.
                                    <strong> {preview.files_unchanged}</strong> files are already in the correct location.
                                </p>
                            </Grid.Column>
                        </Grid.Row>
                        {preview.files_to_move > 0 && (
                            <Grid.Row>
                                <Grid.Column>
                                    <Table compact size='small'>
                                        <Table.Header>
                                            <Table.Row>
                                                <Table.HeaderCell>Current Path</Table.HeaderCell>
                                                <Table.HeaderCell>New Path</Table.HeaderCell>
                                            </Table.Row>
                                        </Table.Header>
                                        <Table.Body>
                                            {preview.moves.slice(0, 50).map((move, i) => (
                                                <Table.Row key={i}>
                                                    <Table.Cell>{move.from}</Table.Cell>
                                                    <Table.Cell>{move.to}</Table.Cell>
                                                </Table.Row>
                                            ))}
                                        </Table.Body>
                                    </Table>
                                    {preview.moves.length > 50 && (
                                        <p><em>...and {preview.moves.length - 50} more files</em></p>
                                    )}
                                </Grid.Column>
                            </Grid.Row>
                        )}
                    </Grid>
                )}
            </Modal.Content>
            <Modal.Actions>
                <Button onClick={onClose}>Cancel</Button>
                <APIButton
                    color='violet'
                    onClick={handleReorganize}
                    obeyWROLMode={true}
                    disabled={loading || !preview || preview.files_to_move === 0}
                >
                    {`Reorganize ${preview?.files_to_move || 0} Files`}
                </APIButton>
            </Modal.Actions>
        </Modal>
    );
}
