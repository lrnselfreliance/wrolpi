import React from 'react';
import {act, render, renderHook} from '@testing-library/react';
import {getResumePosition, useFileProgress, useMediaProgress} from './useFileProgress';
import {ViewProgress} from '../components/Common';

const PATH = 'videos/movie.mp4';
const CACHE_KEY = `wrolpi-progress:${PATH}`;

/** The bodies of the progress saves sent by beacon or fetch, in order. */
const sent = () => [
    ...navigator.sendBeacon.mock.calls.map(([, blob]) => blob.__body),
    ...global.fetch.mock.calls.map(([, init]) => init.body),
].map(i => JSON.parse(i));

beforeEach(() => {
    jest.useFakeTimers();
    window.sessionStorage.clear();
    navigator.sendBeacon = jest.fn(() => true);
    global.fetch = jest.fn(() => Promise.resolve({ok: true}));
    // jsdom's Blob cannot be read synchronously; keep the body so a test can check it.
    global.Blob = class {
        constructor(parts) {
            this.__body = parts.join('');
        }
    };
});

afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
});

describe('getResumePosition', () => {
    const position = {kind: 'time', seconds: 300, updated_at: 1000};

    test('resumes from the server', () => {
        expect(getResumePosition(PATH, {progress: 0.5, position})).toEqual(position);
    });

    test('a newer position from this tab wins over the server', () => {
        const cached = {kind: 'time', seconds: 400, updated_at: 2000};
        window.sessionStorage.setItem(CACHE_KEY, JSON.stringify({progress: 0.6, position: cached, updated_at: 2000}));
        expect(getResumePosition(PATH, {progress: 0.5, position})).toEqual(cached);
    });

    test('a newer position from the server wins over this tab', () => {
        const cached = {kind: 'time', seconds: 400, updated_at: 500};
        window.sessionStorage.setItem(CACHE_KEY, JSON.stringify({progress: 0.6, position: cached, updated_at: 500}));
        expect(getResumePosition(PATH, {progress: 0.5, position})).toEqual(position);
    });

    test('a file finished on another device starts over', () => {
        const cached = {kind: 'time', seconds: 400, updated_at: 500};
        window.sessionStorage.setItem(CACHE_KEY, JSON.stringify({progress: 0.6, position: cached, updated_at: 500}));
        const fileGroup = {progress: 1, position: null, viewed: new Date(9000).toISOString()};
        expect(getResumePosition(PATH, fileGroup)).toBeNull();
    });

    test.each([
        ['finished', {progress: 1, position: null}],
        ['too early', {progress: 0.2, position: {kind: 'time', seconds: 5}}],
        ['first page', {progress: 0.1, position: {kind: 'page', page: 0}}],
        ['never viewed', {progress: null, position: null}],
        ['no file group', null],
    ])('%s starts from the beginning', (_, fileGroup) => {
        expect(getResumePosition(PATH, fileGroup)).toBeNull();
    });

    test('unreadable storage falls back to the server', () => {
        const getItem = jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
            throw new Error('denied');
        });
        try {
            expect(getResumePosition(PATH, {progress: 0.5, position})).toEqual(position);
        } finally {
            getItem.mockRestore();
        }
    });
});

