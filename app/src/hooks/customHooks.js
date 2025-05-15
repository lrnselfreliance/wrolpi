import React, {useContext, useEffect, useRef, useState} from "react";
import {
    ApiDownError,
    createChannel,
    fetchDecoded,
    fetchDomains,
    fetchFilesProgress,
    filesSearch,
    getArchive,
    getChannel,
    getChannels,
    getConfigs,
    getDownloads,
    getFiles,
    getInventory,
    getOutdatedZims,
    getSettings,
    getStatistics,
    getStatus,
    getVideo,
    getVideoCaptions,
    getVideoComments,
    getVideosStatistics,
    postDumpConfig,
    postImportConfig,
    saveSettings,
    searchArchives,
    searchChannels,
    searchDirectories,
    searchVideos,
    searchZim,
    setHotspot,
    setThrottle,
    updateChannel,
} from "../api";
import {createSearchParams, useLocation, useSearchParams} from "react-router-dom";
import {enumerate, filterToMimetypes, humanFileSize, secondsToFullDuration} from "../components/Common";
import {QueryContext, SettingsContext, StatusContext} from "../contexts/contexts";
import {toast} from "react-semantic-toasts-2";
import {useSearch} from "../components/Search";
import _ from "lodash";
import {TagsSelector} from "../Tags";
import {useForm} from "./useForm";

const calculatePage = (offset, limit) => {
    return offset && limit ? Math.round((offset / limit) + 1) : 1;
}

const calculateTotalPages = (total, limit) => {
    // Return the total divided by the limit, but always at least 1.
    if (!total || !limit || total < limit) {
        return 1;
    }
    return Math.round(total / limit) + 1;
}

export const useRecurringTimeout = (callback, delay) => {
    const timer = useRef(null);

    useEffect(() => {
        const repeat = async () => {
            // Recursively call the callback.
            await callback();
            timer.current = window.setTimeout(repeat, delay);
        }

        // Call the repeating function instantly to fetch data fast.
        repeat();

        // Clear the timeout on unload.
        return () => clearTimeout(timer.current);
    }, [delay])
}

export const useLatestRequest = (delay = 300, defaultLoading = false) => {
    // A hook which ignores older requests and will only set `data` to the latest response's data.
    // usage: sendRequest(async () => await yourAPICall(...args));

    // The results from awaiting `fetchFunction`.
    const [data, setData] = React.useState(null);
    const latestRequestRef = React.useRef(0);
    const debounceTimerRef = React.useRef(null);
    // Loading while awaiting.
    const [loading, setLoading] = React.useState(defaultLoading);

    const sendRequest = React.useCallback((fetchFunction) => {
        if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current);
        }

        debounceTimerRef.current = setTimeout(async () => {
            setLoading(true);
            const requestId = ++latestRequestRef.current;

            try {
                const result = await fetchFunction();

                if (requestId === latestRequestRef.current) {
                    setData(result);
                }
            } catch (error) {
                console.error('Request failed:', error);
                setData(null);
            } finally {
                if (requestId === latestRequestRef.current) {
                    setLoading(false);
                }
            }
        }, delay);
    }, [delay]);

    return {data, sendRequest, loading};
};

const getSearchParamCopy = (searchParams) => {
    let copy = {};
    if (searchParams) {
        Array.from(searchParams.keys()).forEach(key => {
            const value = searchParams.getAll(key)
            copy[key] = value.length === 1 ? value[0] : value;
        })
    }
    copy = removeEmptyValues(copy);
    return copy;
}

const removeEmptyValues = (obj) => {
    Object.entries(obj).forEach(([k, v]) => {
        // Clear any empty values.
        if (v === null || v === undefined || (Array.isArray(v) && v.length === 0)) {
            delete obj[k];
        }
    });
    return obj
}


export const useQuery = () => {
    const location = useLocation();
    const [searchParams, setSearchParams] = useSearchParams();

    const updateQuery = (newParams, replace = false) => {
        // Update the old state with the new values.
        let newSearchParams = replace ?
            newParams
            : {...getSearchParamCopy(searchParams), ...newParams};
        newSearchParams = removeEmptyValues(newSearchParams);
        console.debug('useQuery.updateQuery', newSearchParams);
        setSearchParams(newSearchParams);
    };

    const getLocationStr = (newSearchParams, pathname) => {
        // Get the current location, but with new params appended.
        newSearchParams = removeEmptyValues({...getSearchParamCopy(searchParams), ...newSearchParams});
        const newQuery = createSearchParams(newSearchParams);
        return `${pathname || location.pathname}?${newQuery.toString()}`
    }

    return {searchParams, updateQuery, getLocationStr}
}


export const QueryProvider = (props) => {
    return <QueryContext.Provider value={useQuery()}>
        {props.children}
    </QueryContext.Provider>
}

export const useOneQuery = (name) => {
    const {searchParams, updateQuery} = React.useContext(QueryContext);
    const value = searchParams.get(name);

    const setValue = (newValue, replace = false) => {
        updateQuery({[name]: newValue}, replace);
    }

    return [value, setValue]
}

