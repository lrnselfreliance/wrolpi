import {useEffect, useState} from "react";
import {
    fetchDomains,
    filesSearch,
    getHotspotStatus,
    getDownloaders,
    getFiles,
    getVersion,
    killDownloads,
    searchArchives,
    searchVideos,
    setHotspot,
    startDownloads
} from "../api";
import {useHistory} from "react-router-dom";

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
        const [archives] = await searchArchives(0, 6, null, term);
        setArchives(archives);
    }

    const localSearchVideos = async (term) => {
        setVideos(null);
        const [videos] = await searchVideos(0, 6, null, term);
        setVideos(videos);
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
        let [domains, total] = await fetchDomains();
        setDomains(domains);
        setTotal(total);
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
        const [archives, total] = await searchArchives(offset, limit, domain, searchStr);
        setTotalPages(Math.floor(total / limit) + 1);
        setArchives(archives);
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
        let version = await getVersion();
        setVersion(version);
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
            let [files, total] = await filesSearch(offset, limit, searchStr);
            setSearchFiles(files);
            setTotalPages(Math.floor(total / limit) + 1);
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
        const files = await getFiles(openFolders);
        setBrowseFiles(files);
    }

    useEffect(() => {
        fetchFiles();
    }, [openFolders])

    return {browseFiles, openFolders, setOpenFolders, fetchFiles};
}

export const useHotspot = () => {
    const [on, setOn] = useState(null);

    const fetchHotspotStatus = async () => {
        const status = await getHotspotStatus();
        // Wi-Fi can be: connected, disconnected, unavailable.
        setOn(status === 'connected');
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
        let data = await getDownloaders();
        setDownloaders(data['downloaders']);
        setOn(!data['manager_disabled']);
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