describe('useFileProgress', () => {
    const snapshot = {progress: 0.25, position: {kind: 'time', seconds: 150}};

    test('a report is sent by the heartbeat, once while it is unchanged', () => {
        const {result} = renderHook(() => useFileProgress(PATH));
        act(() => result.current.report(snapshot));
        expect(sent()).toEqual([]);

        act(() => jest.advanceTimersByTime(15_000));
        act(() => jest.advanceTimersByTime(15_000));
        expect(sent()).toEqual([{
            file: PATH, progress: 0.25, final: false,
            position: {kind: 'time', seconds: 150, updated_at: expect.any(Number)},
        }]);
        // Heartbeats use fetch; only a final save needs a beacon.
        expect(navigator.sendBeacon).not.toHaveBeenCalled();
        expect(JSON.parse(window.sessionStorage.getItem(CACHE_KEY)).position.seconds).toBe(150);
    });

    test('leaving the page sends a final save by beacon', () => {
        const {result, unmount} = renderHook(() => useFileProgress(PATH));
        act(() => result.current.report(snapshot));
        unmount();
        expect(navigator.sendBeacon).toHaveBeenCalledTimes(1);
        expect(sent()[0]).toMatchObject({file: PATH, progress: 0.25, final: true});
    });

    test('hiding the page sends a final save', () => {
        const {result} = renderHook(() => useFileProgress(PATH));
        act(() => result.current.report(snapshot));
        jest.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
        act(() => document.dispatchEvent(new Event('visibilitychange')));
        expect(sent()).toEqual([expect.objectContaining({final: true})]);
    });

    test('a new file saves the old one under its own path, and starts empty', () => {
        const {result, rerender} = renderHook(({path}) => useFileProgress(path), {initialProps: {path: PATH}});
        act(() => result.current.report(snapshot));
        rerender({path: 'videos/next.mp4'});
        expect(sent()).toEqual([expect.objectContaining({file: PATH, final: true})]);

        // Nothing has been reported for the next file.
        act(() => jest.advanceTimersByTime(15_000));
        expect(sent()).toHaveLength(1);
    });

    test('nothing is sent until something is reported', () => {
        const {unmount} = renderHook(() => useFileProgress(PATH));
        act(() => jest.advanceTimersByTime(60_000));
        unmount();
        expect(sent()).toEqual([]);
    });
});

describe('useMediaProgress', () => {
    /** A stand-in for the <video> element the handlers receive as `e.currentTarget`. */
    const media = (props) => ({currentTarget: {duration: 600, currentTime: 0, ...props}});

    test('resumes the saved position when the metadata loads', () => {
        const fileGroup = {progress: 0.5, position: {kind: 'time', seconds: 300}};
        const {result} = renderHook(() => useMediaProgress(PATH, fileGroup));
        const event = media();
        act(() => result.current.onLoadedMetadata(event));
        expect(event.currentTarget.currentTime).toBe(300);

        // Only once; a later `loadedmetadata` does not jump back.
        event.currentTarget.currentTime = 450;
        act(() => result.current.onLoadedMetadata(event));
        expect(event.currentTarget.currentTime).toBe(450);
    });

    test('an explicit start time wins over the saved position', () => {
        const fileGroup = {progress: 0.5, position: {kind: 'time', seconds: 300}};
        const {result} = renderHook(() => useMediaProgress(PATH, fileGroup, {startSeconds: 42}));
        const event = media();
        act(() => result.current.onLoadedMetadata(event));
        expect(event.currentTarget.currentTime).toBe(42);
    });

    test('a finished file starts from the beginning', () => {
        const {result} = renderHook(() => useMediaProgress(PATH, {progress: 1, position: null}));
        const event = media();
        act(() => result.current.onLoadedMetadata(event));
        expect(event.currentTarget.currentTime).toBe(0);
    });

    test('pausing saves where the user is; the end saves it finished', () => {
        const {result} = renderHook(() => useMediaProgress(PATH, null));
        act(() => result.current.onTimeUpdate(media({currentTime: 120})));
        act(() => result.current.onPause());
        act(() => result.current.onEnded());
        expect(sent()).toEqual([
            expect.objectContaining({progress: 0.2, position: expect.objectContaining({seconds: 120}), final: true}),
            expect.objectContaining({progress: 1, position: null, final: true}),
        ]);
    });

    test('nothing is saved before the duration is known', () => {
        const {result} = renderHook(() => useMediaProgress(PATH, null));
        act(() => result.current.onTimeUpdate(media({duration: NaN, currentTime: 3})));
        act(() => result.current.onPause());
        expect(sent()).toEqual([]);
    });
});

describe('ViewProgress', () => {
    test.each([[0], [null], [undefined]])('no bar for progress %s', (progress) => {
        const {container} = render(<ViewProgress progress={progress}/>);
        expect(container).toBeEmptyDOMElement();
    });

    test('the bar is as wide as the progress', () => {
        const {getByRole} = render(<ViewProgress progress={0.4}/>);
        const bar = getByRole('progressbar');
        expect(bar).toHaveAttribute('aria-valuenow', '40');
        expect(bar.firstChild).toHaveStyle({width: '40%'});
    });
});
