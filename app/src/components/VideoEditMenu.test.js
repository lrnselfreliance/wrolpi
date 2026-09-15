import React from 'react';
import {act, fireEvent, screen, waitFor} from '@testing-library/react';
import {renderWithProviders} from '../test-utils';
import {currentCodecs, EditVideoModal, JobProgress, preferredTarget, TranscodeModal, VideoEditMenu} from './VideoEditMenu';
import {TRANSCODE_COPY, transcodeAudioCodecOptions, transcodeVideoCodecOptions} from './Vars';

jest.mock('../api', () => ({
    cancelJob: jest.fn(),
    fetchVideoDownloadDefaults: jest.fn(),
    getJob: jest.fn(),
    transcodeVideo: jest.fn(),
    updateVideo: jest.fn(),
}));

import {cancelJob, fetchVideoDownloadDefaults, getJob, transcodeVideo, updateVideo} from '../api';

const video = {
    codec_names: ['vp9', 'mjpeg', 'opus'],
    codec_types: ['video', 'video', 'audio'],
    video_path: 'videos/movie.webm',
};
const videoFile = {id: 7, url: 'https://example.com/watch?v=1', mimetype: 'video/webm', title: 'Old Title', video};

// Mantine's Select renders a hidden input next to the visible one, both tied to the label.
const selectInput = (label) => screen.getAllByLabelText(label).find(i => i.type !== 'hidden');

// `renderWithProviders`' `settings` option replaces the SettingsContext value; the WROL flag lives
// one level down in its `settings`.
const wrolMode = {settings: {settings: {wrol_mode: true}}};

const pendingJob = {
    id: 'transcode_video-abc', status: 'pending', progress: null, log: [], error: null, cancel_requested: false,
    description: 'Transcode movie.webm',
};

