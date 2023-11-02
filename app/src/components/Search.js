import React, {useEffect, useState} from "react";
import {createSearchParams, Route, Routes, useNavigate} from "react-router-dom";
import {FilesSearchView} from "./Files";
import {usePages, useQuery} from "../hooks/customHooks";
import {ZimSearchView} from "./Zim";
import {searchEstimate} from "../api";
import {normalizeEstimate, TabLinks} from "./Common";

export const useSearch = (defaultLimit = 48, totalPages = 0, emptySearch = false, model) => {
    const navigate = useNavigate();

    const {searchParams, updateQuery} = useQuery();
    // `searchStr` means actually fetch the files/zims.
    const searchStr = searchParams.get('q');
    // User can search only by Tags, `searchStr` not required.
    const activeTags = searchParams.getAll('tag');
    const pages = usePages(defaultLimit, totalPages);
    // text/html, video*, image*, etc.
    const filter = searchParams.get('filter');
    // archive/video/ebook/etc.
    const model_ = searchParams.get('model') || model;

    const setSearchStr = (value) => {
        const searchQuery = {q: value, o: 0};
        if (filter) {
            searchQuery['filter'] = filter;
        }
        navigate({
            pathname: '/search',
            // Start new search at offset 0.
            search: createSearchParams(searchQuery).toString(),
        });
    }

    const clearSearch = () => {
        navigate({pathname: window.location.pathname, search: ''});
    }

    const setTags = (tags) => {
        updateQuery({tag: tags});
    }

    const addTag = (name) => {
        const newTags = [...activeTags, name];
        setTags(newTags);
    }

    const removeTag = (name) => {
        const newTags = activeTags.filter(i => i !== name);
        setTags(newTags);
    }

    return {
        activeTags,
        addTag,
        filter,
        model: model_,
        pages,
        removeTag,
        searchParams,
        searchStr,
        setSearchStr,
        clearSearch,
        setTags,
    }
}


export const useSearchEstimate = (search_str, activeTags) => {
    const [fileGroups, setFileGroups] = useState('?');
    const [zims, setZims] = useState(null);
    const [zimsSum, setZimsSum] = useState('?');

    const localFetchSearchEstimate = async () => {
        if (!search_str && (!activeTags || activeTags.length === 0)) {
            return;
        }
        try {
            const estimates = await searchEstimate(search_str, activeTags);
            console.debug('estimates', estimates);
            setFileGroups(estimates['file_groups']);
            setZimsSum(estimates['zimSum']);
            setZims(estimates['zims']);
        } catch (e) {
            console.error('Failed to fetch estimates');
            console.error(e);
            setFileGroups(null);
            setZimsSum(null);
            setZims(null);
        }
    }

    useEffect(() => {
        localFetchSearchEstimate();
    }, [search_str, JSON.stringify(activeTags)]);

    return {fileGroups, zimsSum, zims}
}

export function SearchView() {
    const {searchStr, activeTags} = useSearch();
    const estimates = useSearchEstimate(searchStr, activeTags);

    let filesTabName = 'Files';
    let zimsTabName = 'Zims';
    if (estimates) {
        const {fileGroups, zimsSum} = estimates;
        filesTabName = `Files (${normalizeEstimate(fileGroups)})`;
        zimsTabName = `Zims (${normalizeEstimate(zimsSum)})`;
    }

    const links = [
        {text: filesTabName, to: '/search', key: 'filesSearch', end: true},
        {text: zimsTabName, to: '/search/zim', key: 'zimsSearch'},
    ]

    return <React.Fragment>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/*' element={<FilesSearchView/>}/>
            <Route path='/zim' exact element={<ZimSearchView estimates={estimates}/>}/>
        </Routes>
    </React.Fragment>
}
