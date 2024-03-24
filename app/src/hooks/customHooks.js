import React, {useContext, useEffect, useRef, useState} from "react";
import {
    fetchDecoded,
    fetchDomains,
    fetchFilesProgress,
    getArchive,
    getChannel,
    getChannels,
    getDirectories,
    getDownloads,
    getFiles,
    getInventory,
    getOutdatedZims,
    getSettings,
    getStatistics,
    getStatus,
    getVideo,
    getVideosStatistics,
    searchArchives,
    searchDirectories,
    searchVideos,
    searchZim,
    setHotspot,
    setThrottle,
} from "../api";
import {createSearchParams, useLocation, useNavigate, useSearchParams} from "react-router-dom";
import {defaultFileOrder, enumerate, humanFileSize, secondsToFullDuration} from "../components/Common";
import {QueryContext, SearchGlobalContext, SettingsContext, StatusContext,} from "../contexts/contexts";
import {toast} from "react-semantic-toasts-2";

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
        // Delete any items that have null/undefined/empty-array values.
        if (v === null || v === undefined || (Array.isArray(v) && v.length === 0)) {
            delete obj[k];
        }
    });
    return obj
}


export function QueryProvider({...props}) {
    const value = useQuery();
    return <QueryContext.Provider value={value}>
        {props.children}
    </QueryContext.Provider>
}

export const useQuery = () => {
    // Used to control URL query parameters.

    const location = useLocation();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const [state, setState] = React.useState(getSearchParamCopy(searchParams));

    React.useEffect(() => {
        // Always copy URL to state.  URL may change outside useQuery.
        setState(getSearchParamCopy(searchParams));
    }, [JSON.stringify(location)]);

    const updateQuery = (newParams, replace = false) => {
        // Update the old state with the new values.
        setState(oldState => {
            console.debug(`updateParams replace=${replace}`, newParams, oldState);
            const newState = replace ?
                removeEmptyValues(newParams) : removeEmptyValues({...oldState, ...newParams});
            setSearchParams(newState);
            return newState;
        });
    };

    const queryNavigate = (newSearchParams, pathname, replace = false) => {
        // Navigate to a new page, but keep the state in sync with the params.
        newSearchParams = replace ?
            removeEmptyValues(newSearchParams) : removeEmptyValues({...state, ...newSearchParams});
        const newQuery = createSearchParams(newSearchParams);
        const newLocation = `${pathname || location.pathname}?${newQuery.toString()}`;
        navigate(newLocation);
    }

    const clearQuery = () => setState({});

    return {searchParams, setSearchParams, updateQuery, clearQuery, queryNavigate}
}

export const useOneQuery = (name, defaultValue = null, type) => {
    const {searchParams, updateQuery} = React.useContext(QueryContext);
    let value = searchParams.get(name) || defaultValue;
    if (type && value) {
        value = type(value)
    }

    const setValue = (newValue, replace = false) => {
        updateQuery({[name]: newValue}, replace);
    }

    const clearValue = (replace = false) => {
        setValue(defaultValue, replace);
    }

    return [value, setValue, clearValue]
}