export const useAllQuery = (name) => {
    const {searchParams, updateQuery} = React.useContext(QueryContext);
    const value = searchParams.getAll(name);

    const setValue = (newValue, replace = false) => {
        updateQuery({[name]: newValue}, replace);
    }

    return [value, setValue]
}

export const useDomains = () => {
    const [domains, setDomains] = useState(null);
    const [total, setTotal] = useState(null);

    const _fetchDomains = async () => {
        setDomains(null);
        setTotal(0);
        try {
            let [domains, total] = await fetchDomains();
            setDomains(domains);
            setTotal(total);
        } catch (e) {
            setDomains(undefined); // Display error.
            setTotal(0);
        }
    }

    useEffect(() => {
        _fetchDomains();
    }, []);

    return [domains, total];
}

export const useArchive = (archiveId) => {
    const [archiveFileGroup, setArchiveFileGroup] = useState(null);
    const [history, setHistory] = useState(null);

    const fetchArchive = async () => {
        try {
            const {file_group, history} = await getArchive(archiveId);
            setArchiveFileGroup(file_group);
            setHistory(history);
        } catch (e) {
            console.error(e);
            setArchiveFileGroup(undefined);
        }
    }

    useEffect(() => {
        fetchArchive();
    }, [archiveId]);

    return {archiveFile: archiveFileGroup, history, fetchArchive};
}

export const usePages = (defaultLimit = 24, totalPages = 0) => {
    const {searchParams, updateQuery} = React.useContext(QueryContext);
    const offset = searchParams.get('o') || 0;
    const limit = parseInt(searchParams.get('l') || defaultLimit || 24);
    const [activePage, setActivePage] = useState(calculatePage(offset, limit));
    const [totalPages_, setTotalPages] = useState(totalPages);

    const setLimit = (value) => {
        setPage(1);
        updateQuery({l: value, o: null});
    }

    const setPage = (value) => {
        console.debug(`setPage ${value}`);
        setActivePage(value);
        value = value - 1;  // Page really starts as 0.
        updateQuery({o: value * limit});
    }

    const setTotal = (total) => {
        const newTotalPages = calculateTotalPages(total, limit);
        console.debug('newTotalPages', newTotalPages);
        setTotalPages(newTotalPages);
    }

    // Used for useEffect.
    const effect = JSON.stringify({offset, limit, activePage});

    return {offset, limit, setLimit, activePage, setPage, totalPages: totalPages_, setTotal, effect};
}

export const useSearchArchives = (defaultLimit) => {
    const {domain} = useSearchDomain();
    const {offset, limit, setLimit, activePage, setPage} = usePages(defaultLimit);
    const {searchParams, updateQuery} = React.useContext(QueryContext);
    const searchStr = searchParams.get('q') || '';
    const order = searchParams.get('order');
    const activeTags = searchParams.getAll('tag');
    const {view} = useSearchView();
    const headline = view === 'headline';

    const [archives, setArchives] = useState(null);
    const [totalPages, setTotalPages] = useState(0);

    const localSearchArchives = async () => {
        setArchives(null);
        setTotalPages(0);
        try {
            let [archives_, total] = await searchArchives(offset, limit, domain, searchStr, order, activeTags, headline);
            setArchives(archives_);
            setTotalPages(calculateTotalPages(total, limit));
        } catch (e) {
            console.error(e);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get archives',
                time: 5000,
            });
            setArchives(undefined); // Could not get Archives, display error.
        }
    }

    useEffect(() => {
        localSearchArchives();
    }, [searchStr, limit, domain, order, activePage, JSON.stringify(activeTags), headline]);

    const setSearchStr = (value) => {
        updateQuery({q: value, o: 0, order: undefined});
    }

    const setOrderBy = (value) => {
        setPage(1);
        updateQuery({order: value});
    }

    return {
        archives,
        limit,
        setLimit,
        offset,
        order,
        setOrderBy,
        totalPages,
        activePage,
        setPage,
        searchStr,
        setSearchStr,
        fetchArchives: localSearchArchives,
    }
}

export const useSearchVideos = (defaultLimit, channelId, order_by) => {
    const {searchParams, updateQuery} = React.useContext(QueryContext);
    const {offset, limit, setLimit, activePage, setPage} = usePages(defaultLimit);
    const searchStr = searchParams.get('q') || '';
    const order = searchParams.get('order') || order_by;
    const activeTags = searchParams.getAll('tag');
    const {view} = useSearchView();
    const headline = view === 'headline';
    const anyTag = searchParams.get('anyTag') === 'true';

    const [videos, setVideos] = useState(null);
    const [totalPages, setTotalPages] = useState(0);
    const [loading, setLoading] = useState(false);

    const localSearchVideos = async () => {
        setVideos(null);
        setLoading(true);
        setTotalPages(0);
        try {
            let [videos_, total] = await searchVideos(offset, limit, channelId, searchStr, order, activeTags, headline, anyTag);
            setVideos(videos_);
            setTotalPages(calculateTotalPages(total, limit));
        } catch (e) {
            console.error(e);
            setVideos(undefined);// Could not get Videos, display error.
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        localSearchVideos();
    }, [searchStr, limit, channelId, offset, order_by, JSON.stringify(activeTags), headline]);

    const setSearchStr = (value) => {
        updateQuery({q: value, o: 0, order: undefined});
    }

    const setOrderBy = (value) => {
        setPage(1);
        updateQuery({order: value});
    }

    return {
        videos,
        totalPages,
        limit,
        offset,
        order,
        searchStr,
        activePage,
        setPage,
        setLimit,
        setSearchStr,
        setOrderBy,
        fetchVideos: localSearchVideos,
        activeTags,
        loading,
    }
}

