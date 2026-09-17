import React, {useEffect, useRef, useState} from 'react';
import {cancelJob, fetchVideoDownloadDefaults, getJob, transcodeVideo, updateVideo} from '../api';
import {useWROLMode} from '../hooks/customHooks';
import {
    Button, Confirm, Group, Icon, Menu, Modal, Progress, Select, Stack, Status, Text, Textarea, TextInput, Toggle,
    toast,
} from './ui';
import {
    audioContainerForCodec,
    TRANSCODE_COPY,
    TRANSCODE_REMOVE_VIDEO,
    transcodeAudioCodecOptions,
    transcodeAudioContainerOptions,
    transcodeContainerOptions,
    transcodeVideoCodecOptions,
} from './Vars';

const JOB_POLL_MS = 2000;
// Consecutive failed polls before a Job is given up as lost (the API restarted and forgot it).
const JOB_POLL_MAX_FAILURES = 5;
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

/** The container of a video (or audio) file, when it is one ffmpeg can write for us. */
export function currentContainer(video) {
    const suffix = String(video?.video_path || '').split('.').pop().toLowerCase();
    const known = [...transcodeContainerOptions, ...transcodeAudioContainerOptions];
    return known.some(i => i.value === suffix) ? suffix : null;
}

/**
 * The container to offer for the chosen codecs: audio-only output gets the natural container of
 * the audio codec that will be in it (the target, or the source's when copied); output with video
 * keeps the file's own container when possible.
 */
export function containerFor({audioOutput, audioCodec, video}) {
    if (audioOutput) {
        const codec = audioCodec !== TRANSCODE_COPY ? audioCodec : currentCodecs(video).audio[0];
        return audioContainerForCodec(codec);
    }
    const current = currentContainer(video);
    return transcodeContainerOptions.some(i => i.value === current) ? current : 'mp4';
}

const statusKind = (status) => {
    if (status === 'complete') return 'complete';
    if (status === 'running') return 'active';
    if (status === 'failed' || status === 'cancelled') return 'failed';
    return 'pending';
}

/**
 * Poll a Job until it finishes; `onFinished(job)` is called once.  A failed request is retried;
 * a 404 (the API restarted and forgot its Jobs) or `JOB_POLL_MAX_FAILURES` failures in a row stop
 * the polling and call `onLost(error)` instead.
 */
