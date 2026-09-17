import React from 'react';
import {act, fireEvent, screen, waitFor} from '@testing-library/react';
import {renderWithProviders} from '../test-utils';
import {
    containerFor, currentCodecs, currentContainer, EditVideoModal, JobProgress, preferredTarget, TranscodeModal,
    useJob, VideoEditMenu,
} from './VideoEditMenu';
import {
    audioContainerForCodec, TRANSCODE_COPY, TRANSCODE_REMOVE_VIDEO, transcodeAudioCodecOptions,
    transcodeVideoCodecOptions,
} from './Vars';

jest.mock('../api', () => ({
    cancelJob: jest.fn(),
    fetchVideoDownloadDefaults: jest.fn(),
    getJob: jest.fn(),
    transcodeVideo: jest.fn(),
    updateVideo: jest.fn(),
}));

import {cancelJob, fetchVideoDownloadDefaults, getJob, transcodeVideo, updateVideo} from '../api';

// The ui index re-exports `toast` from here; a spy lets tests see what the page tells the user.
jest.mock('./ui/toast', () => ({...jest.requireActual('./ui/toast'), toast: jest.fn()}));
import {toast} from './ui/toast';

const video = {
    codec_names: ['vp9', 'mjpeg', 'opus'],
    codec_types: ['video', 'video', 'audio'],
    video_path: 'videos/movie.webm',
};
const videoFile = {id: 7, url: 'https://example.com/watch?v=1', mimetype: 'video/webm', title: 'Old Title', video};
const audio = {codec_names: ['aac'], codec_types: ['audio'], video_path: 'videos/song.m4a'};
const audioFile = {id: 8, url: null, mimetype: 'audio/mp4', title: 'Song', video: audio};

// Mantine's Select renders a hidden input next to the visible one, both tied to the label.
const selectInput = (label) => screen.getAllByLabelText(label).find(i => i.type !== 'hidden');

// `renderWithProviders`' `settings` option replaces the SettingsContext value; the WROL flag lives
// one level down in its `settings`.
const wrolMode = {settings: {settings: {wrol_mode: true}}};

const pendingJob = {
    id: 'transcode_video-abc', status: 'pending', progress: null, log: [], error: null, cancel_requested: false,
    description: 'Transcode movie.webm',
};
const runningJob = {...pendingJob, status: 'running', progress: 40, log: ['out_time_us=1']};
const completeJob = {...pendingJob, status: 'complete', progress: 100, log: ['done']};
const failedJob = {...pendingJob, status: 'failed', progress: 12, error: 'ffmpeg exited with 1', log: ['boom']};
const notFound = Object.assign(new Error('Job does not exist'), {status: 404});

describe('helpers', () => {
    test('currentCodecs ignores embedded thumbnail streams', () => {
        expect(currentCodecs(video)).toEqual({video: ['vp9'], audio: ['opus']});
        expect(currentCodecs(null)).toEqual({video: [], audio: []});
    });

    test('currentContainer reads the file suffix, only for containers we can write', () => {
        expect(currentContainer({video_path: 'videos/a/movie.MP4'})).toBe('mp4');
        expect(currentContainer({video_path: 'videos/a/movie.mkv'})).toBe('mkv');
        expect(currentContainer({video_path: 'videos/a/song.m4a'})).toBe('m4a');
        expect(currentContainer({video_path: 'videos/a/movie.webm'})).toBeNull();
        expect(currentContainer(null)).toBeNull();
    });

    test('audioContainerForCodec mirrors the backend default', () => {
        expect(audioContainerForCodec('aac')).toBe('m4a');
        expect(audioContainerForCodec('mp3')).toBe('mp3');
        expect(audioContainerForCodec('opus')).toBe('ogg');
        expect(audioContainerForCodec('vorbis')).toBe('ogg');
        expect(audioContainerForCodec(undefined)).toBe('m4a');
    });

    test('containerFor follows the audio codec for audio output, the file for video output', () => {
        // Removing the video from a vp9/opus webm, copying the audio: opus lives in ogg.
        expect(containerFor({audioOutput: true, audioCodec: TRANSCODE_COPY, video})).toBe('ogg');
        expect(containerFor({audioOutput: true, audioCodec: 'aac', video})).toBe('m4a');
        expect(containerFor({audioOutput: true, audioCodec: 'mp3', video})).toBe('mp3');
        // Video output keeps a container we can write, else mp4.
        expect(containerFor({audioOutput: false, audioCodec: 'aac', video})).toBe('mp4');
        expect(containerFor({audioOutput: false, audioCodec: 'aac', video: {video_path: 'a.mkv'}})).toBe('mkv');
        // An audio file's own suffix is not a video container.
        expect(containerFor({audioOutput: false, audioCodec: TRANSCODE_COPY, video: audio})).toBe('mp4');
    });

    test('preferredTarget picks the first preference ffmpeg can produce', () => {
        expect(preferredTarget(['vp9', 'h264'], transcodeVideoCodecOptions)).toBe('h264');
        expect(preferredTarget(['vp9', 'av1'], transcodeVideoCodecOptions)).toBe(TRANSCODE_COPY);
        expect(preferredTarget(['opus', 'aac'], transcodeAudioCodecOptions)).toBe('opus');
        expect(preferredTarget([], transcodeAudioCodecOptions)).toBe(TRANSCODE_COPY);
        expect(preferredTarget(undefined, transcodeAudioCodecOptions)).toBe(TRANSCODE_COPY);
    });
});

