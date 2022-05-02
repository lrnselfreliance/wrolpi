import {useEffect, useState} from "react";
import {
    fetchDomains,
    filesSearch,
    getAPIStatus,
    getDownloaders,
    getFiles,
    getHotspotStatus,
    getThrottleStatus,
    getVersion,
    killDownloads,
    searchArchives,
    searchVideos,
    setHotspot,
    setThrottle,
    startDownloads
} from "../api";
import {useHistory} from "react-router-dom";
import {toast} from "react-semantic-toasts";

export const useSearchParam = (key, defaultValue = null) => {
    // Get a window.location.search param.
    const startingValue = new URLSearchParams(window.location.search).get(key);

    const [value, setValue] = useState(startingValue || defaultValue);
    const history = useHistory();

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        params.delete(key);
        if (value) {
            params.append(key, value);
        }
        history.push({search: params.toString()});
    }, [value, history, key])

    return [value, setValue];
}

export const useSearch = () => {
    let [searchStr, setSearchStr] = useSearchParam('q');

    const [archives, setArchives] = useState();
    const [videos, setVideos] = useState();

    const localSearchArchives = async (term) => {
        setArchives(null);
        try {
            const [archives] = await searchArchives(0, 6, null, term);
            setArchives(archives);
        } catch (e) {
            console.error(e);
            setArchives([]);
        }
    }

    const localSearchVideos = async (term) => {
        setVideos(null);
        try {
            const [videos] = await searchVideos(0, 6, null, term);
            setVideos(videos);
        } catch (e) {
            console.error(e);
            setVideos([]);
        }
    }

    useEffect(() => {
        if (searchStr) {
            localSearchArchives(searchStr);
            localSearchVideos(searchStr)
        }
    }, [searchStr]);

    return {searchStr, setSearchStr, archives, videos}
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

export const useArchives = ({defaultLimit = 20}) => {
    let [limit, setLimit] = useSearchParam('l', defaultLimit);
    let [offset, setOffset] = useSearchParam('o');
    let [searchStr, setSearchStr] = useSearchParam('q');
    let [domain, setDomain] = useSearchParam('domain');

    const [archives, setArchives] = useState(null);
    const [totalPages, setTotalPages] = useState(0);
    const [activePage, setActivePage] = useState((offset / limit) + 1);

    const search = async () => {
        setArchives(null);
        try {
            const [archives, total] = await searchArchives(offset, limit, domain, searchStr);
            setTotalPages(Math.floor(total / limit) + 1);
            setArchives(archives);
        } catch (e) {
            console.error(e);
            setTotalPages(0);
            setArchives([]);
        }
    }

    useEffect(() => {
        search();
    }, [offset, limit, domain, searchStr]);

    const setPage = (i) => {
        i = parseInt(i);
        let l = parseInt(limit);
        setOffset((l * i) - l);
        setActivePage(i);
    }

    return {
        archives,
        totalPages,
        setTotalPages,
        offset,
        setOffset,
        setPage,
        limit,
        setLimit,
        domain,
        setDomain,
        searchStr,
        setSearchStr,
        activePage,
        setActivePage,
        search,
    };
}

export const useVersion = () => {
    const [version, setVersion] = useState('');

    const fetchVersion = async () => {
        try {
            let version = await getVersion();
            setVersion(version);
        } catch (e) {
            console.error(e);
        }
    }

    useEffect(() => {
        fetchVersion();
    })

    return version;
}

export const useSearchFiles = ({defaultLimit = 50}) => {
    let [limit, setLimit] = useSearchParam('l', defaultLimit);
    let [offset, setOffset] = useSearchParam('o');
    let [searchStr, setSearchStr] = useSearchParam('q');

    const [searchFiles, setSearchFiles] = useState([]);
    const [totalPages, setTotalPages] = useState(0);
    const [activePage, setActivePage] = useState(1);

    const localSearchFiles = async () => {
        setSearchFiles([]);
        setTotalPages(0);
        if (searchStr) {
            try {
                let [files, total] = await filesSearch(offset, limit, searchStr);
                setSearchFiles(files);
                setTotalPages(Math.floor(total / limit) + 1);
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
    }

    useEffect(() => {
        localSearchFiles();
    }, [searchStr, limit, offset, activePage]);

    const setPage = (i) => {
        i = parseInt(i);
        let l = parseInt(limit);
        setOffset((l * i) - l);
        setActivePage(i);
    }

    return {searchFiles, totalPages, limit, setLimit, setOffset, searchStr, setSearchStr, activePage, setPage};
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

export const useUp = () => {
    // Checks that the API is up.
    const fetchAPIStatus = async () => {
        let status = await getAPIStatus();
        if (status === false) {
            toast({
                type: 'error',
                title: 'Error!',
                description: `API did not respond.  Check the server's status.`,
                time: 5000,
            });
        }
    }

    useEffect(() => {
        fetchAPIStatus();
    }, []);
}
