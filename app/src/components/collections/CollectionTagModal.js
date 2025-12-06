import React, {useState, useEffect, useCallback} from 'react';
import {Grid, Input} from 'semantic-ui-react';
import Message from 'semantic-ui-react/dist/commonjs/collections/Message';
import {Button, Modal, ModalActions, ModalContent, ModalHeader} from '../Theme';
import {TagsSelector} from '../../Tags';
import {APIButton, Toggle} from '../Common';

/**
 * Reusable modal component for tagging collections (Domains, Channels, etc).
 * Handles tag selection, directory suggestions, conflict warnings, and state reset on close.
 *
 * @param {boolean} open - Whether the modal is open
 * @param {Function} onClose - Callback when modal is closed
 * @param {string} currentTagName - The current tag name of the collection (if any)
 * @param {string} originalDirectory - The original directory of the collection (for reset)
 * @param {Function} getTagInfo - Async function to fetch tag info: (tagName) => Promise<{suggested_directory, conflict, conflict_message}>
 * @param {Function} onSave - Async function called when saving: (tagName, directory) => Promise<void>
 * @param {string} collectionName - Name of the collection for toast messages (e.g., "Domain", "Channel")
 * @param {boolean} hasDirectory - Whether the collection has a directory (default true for backward compatibility)
 *                                 When false, hides directory toggle and input, always passes null for directory
 */
export function CollectionTagModal({
    open,
    onClose,
    currentTagName,
    originalDirectory,
    getTagInfo,
    onSave,
    collectionName = 'Collection',
    hasDirectory = true,
}) {
    const [newTagName, setNewTagName] = useState(currentTagName || null);
    const [moveToTagDirectory, setMoveToTagDirectory] = useState(true);
    const [newTagDirectory, setNewTagDirectory] = useState(originalDirectory || '');
    const [conflictMessage, setConflictMessage] = useState(null);

    // Reset state when modal opens or collection changes
    useEffect(() => {
        if (open) {
            setNewTagName(currentTagName || null);
            setNewTagDirectory(originalDirectory || '');
            setConflictMessage(null);
        }
    }, [open, currentTagName, originalDirectory]);

    // Handle modal close - reset to original values
    const handleClose = useCallback(() => {
        setNewTagName(currentTagName || null);
        setNewTagDirectory(originalDirectory || '');
        setConflictMessage(null);
        onClose();
    }, [currentTagName, originalDirectory, onClose]);

    // Handle tag selection change - fetch tag info
    const handleTagChange = useCallback(async (tagName) => {
        setNewTagName(tagName);
        setConflictMessage(null);

        // Always fetch tag info when tag changes (including removal)
        try {
            const tagInfo = await getTagInfo(tagName);
            if (tagInfo) {
                // Handle both response formats:
                // - Object format: {suggested_directory, conflict, conflict_message}
                // - String format: just the directory path (legacy channel API)
                if (typeof tagInfo === 'string') {
                    // Legacy format - just a directory string
                    setNewTagDirectory(tagInfo);
                } else if (tagInfo.suggested_directory) {
                    setNewTagDirectory(tagInfo.suggested_directory);
                } else if (!tagName) {
                    // If tag removed and no suggestion, reset to original
                    setNewTagDirectory(originalDirectory || '');
                }

                // Handle conflict message (only in object format)
                if (typeof tagInfo === 'object' && tagInfo.conflict && tagInfo.conflict_message) {
                    setConflictMessage(tagInfo.conflict_message);
                }
            } else if (!tagName) {
                // If no tag info returned and tag was removed, reset to original
                setNewTagDirectory(originalDirectory || '');
            }
        } catch (e) {
            console.error(`Failed to get tag info for ${collectionName}`, e);
            // Don't block the UI if tag info fails
        }
    }, [getTagInfo, originalDirectory, collectionName]);

    // Handle save
    const handleSave = useCallback(async () => {
        // When hasDirectory is false, always pass null for directory
        const directoryToSave = hasDirectory && moveToTagDirectory ? newTagDirectory : null;
        await onSave(newTagName, directoryToSave);
        handleClose();
    }, [newTagName, hasDirectory, moveToTagDirectory, newTagDirectory, onSave, handleClose]);

    const modalTitle = currentTagName ? 'Modify Tag' : 'Add Tag';
    // Show "Move" button only when hasDirectory is true and move toggle is on
    const saveButtonText = hasDirectory && moveToTagDirectory ? 'Move' : 'Save';

    return (
        <Modal
            open={open}
            onClose={handleClose}
            closeIcon
        >
            <ModalHeader>{modalTitle}</ModalHeader>
            <ModalContent>
                <Grid columns={1}>
                    <Grid.Row>
                        <Grid.Column>
                            <TagsSelector
                                limit={1}
                                selectedTagNames={newTagName ? [newTagName] : []}
                                onAdd={handleTagChange}
                                onRemove={() => handleTagChange(null)}
                            />
                        </Grid.Column>
                    </Grid.Row>
                    {hasDirectory && (
                        <Grid.Row>
                            <Grid.Column>
                                <Toggle
                                    label='Move to directory: '
                                    checked={moveToTagDirectory}
                                    onChange={setMoveToTagDirectory}
                                />
                            </Grid.Column>
                        </Grid.Row>
                    )}
                    {hasDirectory && (
                        <Grid.Row>
                            <Grid.Column>
                                <Input
                                    fluid
                                    value={newTagDirectory}
                                    onChange={(e, {value}) => setNewTagDirectory(value)}
                                    disabled={!moveToTagDirectory}
                                />
                            </Grid.Column>
                        </Grid.Row>
                    )}
                    {hasDirectory && conflictMessage && (
                        <Grid.Row>
                            <Grid.Column>
                                <Message warning>
                                    <Message.Header>Directory Conflict</Message.Header>
                                    <p>{conflictMessage}</p>
                                </Message>
                            </Grid.Column>
                        </Grid.Row>
                    )}
                </Grid>
            </ModalContent>
            <ModalActions>
                <Button onClick={handleClose}>Cancel</Button>
                <APIButton
                    color='violet'
                    onClick={handleSave}
                    obeyWROLMode={true}
                >{saveButtonText}</APIButton>
            </ModalActions>
        </Modal>
    );
}