describe('TranscodeModal', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        fetchVideoDownloadDefaults.mockResolvedValue({video_codecs: ['h264'], audio_codecs: ['vorbis', 'aac']});
        transcodeVideo.mockResolvedValue('transcode_video-abc');
    });

    test('pre-populates from the preferred codecs and queues the Job', async () => {
        const onQueued = jest.fn();
        renderWithProviders(
            <TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={video} onQueued={onQueued}/>,
        );

        expect(screen.getByText(/Current codecs: video vp9, audio opus/)).toBeInTheDocument();

        // The defaults arrive: h264 is producible, vorbis is not, so aac is the audio target.
        await waitFor(() => expect(selectInput('Video codec')).toHaveValue('h264 (avc1)'));
        expect(selectInput('Audio codec')).toHaveValue('aac');
        expect(selectInput('Container')).toHaveValue('mp4');

        fireEvent.click(screen.getByRole('button', {name: /Transcode/}));

        await waitFor(() => expect(transcodeVideo).toHaveBeenCalledWith(7, {
            video_codec: 'h264', audio_codec: 'aac', container: 'mp4', fragmented: false,
        }));
        await waitFor(() => expect(onQueued).toHaveBeenCalledWith('transcode_video-abc'));
    });

    test('shows the Job instead of the form once one is queued', () => {
        renderWithProviders(
            <TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={video}
                            jobId='transcode_video-abc' job={runningJob} onCancelJob={jest.fn()}/>,
        );
        expect(screen.queryAllByLabelText('Video codec')).toHaveLength(0);
        expect(screen.getByText('running')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Close'})).toBeInTheDocument();
        expect(screen.queryByRole('button', {name: /Transcode/})).not.toBeInTheDocument();
    });

    test('keeping every stream is a remux into the chosen container', async () => {
        fetchVideoDownloadDefaults.mockResolvedValue({video_codecs: [], audio_codecs: []});
        // A webm cannot be kept (not a container we write), so the select starts at mp4: a change.
        renderWithProviders(
            <TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={video} onQueued={jest.fn()}/>,
        );

        await waitFor(() => expect(selectInput('Container')).toHaveValue('mp4'));
        expect(await screen.findByText(/only the container changes to mp4/)).toBeInTheDocument();

        const button = screen.getByRole('button', {name: 'Remux'});
        expect(button).toBeEnabled();
        fireEvent.click(button);
        await waitFor(() => expect(transcodeVideo).toHaveBeenCalledWith(7, {
            video_codec: null, audio_codec: null, container: 'mp4', fragmented: false,
        }));
    });

    test('Fragmented is offered for mp4 and sent with the request', async () => {
        fetchVideoDownloadDefaults.mockResolvedValue({video_codecs: [], audio_codecs: []});
        const mp4 = {...video, video_path: 'videos/movie.mp4'};
        renderWithProviders(
            <TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={mp4} onQueued={jest.fn()}/>,
        );
        await waitFor(() => expect(selectInput('Container')).toHaveValue('mp4'));
        const toggle = screen.getByRole('switch', {name: /Fragmented/});
        expect(toggle).not.toBeChecked();

        fireEvent.click(toggle);
        expect(await screen.findByText(/rewritten as-is in fragments/)).toBeInTheDocument();
        expect(screen.queryByText(/fast start/)).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Remux'}));
        await waitFor(() => expect(transcodeVideo).toHaveBeenCalledWith(7, {
            video_codec: null, audio_codec: null, container: 'mp4', fragmented: true,
        }));
    });

    test('Fragmented is not offered for mkv', async () => {
        fetchVideoDownloadDefaults.mockResolvedValue({video_codecs: [], audio_codecs: []});
        const mkv = {...video, video_path: 'videos/movie.mkv'};
        renderWithProviders(<TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={mkv}/>);
        await waitFor(() => expect(selectInput('Container')).toHaveValue('mkv'));
        expect(screen.queryByRole('switch', {name: /Fragmented/})).not.toBeInTheDocument();
    });

    test('a remux into the same container is described as a fast-start rewrite', async () => {
        fetchVideoDownloadDefaults.mockResolvedValue({video_codecs: [], audio_codecs: []});
        const mkv = {...video, video_path: 'videos/movie.mkv'};
        renderWithProviders(<TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={mkv}/>);

        await waitFor(() => expect(selectInput('Container')).toHaveValue('mkv'));
        // mkv has no fast start; the hint must not promise one.
        expect(await screen.findByText(/Both streams are kept: the file is rewritten as-is\./)).toBeInTheDocument();
        expect(screen.queryByText(/fast start/)).not.toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Remux'})).toBeEnabled();
    });

    test('an audio file offers audio codecs and containers only', async () => {
        fetchVideoDownloadDefaults.mockResolvedValue({video_codecs: ['h264'], audio_codecs: []});
        renderWithProviders(
            <TranscodeModal open={true} onClose={jest.fn()} fileGroupId={8} video={audio} audioOnly={true}
                            onQueued={jest.fn()}/>,
        );

        expect(screen.getByText('Transcode Audio')).toBeInTheDocument();
        expect(screen.getByText(/Current codec: audio aac/)).toBeInTheDocument();
        // The aac source, copied, belongs in m4a; the file already is one.
        await waitFor(() => expect(selectInput('Container')).toHaveValue('m4a (aac)'));
        expect(screen.queryAllByLabelText('Video codec')).toHaveLength(0);
        expect(await screen.findByText(/The audio is kept: the file is rewritten as-is with fast start/))
            .toBeInTheDocument();
        expect(screen.queryByText(/Both streams/)).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Remux'}));
        // No video codec is sent for an audio file, whatever the video preferences say.
        await waitFor(() => expect(transcodeVideo).toHaveBeenCalledWith(8, {
            video_codec: null, audio_codec: null, container: 'm4a', fragmented: false,
        }));
    });

    test('the Remove video option is offered for videos', async () => {
        renderWithProviders(
            <TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={video} onQueued={jest.fn()}/>,
        );
        await waitFor(() => expect(selectInput('Video codec')).toHaveValue('h264 (avc1)'));
        expect(transcodeVideoCodecOptions.some(i => i.value === TRANSCODE_REMOVE_VIDEO)).toBe(true);
        // Selecting it is exercised through containerFor (Mantine's dropdown is not driveable in jsdom).
    });

    test('WROL Mode disables starting a transcode', async () => {
        renderWithProviders(
            <TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={video}/>,
            wrolMode,
        );
        await waitFor(() => expect(selectInput('Video codec')).toHaveValue('h264 (avc1)'));
        expect(screen.getByRole('button', {name: /Transcode/})).toBeDisabled();
    });
});