export const useAllQuery = (name) => {
    const {searchParams, updateQuery} = React.useContext(QueryContext);
    const value = searchParams.getAll(name);

    const setValue = (newValue, replace = false) => {
        updateQuery({[name]: newValue}, replace);
    }

    const clearValue = (replace = false) => {
        updateQuery({[name]: null}, replace);
    }

    return [value, setValue, clearValue]
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
            const [file_group, history] = await getArchive(archiveId);
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

export const usePages = () => {
    // o=0&l=24
    const [offset, setOffset, clearOffset] = useOneQuery('o', 0);
    const [limit, setLimit, clearLimit] = useOneQuery('l', 24, parseInt);
    const activePage = calculatePage(offset, limit);
    // This is set by the caller.
    const [totalPages_, setTotalPages] = useState(1);

    const setPage = (value) => {
        console.debug(`setPage ${value}`);
        value = value - 1;  // Page really starts as 0.
        setOffset(value * limit);
    }

    const localSetLimit = (value) => {
        setLimit(value);
        setOffset(null);
    }

    const setTotal = (total) => {
        const newTotalPages = calculateTotalPages(total, limit);
        console.debug('newTotalPages', newTotalPages);
        setTotalPages(newTotalPages);
    }

    // Used for useEffect.
    const effect = JSON.stringify({offset, limit, activePage});

    const clearPages = () => {
        clearOffset();
        clearLimit();
    }

    return {
        offset,
        limit,
        setLimit: localSetLimit,
        activePage,
        setPage,
        totalPages: totalPages_,
        setTotal,
        effect,
        clearPages
    };
}

export const useSearchArchives = () => {
    const {
        pages,
        searchStr, setSearchStr, clearSearch,
        pendingSearchStr, setPendingSearchStr,
        activeTags,
        view,
        order,
        effect,
        submitSearch,
    } = React.useContext(SearchGlobalContext);

    const {domain} = useSearchDomain();
    const headline = view === 'headline';

    const [loading, setLoading] = useState(false);
    const [archives, setArchives] = useState(null);
    const [totalPages, setTotalPages] = useState(0);

    const localSearchArchives = async () => {
        setLoading(true);
        setArchives(null);
        setTotalPages(0);
        try {
            let [archives_, total] = await searchArchives(
                pages.offset,
                pages.limit,
                domain,
                searchStr,
                order || defaultFileOrder,
                activeTags,
                headline,
            );
            setArchives(archives_);
            setTotalPages(calculateTotalPages(total, pages.limit));
        } catch (e) {
            console.error(e);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get archives',
                time: 5000,
            });
            setArchives(undefined); // Could not get Archives, display error.
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        // Search archives again whenever search params change.
        localSearchArchives();
    }, [effect, domain]);

    return {
        loading,
        archives,
        limit: pages.limit,
        setLimit: pages.setLimit,
        offset: pages.offset,
        order,
        setOrderBy: pages.setOrder,
        totalPages,
        activePage: pages.activePage,
        setPage: pages.setPage,
        searchStr, setSearchStr,
        pendingSearchStr, setPendingSearchStr,
        fetchArchives: localSearchArchives,
        submitSearch, clearSearch,
    }
}

