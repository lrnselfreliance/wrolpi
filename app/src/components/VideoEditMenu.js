import React, {useEffect, useRef, useState} from 'react';
import {cancelJob, fetchVideoDownloadDefaults, getJob, transcodeVideo, updateVideo} from '../api';
import {useWROLMode} from '../hooks/customHooks';
import {
    Button, Confirm, Group, Icon, Menu, Modal, Progress, Select, Stack, Status, Text, Textarea, TextInput, toast,
} from './ui';
import {
    TRANSCODE_COPY,
    transcodeAudioCodecOptions,
    transcodeContainerOptions,
    transcodeVideoCodecOptions,
} from './Vars';

const JOB_POLL_MS = 2000;
export const FINISHED_STATUSES = ['complete', 'failed', 'cancelled'];
// ffprobe calls an embedded thumbnail a video stream.
const THUMBNAIL_CODECS = ['mjpeg', 'png', 'bmp', 'gif'];

export const isJobFinished = (job) => !!job && FINISHED_STATUSES.includes(job.status);

/** The codec names of a Video's real streams, from the `codec_names`/`codec_types` the API sends. */
export function currentCodecs(video) {
    const names = video?.codec_names || [];
    const types = video?.codec_types || [];
    const video_ = names.filter((name, i) => types[i] === 'video' && !THUMBNAIL_CODECS.includes(name));
    const audio = names.filter((name, i) => types[i] === 'audio');
    return {video: video_, audio};
}

/**
 * The transcode target implied by the user's ordered codec preferences: the first preferred codec
 * that ffmpeg can produce (the same rule the downloader uses).  `copy` when none can be.
 */
export function preferredTarget(preferences, options) {
    const producible = options.map(i => i.value).filter(i => i !== TRANSCODE_COPY);
    for (const codec of preferences || []) {
        if (producible.includes(codec)) {
            return codec;
        }
    }
    return TRANSCODE_COPY;
}

/** The container of a video file, when it is one ffmpeg can write for us. */
export function currentContainer(video) {
    const suffix = String(video?.video_path || '').split('.').pop().toLowerCase();
    return transcodeContainerOptions.some(i => i.value === suffix) ? suffix : null;
}

const statusKind = (status) => {
    if (status === 'complete') return 'complete';
    if (status === 'running') return 'active';
    if (status === 'failed' || status === 'cancelled') return 'failed';
    return 'pending';
}

/**
 * Poll a Job until it finishes.  Lives in whichever component must outlive the UI showing the Job:
 * the page must learn the Job finished even when the user closed the modal that started it.
 *
 * A failed request is retried on the next tick; only unmount, a new `jobId`, or a finished status
 * stops the polling.  `onFinished` is called once per Job.
 */
export function useJob(jobId, onFinished) {
    const [job, setJob] = useState(null);
    const onFinishedRef = useRef(onFinished);
    onFinishedRef.current = onFinished;

    useEffect(() => {
        setJob(null);
        if (!jobId) {
            return;
        }
        let stopped = false;
        let timer = null;

        const poll = async () => {
            let latest = null;
            try {
                latest = await getJob(jobId);
            } catch (e) {
                console.error(e);
            }
            if (stopped) return;
            if (latest) {
                setJob(latest);
                if (isJobFinished(latest)) {
                    if (onFinishedRef.current) onFinishedRef.current(latest);
                    return;
                }
            }
            timer = window.setTimeout(poll, JOB_POLL_MS);
        };

        poll();
        return () => {
            stopped = true;
            clearTimeout(timer);
        };
    }, [jobId]);

    const cancel = async () => {
        const latest = await cancelJob(jobId);
        setJob(latest);
        return latest;
    };

    return {job, cancel};
}