describe('helpers', () => {
    test('currentCodecs ignores embedded thumbnail streams', () => {
        expect(currentCodecs(video)).toEqual({video: ['vp9'], audio: ['opus']});
        expect(currentCodecs(null)).toEqual({video: [], audio: []});
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
        getJob.mockResolvedValue(pendingJob);
    });

    test('pre-populates from the preferred codecs and queues the Job', async () => {
        renderWithProviders(<TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={video}/>);

        expect(screen.getByText(/Current codecs: video vp9, audio opus/)).toBeInTheDocument();

        // The defaults arrive: h264 is producible, vorbis is not, so aac is the audio target.
        await waitFor(() => expect(selectInput('Video codec')).toHaveValue('h264 (avc1)'));
        expect(selectInput('Audio codec')).toHaveValue('aac');
        expect(selectInput('Container')).toHaveValue('mp4');

        fireEvent.click(screen.getByRole('button', {name: /Transcode/}));

        await waitFor(() => expect(transcodeVideo).toHaveBeenCalledWith(7, {
            video_codec: 'h264', audio_codec: 'aac', container: 'mp4',
        }));
        // The form is replaced by the Job's progress.
        await waitFor(() => expect(getJob).toHaveBeenCalledWith('transcode_video-abc'));
        expect(screen.queryAllByLabelText('Video codec')).toHaveLength(0);
        expect(await screen.findByText('pending')).toBeInTheDocument();
    });

    test('refuses to start when every stream is kept', async () => {
        fetchVideoDownloadDefaults.mockResolvedValue({video_codecs: [], audio_codecs: []});
        renderWithProviders(<TranscodeModal open={true} onClose={jest.fn()} fileGroupId={7} video={video}/>);

        await waitFor(() => expect(screen.getByText('Choose at least one codec to convert.')).toBeInTheDocument());
        expect(screen.getByRole('button', {name: /Transcode/})).toBeDisabled();
        expect(transcodeVideo).not.toHaveBeenCalled();
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

describe('JobProgress', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    test('polls until the Job finishes, then reports once', async () => {
        const onFinished = jest.fn();
        getJob
            .mockResolvedValueOnce({...pendingJob, status: 'running', progress: 40, log: ['out_time_us=1']})
            .mockResolvedValueOnce({...pendingJob, status: 'complete', progress: 100, log: ['done']});

        renderWithProviders(<JobProgress jobId='transcode_video-abc' onFinished={onFinished}/>);

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

    test('Cancel asks the API to cancel the Job', async () => {
        getJob.mockResolvedValue({...pendingJob, status: 'running', progress: 10});
        cancelJob.mockResolvedValue({...pendingJob, status: 'running', progress: 10, cancel_requested: true});

        renderWithProviders(<JobProgress jobId='transcode_video-abc'/>);

        await waitFor(() => expect(screen.getByRole('button', {name: 'Cancel'})).toBeInTheDocument());
        fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));

        await waitFor(() => expect(cancelJob).toHaveBeenCalledWith('transcode_video-abc'));
        await waitFor(() => expect(screen.getByRole('button', {name: 'Cancelling...'})).toBeDisabled());
    });

    test('shows the error of a failed Job', async () => {
        getJob.mockResolvedValue({...pendingJob, status: 'failed', error: 'ffmpeg exited with 1', log: ['boom']});

        renderWithProviders(<JobProgress jobId='transcode_video-abc'/>);

        await waitFor(() => expect(screen.getByText('failed')).toBeInTheDocument());
        expect(screen.getByText('ffmpeg exited with 1')).toBeInTheDocument();
    });
});

describe('VideoEditMenu', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        fetchVideoDownloadDefaults.mockResolvedValue({video_codecs: [], audio_codecs: []});
    });

    test('Refresh calls onRefresh; Transcode opens the modal', async () => {
        const onRefresh = jest.fn().mockResolvedValue(undefined);
        renderWithProviders(<VideoEditMenu videoFile={videoFile} video={video} onRefresh={onRefresh}/>);

        fireEvent.click(screen.getByRole('button', {name: /Edit/}));
        fireEvent.click(await screen.findByRole('menuitem', {name: /Refresh/}));
        await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));

        fireEvent.click(screen.getByRole('button', {name: /Edit/}));
        fireEvent.click(await screen.findByRole('menuitem', {name: /Transcode/}));
        await waitFor(() => expect(screen.getByText('Transcode Video')).toBeInTheDocument());
    });

    test('Refresh is unavailable without a URL, Transcode for non-video files', async () => {
        const audioFile = {...videoFile, url: null, mimetype: 'audio/mpeg'};
        renderWithProviders(<VideoEditMenu videoFile={audioFile} video={video} onRefresh={jest.fn()}/>);

        fireEvent.click(screen.getByRole('button', {name: /Edit/}));
        const refresh = await screen.findByRole('menuitem', {name: /Refresh/});
        expect(refresh).toBeDisabled();
        expect(screen.getByRole('menuitem', {name: /Transcode/})).toBeDisabled();
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

    test('Edit opens the details modal', async () => {
        renderWithProviders(<VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()}/>);
        fireEvent.click(screen.getByRole('button', {name: /Edit/}));
        fireEvent.click(await screen.findByRole('menuitem', {name: /^Edit/}));
        expect(await screen.findByText('Edit Video')).toBeInTheDocument();
        expect(screen.getByLabelText('Title')).toHaveValue('Old Title');
    });

    test('Delete asks for confirmation before calling onDelete', async () => {
        const onDelete = jest.fn().mockResolvedValue(undefined);
        renderWithProviders(
            <VideoEditMenu videoFile={videoFile} video={video} onRefresh={jest.fn()} onDelete={onDelete}/>,
        );

        fireEvent.click(screen.getByRole('button', {name: /Edit/}));
        fireEvent.click(await screen.findByRole('menuitem', {name: /Delete/}));
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

        fireEvent.click(screen.getByRole('button', {name: /Edit/}));
        fireEvent.click(await screen.findByRole('menuitem', {name: /Delete/}));
        expect(await screen.findByText('Delete video?')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
        await waitFor(() => expect(screen.queryByText('Delete video?')).not.toBeInTheDocument());
        expect(onDelete).not.toHaveBeenCalled();
    });
});