export const useVideo = (videoId) => {
    const [videoFile, setVideoFile] = useState(null);
    const [prevFile, setPrevFile] = useState(null);
    const [nextFile, setNextFile] = useState(null);

    const fetchVideo = async () => {
        if (videoId && videoFile && Number(videoFile.video.id) !== Number(videoId)) {
            // Video is changing.  Clear the old video before fetching.
            setVideoFile(null);
            setPrevFile(null);
            setNextFile(null);
        }
        try {
            const [v, p, n] = await getVideo(videoId);
            setVideoFile(v);
            setPrevFile(p);
            setNextFile(n);
        } catch (e) {
            console.error(e);
            setVideoFile(undefined);
            setPrevFile(undefined);
            setNextFile(undefined);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get the video',
                time: 5000,
            })
        }
    }

    useEffect(() => {
        fetchVideo();
    }, [videoId]);

    return {videoFile, prevFile, nextFile, fetchVideo};
}

export const useVideoExtras = (videoId) => {
    // Fetches extra data to display on a Video's page.
    const [comments, setComments] = useState(null);
    const [captions, setCaptions] = useState(null);

    const fetchComments = async () => {
        try {
            const result = await getVideoComments(videoId);
            setComments(result.comments);
        } catch (e) {
            console.error(e);
        }
    }

    const fetchCaptions = async () => {
        try {
            const result = await getVideoCaptions(videoId);
            setCaptions(result.captions);
        } catch (e) {
            console.error(e);
        }
    }

    useEffect(() => {
        if (videoId) {
            fetchComments();
            fetchCaptions();
        } else {
            setComments(null);
            setCaptions(null);
        }
    }, [videoId]);

    return {comments, captions}
}

export const useChannel = (channel_id) => {
    const emptyChannel = {
        name: '',
        directory: '',
        url: '',
        tag_name: null,
        download_missing_data: null,
    };

    const fetchChannel = async () => {
        if (!channel_id) {
            console.debug('Not fetching channel because no channel_id is provided');
            return;
        }
        const c = await getChannel(channel_id);
        // Prevent controlled to uncontrolled.
        c['url'] = c['url'] || '';
        c['download_frequency'] = c['download_frequency'] || '';
        c['match_regex'] = c['match_regex'] || '';
        c['download_missing_data'] = c['download_missing_data'] ?? true;
        return c;
    }

    const submitChannel = async () => {
        const body = {
            name: form.formData.name,
            directory: form.formData.directory,
            url: form.formData.url,
            download_missing_data: form.formData.download_missing_data,
        };

        if (channel_id) {
            // Can create a Channel with a Tag.
            body.tag_name = form.formData.tag_name;
            return await createChannel(body);
        } else {
            return await updateChannel(channel_id, body);
        }
    }

    const form = useForm({
        fetcher: fetchChannel,
        emptyFormData: emptyChannel,
        clearOnSuccess: false,
        submitter: submitChannel
    });

    React.useEffect(() => {
        // Channel may be gotten from Video data, fetch the Channel again.
        form.fetcher();
    }, [channel_id]);

    return {
        channel: form.formData,
        form,
        fetchChannel,
    };
}

export const useChannels = () => {
    const [channels, setChannels] = useState(null);

    const fetchChannels = async () => {
        setChannels(null);
        try {
            const c = await getChannels();
            setChannels(c);
        } catch (e) {
            console.error(e);
            setChannels(undefined); // Could not get Channels, display error.
        }
    }

    useEffect(() => {
        fetchChannels();
    }, []);

    return {channels, fetchChannels}
}

export const useSearchRecentFiles = () => {
    const [searchFiles, setSearchFiles] = useState(null);
    const [loading, setLoading] = useState(false);

    const localSearchFiles = async () => {
        setLoading(true);
        try {
            let [file_groups, total] = await filesSearch(
                null, 12, null, null, null, [], false,
                null, null, null, false, 'viewed');
            setSearchFiles(file_groups);
        } catch (e) {
            console.error(e);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get recent files',
                time: 5000,
            });
        } finally {
            setLoading(false);
        }
    }

    React.useEffect(() => {
        localSearchFiles();
    }, []);

    return {searchFiles, loading, fetchFiles: localSearchFiles};
}

