import React, {useContext, useState} from "react";
import {createSearchParams, Route, Routes, useNavigate} from "react-router-dom";
import {FileSearchFilterButton, FilesSearchView} from "./Files";
import {useLatestRequest, usePages, useQuery} from "../hooks/customHooks";
import {ZimSearchView} from "./Zim";
import {searchEstimateZims, searchSuggestions} from "../api";
import {fuzzyMatch, normalizeEstimate, SearchResultsInput, TabLinks} from "./Common";
import _ from "lodash";
import {TagsContext} from "../Tags";
import {Header as SHeader, Label} from "semantic-ui-react";
import {Button, Modal, ModalContent} from "./Theme";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";

const SUGGESTED_APPS = [
    {location: '/admin', title: 'Downloads', description: 'View and control your downloads'},
    {location: '/admin/settings', title: 'Hotspot', description: 'Control your hotspot'},
    {location: '/admin/settings', title: 'Restart', description: 'Restart your WROLPi'},
    {location: '/admin/settings', title: 'Settings', description: 'View and modify your settings'},
    {location: '/admin/settings', title: 'Shutdown', description: 'Shutdown your WROLPi'},
    {location: '/admin/status', title: 'Status', description: 'View the status of this WROLPi server'},
    {location: '/admin/wrol', title: 'WROL Mode', description: 'Enable or disable WROL Mode'},
    {location: '/archive', title: 'Archives', description: 'View your Archives'},
    {location: '/archive/domains', title: 'Domains', description: 'View the domains of your Archives'},
    {location: '/files', title: 'Files', description: 'View your files'},
    {location: '/help', title: 'Help', description: 'Help documents for WROLPi'},
    {location: '/inventory', title: 'Inventory', description: 'Track and organize your food storage'},
    {location: '/map', title: 'Map', description: 'View your Map'},
    {location: '/map/manage', title: 'Manage Map', description: 'Manage your Map'},
    {location: '/more/otp', title: 'One Time Pad', description: 'Encrypt and Decrypt messages'},
    {location: '/more/statistics', title: 'Statistics', description: 'View the statistics of your WROLPi'},
    {location: '/more/vin', title: 'Vin Decoder', description: 'Decode and analyze vehicle VIN numbers'},
    {location: '/videos', title: 'Videos', description: 'View your Videos'},
    {location: '/videos/channel', title: 'Channels', description: 'View the Channels of your Videos'},
    {location: '/zim', title: 'Zim', description: 'View your Zims'},
    {location: '/zim/manage', title: 'Manage Zim', description: 'Manage your Zims'},
];

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

export const SearchSuggestionsContext = React.createContext({
    suggestions: {}, // from the api
    suggestionsResults: {}, // suggestions converted for <Search/> results.
    suggestionsSums: {}, // suggestions from the api summarized.
    handleResultSelect: null, // user clicks "result"
    resultRenderer: null,
    loading: false,
    searchStr: '',
    setSearchStr: null,
    setSearchTags: null,
});

export function useSuggestions(searchStr, tagNames) {
    const defaultSuggestions = {
        fileGroups: [],
        channels: [],
        domains: [],
        zimsEstimates: [],
    }
    const [suggestions, setSuggestions] = React.useState(defaultSuggestions);
    // fileGroups/channels/domains.
    const {data, sendRequest, loading} = useLatestRequest(500, true);
    // Zims are slow, so they are separate.
    const {data: zimData, sendRequest: sendZimRequest, loading: zimLoading} = useLatestRequest(500, true);

    React.useEffect(() => {
        if ((searchStr && searchStr.length > 0) || (tagNames && tagNames.length > 0)) {
            sendRequest(async () => await searchSuggestions(searchStr, tagNames));
            sendZimRequest(async () => await searchEstimateZims(searchStr, tagNames));
        }
    }, [searchStr, sendRequest, sendZimRequest, JSON.stringify(tagNames)]);

    React.useEffect(() => {
        if (!_.isEmpty(data)) {
            setSuggestions({
                ...suggestions,
                channels: data.channels,
                fileGroups: data.fileGroups,
                domains: data.domains,
            });
        }
    }, [JSON.stringify(data)]);

    React.useEffect(() => {
        if (!_.isEmpty(zimData)) {
            setSuggestions({...suggestions, zimsEstimates: zimData.zimsEstimates});
        }
    }, [JSON.stringify(zimData)]);

    return {suggestions, loading: loading || zimLoading}
}


