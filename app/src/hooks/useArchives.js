import {useEffect, useState} from "react";
import {searchArchives} from "../api";
import {useSearchParam} from "./useSearchParam";


export const useArchives = (defaultLimit = 20) => {
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
        setTotalPages(Math.floor(t / limit) + 1);
        setArchives({archives: a, total: t});
    }

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
        limit,
        setLimit,
        setDomain,
        setSearchStr,
        setActivePage,
    };
}