export const useSearchFiles = (defaultLimit = 48, emptySearch = false, model) => {
    const {
        activeTags, anyTag,
        pages,
        searchStr,
        filter,
        model: model_,
        setSearchStr,
        months,
        dateRange,
    } = useSearch(defaultLimit, emptySearch, model);
    const {view} = useSearchView();

    const [searchFiles, setSearchFiles] = useState(null);
    const [loading, setLoading] = useState(false);
    const headline = view === 'headline';

    const localSearchFiles = async () => {
        if (!emptySearch && !searchStr && !activeTags) {
            return;
        }
        const mimetypes = filterToMimetypes(filter);
        setSearchFiles(null);
        let fromDate;
        let toDate;
        if (dateRange) {
            fromDate = dateRange[0];
            toDate = dateRange[1];
        }
        setLoading(true);
        console.log('localSearchFiles', fromDate, toDate, months);
        try {
            let [file_groups, total] = await filesSearch(
                pages.offset, pages.limit, searchStr, mimetypes, model || model_, activeTags, headline,
                months, fromDate, toDate, anyTag);
            setSearchFiles(file_groups);
            pages.setTotal(total);
        } catch (e) {
            pages.setTotal(0);
            console.error(e);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get files',
                time: 5000,
            });
        } finally {
            setLoading(false);
        }
    }

    // Only search after the user has stopped typing.  Estimates will always happen.
    const debouncedLocalSearchFiles = _.debounce(async () => {
        await localSearchFiles();
    }, 1000);

    useEffect(() => {
        if (searchStr || (activeTags && activeTags.length > 0)) {
            setLoading(true);
            debouncedLocalSearchFiles();
        }
        // Handle when this is unmounted.
        return () => debouncedLocalSearchFiles.cancel();
    }, [
        searchStr,
        pages.effect,
        filter,
        model,
        model_,
        JSON.stringify(activeTags),
        headline,
        JSON.stringify(months),
        JSON.stringify(dateRange),
        anyTag,
    ]);

    return {
        searchFiles,
        searchStr,
        filter,
        setSearchStr,
        pages,
        activeTags,
        loading,
    };
}

export const useBrowseFiles = () => {
    const [browseFiles, setBrowseFiles] = useState(null);
    const [openFolders, setOpenFolders] = useAllQuery('folders');

    const fetchFiles = async () => {
        try {
            const files = await getFiles(openFolders);
            setBrowseFiles(files);
        } catch (e) {
            console.error(e);
            setBrowseFiles(undefined); // Display error.
        }
    }

    useEffect(() => {
        fetchFiles();
    }, [JSON.stringify(openFolders)])

    return {browseFiles, openFolders, setOpenFolders, fetchFiles};
}

export const useFilesProgress = () => {
    const [progress, setProgress] = useState(null);

    const localFetchFilesProgress = async () => {
        try {
            let p = await fetchFilesProgress();
            setProgress(p);
        } catch (e) {
            setProgress(null);
            console.error(e);
        }
    }

    useEffect(() => {
        localFetchFilesProgress();
    }, []);

    return {progress, fetchFilesProgress: localFetchFilesProgress}
}

export const useFilesProgressInterval = () => {
    const {progress, fetchFilesProgress} = useFilesProgress();

    useRecurringTimeout(fetchFilesProgress, 1000 * 3);

    return {progress, fetchFilesProgress};
}

export const useHotspot = () => {
    const [on, setOn] = useState(null);
    const [inUse, setInUse] = useState(false);
    const {status} = useContext(StatusContext);
    // Hotspot is unsupported on Docker.
    const {dockerized, hotspot_ssid} = status;

    useEffect(() => {
        if (status && status['hotspot_status']) {
            const {hotspot_status} = status;
            if (hotspot_status === 'connected') {
                setOn(true);
                setInUse(false);
            } else if (hotspot_status === 'in_use') {
                setInUse(true);
                setOn(false);
            } else if (hotspot_status === 'disconnected' || hotspot_status === 'unavailable') {
                setOn(false);
                setInUse(false);
            } else {
                setOn(null);
            }
        }
    }, [status]);

    const localSetHotspot = async (on) => {
        setOn(null);
        await setHotspot(on);
    }

    return {on, inUse, hotspotSsid: hotspot_ssid, setOn, setHotspot: localSetHotspot, dockerized};
}

export const useDownloads = () => {
    const [onceDownloads, setOnceDownloads] = useState(null);
    const [recurringDownloads, setRecurringDownloads] = useState(null);
    const [pendingOnceDownloads, setPendingOnceDownloads] = useState(null);

    const fetchDownloads = async () => {
        try {
            const data = await getDownloads();
            setOnceDownloads(data['once_downloads']);
            setRecurringDownloads(data['recurring_downloads']);
            setPendingOnceDownloads(data['pending_once_downloads']);
        } catch (e) {
            console.error(e);
            // Display errors.
            setOnceDownloads(undefined);
            setRecurringDownloads(undefined);
            setPendingOnceDownloads(undefined);
        }
    }

    useRecurringTimeout(fetchDownloads, 3 * 1000);

    return {onceDownloads, recurringDownloads, pendingOnceDownloads, fetchDownloads}
}

