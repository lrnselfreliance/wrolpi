import {useContext, useEffect, useRef, useState} from "react";
import {
    favoriteVideo,
    fetchDomains,
    filesSearch,
    getArchive,
    getChannel,
    getChannels,
    getDirectories,
    getDownloaders,
    getDownloads,
    getFiles,
    getStatistics,
    getInventory,
    getSettings,
    getVideosStatistics,
    getStatus,
    getThrottleStatus,
    getVideo,
    killDownloads,
    searchArchives,
    searchVideos,
    setHotspot,
    setThrottle,
    startDownloads
} from "../api";
import {createSearchParams, useSearchParams} from "react-router-dom";
import {toast} from "react-semantic-toasts";
import {enumerate, filterToMimetypes, humanFileSize, secondsToFullDuration} from "../components/Common";
import {StatusContext} from "../contexts/contexts";

const calculatePage = (offset, limit) => {
    return offset && limit ? Math.round((offset / limit) + 1) : 1;
}

const calculateTotalPages = (total, limit) => {
    return total && limit ? Math.round(total / limit) + 1 : 1;
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
            setDomains([]);
            setTotal(0);
        }
    }

    useEffect(() => {
        _fetchDomains();
    }, []);

    return [domains, total];
}

export const useArchive = (archiveId) => {
    const [archiveFile, setArchiveFile] = useState(null);
    const [history, setHistory] = useState(null);

    const fetchArchive = async () => {
        try {
            const [file, history] = await getArchive(archiveId);
            setArchiveFile(file);
            setHistory(history);
        } catch (e) {
            console.error(e);
            setArchiveFile(undefined);
        }
    }

    useEffect(() => {
        fetchArchive();
    }, [archiveId]);

    return {archiveFile, history};
}

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

export const usePages = (defaultLimit) => {
    const {searchParams, updateQuery} = useQuery();
    const offset = searchParams.get('o') || 0;
    const limit = searchParams.get('l') || defaultLimit || 24;
    const [activePage, setActivePage] = useState(calculatePage(offset, limit));

    const setLimit = (value) => {
        setPage(1);
        updateQuery({l: value, o: null});
    }

    const setPage = (value) => {
        setActivePage(value);
        value = value - 1;  // Page really starts as 0.
        updateQuery({o: value * limit});
    }

    return {offset, limit, setLimit, activePage, setPage};
}

export const useSearchArchives = (defaultLimit, domain, order_by) => {
    const {offset, limit, setLimit, activePage, setPage} = usePages(defaultLimit)
    const {searchParams, updateQuery} = useQuery();
    const searchStr = searchParams.get('q') || '';
    const order = searchParams.get('order') || order_by;

    const [archives, setArchives] = useState();
    const [totalPages, setTotalPages] = useState(0);

    const localSearchArchives = async () => {
        setArchives(null);
        setTotalPages(0);
        try {
            let [archives_, total] = await searchArchives(offset, limit, domain, searchStr, order);
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
            setArchives([]);
        }
    }

    useEffect(() => {
        localSearchArchives();
    }, [searchStr, limit, domain, order, activePage]);

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

export const useSearchVideos = (defaultLimit, channelId, order_by, filters) => {
    const {searchParams, updateQuery} = useQuery();
    const {offset, limit, setLimit, activePage, setPage} = usePages(defaultLimit)
    const searchStr = searchParams.get('q') || '';
    const order = searchParams.get('order') || order_by;

    const [videos, setVideos] = useState();
    const [totalPages, setTotalPages] = useState(0);

    const localSearchVideos = async () => {
        setVideos(null);
        setTotalPages(0);
        try {
            let [videos_, total] = await searchVideos(offset, limit, channelId, searchStr, order, filters);
            setVideos(videos_);
            setTotalPages(calculateTotalPages(total, limit));
        } catch (e) {
            console.error(e);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get videos',
                time: 5000,
            });
            setVideos([]);
        }
    }

    useEffect(() => {
        localSearchVideos();
    }, [searchStr, limit, channelId, offset, order_by, filters.join('')]);

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

    const setFavorite = async (value) => {
        if (!videoFile) {
            console.error('No video to favorite');
            return
        }
        try {
            await favoriteVideo(videoFile.video.id, value);
            fetchVideo();
        } catch (e) {
            console.error(e);
        }
    }

    useEffect(() => {
        fetchVideo();
    }, [videoId]);

    return {videoFile, prevFile, nextFile, setFavorite};
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
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get channels',
                time: 5000,
            });
        }
    }

    useEffect(() => {
        fetchChannels();
    }, []);

    return {channels, fetchChannels}
}

