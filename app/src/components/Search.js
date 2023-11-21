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
    {location: '/admin/status', title: 'Status', description: 'View the status of this WROLPi'},
    {location: '/admin/wrol', title: 'WROL Mode', description: 'Enable or disable WROL Mode'},
];

export function useSearchSuggestions() {
    const navigate = useNavigate();
    const {searchParams} = useQuery();
    const {SingleTag, fuzzyMatchTagsByName} = React.useContext(TagsContext);

    const searchStr = searchParams.get('q');

    const [suggestions, setSuggestions] = useState(null);

    const fetchSuggestions = async () => {
        if (searchStr && searchStr.length > 0) {
            const lowerSearchStr = searchStr.toLowerCase();
            try {
                const newSuggestions = await searchSuggestions(searchStr);
                const matchingApps = suggestedApps.filter(i =>
                    i.title.toLowerCase().includes(lowerSearchStr)
                    || fuzzyMatch(i.title.toLowerCase(), lowerSearchStr));

                const zimSum = newSuggestions.zimsEstimates.reduce((i, j) => i + j['estimate'], 0);

                // Suggested results are ordered.
                let matchingSuggestions = {};
                if (newSuggestions.fileGroups > 0) {
                    matchingSuggestions.fileGroups = {
                        name: 'Files', results: [
                            {description: newSuggestions.fileGroups, type: 'files'}
                        ]
                    };
                }
                if (zimSum > 0) {
                    matchingSuggestions.zimsSum = {
                        name: 'Zims', results: [
                            {description: zimSum, type: 'zims'}
                        ],
                    }
                }
                if (newSuggestions.channels && newSuggestions.channels.length > 0) {
                    matchingSuggestions.channels = {
                        name: 'Channels', results: newSuggestions.channels.map(i => {
                            return {type: 'channel', description: i['name'], id: i['id']}
                        })
                    }
                }
                if (newSuggestions.domains && newSuggestions.domains.length > 0) {
                    matchingSuggestions.domains = {
                        name: 'Domains', results: newSuggestions.domains.map(i => {
                            return {type: 'domain', description: i.domain, id: i['id'], domain: i.domain}
                        })
                    }
                }

                matchingSuggestions.tags = {
                    name: 'Tags', results: fuzzyMatchTagsByName(searchStr).map(i => {
                        return {type: 'tag', description: i.name}
                    })
                }

                if (matchingApps && matchingApps.length > 0) {
                    matchingSuggestions.apps = {name: 'Apps', results: matchingApps};
                }

                console.debug('matchingSuggestions', matchingSuggestions);
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
            return navigate(result.location);
        } else if (result['type'] === 'channel') {
            return navigate(`/videos/channel/${result['id']}/video`);
        } else if (result['type'] === 'domain') {
            return navigate(`/archive?domain=${result['domain']}`);
        } else if (result['type'] === 'tag') {
            return navigate(`/search?tag=${encodeURIComponent(result['description'])}`);
        } else if (result['type'] === 'files') {
            return navigate(`/search?q=${encodeURIComponent(searchStr)}`);
        } else if (result['type'] === 'zims') {
            return navigate(`/search/zim?q=${encodeURIComponent(searchStr)}`);
        }
        console.error('No handleResultSelect defined:', result);
    };

    const resultRenderer = ({type, title, description}) => {
        if (type === 'tag') {
            return <SingleTag name={description}/>;
        }

        // No specific renderer, use the generic.
        if (title) {
            return <>
                <SHeader as='h4'>{title}</SHeader>
                {description}
            </>
        }
        return <span>{description}</span>
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