export const useConfigs = () => {
    const [configs, setConfigs] = useState(null);
    const [loading, setLoading] = useState(false);

    const fetchConfigs = async () => {
        setLoading(true);
        console.log('fetching configs...');
        try {
            const data = await getConfigs();
            setConfigs(data['configs']);
            console.debug('fetching configs successful');
        } catch (e) {
            // Ignore SyntaxError because they happen when the API is down.
            if (!(e instanceof SyntaxError)) {
                console.error(e);
            }
            setConfigs(undefined);
        } finally {
            setLoading(false);
        }
    }

    const importConfig = async (fileName) => {
        try {
            await postImportConfig(fileName);
        } catch (e) {
            console.error(e);
        }
    }

    const saveConfig = async (fileName) => {
        try {
            await postDumpConfig(fileName);
        } catch (e) {
            console.error(e);
        }
    }

    return {configs, loading, fetchConfigs, importConfig, saveConfig}
}

export const useThrottle = () => {
    const [on, setOn] = useState(null);
    const {settings, fetchSettings} = React.useContext(SettingsContext);

    useEffect(() => {
        const status = settings['throttle_status'];
        if (status === 'powersave') {
            setOn(true);
        } else if (status === 'ondemand') {
            setOn(false);
        } else {
            setOn(null);
        }
    }, [JSON.stringify(settings)]);

    const localSetThrottle = async (on) => {
        setOn(null);
        await setThrottle(on);
        await fetchSettings();
    }

    return {on, setOn, setThrottle: localSetThrottle};
}

export const useSearchDirectories = (value) => {
    const [directoryName, setDirectoryName] = useState(value ?? '');
    const [directories, setDirectories] = useState(null);
    const [channelDirectories, setChannelDirectories] = useState(null);
    const [domainDirectories, setDomainDirectories] = useState(null);
    const [isDir, setIsDir] = useState(false);
    const [loading, setLoading] = useState(false);

    const localSearchDirectories = async () => {
        setLoading(true);
        try {
            const result = await searchDirectories(directoryName);
            setDirectories(result.directories);
            setChannelDirectories(result.channel_directories);
            setDomainDirectories(result.domain_directories);
            setIsDir(result.is_dir);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        localSearchDirectories();
    }, [directoryName]);

    useEffect(() => {
        // Directory value was changed above.
        setDirectoryName(value);
    }, [value]);

    return {
        directoryName,
        setDirectoryName,
        directories,
        loading,
        channelDirectories,
        domainDirectories,
        isDir,
    }
}

export const useSettings = () => {
    const [settings, setSettings] = useState({});
    const [pending, setPending] = useState(false);

    const fetchSettings = async () => {
        if (window.apiDown) {
            return;
        }
        setPending(true);
        try {
            setSettings(await getSettings())
        } catch (e) {
            setSettings({});
        } finally {
            setPending(false);
        }
    }

    useEffect(() => {
        fetchSettings();
    }, []);

    return {settings, pending, fetchSettings, saveSettings};
}

export const useSettingsInterval = () => {
    const {settings, pending, fetchSettings, saveSettings} = useSettings();

    useRecurringTimeout(fetchSettings, 1000 * 10);

    return {settings, pending, fetchSettings, saveSettings};
}

export const useMediaDirectory = () => {
    const {settings} = React.useContext(SettingsContext);

    return settings['media_directory'];
}

export const useStatus = () => {
    const [status, setStatus] = useState({});

    const fetchStatus = async () => {
        try {
            setStatus(await getStatus());
            window.apiDown = false;
        } catch (e) {
            if (e instanceof ApiDownError) {
                // API is down, do not log this error.
                window.apiDown = true;
                setStatus({});
                return;
            }
            // Ignore SyntaxError because they happen when the API is down.
            if (!(e instanceof SyntaxError)) {
                console.error(e);
            }
        }
    }

    useEffect(() => {
        // Used to tell other hooks to stop fetching intervals.
        window.apiDown = false;
    }, []);

    return {status, fetchStatus}
}

export const useStatusInterval = () => {
    const {status, fetchStatus} = useStatus();

    useRecurringTimeout(fetchStatus, 1000 * 3);

    return {status, fetchStatus};
}

export const StatusProvider = (props) => {
    const statusValue = useStatusInterval();
    const settingsValue = useSettingsInterval();

    const statusMemoValue = React.useMemo(() => statusValue, [statusValue]);
    const settingsMemoValue = React.useMemo(() => settingsValue, [settingsValue]);

    return <StatusContext.Provider value={statusMemoValue}>
        <SettingsContext.Provider value={settingsMemoValue}>
            {props.children}
        </SettingsContext.Provider>
    </StatusContext.Provider>
}

export const useStatusFlag = (flag) => {
    const {status} = useContext(StatusContext);
    return status?.flags?.[flag] || false;
}

export const useCPUTemperature = () => {
    const {status} = React.useContext(StatusContext);
    const temperature = status?.cpu_stats?.temperature || 0;
    const highTemperature = status?.cpu_stats?.high_temperature || 75;
    const criticalTemperature = status?.cpu_stats?.critical_temperature || 85;
    return {temperature, highTemperature, criticalTemperature}
}