export function useJob(jobId, onFinished, onLost) {
    const [job, setJob] = useState(null);
    const onFinishedRef = useRef(onFinished);
    const onLostRef = useRef(onLost);
    onFinishedRef.current = onFinished;
    onLostRef.current = onLost;

    useEffect(() => {
        setJob(null);
        if (!jobId) {
            return;
        }
        let stopped = false;
        let timer = null;
        let failures = 0;

        const poll = async () => {
            let latest = null;
            try {
                latest = await getJob(jobId);
                failures = 0;
            } catch (e) {
                console.error(e);
                failures += 1;
                if (!stopped && (e?.status === 404 || failures >= JOB_POLL_MAX_FAILURES)) {
                    if (onLostRef.current) onLostRef.current(e);
                    return;
                }
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
 * Choose target codecs for one Video and queue the transcode Job (`onQueued(jobId)`), or show the
 * given `job`.  The selects start at the user's preferred codecs from the Videos settings.
 */
export function TranscodeModal({
                                   open, onClose, fileGroupId, video, audioOnly = false, job, jobId, onQueued,
                                   onCancelJob,
                               }) {
    const wrolModeEnabled = useWROLMode();
    const [videoCodec, setVideoCodec] = useState(TRANSCODE_COPY);
    const [audioCodec, setAudioCodec] = useState(TRANSCODE_COPY);
    const [container, setContainer] = useState('mp4');
    const [fragmented, setFragmented] = useState(false);
    const [defaultsLoaded, setDefaultsLoaded] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    const current = currentCodecs(video);
    const removeVideo = videoCodec === TRANSCODE_REMOVE_VIDEO;
    // An audio file has no video stream to keep or remove; removing the video makes an audio file.
    const audioOutput = audioOnly || removeVideo;

    useEffect(() => {
        if (!open) {
            return;
        }
        setDefaultsLoaded(false);
        setFragmented(false);
        let stale = false;
        const load = async () => {
            let nextVideo = TRANSCODE_COPY;
            let nextAudio = TRANSCODE_COPY;
            try {
                const defaults = await fetchVideoDownloadDefaults();
                if (stale) return;
                nextVideo = audioOnly ? TRANSCODE_COPY
                    : preferredTarget(defaults?.video_codecs, transcodeVideoCodecOptions);
                nextAudio = preferredTarget(defaults?.audio_codecs, transcodeAudioCodecOptions);
            } catch (e) {
                console.error(e);
            } finally {
                if (!stale) {
                    setVideoCodec(nextVideo);
                    setAudioCodec(nextAudio);
                    setContainer(containerFor({audioOutput: audioOnly, audioCodec: nextAudio, video}));
                    setDefaultsLoaded(true);
                }
            }
        };
        load();
        return () => {
            stale = true;
        };
    }, [open]);

    const changeVideoCodec = (value) => {
        const next = value || TRANSCODE_COPY;
        setVideoCodec(next);
        setContainer(containerFor({audioOutput: audioOnly || next === TRANSCODE_REMOVE_VIDEO, audioCodec, video}));
    };
    const changeAudioCodec = (value) => {
        const next = value || TRANSCODE_COPY;
        setAudioCodec(next);
        setContainer(containerFor({audioOutput, audioCodec: next, video}));
    };

    const remuxOnly = !removeVideo && videoCodec === TRANSCODE_COPY && audioCodec === TRANSCODE_COPY;
    const sameContainer = container === currentContainer(video);
    const containerOptions = audioOutput ? transcodeAudioContainerOptions : transcodeContainerOptions;
    // Fragments are an mp4 concept (m4a is an mp4).
    const canFragment = container === 'mp4' || container === 'm4a';

    const handleStart = async () => {
        setSubmitting(true);
        try {
            const id = await transcodeVideo(fileGroupId, {
                video_codec: videoCodec === TRANSCODE_COPY ? null : videoCodec,
                audio_codec: audioCodec === TRANSCODE_COPY ? null : audioCodec,
                container,
                fragmented: canFragment && fragmented,
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
    const showJob = !!jobId;

    let hint = null;
    if (defaultsLoaded && removeVideo) {
        hint = `The video stream is removed; the result is an audio file (.${container}).  `
            + (audioCodec === TRANSCODE_COPY ? 'The audio is copied without re-encoding.' : `The audio is converted to ${audioCodec}.`);
    } else if (defaultsLoaded && remuxOnly) {
        const kept = audioOnly ? 'The audio is kept' : 'Both streams are kept';
        if (sameContainer && canFragment && fragmented) {
            hint = `${kept}: the file is rewritten as-is in fragments (a quick remux, no quality loss).`;
        } else if (sameContainer) {
            hint = `${kept}: the file is rewritten as-is` + (canFragment
                ? ' with fast start (moves the index to the front for quicker playback start).' : '.');
        } else {
            hint = `${kept}: only the container changes to ${container} (a quick remux, no quality loss).`;
        }
    }
    const buttonLabel = removeVideo ? 'Extract Audio' : remuxOnly ? 'Remux' : 'Transcode';

    return <Modal open={open} onClose={onClose} size='small'>
        <Modal.Header>{audioOnly ? 'Transcode Audio' : 'Transcode Video'}</Modal.Header>
        <Modal.Content>
            <Stack gap='md'>
                <Text size='sm' c='var(--muted)'>
                    {audioOnly
                        ? `Current codec: audio ${describe(current.audio)}.  `
                        : `Current codecs: video ${describe(current.video)}, audio ${describe(current.audio)}.  `}
                    Streams set to Keep are copied without re-encoding.  Transcoding is slow and slightly
                    reduces quality; the original file is replaced when it finishes.
                </Text>
                {!showJob && <>
                    {!audioOnly && <Select
                        label='Video codec'
                        data={transcodeVideoCodecOptions}
                        value={videoCodec}
                        onChange={changeVideoCodec}
                        disabled={!defaultsLoaded}
                        allowDeselect={false}
                    />}
                    <Select
                        label='Audio codec'
                        data={transcodeAudioCodecOptions}
                        value={audioCodec}
                        onChange={changeAudioCodec}
                        disabled={!defaultsLoaded}
                        allowDeselect={false}
                    />
                    <Select
                        label='Container'
                        data={containerOptions}
                        value={container}
                        onChange={value => setContainer(value || containerOptions[0].value)}
                        disabled={!defaultsLoaded}
                        allowDeselect={false}
                    />
                    {canFragment && <Toggle
                        label='Fragmented (for very long videos)'
                        checked={fragmented}
                        onChange={e => setFragmented(e.currentTarget.checked)}
                        disabled={!defaultsLoaded}
                        info='Splits the index into fragments instead of one block at the front.  A video many
                         hours long then starts and seeks quickly on phones, which otherwise must download the
                         whole index first.'
                    />}
                    {hint && <Text size='sm' c='var(--muted)'>{hint}</Text>}
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
                {buttonLabel}
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
 * The "Edit" dropdown on the Video page: Edit, Refresh, Transcode, Delete.  Holds this video's
 * active transcode Job; `onTranscodeComplete` fires whether or not the modal is open.
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
        } else if (finished.status === 'failed') {
            toast({
                type: 'error', title: 'Transcode failed', time: 10000,
                description: `${finished.description}: ${finished.error || 'unknown error'}.  The original file was kept.`,
            });
        } else if (finished.status === 'cancelled') {
            toast({type: 'info', title: 'Transcode cancelled', description: finished.description, time: 5000});
        }
        if (!transcodeOpen) {
            // Nobody is looking at the result; make room for the next transcode.
            setJobId(null);
        }
    };
    const handleJobLost = (error) => {
        toast({
            type: 'warning', title: 'Lost track of the transcode', time: 10000,
            description: 'The job is no longer known (the API may have restarted).  Check the file before trying again.',
        });
        setJobId(null);
        setTranscodeOpen(false);
    };
    const {job, cancel} = useJob(jobId, handleJobFinished, handleJobLost);

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
    const isAudio = !!videoFile?.mimetype?.startsWith('audio/');
    const transcoding = !!jobId && !isJobFinished(job);

    return <>
        <Menu position='bottom-start' withinPortal>
            <Menu.Target>
                <Button color='yellow' icon='edit' iconAfter='dropdown' loading={refreshing}>Edit</Button>
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
                    disabled={!(isVideo || isAudio) || (!!wrolModeEnabled && !transcoding)}
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
            audioOnly={isAudio}
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
