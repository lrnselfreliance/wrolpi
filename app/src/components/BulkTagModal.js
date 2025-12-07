import React from 'react';
import {Button, Divider, Header, Loader, Modal, Progress} from "./Theme";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {applyBulkTags, getBulkTagPreview, getBulkTagProgress} from "../api";
import {TagsContext} from "../Tags";
import {ThemeContext} from "../contexts/contexts";

const BULK_TAG_WARNING_THRESHOLD = 50;
const POLL_INTERVAL = 500; // Poll progress every 500ms

export function BulkTagModal({open, onClose, paths, onComplete}) {
    // State machine: 'loading' -> 'preview' -> 'applying' -> 'complete'
    const [state, setState] = React.useState('loading');
    const [fileCount, setFileCount] = React.useState(0);
    const [sharedTagNames, setSharedTagNames] = React.useState([]);
    const [localTags, setLocalTags] = React.useState([]);
    const [progress, setProgress] = React.useState({total: 0, completed: 0, queued_jobs: 0});
    const [error, setError] = React.useState(null);

    const {tagNames, TagsGroup} = React.useContext(TagsContext);
    const {t} = React.useContext(ThemeContext);

    // Fetch preview when modal opens
    React.useEffect(() => {
        if (open && paths && paths.length > 0) {
            setState('loading');
            setLocalTags([]);
            setError(null);

            getBulkTagPreview(paths).then(preview => {
                if (preview) {
                    setFileCount(preview.file_count);
                    setSharedTagNames(preview.shared_tag_names || []);
                    setLocalTags(preview.shared_tag_names || []);
                    setState('preview');
                } else {
                    setError('Failed to get preview');
                    setState('preview');
                }
            }).catch(err => {
                console.error('Failed to get bulk tag preview', err);
                setError(err.message || 'Failed to get preview');
                setState('preview');
            });
        }
    }, [open, paths]);

    // Poll progress while applying
    React.useEffect(() => {
        if (state !== 'applying') {
            return;
        }

        const pollProgress = async () => {
            const progressData = await getBulkTagProgress();
            if (progressData) {
                setProgress(progressData);
                if (progressData.status === 'idle' && progressData.queued_jobs === 0) {
                    // Done applying
                    setState('complete');
                }
                if (progressData.error) {
                    setError(progressData.error);
                }
            }
        };

        const interval = setInterval(pollProgress, POLL_INTERVAL);
        pollProgress(); // Initial poll

        return () => clearInterval(interval);
    }, [state]);

    const addTag = (name) => {
        if (!localTags.includes(name)) {
            setLocalTags([...localTags, name]);
        }
    };

    const removeTag = (name) => {
        setLocalTags(localTags.filter(t => t !== name));
    };

    const handleApply = async () => {
        // Compute what changed
        const tagsToAdd = localTags.filter(t => !sharedTagNames.includes(t));
        const tagsToRemove = sharedTagNames.filter(t => !localTags.includes(t));

        if (tagsToAdd.length === 0 && tagsToRemove.length === 0) {
            return;
        }

        setState('applying');
        setProgress({total: 0, completed: 0, queued_jobs: 1});

        try {
            await applyBulkTags(paths, tagsToAdd, tagsToRemove);
        } catch (err) {
            console.error('Failed to apply bulk tags', err);
            setError(err.message || 'Failed to apply tags');
        }
    };

    const handleClose = () => {
        if (state === 'complete' && onComplete) {
            onComplete();
        }
        setState('loading');
        setFileCount(0);
        setSharedTagNames([]);
        setLocalTags([]);
        setProgress({total: 0, completed: 0, queued_jobs: 0});
        setError(null);
        onClose();
    };

    // Tags not currently applied (available to add)
    const unusedTags = tagNames ? tagNames.filter(name => !localTags.includes(name)) : [];

    // Check if there are any changes from original
    const hasChanges =
        localTags.some(t => !sharedTagNames.includes(t)) ||  // Added tags
        sharedTagNames.some(t => !localTags.includes(t));    // Removed tags
    const showWarning = fileCount >= BULK_TAG_WARNING_THRESHOLD;

    const progressPercent = progress.total > 0
        ? Math.round((progress.completed / progress.total) * 100)
        : 0;

    return (
        <Modal closeIcon open={open} onClose={handleClose} size="small">
            <Modal.Header>Bulk Tag Files</Modal.Header>
            <Modal.Content>
                {state === 'loading' && (
                    <div style={{textAlign: 'center', padding: '2em'}}>
                        <Loader active inline="centered">Loading preview...</Loader>
                    </div>
                )}

                {state === 'preview' && (
                    <>
                        {error && (
                            <Message negative>
                                <Message.Header>Error</Message.Header>
                                <p>{error}</p>
                            </Message>
                        )}

                        <Header as="h4">
                            {fileCount} file{fileCount !== 1 ? 's' : ''} will be affected
                        </Header>

                        {showWarning && (
                            <Message warning>
                                <Message.Header>Warning</Message.Header>
                                <p>Tagging over {BULK_TAG_WARNING_THRESHOLD} files may make it difficult to find what you are looking for. Are you sure?</p>
                            </Message>
                        )}

                        <Divider/>

                        <Header as="h4">Applied Tags</Header>
                        {localTags.length > 0 ? (
                            <TagsGroup tagNames={localTags} onClick={removeTag}/>
                        ) : (
                            <p {...t}>Add one or more tags below</p>
                        )}

                        <Divider/>

                        {unusedTags.length > 0 ? (
                            <TagsGroup tagNames={unusedTags} onClick={addTag}/>
                        ) : (
                            <p {...t}>You have no tags</p>
                        )}
                    </>
                )}

                {state === 'applying' && (
                    <div style={{padding: '1em'}}>
                        <Header as="h4">Applying tags...</Header>
                        <Progress
                            percent={progressPercent}
                            progress
                            indicating
                            color="blue"
                        >
                            <span {...t}>{progress.completed} / {progress.total} files</span>
                        </Progress>
                        {progress.queued_jobs > 0 && (
                            <p {...t}>{progress.queued_jobs} job{progress.queued_jobs !== 1 ? 's' : ''} queued</p>
                        )}
                        {error && (
                            <Message negative>
                                <Message.Header>Error</Message.Header>
                                <p>{error}</p>
                            </Message>
                        )}
                    </div>
                )}

                {state === 'complete' && (
                    <div style={{padding: '1em'}}>
                        <Message positive>
                            <Message.Header>Complete</Message.Header>
                            <p>Successfully tagged {progress.total} file{progress.total !== 1 ? 's' : ''}.</p>
                        </Message>
                        {error && (
                            <Message warning>
                                <Message.Header>Warning</Message.Header>
                                <p>Some errors occurred: {error}</p>
                            </Message>
                        )}
                    </div>
                )}
            </Modal.Content>
            <Modal.Actions>
                {state === 'preview' && (
                    <>
                        <Button onClick={handleClose}>Cancel</Button>
                        <Button
                            color="violet"
                            onClick={handleApply}
                            disabled={!hasChanges || fileCount === 0}
                        >
                            Apply Tags
                        </Button>
                    </>
                )}
                {state === 'applying' && (
                    <Button onClick={handleClose} disabled>
                        Please wait...
                    </Button>
                )}
                {state === 'complete' && (
                    <Button color="green" onClick={handleClose}>
                        Done
                    </Button>
                )}
            </Modal.Actions>
        </Modal>
    );
}

export default BulkTagModal;