export const useLoad = () => {
    const {status} = React.useContext(StatusContext);
    let minute_1 = status?.load_stats?.minute_1;
    let minute_5 = status?.load_stats?.minute_5;
    let minute_15 = status?.load_stats?.minute_15;
    let mediumLoad = false;
    let highLoad = false;
    let cores;

    if (status && status.cpu_stats) {
        // Medium load when 1/2 cores are busy, High load when 3/4+ cores are busy.
        cores = status.cpu_stats.cores;
        const quarter = cores / 4;
        if (cores && minute_1 >= (quarter * 3)) {
            highLoad = true;
        } else if (cores && minute_1 >= (quarter * 2)) {
            mediumLoad = true;
        }
    }

    return {minute_1, minute_5, minute_15, mediumLoad, highLoad, cores};
}

export const useIOStats = () => {
    const {status} = React.useContext(StatusContext);
    const percentIdle = status?.iostat_stats?.percent_idle;
    const percentIOWait = status?.iostat_stats?.percent_iowait;
    const percentNice = status?.iostat_stats?.percent_nice;
    const percentSteal = status?.iostat_stats?.percent_steal;
    const percentSystem = status?.iostat_stats?.percent_system;
    const percentUser = status?.iostat_stats?.percent_user;

    return {percentIdle, percentIOWait, percentNice, percentSteal, percentSystem, percentUser};
}

export const useMemoryStats = () => {
    const {status} = React.useContext(StatusContext);
    const total = status?.memory_stats?.total;
    const used = status?.memory_stats?.used;
    const free = status?.memory_stats?.free;
    const cached = status?.memory_stats?.cached;
    let percent;
    if (total && used) {
        percent = Math.round((used / total) * 100);
    }
    return {total, used, free, cached, percent}
}

export const usePowerStats = () => {
    const {status} = React.useContext(StatusContext);
    const underVoltage = status?.power_stats?.under_voltage;
    const overCurrent = status?.power_stats?.over_current;
    return {underVoltage, overCurrent};
}

export const useVideoStatistics = () => {
    const [statistics, setStatistics] = useState(null);

    const fetchStatistics = async () => {
        try {
            let stats = await getVideosStatistics();
            stats.videos.sum_duration = secondsToFullDuration(stats.videos.sum_duration);
            stats.videos.sum_size = humanFileSize(stats.videos.sum_size);
            stats.videos.max_size = humanFileSize(stats.videos.max_size);
            stats.historical.average_size = humanFileSize(stats.historical.average_size);
            setStatistics(stats);
        } catch (e) {
            console.error(e);
            setStatistics(undefined); // Display error.
        }
    }

    useEffect(() => {
        fetchStatistics();
    }, []);

    return {statistics, fetchStatistics}
}

export const useInventory = (inventoryId) => {
    const [byCategory, setByCategory] = useState();
    const [bySubcategory, setBySubcategory] = useState();
    const [byName, setByName] = useState();

    const fetchInventory = async () => {
        if (!inventoryId) {
            return
        }

        try {
            const inventory = await getInventory(inventoryId);
            setByCategory(enumerate(inventory['by_category']));
            setBySubcategory(enumerate(inventory['by_subcategory']));
            setByName(enumerate(inventory['by_name']));
        } catch (e) {
            console.error(e);
        }
    }

    useEffect(() => {
        fetchInventory();
    }, [inventoryId]);

    return {byCategory, bySubcategory, byName, fetchInventory}
}

export const useStatistics = () => {
    const [statistics, setStatistics] = useState();

    const fetchFileStatistics = async () => {
        try {
            const s = await getStatistics();
            setStatistics(s);
        } catch (e) {
            console.error(e);
            setStatistics(undefined);
        }
    }

    useEffect(() => {
        setStatistics({});
        fetchFileStatistics();
    }, []);

    return {statistics};
}

export const useSearchFilter = () => {
    const [filter, setFilter] = useOneQuery('filter');
    return {filter, setFilter}
}

export const useSearchDomain = () => {
    const [domains] = useDomains();
    const [domain, setDomain] = useOneQuery('domain');
    return {domain, domains, setDomain}
}

export const useSearchView = () => {
    const [view, setView] = useOneQuery('view');
    return {view, setView}
}

export const useSearchOrder = () => {
    const [sort, setSort] = useOneQuery('order');
    return {sort, setSort}
}

export const useSearchDate = () => {
    // Filters files using
    //      ?month=1&month=2&month=3
    // and
    //      ?fromDate=2023&toDate=2024
    const {searchParams, updateQuery} = React.useContext(QueryContext);
    const months = searchParams.getAll('month');
    let fromDate = searchParams.get('fromDate');
    let toDate = searchParams.get('toDate');
    fromDate = fromDate ? parseInt(fromDate) : null;
    toDate = toDate ? parseInt(toDate) : null;

    const clearDate = () => {
        console.log('clearDate');
        updateQuery({fromDate: null, toDate: null, month: null, 'o': 0});
    }

    const setDates = (newFromDate, newToDate, newMonths) => {
        console.log('setDates', newFromDate, newToDate, newMonths);
        updateQuery({fromDate: newFromDate, toDate: newToDate, month: newMonths, 'o': 0});
    }

    const anySearch = (months && months.length > 0) || (fromDate !== null || toDate !== null);
    const isEmpty = !anySearch;

    return {dateRange: [fromDate, toDate], setDates, months, clearDate, isEmpty}
}

