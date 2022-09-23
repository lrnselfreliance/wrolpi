import {useEffect, useState} from "react";
import {
    fetchDomains,
    filesSearch,
    getArchive,
    getChannel,
    getChannels,
    getDirectories,
    getDownloaders,
    getDownloads,
    getFiles,
    getHotspotStatus,
    getInventory,
    getSettings,
    getStatistics,
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
import {enumerate, humanFileSize, secondsToString} from "../components/Common";

const calculatePage = (offset, limit) => {
    return offset && limit ? Math.round((offset / limit) + 1) : 1;
}

const calculateTotalPages = (total, limit) => {
    return total && limit ? Math.round(total / limit) + 1 : 1;
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
    const [alternatives, setAlternatives] = useState(null);

    const fetchArchive = async () => {
        try {
            const [file, alt] = await getArchive(archiveId);
            setArchiveFile(file);
            setAlternatives(alt);
        } catch (e) {
            console.error(e);
            setArchiveFile(undefined);
        }
    }

    useEffect(() => {
        fetchArchive();
    }, [archiveId]);

    return {archiveFile, alternatives};
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
    }
}

export const useVideo = (videoId) => {
    const [videoFile, setVideoFile] = useState(null);
    const [prevFile, setPrevFile] = useState(null);
    const [nextFile, setNextFile] = useState(null);

    const fetchVideo = async () => {
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

    return {videoFile, prevFile, nextFile};
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

export const useSearchFiles = (defaultLimit = 48, emptySearch = false, mimetype, model) => {
    const {searchParams, updateQuery} = useQuery();
    const limit = searchParams.get('l') || defaultLimit;
    const offset = searchParams.get('o') || 0;
    const searchStr = searchParams.get('q');
    const mimetype_ = searchParams.get('mimetype');
    const model_ = searchParams.get('model');

    const [searchFiles, setSearchFiles] = useState(null);
    const [totalPages, setTotalPages] = useState(0);
    const [activePage, setActivePage] = useState(calculatePage(offset, limit));

    const localSearchFiles = async () => {
        if (!emptySearch && !searchStr) {
            return;
        }
        setSearchFiles(null);
        setTotalPages(0);
        try {
            let [files, total] = await filesSearch(
                offset, limit, searchStr, mimetype || mimetype_, model || model_);
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
    }, [searchStr, limit, offset, activePage, mimetype, mimetype_, model, model_]);

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

    return {searchFiles, totalPages, limit, searchStr, mimetype, setSearchStr, activePage, setPage, setLimit};
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

    const fetchHotspotStatus = async () => {
        let status;
        try {
            status = await getHotspotStatus();
        } catch (e) {
            console.error(e);
        }
        if (status === 'connected') {
            // Hotspot is on.
            setOn(true);
        } else if (status === 'disconnected' || status === 'unavailable') {
            // Hotspot can be turned on.
            setOn(false);
        } else {
            // Hotspot is not supported.  API is probably running in a Docker container.
            setOn(null);
        }
    }

    useEffect(() => {
        fetchHotspotStatus();
    }, []);

    const localSetHotspot = async (on) => {
        setOn(null);
        await setHotspot(on);
        await fetchHotspotStatus();
    }

    return {on, setOn, setHotspot: localSetHotspot};
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

    useEffect(() => {
        fetchDownloads();
        const interval = setInterval(() => {
            fetchDownloads();
        }, 1000 * 3);
        return () => clearInterval(interval);
    }, []);

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

    const fetchDirectories = async () => {
        if (defaultDirectory && directory === '') {
            setDirectory(defaultDirectory);
        }
        try {
            setDirectories(await getDirectories(directory));
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

    return {directory, directories, setDirectory};
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

    useEffect(() => {
        const interval = setInterval(() => {
            fetchSettings();
        }, 1000 * 3);
        return () => clearInterval(interval);
    }, []);

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

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(() => {
            // console.log('fetch');
            fetchStatus();
        }, 1000 * 5);
        return () => clearInterval(interval);
    }, []);

    return {status, fetchStatus}
}

export const useVideoStatistics = () => {
    const [statistics, setStatistics] = useState({});

    const fetchStatistics = async () => {
        try {
            let stats = await getStatistics();
            stats.videos.sum_duration = secondsToString(stats.videos.sum_duration);
            stats.videos.sum_size = humanFileSize(stats.videos.sum_size, true);
            stats.videos.max_size = humanFileSize(stats.videos.max_size, true);
            stats.historical.average_size = humanFileSize(stats.historical.average_size, true);
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
