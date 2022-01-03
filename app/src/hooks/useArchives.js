import {useEffect, useState} from "react";
import {searchArchives} from "../api";
import {useHistory} from "react-router-dom";

const useSearchParam = (name, defaultValue = null) => {
    const startingValue = new URLSearchParams().get(name);

    const [value, setValue] = useState(startingValue || defaultValue);
    const history = useHistory();

    useEffect(() => {
        const params = new URLSearchParams();
        if (value) {
            params.append(name, value);
        } else {
            params.delete(name);
        }
        history.push({search: params.toString()});
    }, [value, history])

    return [value, setValue];
}

const useArchives = (defaultLimit = 20) => {
    const [archivesData, setArchives] = useState({archives: null, total: 0});
    const [totalPages, setTotalPages] = useState(0);
    const [activePage, setActivePage] = useState(1);

    let [offset, setOffset] = useSearchParam('o');
    let [limit, setLimit] = useSearchParam('l', defaultLimit);
    let [domain, setDomain] = useSearchParam('domain');
    let [searchStr, setSearchStr] = useSearchParam('q');

    const setPage = (i) => {
        i = parseInt(i);
        let l = parseInt(limit);
        setOffset((l * i) - l);
        setActivePage(i);
    }

    const search = async (term) => {
        const [a, t] = await searchArchives(offset, limit, domain, term);
        setTotalPages(Math.floor(t / limit));
        setArchives({archives: a, total: t});
    }

    useEffect(() => {
        setPage(1);
    }, []);

    useEffect(() => {
        // Load the first page of results on load.
        search();
    }, []);

    useEffect(() => {
        search(searchStr);
    }, [offset, limit, domain, searchStr]);

    return {
        archivesData,
        totalPages,
        activePage,
        setTotalPages,
        offset,
        setOffset,
        setPage,
        setLimit,
        setDomain,
        setSearchStr,
        setActivePage,
    };
}

export default useArchives;