export const useUploadFile = () => {
    const [files, setFiles] = useState([]);
    const [progresses, setProgresses] = useState({});
    const [destination, setDestination] = useState('');
    const [tagNames, setTagNames] = React.useState([]);
    const [overwrite, setOverwrite] = React.useState(false);
    const [totalSize, setTotalSize] = useState(0);
    const [uploadedSize, setUploadedSize] = useState(0);
    const [overallProgress, setOverallProgress] = useState(0);
    const [inProgress, setInProgress] = useState(false);

    const handleProgress = (name, chunk, totalChunks, status, type) => {
        const percent = Math.round((100 * chunk) / totalChunks);
        const newProgress = {[name]: {percent, status, type}};

        setProgresses(prevState => {
            const updatedProgresses = {...prevState, ...newProgress};

            // Calculate total uploaded size based on all files' progress
            let totalUploaded = 0;
            files.forEach(file => {
                const fileProgress = updatedProgresses[file.name];
                if (fileProgress) {
                    const chunkSize = 10 * 1024 * 1024; // 10MB - same as in doUpload
                    const fileSize = file.size;
                    const totalFileChunks = Math.ceil(fileSize / chunkSize);

                    // For completed files, count the full size
                    if (fileProgress.status === 'complete' || fileProgress.status === 'conflicting') {
                        totalUploaded += fileSize;
                    }
                    // For files in progress, count the completed chunks
                    else if (fileProgress.percent > 0) {
                        const completedChunks = Math.floor((fileProgress.percent / 100) * totalFileChunks);
                        const completedSize = Math.min(completedChunks * chunkSize, fileSize);
                        totalUploaded += completedSize;
                    }
                }
            });

            setUploadedSize(totalUploaded);

            if (totalSize > 0) {
                const newOverallProgress = Math.round((totalUploaded / totalSize) * 100);
                setOverallProgress(newOverallProgress);
            }

            return updatedProgresses;
        });
    }

    const handleFilesChange = (newFiles) => {
        let newProgresses = {};
        let newTotalSize = 0;

        newFiles.forEach(file => {
            newProgresses = {...newProgresses, [file.name]: {percent: 0, status: 'pending'}};
            newTotalSize += file.size;
        });

        setProgresses(newProgresses);
        setFiles(newFiles);
        setTotalSize(newTotalSize);
        setUploadedSize(0);
        setOverallProgress(0);
    }

    const doUpload = async () => {
        if (!files || files.length === 0 || !destination) {
            return;
        }

        setInProgress(true);

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            console.log(`Uploading file:`, file.path);

            const chunkNum = 0;
            const chunkSize = 10 * 1024 * 1024; // 10MB
            const totalChunks = Math.ceil(file.size / chunkSize);
            const tries = 0;
            const maxTries = 20;

            // Start recursive function to upload the file and wait for it to complete
            // before moving to the next file
            try {
                await new Promise((resolve, reject) => {
                    const uploadNextChunk = async (currentChunkNum, currentTries) => {
                        if (currentTries > maxTries) {
                            console.error(`Exceeded max tries ${maxTries}`);
                            reject(new Error(`Exceeded max tries ${maxTries}`));
                            return;
                        }

                        const start = currentChunkNum * chunkSize;
                        const end = Math.min(start + chunkSize, file.size);
                        const chunk = file.slice(start, end);

                        const formData = new FormData();
                        formData.append('chunkNumber', currentChunkNum.toString());
                        formData.append('filename', file.path);
                        formData.append('totalChunks', totalChunks.toString());
                        formData.append('destination', destination);
                        formData.append('mkdir', 'true');
                        if (overwrite) {
                            formData.append('overwrite', 'true');
                        }
                        formData.append('chunkSize', chunk.size.toString());
                        formData.append('chunk', chunk);
                        for (let j = 0; j < tagNames.length; j++) {
                            formData.append('tagNames', tagNames[j]);
                        }

                        console.debug(`file upload: tries=${currentTries} chunkNum=${currentChunkNum} totalChunks=${totalChunks} chunkSize=${chunk.size} destination=${destination} tagNames=${tagNames}`);

                        // Create a new XMLHttpRequest for each chunk to avoid InvalidStateError
                        const chunkXhr = new XMLHttpRequest();
                        chunkXhr.open('POST', '/api/files/upload', true);

                        chunkXhr.onreadystatechange = async () => {
                            if (chunkXhr.readyState === 4) {
                                if (chunkXhr.status === 200 || chunkXhr.status === 416) {
                                    const data = JSON.parse(chunkXhr.responseText);
                                    handleProgress(file.name, currentChunkNum, totalChunks, 'pending', file.type);
                                    const expectedChunk = data['expected_chunk'];
                                    if (chunkXhr.status === 416) {
                                        console.warn(`Server requested a different chunk ${currentChunkNum}`);
                                        uploadNextChunk(expectedChunk, currentTries + 1);
                                    } else {
                                        console.debug(`Uploading of chunk ${currentChunkNum} succeeded, got request for chunk ${expectedChunk}`);
                                        // Success, reset tries.
                                        uploadNextChunk(expectedChunk, 0);
                                    }
                                } else if (chunkXhr.status === 201) {
                                    handleProgress(file.name, totalChunks, totalChunks, 'complete', file.type);
                                    console.info(`Uploading of ${file.path} completed.`);
                                    resolve(); // File upload completed successfully
                                } else if (chunkXhr.status === 400) {
                                    handleProgress(file.name, totalChunks, totalChunks, 'conflicting', file.type);
                                    const data = JSON.parse(chunkXhr.responseText);
                                    if (data['code'] === 'FILE_UPLOAD_FAILED') {
                                        console.error('File already exists. Giving up.');
                                        reject(new Error('File already exists'));
                                    }
                                } else {
                                    handleProgress(file.name, totalChunks, totalChunks, 'failed', file.type);
                                    console.error(`Failed to upload chunk ${currentChunkNum}. Giving up.`);
                                    reject(new Error(`Failed to upload chunk ${currentChunkNum}`));
                                }
                            }
                        };

                        chunkXhr.send(formData);
                    };

                    // Start uploading the first chunk
                    uploadNextChunk(chunkNum, tries);
                });
            } catch (error) {
                console.error(`Error uploading file ${file.path}:`, error);
                // Continue with the next file even if this one failed
            }
        }

        // Clear form after upload.
        setFiles([]);
        setInProgress(false);
    }

    const doClear = () => {
        setFiles([]);
        setProgresses({});
        setTotalSize(0);
        setUploadedSize(0);
        setOverallProgress(0);
        setInProgress(false);
    }

    useEffect(() => {
        doUpload()
    }, [JSON.stringify(files)]);

    const tagsSelector = <TagsSelector selectedTagNames={tagNames} onChange={(i,) => setTagNames(i)}/>;

    return {
        destination, setDestination,
        doClear,
        doUpload,
        files,
        progresses,
        setFiles: handleFilesChange,
        tagNames,
        tagsSelector,
        overwrite, setOverwrite,
        overallProgress,
        totalSize,
        uploadedSize,
        inProgress,
    }
}