export const useSearchFiles = (defaultLimit = 48, emptySearch = false, model) => {
    const {searchParams, updateQuery} = useQuery();
    const limit = searchParams.get('l') || defaultLimit;
    const offset = searchParams.get('o') || 0;
    const searchStr = searchParams.get('q');
    const filter = searchParams.get('filter');
    const model_ = searchParams.get('model');

    const [searchFiles, setSearchFiles] = useState(null);
    const [totalPages, setTotalPages] = useState(0);
    const [activePage, setActivePage] = useState(calculatePage(offset, limit));

    const localSearchFiles = async () => {
        if (!emptySearch && !searchStr) {
            return;
        }
        const mimetypes = filterToMimetypes(filter);
        setSearchFiles(null);
        setTotalPages(0);
        try {
            let [files, total] = await filesSearch(
                offset, limit, searchStr, mimetypes, model || model_);
            setSearchFiles(files);
            setTotalPages(calculateTotalPages(total, limit));
        } catch (e) {
            console.error(e);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get files',
                time: 5000,
            });
        }
    }

    useEffect(() => {
        localSearchFiles();
    }, [searchStr, limit, offset, activePage, filter, model, model_]);

    const setPage = (i) => {
        i = parseInt(i);
        let l = parseInt(limit);
        updateQuery({o: (l * i) - l})
        setActivePage(i);
    }

    const setSearchStr = (value) => {
        updateQuery({q: value, o: null});
    }

    const setLimit = (value) => {
        setActivePage(1);
        updateQuery({l: value, o: 0});
    }

    return {searchFiles, totalPages, limit, searchStr, filter, setSearchStr, activePage, setPage, setLimit};
}

export const useBrowseFiles = () => {
    const [browseFiles, setBrowseFiles] = useState([]);
    const [openFolders, setOpenFolders] = useState([]);

    const fetchFiles = async () => {
        try {
            const files = await getFiles(openFolders);
            setBrowseFiles(files);
        } catch (e) {
            console.log(e);
            setBrowseFiles([]);
        }
    }

    useEffect(() => {
        fetchFiles();
    }, [openFolders])

    return {browseFiles, openFolders, setOpenFolders, fetchFiles};
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
    const [onceDownloads, setOnceDownloads] = useState();
    const [recurringDownloads, setRecurringDownloads] = useState();

    const fetchDownloads = async () => {
        try {
            const data = await getDownloads();
            setOnceDownloads(data['once_downloads']);
            setRecurringDownloads(data['recurring_downloads']);
        } catch (e) {
            console.error(e);
        }
    }

    useRecurringTimeout(fetchDownloads, 3 * 1000);

    return {onceDownloads, recurringDownloads, fetchDownloads}
}

export const useDownloaders = () => {
    const [on, setOn] = useState(null);
    const [downloaders, setDownloaders] = useState(null);

    const fetchDownloaders = async () => {
        try {
            let data = await getDownloaders();
            setDownloaders(data['downloaders']);
            setOn(!data['manager_disabled']);
        } catch (e) {
            console.error(e);
        }
    }

    useEffect(() => {
        fetchDownloaders();
    }, []);

    const localSetDownloads = async (on) => {
        setOn(null);
        if (on) {
            await startDownloads();
        } else {
            await killDownloads();
        }
        await fetchDownloaders();
    }

    return {on, setOn, downloaders, setDownloads: localSetDownloads};
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
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get server status',
                time: 5000,
            });
        }
    }

    return {status, fetchStatus}
}

export const useStatusInterval = () => {
    const {status, fetchStatus} = useStatus();

    useRecurringTimeout(fetchStatus, 1000 * 3);

    return {status, fetchStatus};
}

export const useVideoStatistics = () => {
    const [statistics, setStatistics] = useState({});

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