export const useSearchVideos = (defaultLimit, channelId) => {
    const {
        pages,
        searchStr, setSearchStr, clearSearch,
        pendingSearchStr, setPendingSearchStr,
        activeTags,
        view,
        order,
        effect,
        submitSearch,
    } = React.useContext(SearchGlobalContext);

    const headline = view === 'headline';

    const [videos, setVideos] = useState(null);

    const localSearchVideos = async () => {
        setVideos(null);
        try {
            let [videos_, total] = await searchVideos(
                pages.offset,
                pages.limit,
                channelId,
                searchStr,
                order || defaultFileOrder,
                activeTags,
                headline,
            );
            setVideos(videos_);
            pages.setTotal(total);
        } catch (e) {
            console.error(e);
            setVideos(undefined);// Could not get Videos, display error.
        }
    }

    useEffect(() => {
        // Search videos again whenever search params change.
        localSearchVideos();
    }, [effect, channelId]);

    return {
        videos,
        totalPages: pages.totalPages,
        limit: pages.limit,
        activePage: pages.activePage,
        setPage: pages.setPage,
        setLimit: pages.setLimit,
        setOrderBy: pages.setOrder,
        offset: pages.offset,
        order,
        searchStr, setSearchStr, clearSearch, submitSearch,
        pendingSearchStr, setPendingSearchStr,
        fetchVideos: localSearchVideos,
        activeTags,
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

export const useChannel = (channel_id) => {
    const emptyChannel = {
        name: '',
        directory: '',
        mkdir: false,
        url: '',
        download_frequency: '',
        match_regex: '',
    };
    const [fetched, setFetched] = useState(false);
    const [channel, setChannel] = useState(emptyChannel);
    const [original, setOriginal] = useState({});

    const localGetChannel = async () => {
        if (channel_id) {
            try {
                const c = await getChannel(channel_id);
                // Prevent controlled to uncontrolled.
                c['url'] = c['url'] || '';
                c['download_frequency'] = c['download_frequency'] || '';
                c['match_regex'] = c['match_regex'] || '';
                setChannel(c);
                setOriginal(c);
                setFetched(true);
            } catch (e) {
                console.error(e);
                toast({
                    type: 'error',
                    title: 'Unexpected server response',
                    description: 'Could not get Channel',
                    time: 5000,
                });
            }
        } else {
            setChannel(emptyChannel);
        }
    }

    useEffect(() => {
        localGetChannel();
    }, [channel_id])

    const changeValue = (name, value) => {
        setChannel({...channel, [name]: value});
    }

    return {channel, changeValue, original, fetched, fetchChannel: localGetChannel};
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
    const {status} = useContext(StatusContext);
    // Hotspot is unsupported on Docker.
    const {dockerized} = status;

    useEffect(() => {
        if (status && status['hotspot_status']) {
            const {hotspot_status} = status;
            if (hotspot_status === 'connected') {
                setOn(true);
            } else if (hotspot_status === 'disconnected' || hotspot_status === 'unavailable') {
                setOn(false);
            } else {
                setOn(null);
            }
        }
    }, [status]);

    const localSetHotspot = async (on) => {
        setOn(null);
        await setHotspot(on);
    }

    return {on, setOn, setHotspot: localSetHotspot, dockerized};
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

export const useDirectories = (defaultDirectory) => {
    const [directories, setDirectories] = useState();
    const [directory, setDirectory] = useState(defaultDirectory);
    const [exists, setExists] = useState();
    const [isDir, setIsDir] = useState();
    const [isFile, setIsFile] = useState();

    const fetchDirectories = async () => {
        if (defaultDirectory && directory === '') {
            setDirectory(defaultDirectory);
        }
        try {
            const {directories, is_dir, exists_, is_file} = await getDirectories(directory);
            setDirectories(directories);
            setIsDir(is_dir);
            setExists(exists_);
            setIsFile(is_file);
        } catch (e) {
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get directories',
                time: 5000,
            });
        }
    }

    useEffect(() => {
        fetchDirectories();
    }, [directory, defaultDirectory]);

    return {directory, directories, setDirectory, exists, isDir, isFile};
}

export const useSearchDirectories = (value) => {
    const [directoryName, setDirectoryName] = useState(value ?? '');
    const [directories, setDirectories] = useState(null);
    const [channelDirectories, setChannelDirectories] = useState(null);
    const [domainDirectories, setDomainDirectories] = useState(null);
    const [loading, setLoading] = useState(false);

    const localSearchDirectories = async () => {
        setLoading(true);
        try {
            const {directories: dirs, channel_directories, domain_directories} = await searchDirectories(directoryName);
            setDirectories(dirs);
            setChannelDirectories(channel_directories);
            setDomainDirectories(domain_directories);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        localSearchDirectories();
    }, [directoryName]);

    return {
        directoryName,
        setDirectoryName,
        directories,
        loading,
        channelDirectories,
        domainDirectories
    }
}

export const useSettings = () => {
    const [settings, setSettings] = useState({});

    const fetchSettings = async () => {
        try {
            setSettings(await getSettings())
        } catch (e) {
            setSettings({});
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get directories',
                time: 5000,
            });
        }
    }

    return {settings, fetchSettings};
}

export const useMediaDirectory = () => {
    const {settings} = React.useContext(SettingsContext);

    return settings['media_directory'];
}

export const useSettingsInterval = () => {
    const {settings, fetchSettings} = useSettings();

    useRecurringTimeout(fetchSettings, 1000 * 10);

    return {settings, fetchSettings};
}

export const useStatus = () => {
    const [status, setStatus] = useState({});

    const fetchStatus = async () => {
        try {
            const s = await getStatus();
            setStatus(s);
        } catch (e) {
            console.error(e);
        }
    }

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
    return status && status['flags'] && status['flags'].indexOf(flag) >= 0;
}

export const useCPUTemperature = () => {
    const {status} = React.useContext(StatusContext);
    let temperature = 0;
    let highTemperature = 75;
    let criticalTemperature = 85;

    if (status && status['cpu_info']) {
        temperature = status['cpu_info']['temperature'];
        highTemperature = status['cpu_info']['high_temperature'];
        criticalTemperature = status['cpu_info']['critical_temperature'];
    }

    return {temperature, highTemperature, criticalTemperature}
}

