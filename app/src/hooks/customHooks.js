import React, {useContext, useEffect, useRef, useState} from "react";
import {
    fetchDecoded,
    fetchDomains,
    fetchFilesProgress,
    filesSearch,
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
    getThrottleStatus,
    getVideo,
    getVideosStatistics,
    searchArchives,
    searchDirectories,
    searchVideos,
    searchZim,
    searchZims,
    setHotspot,
    setThrottle,
} from "../api";
import {createSearchParams, useSearchParams} from "react-router-dom";
import {enumerate, filterToMimetypes, humanFileSize, secondsToFullDuration} from "../components/Common";
import {StatusContext} from "../contexts/contexts";
import {toast} from "react-semantic-toasts-2";
import {useSearch} from "../components/Search";
import _ from "lodash";

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

export const useLatestRequest = (delay = 300) => {
    // A hook which ignores older requests and will only set `data` to the latest response's data.
    // usage: sendRequest(async () => await yourAPICall(...args));

    const [data, setData] = React.useState(null);
    const latestRequestRef = React.useRef(0);
    const debounceTimerRef = React.useRef(null);
    const [loading, setLoading] = React.useState(false);

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


export const useQuery = () => {
    const [searchParams, setSearchParams] = useSearchParams();

    const setQuery = (obj) => {
        setSearchParams(createSearchParams(obj), {replace: true});
    }

    const updateQuery = (obj) => {
        const newQuery = {};
        for (const entry of searchParams.entries()) {
            newQuery[entry[0]] = entry[1];
        }
        Object.entries(obj).forEach(([key, value]) => {
            if (value === undefined || value === null || value === '') {
                delete newQuery[key];
            } else {
                newQuery[key] = value;
            }
        })
        setQuery(newQuery);
    }

    return {searchParams, setSearchParams, setQuery, updateQuery}
}

export const useOneQuery = (name) => {
    const {searchParams, updateQuery} = useQuery();
    const value = searchParams.get(name);

    const setValue = (newValue) => {
        console.debug(`useOneQuery setValue=${newValue}`);
        updateQuery({[name]: newValue});
    }

    return [value, setValue]
}

export const useAllQuery = (name) => {
    const {searchParams, updateQuery} = useQuery();
    const value = searchParams.getAll(name);

    const setValue = (newValue) => {
        updateQuery({[name]: newValue});
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

export const usePages = (defaultLimit = 24, totalPages = 0) => {
    const {searchParams, updateQuery} = useQuery();
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
        console.log('newTotalPages', newTotalPages);
        setTotalPages(newTotalPages);
    }

    // Used for useEffect.
    const effect = JSON.stringify({offset, limit, activePage});

    return {offset, limit, setLimit, activePage, setPage, totalPages: totalPages_, setTotal, effect};
}

export const useSearchArchives = (defaultLimit) => {
    const {domain} = useSearchDomain();
    const {offset, limit, setLimit, activePage, setPage} = usePages(defaultLimit);
    const {searchParams, updateQuery} = useQuery();
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
    const {searchParams, updateQuery} = useQuery();
    const {offset, limit, setLimit, activePage, setPage} = usePages(defaultLimit);
    const searchStr = searchParams.get('q') || '';
    const order = searchParams.get('order') || order_by;
    const activeTags = searchParams.getAll('tag');
    const {view} = useSearchView();
    const headline = view === 'headline';

    const [videos, setVideos] = useState(null);
    const [totalPages, setTotalPages] = useState(0);

    const localSearchVideos = async () => {
        setVideos(null);
        setTotalPages(0);
        try {
            let [videos_, total] = await searchVideos(offset, limit, channelId, searchStr, order, activeTags, headline);
            setVideos(videos_);
            setTotalPages(calculateTotalPages(total, limit));
        } catch (e) {
            console.error(e);
            setVideos(undefined);// Could not get Videos, display error.
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

export const useSearchFiles = (defaultLimit = 48, emptySearch = false, model) => {
    const {
        activeTags,
        pages,
        searchStr,
        filter,
        model: model_,
        setSearchStr
    } = useSearch(defaultLimit, emptySearch, model);
    const {view} = useSearchView();

    const [searchFiles, setSearchFiles] = useState(null);
    const headline = view === 'headline';

    const localSearchFiles = async () => {
        if (!emptySearch && !searchStr && !activeTags) {
            return;
        }
        const mimetypes = filterToMimetypes(filter);
        setSearchFiles(null);
        try {
            let [file_groups, total] = await filesSearch(
                pages.offset, pages.limit, searchStr, mimetypes, model || model_, activeTags, headline);
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
        }
    }

    // Only search after the user has stopped typing.  Estimates will always happen.
    const debouncedLocalSearchFiles = _.debounce(async () => {
        await localSearchFiles();
    }, 1000);

    useEffect(() => {
        if (searchStr || (activeTags && activeTags.length > 0)) {
            debouncedLocalSearchFiles();
        }
        // Handle when this is unmounted.
        return () => debouncedLocalSearchFiles.cancel();
    }, [searchStr, pages.effect, filter, model, model_, JSON.stringify(activeTags), headline]);

    return {
        searchFiles,
        searchStr,
        filter,
        setSearchStr,
        pages,
        activeTags
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

    const fetchThrottleStatus = async () => {
        let status;
        try {
            status = await getThrottleStatus();
        } catch (e) {
            console.error(e);
        }
        if (status === 'powersave') {
            setOn(true);
        } else if (status === 'ondemand') {
            setOn(false);
        } else {
            setOn(null);
        }
    }

    useEffect(() => {
        fetchThrottleStatus();
    }, []);

    const localSetThrottle = async (on) => {
        setOn(null);
        await setThrottle(on);
        await fetchThrottleStatus();
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

    useEffect(() => {
        fetchSettings();
    }, []);

    return {settings, fetchSettings};
}

export const useMediaDirectory = () => {
    const {settings} = useSettings();

    return settings['media_directory'];
}

export const useSettingsInterval = () => {
    const {settings, fetchSettings} = useSettings();

    useRecurringTimeout(fetchSettings(), 1000 * 3);

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
    const value = useStatusInterval();

    return <StatusContext.Provider value={value}>
        {props.children}
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
                        console.log(`Server requested a different chunk ${chunkNum}`);
                        await uploadChunk(file, expectedChunk, chunkSize, totalChunks, tries + 1, maxTries);
                    } else {
                        console.debug(`Uploading of chunk ${chunkNum} succeeded, got request for chunk ${chunkNum}`);
                        // Success, reset tries.
                        await uploadChunk(file, expectedChunk, chunkSize, totalChunks, 0, maxTries);
                    }
                } else if (xhr.status === 201) {
                    handleProgress(file.name, totalChunks, totalChunks, 'complete', file.type);
                    console.log(`Uploading of ${file.path} completed.`);
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

export const useSearchZims = (defaultLimit) => {
    const {offset, limit, setLimit, activePage, setPage} = usePages(defaultLimit);
    const {searchParams, updateQuery} = useQuery();
    const searchStr = searchParams.get('q') || '';

    const [zims, setZims] = useState(null);
    const [totalPages, setTotalPages] = useState(0);

    const localSearchZims = async () => {
        setZims(null);
        try {
            let [zims_,] = await searchZims(offset, limit, searchStr);
            setZims(zims_);
        } catch (e) {
            console.error(e);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get archives',
                time: 5000,
            });
            setZims([]);
        }
    }

    useEffect(() => {
        localSearchZims();
    }, [searchStr, limit, activePage, setZims]);

    const setSearchStr = (value) => {
        updateQuery({q: value, o: 0, order: undefined});
    }

    const setOrderBy = (value) => {
        setPage(1);
        updateQuery({order: value});
    }

    return {
        zims,
        limit,
        setLimit,
        offset,
        setOrderBy,
        totalPages,
        activePage,
        setPage,
        searchStr,
        setSearchStr,
        fetchArchives: localSearchZims,
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
