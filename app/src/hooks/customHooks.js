import {useEffect, useState} from "react";
import {fetchDomains, filesSearch, getFiles, getVersion, searchArchives, searchVideos} from "../api";
import {useHistory} from "react-router-dom";
import {secondsToDateTime} from "../components/Common";

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

export const useSearchParams = ({defaultLimit = 20}) => {
    let [limit, setLimit] = useSearchParam('l', defaultLimit);
    let [offset, setOffset] = useSearchParam('o');
    let [searchStr, setSearchStr] = useSearchParam('q');

    let [activePage, setActivePage] = useState(1);

    const setPage = (i) => {
        i = parseInt(i);
        let l = parseInt(limit);
        setOffset((l * i) - l);
        setActivePage(i);
    }

    return {limit, setLimit, offset, setOffset, searchStr, setSearchStr, activePage, setPage};
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

export const useArchives = (defaultLimit = 20) => {
    const [archivesData, setArchives] = useState({archives: null, total: 0});
    const [totalPages, setTotalPages] = useState(0);
    const [activePage, setActivePage] = useState(1);

    let {limit, setLimit, offset, setOffset, searchStr, setSearchStr, setPage} = useSearchParams(defaultLimit);
    let [domain, setDomain] = useSearchParam('domain');

    const search = async (term) => {
        setArchives({archives: null, total: 0});
        setTotalPages(0);
        const [archives, total] = await searchArchives(offset, limit, domain, term);
        setTotalPages(Math.floor(total / limit) + 1);
        setArchives({archives, total});
    }

    useEffect(() => {
        search(searchStr);
    }, [offset, limit, domain, searchStr]);

    return {
        archivesData,
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

const replaceFileDatetimes = (files) => {
    for (let i = 0; i < files.length; i++) {
        if (files[i]['modified']) {
            files[i]['modified'] = secondsToDateTime(files[i]['modified']);
        }
    }
    return files;
}

export const useSearchFiles = ({defaultLimit = 50}) => {
    let {limit, setLimit, offset, setOffset, searchStr, setSearchStr, activePage, setPage} =
        useSearchParams(defaultLimit);

    const [searchFiles, setSearchFiles] = useState([]);
    const [totalPages, setTotalPages] = useState(0);

    const localSearchFiles = async () => {
        setSearchFiles([]);
        setTotalPages(0);
        if (searchStr) {
            let {files, totals} = await filesSearch(offset, limit, searchStr);
            files = replaceFileDatetimes(files);
            setSearchFiles(files);
            setTotalPages(Math.floor(totals['files'] / limit) + 1);
        }
    }

    useEffect(() => {
        localSearchFiles();
    }, [searchStr, limit, offset, activePage]);

    return {searchFiles, totalPages, limit, setLimit, setOffset, searchStr, setSearchStr, activePage, setPage};
}

export const useBrowseFiles = () => {
    const [browseFiles, setBrowseFiles] = useState([]);
    const [openFolders, setOpenFolders] = useState([]);

    const fetchFiles = async () => {
        let {files} = await getFiles(openFolders);
        files = replaceFileDatetimes(files);
        setBrowseFiles(files);
    }

    useEffect(() => {
        fetchFiles();
    }, [openFolders])

    return {browseFiles, openFolders, setOpenFolders, fetchFiles};
}