export const useLoad = () => {
    const {status} = React.useContext(StatusContext);
    let minute_1;
    let minute_5;
    let minute_15;
    let mediumLoad = false;
    let highLoad = false;
    let cores;

    if (status && status['load']) {
        minute_1 = status['load']['minute_1'];
        minute_5 = status['load']['minute_5'];
        minute_15 = status['load']['minute_15'];

        cores = status['cpu_info']['cores'];
        const quarter = cores / 4;
        if (cores && minute_1 >= (quarter * 3)) {
            highLoad = true;
        } else if (cores && minute_1 >= (quarter * 2)) {
            mediumLoad = true;
        }
    }

    return {minute_1, minute_5, minute_15, mediumLoad, highLoad, cores};
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
    // Filter implies more than one mimetype.  See `filterToMimetypes`
    // video, image, etc.
    const {updateQuery} = React.useContext(QueryContext);
    const [filter, setFilter] = useOneQuery('filter');
    const localSetFilter = (newFilter) => {
        // Set new search string, go back to first page.
        updateQuery({'filter': newFilter, 'o': 0});
    }
    const clearFilter = () => setFilter(null);
    return {filter, setFilter: localSetFilter, clearFilter}
}

export const useSearchDomain = () => {
    const [domains] = useDomains();
    const [domain, setDomain] = useOneQuery('domain');
    const clearDomain = () => setDomain(null);
    return {domain, domains, setDomain, clearDomain}
}

export const useSearchModel = () => {
    // archive/video/ebook/etc.
    const [model, setModel] = useOneQuery('model');
    const clearModel = () => setModel(null);
    return {model, setModel, clearModel}
}

export const useSearchView = () => {
    // view=...
    const [view, setView] = useOneQuery('view');
    const clearView = () => setView(null);
    return {view, setView, clearView}
}

export const useSearchOrder = () => {
    // o=...
    let [order, setOrder] = useOneQuery('order');
    const clearOrder = () => setOrder(null);
    return {order, setOrder, clearOrder}
}

export const useSearchStr = () => {
    const {searchParams, updateQuery, clearQuery, queryNavigate} = React.useContext(QueryContext);
    const searchStr = searchParams.get('q');
    // What the user is typing, can be submitted later.
    const [pendingSearchStr, setPendingSearchStr] = React.useState(searchStr);

    const setSearchStr = (newSearchStr) => {
        // Set new search string, go back to first page.
        updateQuery({'q': newSearchStr, 'o': 0});
    }

    const clearSearchStr = () => {
        setPendingSearchStr(''); // Use empty string for text inputs.
        clearQuery(); // Clear any URL parameters that may exist.
    }

    const submitSearch = (newSearchStr) => setSearchStr(newSearchStr || pendingSearchStr);

    // Submit pending search string, navigate to first page of results on /search.
    const submitGlobalSearch = (newSearchStr) => queryNavigate({q: newSearchStr || pendingSearchStr, o: 0}, '/search');

    return {
        searchStr,
        setSearchStr,
        clearSearchStr,
        pendingSearchStr,
        setPendingSearchStr,
        submitSearch,
        submitGlobalSearch,
        searchParams,
    }
}

export const useSearchTags = () => {
    // tag=Name1&tag=Name2
    const [activeTags, setSearchTags] = useAllQuery('tag');

    const addTag = (name) => setSearchTags([...activeTags, name]);
    const removeTag = (name) => setSearchTags(activeTags.filter(i => i !== name));
    const clearTags = () => setSearchTags([]);

    return {activeTags, setSearchTags, addTag, removeTag, clearTags}
}

export const useSearchMonths = () => {
    const {searchParams, updateQuery} = React.useContext(QueryContext);
    const months = searchParams.getAll('month');
    const [pendingMonths, setPendingMonths] = React.useState(months);
    const setMonths = (newMonths) => {
        // Set new months, go back to first page.
        updateQuery({'month': newMonths, 'o': null});
    };

    const clearMonths = () => {
        setMonths([]);
        setPendingMonths([]);
    }

    return {months, setMonths, pendingMonths, setPendingMonths, clearMonths}
}


export const useSearchDateRange = () => {
    // fromDate=...&toDate=...
    const {searchParams, updateQuery} = React.useContext(QueryContext);

    const emptyDateRange = [null, null];
    let fromDate = searchParams.get('fromDate');
    let toDate = searchParams.get('toDate');
    fromDate = fromDate ? parseInt(fromDate) : null;
    toDate = toDate ? parseInt(toDate) : null;
    const [pendingDateRange, setPendingDateRange] = React.useState([fromDate, toDate]);

    const setDateRange = ([newFromDate, newToDate]) => {
        // Set new date range, go back to first page.
        updateQuery({fromDate: newFromDate, toDate: newToDate, 'o': 0});
    }

    const clearDateRange = () => {
        console.log('clearDateRange');
        setDateRange(emptyDateRange);
        setPendingDateRange(emptyDateRange);
    }

    return {dateRange: [fromDate, toDate], setDateRange, pendingDateRange, setPendingDateRange, clearDateRange}
}

