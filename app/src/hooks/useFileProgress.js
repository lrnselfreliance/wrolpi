import React from "react";
import {API_URI} from "../components/Vars";

/*
 * How far the user is through a file, and where to resume it (see wrolpi/files/progress.py).
 *
 * The server is the source of truth; its FileGroup JSON carries `progress` and `position`.  Every save is
 * also written to sessionStorage, because the final save sent while leaving a page can still be in flight
 * when the user comes straight back, and the server would then answer with an older position.  Whichever
 * of the two is newer wins.
 */

const HEARTBEAT_MS = 15_000;
const CACHE_PREFIX = 'wrolpi-progress:';

// Mirrors wrolpi/files/progress.py, so a position the server would discard is not resumed from the cache.
const FINISHED_PROGRESS = 0.95;
const MINIMUM_PROGRESS = 0.01;
const MINIMUM_SECONDS = 10;

function readCache(path) {
    try {
        const raw = window.sessionStorage.getItem(CACHE_PREFIX + path);
        return raw ? JSON.parse(raw) : null;
    } catch (e) {
        return null;
    }
}

function writeCache(path, entry) {
    try {
        window.sessionStorage.setItem(CACHE_PREFIX + path, JSON.stringify(entry));
    } catch (e) {
        // Storage is unavailable (private mode, quota); the server still has the position.
    }
}

/** Send progress to the server.  A final save uses a beacon, which survives the page closing. */
export function sendProgress(path, progress, position, final = false) {
    const url = `${API_URI}/files/progress`;
    const body = JSON.stringify({file: path, progress, position, final});
    if (final && navigator.sendBeacon) {
        if (navigator.sendBeacon(url, new Blob([body], {type: 'application/json'}))) {
            return;
        }
    }
    fetch(url, {method: 'POST', body, keepalive: true})
        .catch(e => console.error('Failed to save progress', e));
}

export function isResumable(progress, position) {
    if (!position || progress === null || progress === undefined) {
        return false;
    }
    if (progress >= FINISHED_PROGRESS || progress < MINIMUM_PROGRESS) {
        return false;
    }
    if (position.kind === 'time') {
        return position.seconds >= MINIMUM_SECONDS;
    }
    if (position.kind === 'page') {
        return position.page > 0;
    }
    return true;
}

/**
 * Where to resume `path`: the newer of the server's position (from `fileGroup`) and this tab's own.
 *
 * @returns {object|null} A position, or null to start from the beginning.
 */
export function getResumePosition(path, fileGroup) {
    if (!path) {
        return null;
    }
    let best = null;
    let bestTime = -1;
    if (fileGroup && fileGroup.progress !== null && fileGroup.progress !== undefined) {
        // A finished file has no position; when it was finished is when it was viewed.
        bestTime = fileGroup.position?.updated_at ?? (Date.parse(fileGroup.viewed) || 0);
        best = {progress: fileGroup.progress, position: fileGroup.position};
    }
    const cached = readCache(path);
    if (cached && cached.updated_at > bestTime) {
        best = cached;
    }
    return best && isResumable(best.progress, best.position) ? best.position : null;
}

/**
 * Save how far the user is through `path`.
 *
 * The viewer calls `report({progress, position})` as the user moves through the file; that is only
 * remembered.  It is sent every 15 seconds if it changed, and as a final save when `save(true)` is called
 * (pause, end), when the page is hidden or closed, and when `path` changes or the viewer unmounts.
 *
 * The last report is kept rather than read from the viewer at unmount, because by then React has detached
 * the viewer's elements.
 */
export function useFileProgress(path, {enabled = true} = {}) {
    const snapshotRef = React.useRef(null);
    const sentRef = React.useRef(null);

    const report = React.useCallback((snapshot) => {
        snapshotRef.current = snapshot;
    }, []);

    const save = React.useCallback((final = false) => {
        const snapshot = snapshotRef.current;
        if (!path || !enabled || !snapshot) {
            return;
        }
        const key = JSON.stringify(snapshot);
        if (!final && key === sentRef.current) {
            return;
        }
        sentRef.current = key;

        const updated_at = Date.now();
        const position = snapshot.position ? {...snapshot.position, updated_at} : null;
        writeCache(path, {progress: snapshot.progress, position, updated_at});
        sendProgress(path, snapshot.progress, position, final);
    }, [path, enabled]);

    React.useEffect(() => {
        if (!path || !enabled) {
            return;
        }
        // A new file starts with nothing to save.
        snapshotRef.current = null;
        sentRef.current = null;

        const interval = setInterval(() => save(false), HEARTBEAT_MS);
        const onVisibilityChange = () => {
            if (document.visibilityState === 'hidden') {
                save(true);
            }
        };
        const onPageHide = () => save(true);
        document.addEventListener('visibilitychange', onVisibilityChange);
        window.addEventListener('pagehide', onPageHide);
        return () => {
            clearInterval(interval);
            document.removeEventListener('visibilitychange', onVisibilityChange);
            window.removeEventListener('pagehide', onPageHide);
            save(true);
        };
    }, [path, enabled, save]);

    return {report, save};
}