/** Progress, status and log tail of one Job. */
export function JobProgress({job, onCancel}) {
    const [cancelling, setCancelling] = useState(false);

    const handleCancel = async () => {
        setCancelling(true);
        try {
            await onCancel();
        } catch (e) {
            console.error(e);
        } finally {
            setCancelling(false);
        }
    };

    if (!job) {
        return <Progress indeterminate showPercent={false} label='Starting...'/>;
    }

    const finished = isJobFinished(job);
    const percent = job.progress ?? 0;
    const logTail = (job.log || []).slice(-8);

    return <Stack gap='sm'>
        <Group justify='space-between' wrap='wrap'>
            <Status kind={statusKind(job.status)}>{job.status}</Status>
            {!finished && onCancel && <Button
                role='danger'
                size='small'
                icon='stop'
                onClick={handleCancel}
                loading={cancelling}
                disabled={cancelling || job.cancel_requested}
            >
                {job.cancel_requested ? 'Cancelling...' : 'Cancel'}
            </Button>}
        </Group>
        <Progress
            percent={percent}
            indeterminate={!finished && job.progress === null}
            color={job.status === 'failed' ? 'red' : job.status === 'complete' ? 'green' : 'blue'}
        />
        {job.error && <Text c='var(--danger)' size='sm'>{job.error}</Text>}
        {logTail.length > 0 && <pre
            data-testid='job-log'
            style={{
                margin: 0,
                maxHeight: '10em',
                overflow: 'auto',
                fontSize: '0.75em',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                background: 'var(--surface-2, var(--surface))',
                padding: '0.5em',
                borderRadius: 'var(--radius, 4px)',
            }}
        >{logTail.join('\n')}</pre>}
    </Stack>
}

/**
 * Choose target codecs for one Video and queue the transcode Job, or show the Job already
 * queued for it.  The Job itself is owned by the parent (`useJob`), so closing this modal does not
 * stop the page from learning when it finishes.
 *
 * The selects start at the user's preferred codecs from the Videos settings.
 */
export function TranscodeModal({open, onClose, fileGroupId, video, job, jobId, onQueued, onCancelJob}) {
    const wrolModeEnabled = useWROLMode();
    const [videoCodec, setVideoCodec] = useState(TRANSCODE_COPY);
    const [audioCodec, setAudioCodec] = useState(TRANSCODE_COPY);
    const [container, setContainer] = useState('mp4');
    const [defaultsLoaded, setDefaultsLoaded] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    const current = currentCodecs(video);

    useEffect(() => {
        if (!open) {
            return;
        }
        setDefaultsLoaded(false);
        setContainer(currentContainer(video) || 'mp4');
        let stale = false;
        const load = async () => {
            try {
                const defaults = await fetchVideoDownloadDefaults();
                if (stale) return;
                setVideoCodec(preferredTarget(defaults?.video_codecs, transcodeVideoCodecOptions));
                setAudioCodec(preferredTarget(defaults?.audio_codecs, transcodeAudioCodecOptions));
            } catch (e) {
                console.error(e);
            } finally {
                if (!stale) setDefaultsLoaded(true);
            }
        };
        load();
        return () => {
            stale = true;
        };
    }, [open]);

    const remuxOnly = videoCodec === TRANSCODE_COPY && audioCodec === TRANSCODE_COPY;
    const sameContainer = container === currentContainer(video);

    const handleStart = async () => {
        setSubmitting(true);
        try {
            const id = await transcodeVideo(fileGroupId, {
                video_codec: videoCodec === TRANSCODE_COPY ? null : videoCodec,
                audio_codec: audioCodec === TRANSCODE_COPY ? null : audioCodec,
                container,
            });
            onQueued(id);
        } catch (e) {
            // transcodeVideo already toasted.
            console.error(e);
        } finally {
            setSubmitting(false);
        }
    };

    const describe = (codecs) => codecs.length ? codecs.join(', ') : 'unknown';
    // A queued or finished Job replaces the form until the parent forgets it.
    const showJob = !!jobId;

    return <Modal open={open} onClose={onClose} size='small'>
        <Modal.Header>Transcode Video</Modal.Header>
        <Modal.Content>
            <Stack gap='md'>
                <Text size='sm' c='var(--muted)'>
                    Current codecs: video {describe(current.video)}, audio {describe(current.audio)}.
                    Streams set to Keep are copied without re-encoding.  Transcoding is slow and slightly
                    reduces quality; the original file is replaced when it finishes.
                </Text>
                {!showJob && <>
                    <Select
                        label='Video codec'
                        data={transcodeVideoCodecOptions}
                        value={videoCodec}
                        onChange={value => setVideoCodec(value || TRANSCODE_COPY)}
                        disabled={!defaultsLoaded}
                        allowDeselect={false}
                    />
                    <Select
                        label='Audio codec'
                        data={transcodeAudioCodecOptions}
                        value={audioCodec}
                        onChange={value => setAudioCodec(value || TRANSCODE_COPY)}
                        disabled={!defaultsLoaded}
                        allowDeselect={false}
                    />
                    <Select
                        label='Container'
                        data={transcodeContainerOptions}
                        value={container}
                        onChange={value => setContainer(value || 'mp4')}
                        allowDeselect={false}
                    />
                    {remuxOnly && defaultsLoaded && <Text size='sm' c='var(--muted)'>
                        {sameContainer
                            ? 'Both streams are kept: the file is rewritten as-is with fast start (moves the index to the front for quicker playback start).'
                            : `Both streams are kept: only the container changes to ${container} (a quick remux, no quality loss).`}
                    </Text>}
                </>}
                {showJob && <JobProgress job={job} onCancel={onCancelJob}/>}
            </Stack>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>{showJob ? 'Close' : 'Cancel'}</Button>
            {!showJob && <Button
                role='primary'
                icon='film'
                onClick={handleStart}
                loading={submitting}
                disabled={submitting || !defaultsLoaded || !!wrolModeEnabled}
            >
                {remuxOnly ? 'Remux' : 'Transcode'}
            </Button>}
        </Modal.Actions>
    </Modal>
}