export function useSearchSuggestions(defaultSearchStr, defaultTagNames) {
    const navigate = useNavigate();
    const [searchStr, setSearchStr] = React.useState(defaultSearchStr || '');
    const [searchTags, setSearchTags] = React.useState(defaultTagNames);
    const {SingleTag, fuzzyMatchTagsByName} = React.useContext(TagsContext);
    const {suggestions, loading} = useSuggestions(searchStr, searchTags);

    // The results that will be displayed by <Search>.
    const [suggestionsResults, setSuggestionsResults] = useState({});
    // The results summarized.
    const [suggestionsSums, setSuggestionsSums] = useState({});

    const normalizeSuggestionsResults = (newSuggestions) => {
        // Convert the suggestions from the Backend to what the Semantic <Search> expects.
        const lowerSearchStr = searchStr ? searchStr.toLowerCase() : '';

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

        const zimSum = newSuggestions.zimsEstimates && newSuggestions.zimsEstimates.length > 0
            ? newSuggestions.zimsEstimates.reduce((i, j) => i + j.estimate, 0)
            : null;
        if (newSuggestions && zimSum > 0) {
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

        // Match at most 5 Tags.
        const matchingTags = searchStr ? fuzzyMatchTagsByName(searchStr).slice(0, 5) : null;
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
            // Match at most 5 apps.
            results.apps = {name: 'Apps', results: matchingApps.slice(0, 5)};
        }

        setSuggestionsResults(results);
        setSuggestionsSums({
            fileGroups: newSuggestions.fileGroups,
            zims: zimSum,
            channels: newSuggestions.channels.length,
            domains: newSuggestions.domains.length,
            tags: matchingTags?.length,
            apps: matchingApps?.length,
        });
    }

    React.useEffect(() => {
        setSuggestionsSums({});
        setSuggestionsResults({});

        if (!_.isEmpty(suggestions)) {
            normalizeSuggestionsResults(suggestions);
        }
    }, [JSON.stringify(suggestions)]);

    // User clicked on a result in the dropdown.
    const handleResultSelect = ({result}) => navigate(result.location);

    const resultRenderer = ({type, title, description}) => {
        if (type === 'tag') {
            return <SingleTag name={title}/>;
        }

        if (description) {
            return <>
                <SHeader as='h4'>{title}</SHeader>
                {description}
            </>
        }
        // No specific renderer, use the generic.
        return <span>{title}</span>
    };

    return {
        suggestions,
        suggestionsResults,
        suggestionsSums,
        searchStr,
        setSearchStr,
        setSearchTags,
        handleResultSelect,
        resultRenderer,
        loading
    }
}


export const SearchSuggestionsProvider = (props) => {
    const value = useSearchSuggestions();

    return <SearchSuggestionsContext.Provider value={value}>
        {props.children}
    </SearchSuggestionsContext.Provider>
}


export function SearchView() {
    const {suggestions, suggestionsSums, loading} = useContext(SearchSuggestionsContext);

    const filesTabName = <span>Files <Label>{normalizeEstimate(suggestionsSums?.fileGroups)}</Label></span>;
    const zimsTabName = <span>Zims <Label>{normalizeEstimate(suggestionsSums?.zims)}</Label></span>;

    const links = [
        {text: filesTabName, to: '/search', key: 'filesSearch', end: true},
        {text: zimsTabName, to: '/search/zim', key: 'zimsSearch'},
    ]

    return <React.Fragment>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/*' element={<FilesSearchView/>}/>
            <Route path='/zim' exact element={<ZimSearchView suggestions={suggestions} loading={loading}/>}/>
        </Routes>
    </React.Fragment>
}

export function SearchIconButton() {
    // A single button which displays a modal for search suggestions.
    const {
        suggestionsResults,
        handleResultSelect,
        resultRenderer,
        loading,
        searchStr,
        setSearchStr,
    } = useContext(SearchSuggestionsContext);
    const [open, setOpen] = React.useState(false);

    const localHandleResultSelect = (i) => {
        // Close modal when user selects a result.
        setOpen(false);
        handleResultSelect(i);
    }

    return <React.Fragment>
        <Button icon='search' onClick={() => setOpen(!open)}/>
        <Modal open={open} onClose={() => setOpen(false)} centered={false}>
            <ModalContent>
                <Grid columns={2}>
                    <Grid.Row>
                        <Grid.Column mobile={13} computer={14}>
                            <SearchResultsInput clearable
                                                searchStr={searchStr}
                                                onChange={setSearchStr}
                                                onSubmit={setSearchStr}
                                                size='large'
                                                placeholder='Search everywhere...'
                                                results={suggestionsResults}
                                                handleResultSelect={localHandleResultSelect}
                                                resultRenderer={resultRenderer}
                                                loading={loading}
                            />
                        </Grid.Column>
                        <Grid.Column mobile={3} computer={2}>
                            <FileSearchFilterButton/>
                        </Grid.Column>
                    </Grid.Row>
                </Grid>
            </ModalContent>
        </Modal>
    </React.Fragment>
}