export const useUploadFile = () => {
    const [files, setFiles] = useState([]);
    const [progresses, setProgresses] = useState({});
    const [destination, setDestination] = useState('');

    const handleProgress = (name, chunk, totalChunks, status, type) => {
        const percent = Math.round((100 * chunk) / totalChunks);
        const newProgress = {[name]: {percent, status, type}};
        setProgresses(prevState => ({...prevState, ...newProgress}));
    }

    const handleFilesChange = (newFiles) => {
        let newProgresses = {};
        newFiles.map(i => {
            newProgresses = {...newProgresses, [i['name']]: {percent: 0, status: 'pending'}};
        });
        setProgresses(newProgresses);
        setFiles(newFiles);
    }

    const uploadChunk = async (file, chunkNum, chunkSize, totalChunks, tries, maxTries) => {
        if (tries > maxTries) {
            console.error(`Exceeded max tries ${maxTries}`);
        }

        const start = chunkNum * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        // The bytes that we will send.
        const chunk = file.slice(start, end);

        const formData = new FormData();
        formData.append('chunkNumber', chunkNum.toString());
        formData.append('filename', file.path);
        formData.append('totalChunks', totalChunks.toString());
        formData.append('destination', destination);
        // Send the size that we're actually sending.
        formData.append('chunkSize', chunk.size.toString());
        formData.append('chunk', chunk);

        console.debug(`file upload: tries=${tries} chunkNum=${chunkNum} totalChunks=${totalChunks} chunkSize=${chunk.size} destination=${destination}`);

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/files/upload', true);
        xhr.onreadystatechange = async () => {
            if (xhr.readyState === 4) {
                if (xhr.status === 200 || xhr.status === 416) {
                    const data = JSON.parse(xhr.responseText);
                    handleProgress(file.name, chunkNum, totalChunks, 'pending', file.type);
                    const expectedChunk = data['expected_chunk'];
                    if (xhr.status === 416) {
                        console.warn(`Server requested a different chunk ${chunkNum}`);
                        await uploadChunk(file, expectedChunk, chunkSize, totalChunks, tries + 1, maxTries);
                    } else {
                        console.debug(`Uploading of chunk ${chunkNum} succeeded, got request for chunk ${chunkNum}`);
                        // Success, reset tries.
                        await uploadChunk(file, expectedChunk, chunkSize, totalChunks, 0, maxTries);
                    }
                } else if (xhr.status === 201) {
                    handleProgress(file.name, totalChunks, totalChunks, 'complete', file.type);
                    console.info(`Uploading of ${file.path} completed.`);
                } else if (xhr.status === 400) {
                    handleProgress(file.name, totalChunks, totalChunks, 'conflicting', file.type);
                    const data = JSON.parse(xhr.responseText);
                    if (data['code'] === 'FILE_UPLOAD_FAILED') {
                        console.error('File already exists. Giving up.');
                    }
                } else {
                    handleProgress(file.name, totalChunks, totalChunks, 'failed', file.type);
                    console.error(`Failed to upload chunk ${chunkNum}. Giving up.`);
                }
            }
        }
        await xhr.send(formData);
    };

    const doUpload = async () => {
        if (!files || files.length === 0 || !destination) {
            return;
        }

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            console.log(`Starting file upload`);
            console.log(file);

            const chunkNum = 0;
            const chunkSize = 10 * 1024 * 1024; // 10MB
            const totalChunks = Math.ceil(file.size / chunkSize);
            const tries = 0;
            const maxTries = 20;

            // Start recursive function to upload the file.
            await uploadChunk(file, chunkNum, chunkSize, totalChunks, tries, maxTries);
        }

        // Clear form after upload.
        setFiles([]);
    }

    const doClear = () => {
        setFiles([]);
        setProgresses({});
    }

    useEffect(() => {
        doUpload()
    }, [JSON.stringify(files)]);

    return {files, setFiles: handleFilesChange, progresses, destination, setDestination, doClear, doUpload}
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
