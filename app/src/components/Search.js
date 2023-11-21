import React, {useEffect, useState} from "react";
import {createSearchParams, Route, Routes, useNavigate} from "react-router-dom";
import {FilesSearchView} from "./Files";
import {usePages, useQuery} from "../hooks/customHooks";
import {ZimSearchView} from "./Zim";
import {searchEstimate, searchSuggestions} from "../api";
import {fuzzyMatch, normalizeEstimate, TabLinks} from "./Common";
import _ from "lodash";
import {TagsContext} from "../Tags";
import {Header as SHeader} from "semantic-ui-react";

const suggestedApps = [
    {location: '/more/otp', title: 'One Time Pad', description: 'Encrypt and Decrypt messages'},
    {location: '/inventory', title: 'Inventory', description: 'Track and organize your food storage'},
    {location: '/more/vin', title: 'Vin Decoder', description: 'Decode and analyze vehicle VIN numbers'},
    {location: '/admin', title: 'Downloads', description: 'View your downloads'},
    {location: '/admin/settings', title: 'Settings', description: 'View and modify your settings'},
    {location: '/admin/wrol', title: 'WROL Mode', description: 'Enable or disable WROL Mode'},
];

export function useSearchSuggestions() {
    const navigate = useNavigate();
    const {searchParams} = useQuery();
    const {SingleTag} = React.useContext(TagsContext);

    const searchStr = searchParams.get('q');

    const [suggestions, setSuggestions] = useState(null);

    const fetchSuggestions = async () => {
        if (searchStr && searchStr.length > 0) {
            const lowerSearchStr = searchStr.toLowerCase();
            try {
                const i = await searchSuggestions(searchStr);
                const matchingApps = suggestedApps.filter(i =>
                    i.title.toLowerCase().includes(lowerSearchStr)
                    || fuzzyMatch(i.title.toLowerCase(), lowerSearchStr));
                const matchingSuggestions = {
                    channels: {
                        name: 'Channels', results: i.channels.map(i => {
                            return {title: i['name'], id: i['id'], type: 'channel'}
                        })
                    },
                    domains: {
                        name: 'Domains', results: i.domains.map(i => {
                            return {title: i['domain'], id: i['id'], type: 'domain'}
                        })
                    },
                    tags: {
                        name: 'Tags', results: i.tags.map(i => {
                            return {title: i['name'], type: 'tag'}
                        })
                    },
                    apps: {name: 'Apps', results: matchingApps},
                };
                console.debug('newSuggestions', matchingSuggestions);
                setSuggestions(matchingSuggestions);
            } catch (e) {
                console.error(e);
                console.error('Failed to get search suggestions');
            }
        } else {
            setSuggestions(null);
        }
    }

    React.useEffect(() => {
        fetchSuggestions();
    }, [searchStr]);


    const handleResultSelect = ({result}) => {
        if (!result) {
            return;
        }

        if (result.location) {
            navigate(result.location);
        } else if (result['type'] === 'channel') {
            navigate(`/videos/channel/${result['id']}/video`);
        } else if (result['type'] === 'domain') {
            navigate(`/archive?domain=${result['domain']}`);
        } else if (result['type'] === 'tag') {
            navigate(`/search?tag=${encodeURIComponent(result['title'])}`);
        }
    };

    const resultRenderer = ({type, title, description}) => {
        description = description !== null ? <SHeader as='h5'>{description}</SHeader> : null;
        if (type === 'tag') {
            return <SingleTag name={title}/>;
        }

        // No specific renderer, use the generic.
        return <>
            <SHeader as='h4'>{title}</SHeader>
            {description}
        </>
    };

    return {suggestions, searchStr, handleResultSelect, resultRenderer}
}

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

    const debouncedEstimate = _.debounce(async () => await localFetchSearchEstimate(), 800);

    useEffect(() => {
        debouncedEstimate();

        return () => debouncedEstimate.cancel();
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
