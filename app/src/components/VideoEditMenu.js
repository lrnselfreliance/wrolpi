import React, {useEffect, useRef, useState} from 'react';
import {cancelJob, fetchVideoDownloadDefaults, getJob, transcodeVideo} from '../api';
import {useWROLMode} from '../hooks/customHooks';
import {Button, Group, Icon, Menu, Modal, Progress, Select, Stack, Status, Text, toast} from './ui';
import {
    TRANSCODE_COPY,
    transcodeAudioCodecOptions,
    transcodeContainerOptions,
    transcodeVideoCodecOptions,
} from './Vars';

// How often the modal asks the API about the running Job.
const JOB_POLL_MS = 2000;
const FINISHED_STATUSES = ['complete', 'failed', 'cancelled'];
// Embedded thumbnails are "video" streams to ffprobe, but not codecs a user chooses.
const THUMBNAIL_CODECS = ['mjpeg', 'png', 'bmp', 'gif'];

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

const statusKind = (status) => {
    if (status === 'complete') return 'complete';
    if (status === 'running') return 'active';
    if (status === 'failed' || status === 'cancelled') return 'failed';
    return 'pending';
}

/** Progress, status and log tail of one Job, polled until it finishes. */
export function JobProgress({jobId, onFinished}) {
    const [job, setJob] = useState(null);
    const [cancelling, setCancelling] = useState(false);
    const timer = useRef(null);
    const finishedRef = useRef(false);

    useEffect(() => {
        finishedRef.current = false;
        let cancelled = false;

        const poll = async () => {
            let latest;
            try {
                latest = await getJob(jobId);
            } catch (e) {
                console.error(e);
                return;
            }
            if (cancelled) return;
            setJob(latest);
            if (FINISHED_STATUSES.includes(latest.status)) {
                if (!finishedRef.current) {
                    finishedRef.current = true;
                    if (onFinished) onFinished(latest);
                }
                return;
            }
            timer.current = window.setTimeout(poll, JOB_POLL_MS);
        };

        poll();
        return () => {
            cancelled = true;
            clearTimeout(timer.current);
        };
        // Only a new Job restarts polling; `onFinished` may be a fresh closure on every render.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [jobId]);

    const handleCancel = async () => {
        setCancelling(true);
        try {
            const latest = await cancelJob(jobId);
            setJob(latest);
        } catch (e) {
            console.error(e);
        } finally {
            setCancelling(false);
        }
    };

    if (!job) {
        return <Progress indeterminate showPercent={false} label='Starting...'/>;
    }

    const finished = FINISHED_STATUSES.includes(job.status);
    const percent = job.progress ?? 0;
    const logTail = (job.log || []).slice(-8);

    return <Stack gap='sm'>
        <Group justify='space-between' wrap='wrap'>
            <Status kind={statusKind(job.status)}>{job.status}</Status>
            {!finished && <Button
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
 * Choose target codecs for one Video, queue the transcode Job, then watch it.
 *
 * The selects start at the user's preferred codecs from the Videos settings (the same preference
 * lists the downloader honors), so the common case is a glance and a click.
 */
export function TranscodeModal({open, onClose, fileGroupId, video, onComplete}) {
    const wrolModeEnabled = useWROLMode();
    const [videoCodec, setVideoCodec] = useState(TRANSCODE_COPY);
    const [audioCodec, setAudioCodec] = useState(TRANSCODE_COPY);
    const [container, setContainer] = useState('mp4');
    const [defaultsLoaded, setDefaultsLoaded] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [jobId, setJobId] = useState(null);

    const current = currentCodecs(video);

    useEffect(() => {
        if (!open) {
            return;
        }
        // Each opening starts over: a finished Job's progress must not linger on the next open.
        setJobId(null);
        setDefaultsLoaded(false);
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

    const nothingToDo = videoCodec === TRANSCODE_COPY && audioCodec === TRANSCODE_COPY;

    const handleStart = async () => {
        setSubmitting(true);
        try {
            const id = await transcodeVideo(fileGroupId, {
                video_codec: videoCodec === TRANSCODE_COPY ? null : videoCodec,
                audio_codec: audioCodec === TRANSCODE_COPY ? null : audioCodec,
                container,
            });
            setJobId(id);
        } catch (e) {
            // transcodeVideo already toasted.
            console.error(e);
        } finally {
            setSubmitting(false);
        }
    };

    const handleFinished = (job) => {
        if (job.status === 'complete') {
            toast({type: 'success', title: 'Transcode complete', description: job.description, time: 5000});
            if (onComplete) onComplete(job);
        }
    };

    const describe = (codecs) => codecs.length ? codecs.join(', ') : 'unknown';

    return <Modal open={open} onClose={onClose} size='small'>
        <Modal.Header>Transcode Video</Modal.Header>
        <Modal.Content>
            <Stack gap='md'>
                <Text size='sm' c='var(--muted)'>
                    Current codecs: video {describe(current.video)}, audio {describe(current.audio)}.
                    Streams set to Keep are copied without re-encoding.  Transcoding is slow and slightly
                    reduces quality; the original file is replaced when it finishes.
                </Text>
                {!jobId && <>
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
                    {nothingToDo && defaultsLoaded && <Text size='sm' c='var(--muted)'>
                        Choose at least one codec to convert.
                    </Text>}
                </>}
                {jobId && <JobProgress jobId={jobId} onFinished={handleFinished}/>}
            </Stack>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>{jobId ? 'Close' : 'Cancel'}</Button>
            {!jobId && <Button
                role='primary'
                icon='film'
                onClick={handleStart}
                loading={submitting}
                disabled={submitting || nothingToDo || !defaultsLoaded || !!wrolModeEnabled}
            >
                Transcode
            </Button>}
        </Modal.Actions>
    </Modal>
}

/**
 * The "Edit" dropdown on the Video page: Refresh (re-download metadata) and Transcode.
 *
 * `onRefresh` is awaited; `onTranscodeComplete` is called after the file was replaced so the
 * page can fetch the Video again (its path and codecs changed).
 */
export function VideoEditMenu({videoFile, video, onRefresh, onTranscodeComplete}) {
    const wrolModeEnabled = useWROLMode();
    const [transcodeOpen, setTranscodeOpen] = useState(false);
    const [refreshing, setRefreshing] = useState(false);

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            await onRefresh();
        } finally {
            setRefreshing(false);
        }
    };

    const isVideo = !!videoFile?.mimetype?.startsWith('video/');

    return <>
        <Menu position='bottom-start' withinPortal>
            <Menu.Target>
                <Button role='primary' icon='edit' iconAfter='dropdown' loading={refreshing}>Edit</Button>
            </Menu.Target>
            <Menu.Dropdown>
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
                    disabled={!isVideo || !!wrolModeEnabled}
                >
                    Transcode...
                </Menu.Item>
            </Menu.Dropdown>
        </Menu>
        <TranscodeModal
            open={transcodeOpen}
            onClose={() => setTranscodeOpen(false)}
            fileGroupId={videoFile?.id}
            video={video}
            onComplete={onTranscodeComplete}
        />
    </>
}