describe('EditVideoModal', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        updateVideo.mockResolvedValue({...videoFile, title: 'New Title'});
    });

    test('starts from the current title and saves a changed one', async () => {
        const onSaved = jest.fn().mockResolvedValue(undefined);
        const onClose = jest.fn();
        renderWithProviders(
            <EditVideoModal open={true} onClose={onClose} fileGroupId={7} videoFile={videoFile}
                            description='Old words' onSaved={onSaved}/>,
        );

        const input = screen.getByLabelText('Title');
        expect(input).toHaveValue('Old Title');
        expect(screen.getByLabelText('Description')).toHaveValue('Old words');
        // Nothing changed yet: Save is disabled.
        expect(screen.getByRole('button', {name: /Save/})).toBeDisabled();

        fireEvent.change(input, {target: {value: '  New Title '}});
        fireEvent.click(screen.getByRole('button', {name: /Save/}));

        // Only the changed field is sent.
        await waitFor(() => expect(updateVideo).toHaveBeenCalledWith(7, {title: 'New Title'}));
        await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    test('saves a changed description on its own, including clearing it', async () => {
        renderWithProviders(
            <EditVideoModal open={true} onClose={jest.fn()} fileGroupId={7} videoFile={videoFile} description='Old words'/>,
        );
        fireEvent.change(screen.getByLabelText('Description'), {target: {value: ''}});
        fireEvent.click(screen.getByRole('button', {name: /Save/}));
        await waitFor(() => expect(updateVideo).toHaveBeenCalledWith(7, {description: ''}));
    });

    test('WROL Mode disables saving', async () => {
        renderWithProviders(
            <EditVideoModal open={true} onClose={jest.fn()} fileGroupId={7} videoFile={videoFile}/>,
            wrolMode,
        );
        fireEvent.change(screen.getByLabelText('Title'), {target: {value: 'Changed'}});
        expect(screen.getByRole('button', {name: /Save/})).toBeDisabled();
        expect(screen.getByText(/WROL Mode/)).toBeInTheDocument();
    });

    test('an empty title cannot be saved', () => {
        renderWithProviders(<EditVideoModal open={true} onClose={jest.fn()} fileGroupId={7} videoFile={videoFile}/>);
        fireEvent.change(screen.getByLabelText('Title'), {target: {value: '   '}});
        expect(screen.getByText('A title is required')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: /Save/})).toBeDisabled();
        expect(updateVideo).not.toHaveBeenCalled();
    });

    test('a failed save keeps the modal open', async () => {
        updateVideo.mockRejectedValue(new Error('boom'));
        const onClose = jest.fn();
        renderWithProviders(<EditVideoModal open={true} onClose={onClose} fileGroupId={7} videoFile={videoFile}/>);
        fireEvent.change(screen.getByLabelText('Title'), {target: {value: 'Other'}});
        fireEvent.click(screen.getByRole('button', {name: /Save/}));
        await waitFor(() => expect(updateVideo).toHaveBeenCalled());
        expect(onClose).not.toHaveBeenCalled();
        expect(screen.getByLabelText('Title')).toHaveValue('Other');
    });
});

