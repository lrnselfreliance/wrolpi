import React, {useContext, useEffect, useState} from "react";
import {createSearchParams, Route, Routes, useNavigate} from "react-router-dom";
import {FilesSearchView} from "./Files";
import {useLatestRequest, usePages, useQuery} from "../hooks/customHooks";
import {ZimSearchView} from "./Zim";
import {searchEstimate, searchSuggestions} from "../api";
import {fuzzyMatch, normalizeEstimate, TabLinks} from "./Common";
import _ from "lodash";
import {TagsContext} from "../Tags";
import {Header as SHeader} from "semantic-ui-react";

export const SearchSuggestionsContext = React.createContext({
    suggestionsResults: {},
    suggestions: {},
    suggestionsSums: {},
    handleResultSelect: null,
    resultRenderer: null,
    loading: false,
});

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
    const [suggestionsResults, setSuggestionsResults] = useState({});
    const [suggestions, setSuggestions] = useState({});
    const [suggestionsSums, setSuggestionsSums] = useState({});

    const normalizeSuggestionsResults = (newSuggestions) => {
        // Convert the suggestions from the Backend to what the Semantic <Search> expects.
        const lowerSearchStr = searchStr.toLowerCase();

        let results = {};

        // Suggested results are ordered.
        if (newSuggestions.fileGroups > 0) {
            results.fileGroups = {
                name: 'Files', results: [
                    {
                        title: newSuggestions.fileGroups.toString(),
                        type: 'files',
                        location: `/search?q=${encodeURIComponent(searchStr)}`
                    }
                ]
            };
        }

        const zimSum = newSuggestions.zimsEstimates.reduce((i, j) => i + j['estimate'], 0);
        if (zimSum > 0) {
            results.zimsSum = {
                name: 'Zims', results: [
                    {title: zimSum.toString(), type: 'zims', location: `/search/zim?q=${encodeURIComponent(searchStr)}`}
                ],
            }
        }
        if (newSuggestions.channels && newSuggestions.channels.length > 0) {
            results.channels = {
                name: 'Channels', results: newSuggestions.channels.map(i => {
                    return {type: 'channel', title: i['name'], id: i['id'], location: `/videos/channel/${i.id}/video`}
                })
            }
        }
        if (newSuggestions.domains && newSuggestions.domains.length > 0) {
            results.domains = {
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

        const matchingTags = fuzzyMatchTagsByName(searchStr);
        if (matchingTags && matchingTags.length > 0) {
            results.tags = {
                name: 'Tags', results: matchingTags.map(i => {
                    return {type: 'tag', title: i.name, location: `/search?tag=${encodeURIComponent(i.name)}`}
                })
            }
        }

        const matchingApps = SUGGESTED_APPS.filter(i =>
            i.title.toLowerCase().includes(lowerSearchStr)
            || fuzzyMatch(i.title.toLowerCase(), lowerSearchStr));
        if (matchingApps && matchingApps.length > 0) {
            results.apps = {name: 'Apps', results: matchingApps};
        }

        setSuggestionsResults(results);
        setSuggestionsSums({
            fileGroups: newSuggestions.fileGroups,
            zims: zimSum,
            channels: newSuggestions.channels.length,
            domains: newSuggestions.domains.length,
            tags: matchingTags.length,
            apps: matchingApps.length,
        })
    }

    React.useEffect(() => {
        if (data) {
            setSuggestions(data);
            normalizeSuggestionsResults(data);
        }
    }, [JSON.stringify(data)]);

    React.useEffect(() => {
        if (!searchStr || searchStr.length === 0) {
            console.debug('Not getting suggestions because there is no search.');
            return;
        }
        setSuggestions({});
        setSuggestionsSums({});
        setSuggestionsResults({});

        // Use the useLatestRequest to handle user typing.
        sendRequest(async () => await searchSuggestions(searchStr));
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

    return {suggestions, suggestionsResults, suggestionsSums, searchStr, handleResultSelect, resultRenderer, loading}
}

export const SearchSuggestionsProvider = (props) => {
    const value = useSearchSuggestions();

    return <SearchSuggestionsContext.Provider value={value}>
        {props.children}
    </SearchSuggestionsContext.Provider>
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


export function SearchView() {
    const {suggestionsSums, suggestions} = useContext(SearchSuggestionsContext);

    let filesTabName = 'Files';
    let zimsTabName = 'Zims';
    if (!_.isEmpty(suggestionsSums)) {
        filesTabName = `Files (${normalizeEstimate(suggestionsSums.fileGroups)})`;
        zimsTabName = `Zims (${normalizeEstimate(suggestionsSums.zims)})`;
    }

    const links = [
        {text: filesTabName, to: '/search', key: 'filesSearch', end: true},
        {text: zimsTabName, to: '/search/zim', key: 'zimsSearch'},
    ]

    return <React.Fragment>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/*' element={<FilesSearchView/>}/>
            <Route path='/zim' exact element={<ZimSearchView estimates={suggestions}/>}/>
        </Routes>
    </React.Fragment>
}