/**
 * Track and resume a <video> or <audio>.  Spread the returned handlers onto the element.
 *
 * @param path The FileGroup's primary path, relative to the media directory.
 * @param fileGroup The FileGroup JSON, which holds the server's position.
 * @param startSeconds An explicit start (e.g. `?t=`), which wins over any saved position.
 */
export function useMediaProgress(path, fileGroup, {startSeconds = null, enabled = true} = {}) {
    const {report, save} = useFileProgress(path, {enabled});
    // The path whose position was restored; the element fires `loadedmetadata` again on some seeks.
    const restoredRef = React.useRef(null);

    const onLoadedMetadata = (e) => {
        if (!enabled || !path || restoredRef.current === path) {
            return;
        }
        restoredRef.current = path;
        const media = e.currentTarget;
        let seconds = startSeconds;
        if (seconds === null || seconds === undefined) {
            const position = getResumePosition(path, fileGroup);
            seconds = position && position.kind === 'time' ? position.seconds : null;
        }
        if (seconds && Number.isFinite(media.duration) && seconds < media.duration) {
            media.currentTime = seconds;
        }
    };

    const onTimeUpdate = (e) => {
        const media = e.currentTarget;
        if (!Number.isFinite(media.duration) || media.duration <= 0) {
            return;
        }
        report({
            progress: media.currentTime / media.duration,
            position: {kind: 'time', seconds: media.currentTime},
        });
    };

    const onPause = () => save(true);

    const onEnded = () => {
        report({progress: 1, position: null});
        save(true);
    };

    return {onLoadedMetadata, onTimeUpdate, onPause, onEnded};
}

/**
 * Where to resume `path`, decided once when it is opened.  Saves made while it is open do not move it,
 * so a viewer whose URL holds the start (the EPUB viewer) is not reloaded as the user reads.
 */
export function useResumePosition(path, fileGroup) {
    const resumeRef = React.useRef({path: null, position: null});
    if (path && fileGroup && resumeRef.current.path !== path) {
        resumeRef.current = {path, position: getResumePosition(path, fileGroup)};
    }
    return path && resumeRef.current.path === path ? resumeRef.current.position : null;
}

/**
 * Track and resume the EPUB viewer (public/epub/epub.html), which posts its location to this window.
 *
 * @returns {{iframeRef, resumeCfi}} Put `iframeRef` on the viewer's <iframe>, and pass `resumeCfi` to it as `cfi`.
 */
export function useEpubProgress(path, fileGroup, {enabled = true} = {}) {
    const trackedPath = enabled ? path : null;
    const {report} = useFileProgress(trackedPath);
    const resume = useResumePosition(trackedPath, fileGroup);
    const iframeRef = React.useRef(null);

    React.useEffect(() => {
        if (!trackedPath) {
            return;
        }
        const onMessage = (event) => {
            // Only our own viewer, in this iframe.
            if (event.origin !== window.location.origin || !iframeRef.current
                || event.source !== iframeRef.current.contentWindow) {
                return;
            }
            const {type, cfi, progress} = event.data || {};
            if (type !== 'wrolpi:epub-location' || typeof cfi !== 'string' || typeof progress !== 'number') {
                return;
            }
            report({progress, position: {kind: 'epub', cfi}});
        };
        window.addEventListener('message', onMessage);
        return () => window.removeEventListener('message', onMessage);
    }, [trackedPath, report]);

    return {iframeRef, resumeCfi: resume && resume.kind === 'epub' ? resume.cfi : null};
}

/**
 * Track and resume a paged viewer (comic books).
 *
 * @returns {{initialPage, onPageChange}} The 0-based page to open at, and a callback for each page shown.
 */
export function usePageProgress(path, fileGroup, {enabled = true} = {}) {
    const trackedPath = enabled ? path : null;
    const {report} = useFileProgress(trackedPath);
    const resume = useResumePosition(trackedPath, fileGroup);

    const onPageChange = React.useCallback((page, pageCount) => {
        if (pageCount > 0) {
            report({progress: (page + 1) / pageCount, position: {kind: 'page', page}});
        }
    }, [report]);

    return {initialPage: resume && resume.kind === 'page' ? resume.page : 0, onPageChange};
}