// A tiny harness so the hook can be driven like the menu drives it.
function JobHarness({jobId, onFinished, onLost}) {
    const {job, cancel} = useJob(jobId, onFinished, onLost);
    return <JobProgress job={job} onCancel={cancel}/>;
}

// Let pending promise callbacks run (a settled request schedules its next poll), then advance
// the fake clock past the poll interval.
const nextPoll = async () => {
    await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        jest.advanceTimersByTime(2000);
    });
};

describe('useJob + JobProgress', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    test('polls until the Job finishes, then reports once', async () => {
        const onFinished = jest.fn();
        getJob.mockResolvedValueOnce(runningJob).mockResolvedValueOnce(completeJob);

        renderWithProviders(<JobHarness jobId='transcode_video-abc' onFinished={onFinished}/>);

        await waitFor(() => expect(screen.getByText('running')).toBeInTheDocument());
        expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40');
        expect(screen.getByTestId('job-log')).toHaveTextContent('out_time_us=1');
        expect(screen.getByRole('button', {name: 'Cancel'})).toBeInTheDocument();

        await act(async () => {
            jest.advanceTimersByTime(2000);
        });

        await waitFor(() => expect(screen.getByText('complete')).toBeInTheDocument());
        expect(onFinished).toHaveBeenCalledTimes(1);
        expect(onFinished.mock.calls[0][0].status).toBe('complete');
        // A finished Job is not polled again, and cannot be cancelled.
        expect(getJob).toHaveBeenCalledTimes(2);
        expect(screen.queryByRole('button', {name: 'Cancel'})).not.toBeInTheDocument();
    });

    test('a failed request is retried instead of ending the polling', async () => {
        getJob
            .mockRejectedValueOnce(new Error('network'))
            .mockResolvedValueOnce(runningJob)
            .mockRejectedValueOnce(new Error('network'))
            .mockResolvedValueOnce(completeJob);
        const onFinished = jest.fn();

        renderWithProviders(<JobHarness jobId='transcode_video-abc' onFinished={onFinished}/>);

        // First poll failed: still "Starting...", but another poll is scheduled.
        await waitFor(() => expect(getJob).toHaveBeenCalledTimes(1));
        expect(screen.getByText('Starting...')).toBeInTheDocument();
        await nextPoll();
        await waitFor(() => expect(screen.getByText('running')).toBeInTheDocument());

        // A failure mid-way keeps the last good state and keeps polling.
        await nextPoll();
        await waitFor(() => expect(getJob).toHaveBeenCalledTimes(3));
        expect(screen.getByText('running')).toBeInTheDocument();
        await nextPoll();
        await waitFor(() => expect(screen.getByText('complete')).toBeInTheDocument());
        expect(onFinished).toHaveBeenCalledTimes(1);
    });

    test('a 404 means the API forgot the Job: give up at once', async () => {
        getJob.mockRejectedValue(notFound);
        const onLost = jest.fn();
        const onFinished = jest.fn();
        renderWithProviders(<JobHarness jobId='transcode_video-abc' onFinished={onFinished} onLost={onLost}/>);

        await waitFor(() => expect(onLost).toHaveBeenCalledTimes(1));
        expect(onLost.mock.calls[0][0].status).toBe(404);
        await nextPoll();
        expect(getJob).toHaveBeenCalledTimes(1);
        expect(onFinished).not.toHaveBeenCalled();
    });

    test('repeated failures give up after a few polls', async () => {
        getJob.mockRejectedValue(new Error('network'));
        const onLost = jest.fn();
        renderWithProviders(<JobHarness jobId='transcode_video-abc' onLost={onLost}/>);

        for (let i = 0; i < 6; i++) {
            await nextPoll();
        }
        await waitFor(() => expect(onLost).toHaveBeenCalledTimes(1));
        expect(getJob).toHaveBeenCalledTimes(5);
    });

    test('Cancel asks the API to cancel the Job', async () => {
        getJob.mockResolvedValue({...pendingJob, status: 'running', progress: 10});
        cancelJob.mockResolvedValue({...pendingJob, status: 'running', progress: 10, cancel_requested: true});

        renderWithProviders(<JobHarness jobId='transcode_video-abc'/>);

        await waitFor(() => expect(screen.getByRole('button', {name: 'Cancel'})).toBeInTheDocument());
        fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));

        await waitFor(() => expect(cancelJob).toHaveBeenCalledWith('transcode_video-abc'));
        await waitFor(() => expect(screen.getByRole('button', {name: 'Cancelling...'})).toBeDisabled());
    });

    test('shows the error of a failed Job', async () => {
        getJob.mockResolvedValue({...pendingJob, status: 'failed', error: 'ffmpeg exited with 1', log: ['boom']});

        renderWithProviders(<JobHarness jobId='transcode_video-abc'/>);

        await waitFor(() => expect(screen.getByText('failed')).toBeInTheDocument());
        expect(screen.getByText('ffmpeg exited with 1')).toBeInTheDocument();
    });
});

