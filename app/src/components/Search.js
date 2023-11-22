import React, {useEffect, useState} from "react";
import {createSearchParams, Route, Routes, useNavigate} from "react-router-dom";
import {FilesSearchView} from "./Files";
import {useLatestRequest, usePages, useQuery} from "../hooks/customHooks";
import {ZimSearchView} from "./Zim";
import {searchEstimate, searchSuggestions} from "../api";
import {fuzzyMatch, normalizeEstimate, TabLinks} from "./Common";
import _ from "lodash";
import {TagsContext} from "../Tags";
import {Header as SHeader} from "semantic-ui-react";

const SUGGESTED_APPS = [
    {location: '/more/otp', title: 'One Time Pad', description: 'Encrypt and Decrypt messages'},
    {location: '/inventory', title: 'Inventory', description: 'Track and organize your food storage'},
    {location: '/more/vin', title: 'Vin Decoder', description: 'Decode and analyze vehicle VIN numbers'},
    {location: '/admin', title: 'Downloads', description: 'View your downloads'},
    {location: '/admin/settings', title: 'Settings', description: 'View and modify your settings'},
    {location: '/admin/status', title: 'Status', description: 'View the status of this WROLPi server'},
    {location: '/admin/wrol', title: 'WROL Mode', description: 'Enable or disable WROL Mode'},
    {location: '/help', title: 'Help', description: 'Help documents for WROLPi'},
];


export function useSearchSuggestions() {
    const navigate = useNavigate();
    const {searchParams} = useQuery();
    const {SingleTag, fuzzyMatchTagsByName} = React.useContext(TagsContext);

    const searchStr = searchParams.get('q');

    const {data, sendRequest, loading} = useLatestRequest(500);
    const [suggestions, setSuggestions] = useState(null);

    const normalizeSuggestions = (newSuggestions) => {
        // Convert the suggestions from the Backend to what the Semantic <Search> expects.
        const lowerSearchStr = searchStr.toLowerCase();
        const matchingApps = SUGGESTED_APPS.filter(i =>
            i.title.toLowerCase().includes(lowerSearchStr)
            || fuzzyMatch(i.title.toLowerCase(), lowerSearchStr));

        const zimSum = newSuggestions.zimsEstimates.reduce((i, j) => i + j['estimate'], 0).toString();

        // Suggested results are ordered.
        let matchingSuggestions = {};
        if (newSuggestions.fileGroups > 0) {
            matchingSuggestions.fileGroups = {
                name: 'Files', results: [
                    {
                        title: newSuggestions.fileGroups.toString(),
                        type: 'files',
                        location: `/search?q=${encodeURIComponent(searchStr)}`
                    }
                ]
            };
        }
        if (zimSum > 0) {
            matchingSuggestions.zimsSum = {
                name: 'Zims', results: [
                    {title: zimSum, type: 'zims', location: `/search/zim?q=${encodeURIComponent(searchStr)}`}
                ],
            }
        }
        if (newSuggestions.channels && newSuggestions.channels.length > 0) {
            matchingSuggestions.channels = {
                name: 'Channels', results: newSuggestions.channels.map(i => {
                    return {type: 'channel', title: i['name'], id: i['id'], location: `/videos/channel/${i.id}/video`}
                })
            }
        }
        if (newSuggestions.domains && newSuggestions.domains.length > 0) {
            matchingSuggestions.domains = {
                name: 'Domains', results: newSuggestions.domains.map(i => {
                    return {
                        type: 'domain',
                        title: i.domain,
                        id: i.id,
                        domain: i.domain,
                        location: `/archive?domain=${i.domain}`
                    }
                })
            }
        }

        matchingSuggestions.tags = {
            name: 'Tags', results: fuzzyMatchTagsByName(searchStr).map(i => {
                return {type: 'tag', title: i.name, location: `/search?tag=${encodeURIComponent(i.title)}`}
            })
        }

        if (matchingApps && matchingApps.length > 0) {
            matchingSuggestions.apps = {name: 'Apps', results: matchingApps};
        }

        console.debug('matchingSuggestions', matchingSuggestions);
        setSuggestions(matchingSuggestions);
    }

    React.useEffect(() => {
        if (data) {
            normalizeSuggestions(data);
        }
    }, [JSON.stringify(data)]);

    React.useEffect(() => {
        if (!searchStr || searchStr.length === 0) {
            console.debug('Not getting suggestions because there is no search.');
            return;
        }

        // Use the useLatestRequest to handle user typing.
        sendRequest(searchSuggestions(searchStr));
    }, [searchStr, sendRequest]);

    const handleResultSelect = ({result}) => navigate(result.location);

    const resultRenderer = ({type, title, description}) => {
        if (type === 'tag') {
            return <SingleTag name={title}/>;
        }

        // No specific renderer, use the generic.
        if (description) {
            return <>
                <SHeader as='h4'>{title}</SHeader>
                {description}
            </>
        }
        return <span>{title}</span>
    };

    return {suggestions, searchStr, handleResultSelect, resultRenderer, loading}
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