/**
 * Edit a Video's details.  The change is written to the Video's info json, so it survives a
 * refresh; a re-download of the Video's metadata will overwrite it.
 */
export function EditVideoModal({open, onClose, fileGroupId, videoFile, description: currentDescription, onSaved}) {
    const wrolModeEnabled = useWROLMode();
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (open) {
            // Start from the current details on every open, discarding an abandoned edit.
            setTitle(videoFile?.title || '');
            setDescription(currentDescription || '');
        }
    }, [open, videoFile?.title, currentDescription]);

    const trimmed = title.trim();
    const titleChanged = trimmed !== (videoFile?.title || '');
    const descriptionChanged = description !== (currentDescription || '');
    const unchanged = !titleChanged && !descriptionChanged;

    const handleSave = async () => {
        setSaving(true);
        try {
            // Send only what changed, so an untouched field is never rewritten.
            const changes = {};
            if (titleChanged) changes.title = trimmed;
            if (descriptionChanged) changes.description = description;
            const updated = await updateVideo(fileGroupId, changes);
            toast({type: 'success', title: 'Saved', description: 'The video was updated.', time: 3000});
            if (onSaved) await onSaved(updated);
            onClose();
        } catch (e) {
            // updateVideo already toasted.
            console.error(e);
        } finally {
            setSaving(false);
        }
    };

    return <Modal open={open} onClose={onClose} size='small'>
        <Modal.Header>Edit Video</Modal.Header>
        <Modal.Content>
            {/* No submit-on-Enter: Enter belongs to the description's new lines. */}
            <form onSubmit={e => e.preventDefault()}>
                <TextInput
                    label='Title'
                    value={title}
                    onChange={e => setTitle(e.currentTarget.value)}
                    error={!trimmed ? 'A title is required' : null}
                    data-autofocus
                />
                <Textarea
                    label='Description'
                    value={description}
                    onChange={e => setDescription(e.currentTarget.value)}
                    autosize
                    minRows={4}
                    maxRows={14}
                    mt='sm'
                />
                <Text size='sm' c='var(--muted)' mt='sm'>
                    Saved to the video's info json.  Refreshing the video from its source will replace it.
                </Text>
                {wrolModeEnabled && <Text size='sm' c='var(--danger)' mt='sm'>
                    Videos cannot be edited while WROL Mode is enabled.
                </Text>}
            </form>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>Cancel</Button>
            <Button
                role='save'
                icon='save'
                onClick={handleSave}
                loading={saving}
                disabled={saving || !trimmed || unchanged || !!wrolModeEnabled}
            >
                Save
            </Button>
        </Modal.Actions>
    </Modal>
}