describe('VideoEditMenu', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        fetchVideoDownloadDefaults.mockResolvedValue({video_codecs: ['h264'], audio_codecs: ['aac']});
        transcodeVideo.mockResolvedValue('transcode_video-abc');
    });

    // Mantine's Menu in jsdom: after a modal has closed, the first click on the target can land
    // while the dropdown still counts as open (and so toggles it shut).  Click until items show.
    const openMenu = async () => {
        for (let attempt = 0; attempt < 3; attempt++) {
            fireEvent.click(screen.getByRole('button', {name: /Edit/}));
            try {
                return await screen.findByRole('menuitem', {name: /Refresh/}, {timeout: 300});
            } catch (e) {
                // Toggled shut; try again.
            }
        }
        throw new Error('The Edit menu did not open');
    };
    const openMenuItem = async (name) => {
        await openMenu();
        fireEvent.click(screen.getByRole('menuitem', {name}));
    };

    test('Refresh calls onRefresh; Transcode opens the modal', async () => {
        const onRefresh = jest.fn().mockResolvedValue(undefined);
        renderWithProviders(<VideoEditMenu videoFile={videoFile} video={video} onRefresh={onRefresh}/>);

        await openMenuItem(/Refresh/);
        await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));

        await openMenuItem(/Transcode/);
        await waitFor(() => expect(screen.getByText('Transcode Video')).toBeInTheDocument());
    });

    test('Edit opens the details modal', async () => {
        renderWithProviders(<VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()}/>);
        await openMenuItem(/^Edit/);
        expect(await screen.findByText('Edit Video')).toBeInTheDocument();
        expect(screen.getByLabelText('Title')).toHaveValue('Old Title');
    });

    test('Refresh is unavailable without a URL; audio files can be transcoded', async () => {
        renderWithProviders(<VideoEditMenu videoFile={audioFile} video={audio} onRefresh={jest.fn()}/>);

        fireEvent.click(screen.getByRole('button', {name: /Edit/}));
        const refresh = await screen.findByRole('menuitem', {name: /Refresh/});
        expect(refresh).toBeDisabled();
        expect(screen.getByRole('menuitem', {name: /Transcode/})).toBeEnabled();
        fireEvent.click(screen.getByRole('menuitem', {name: /Transcode/}));
        expect(await screen.findByText('Transcode Audio')).toBeInTheDocument();
    });

    test('Transcode is unavailable for files that are neither video nor audio', async () => {
        const other = {...videoFile, mimetype: 'application/pdf'};
        renderWithProviders(<VideoEditMenu videoFile={other} video={video} onRefresh={jest.fn()}/>);
        fireEvent.click(screen.getByRole('button', {name: /Edit/}));
        expect(await screen.findByRole('menuitem', {name: /Transcode/})).toBeDisabled();
    });

    test('WROL Mode disables every item', async () => {
        renderWithProviders(
            <VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()} onDelete={jest.fn()}/>,
            wrolMode,
        );
        fireEvent.click(screen.getByRole('button', {name: /Edit/}));
        expect(await screen.findByRole('menuitem', {name: /Refresh/})).toBeDisabled();
        expect(screen.getByRole('menuitem', {name: /Transcode/})).toBeDisabled();
        expect(screen.getByRole('menuitem', {name: /Delete/})).toBeDisabled();
        expect(screen.getByRole('menuitem', {name: /^Edit/})).toBeDisabled();
    });

    test('Delete asks for confirmation before calling onDelete', async () => {
        const onDelete = jest.fn().mockResolvedValue(undefined);
        renderWithProviders(
            <VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()} onDelete={onDelete}/>,
        );

        await openMenuItem(/Delete/);
        expect(await screen.findByText('Delete video?')).toBeInTheDocument();
        expect(onDelete).not.toHaveBeenCalled();

        fireEvent.click(await screen.findByRole('button', {name: 'Delete'}));
        await waitFor(() => expect(onDelete).toHaveBeenCalledTimes(1));
    });

    test('backing out of the Delete confirmation deletes nothing', async () => {
        const onDelete = jest.fn();
        renderWithProviders(
            <VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()} onDelete={onDelete}/>,
        );

        await openMenuItem(/Delete/);
        expect(await screen.findByText('Delete video?')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
        await waitFor(() => expect(screen.queryByText('Delete video?')).not.toBeInTheDocument());
        expect(onDelete).not.toHaveBeenCalled();
    });

    test('closing the modal keeps watching the Job and reports completion to the page', async () => {
        jest.useFakeTimers();
        try {
            getJob.mockResolvedValueOnce(runningJob).mockResolvedValueOnce(completeJob);
            const onTranscodeComplete = jest.fn();
            renderWithProviders(
                <VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()} onDelete={jest.fn()}
                               onTranscodeComplete={onTranscodeComplete}/>,
            );

            await openMenuItem(/Transcode/);
            await waitFor(() => expect(selectInput('Video codec')).toHaveValue('h264 (avc1)'));
            fireEvent.click(screen.getByRole('button', {name: 'Transcode'}));
            await waitFor(() => expect(screen.getByText('running')).toBeInTheDocument());

            // Close while it runs.  The modal is gone but the Job is still watched.
            fireEvent.click(screen.getByRole('button', {name: 'Close'}));
            await waitFor(() => expect(screen.queryByText('Transcode Video')).not.toBeInTheDocument());

            await nextPoll();
            await waitFor(() => expect(onTranscodeComplete).toHaveBeenCalledTimes(1));
            expect(onTranscodeComplete.mock.calls[0][0].status).toBe('complete');
            expect(getJob).toHaveBeenCalledTimes(2);
        } finally {
            jest.useRealTimers();
        }
    });

    test('while a Job runs, Transcode shows its progress and Delete waits', async () => {
        getJob.mockResolvedValue(runningJob);
        renderWithProviders(
            <VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()} onDelete={jest.fn()}
                           initialJobId='transcode_video-abc'/>,
        );
        await waitFor(() => expect(getJob).toHaveBeenCalled());

        await openMenu();
        expect(screen.getByRole('menuitem', {name: 'Transcoding...'})).toBeEnabled();
        expect(screen.getByRole('menuitem', {name: /Delete/})).toBeDisabled();

        fireEvent.click(screen.getByRole('menuitem', {name: 'Transcoding...'}));
        expect(await screen.findByText('running')).toBeInTheDocument();
        expect(screen.queryAllByLabelText('Video codec')).toHaveLength(0);
        expect(transcodeVideo).not.toHaveBeenCalled();
    });

    test('a Job that fails after the modal was closed still tells the user', async () => {
        getJob.mockResolvedValue(failedJob);
        renderWithProviders(
            <VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()} onDelete={jest.fn()}
                           onTranscodeComplete={jest.fn()} initialJobId='transcode_video-abc'/>,
        );
        await waitFor(() => expect(toast).toHaveBeenCalledTimes(1));
        expect(toast.mock.calls[0][0]).toMatchObject({type: 'error', title: 'Transcode failed'});
        expect(toast.mock.calls[0][0].description).toMatch(/ffmpeg exited with 1/);
        expect(toast.mock.calls[0][0].description).toMatch(/original file was kept/);

        // Forgotten: the menu is unlocked again.
        await openMenu();
        expect(screen.getByRole('menuitem', {name: 'Transcode...'})).toBeEnabled();
        expect(screen.getByRole('menuitem', {name: /Delete/})).toBeEnabled();
    });

    test('a Job the API no longer knows unlocks the menu with a warning', async () => {
        getJob.mockRejectedValue(notFound);
        renderWithProviders(
            <VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()} onDelete={jest.fn()}
                           initialJobId='transcode_video-abc'/>,
        );
        await waitFor(() => expect(toast).toHaveBeenCalledTimes(1));
        expect(toast.mock.calls[0][0]).toMatchObject({type: 'warning', title: 'Lost track of the transcode'});

        await openMenu();
        expect(screen.getByRole('menuitem', {name: 'Transcode...'})).toBeEnabled();
        expect(screen.getByRole('menuitem', {name: /Delete/})).toBeEnabled();
    });

    test('a Job that finished unwatched is forgotten, so the next open offers the form', async () => {
        getJob.mockResolvedValue(completeJob);
        renderWithProviders(
            <VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()} onDelete={jest.fn()}
                           initialJobId='transcode_video-abc'/>,
        );
        await waitFor(() => expect(getJob).toHaveBeenCalled());

        await openMenu();
        expect(await screen.findByRole('menuitem', {name: 'Transcode...'})).toBeEnabled();
        expect(screen.getByRole('menuitem', {name: /Delete/})).toBeEnabled();
        fireEvent.click(screen.getByRole('menuitem', {name: 'Transcode...'}));
        await waitFor(() => expect(selectInput('Video codec')).toBeInTheDocument());
    });
});