export const useSearchZim = (searchStr, zimId, active, activeTags, defaultLimit = 10) => {
    const [zim, setZim] = useState(null);
    const pages = usePages(defaultLimit);
    const [loading, setLoading] = useState(false);

    const localFetchSearch = async () => {
        if (!active) {
            return;
        }
        setLoading(true);
        try {
            const zim = await searchZim(pages.offset, pages.limit, searchStr, zimId, activeTags);
            setZim(zim);
            pages.setTotal(zim.estimate);
        } catch (e) {
            pages.setTotal(0);
            console.error(`Failed to search Zim ${zimId}`);
            console.error(e);
        }
        setLoading(false);
    }

    useEffect(() => {
        localFetchSearch();
    }, [active, searchStr, JSON.stringify(activeTags), pages.effect]);

    return {zim, fetchSearch: localFetchSearch, pages, loading}
}

export const useOutdatedZims = () => {
    const [outdated, setOutdated] = useState(null);
    const [current, setCurrent] = useState(null);

    const localFetchOutdatedZims = async () => {
        const zims = await getOutdatedZims();
        setOutdated(zims['outdated']);
        setCurrent(zims['current']);
    }

    useEffect(() => {
        localFetchOutdatedZims();
    }, []);

    return {outdated, current}
}

export const useVINDecoder = (defaultVINNumber = '') => {
    const [value, setValue] = useState(defaultVINNumber);
    // The response vin from the API.
    const [vin, setVin] = useState(null);

    const localFetchDecoded = async () => {
        if (!value) {
            return;
        }

        try {
            const vin = await fetchDecoded(value);
            setVin(vin);
        } catch (e) {
            console.error('Failed to decode VIN number');
            setVin(null);
        }
    }

    useEffect(() => {
        localFetchDecoded();
    }, [value]);

    return {value, setValue, vin}
}

export const useWROLMode = () => {
    // Returns the current boolean WROL Mode, during fetch this returns null.
    const {status} = useContext(StatusContext);
    return status ? status.wrol_mode : null;
}

export const useDockerized = () => {
    const {status} = React.useContext(StatusContext);
    return status && status['dockerized'] === true;
}

export const useCalcQuery = () => {
    const [calc, setCalc] = useOneQuery('calc');
    return [calc, setCalc]
}

export const useSearchChannels = (defaultTagNames) => {
    const [tagNames, setTagNames] = useState(defaultTagNames || []);
    const [channels, setChannels] = useState([]);
    const [loading, setLoading] = useState(false);

    const localSearchChannels = async () => {
        setLoading(true);
        try {
            const {channels: newChannels} = await searchChannels(tagNames);
            setChannels(newChannels);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        localSearchChannels();
    }, [tagNames]);

    return {
        tagNames,
        setTagNames,
        channels,
        loading,
    }
}