/**
 * The "Edit" dropdown on the Video page: Edit, Refresh, Transcode, Delete.
 *
 * Owns the active transcode Job for this video, so the page hears about its completion whether or
 * not the modal is open, and a second transcode cannot be queued while one is running.
 */
export function VideoEditMenu({
                                  videoFile, video, description, onRefresh, onTranscodeComplete, onDelete, onSaved,
                                  initialJobId = null,
                              }) {
    const wrolModeEnabled = useWROLMode();
    const [editOpen, setEditOpen] = useState(false);
    const [transcodeOpen, setTranscodeOpen] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [deleting, setDeleting] = useState(false);
    // `initialJobId`: resume watching a Job already queued for this video (tests use it too).
    const [jobId, setJobId] = useState(initialJobId);

    const handleJobFinished = (finished) => {
        if (finished.status === 'complete') {
            toast({type: 'success', title: 'Transcode complete', description: finished.description, time: 5000});
            if (onTranscodeComplete) onTranscodeComplete(finished);
        }
        if (!transcodeOpen) {
            // Nobody is looking at the result; make room for the next transcode.
            setJobId(null);
        }
    };
    const {job, cancel} = useJob(jobId, handleJobFinished);

    // Another video: its transcodes are its own.
    const firstVideoId = useRef(videoFile?.id);
    useEffect(() => {
        if (videoFile?.id !== firstVideoId.current) {
            firstVideoId.current = videoFile?.id;
            setJobId(null);
        }
    }, [videoFile?.id]);

    const handleTranscodeClose = () => {
        setTranscodeOpen(false);
        if (isJobFinished(job)) {
            setJobId(null);
        }
    };

    const handleDelete = async () => {
        setDeleting(true);
        try {
            await onDelete();
            setDeleteOpen(false);
        } finally {
            setDeleting(false);
        }
    };

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            await onRefresh();
        } finally {
            setRefreshing(false);
        }
    };

    const isVideo = !!videoFile?.mimetype?.startsWith('video/');
    const transcoding = !!jobId && !isJobFinished(job);

    return <>
        <Menu position='bottom-start' withinPortal>
            <Menu.Target>
                <Button role='primary' icon='edit' iconAfter='dropdown' loading={refreshing}>Edit</Button>
            </Menu.Target>
            <Menu.Dropdown>
                <Menu.Item
                    leftSection={<Icon name='edit'/>}
                    onClick={() => setEditOpen(true)}
                    disabled={!!wrolModeEnabled}
                >
                    Edit...
                </Menu.Item>
                <Menu.Item
                    leftSection={<Icon name='refresh'/>}
                    onClick={handleRefresh}
                    disabled={!videoFile?.url || !!wrolModeEnabled || refreshing}
                >
                    Refresh
                </Menu.Item>
                <Menu.Item
                    leftSection={<Icon name='film'/>}
                    onClick={() => setTranscodeOpen(true)}
                    disabled={!isVideo || (!!wrolModeEnabled && !transcoding)}
                >
                    {transcoding ? 'Transcoding...' : 'Transcode...'}
                </Menu.Item>
                <Menu.Divider/>
                <Menu.Item
                    color='var(--danger)'
                    leftSection={<Icon name='trash'/>}
                    onClick={() => setDeleteOpen(true)}
                    disabled={!onDelete || !!wrolModeEnabled || transcoding}
                >
                    Delete...
                </Menu.Item>
            </Menu.Dropdown>
        </Menu>
        <TranscodeModal
            open={transcodeOpen}
            onClose={handleTranscodeClose}
            fileGroupId={videoFile?.id}
            video={video}
            job={job}
            jobId={jobId}
            onQueued={setJobId}
            onCancelJob={cancel}
        />
        <EditVideoModal
            open={editOpen}
            onClose={() => setEditOpen(false)}
            fileGroupId={videoFile?.id}
            videoFile={videoFile}
            description={description}
            onSaved={onSaved}
        />
        <Confirm
            open={deleteOpen}
            title='Delete video?'
            confirmLabel='Delete'
            destructive
            loading={deleting}
            onConfirm={handleDelete}
            onCancel={() => setDeleteOpen(false)}
        >
            Are you sure you want to delete this video?  All files related to this video will be deleted.
            It will not be downloaded again!
        </Confirm>
    </>
}
