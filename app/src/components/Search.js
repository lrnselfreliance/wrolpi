import React, {useContext, useState} from "react";
import {createSearchParams, Route, Routes, useNavigate} from "react-router-dom";
import {FileSearchFilterButton, FilesSearchView} from "./Files";
import {useLatestRequest, usePages, useQuery} from "../hooks/customHooks";
import {ZimSearchView} from "./Zim";
import {searchEstimateFiles, searchEstimateZims, searchSuggestions} from "../api";
import {fuzzyMatch, normalizeEstimate, SearchResultsInput, TabLinks} from "./Common";
import _ from "lodash";
import {TagsContext} from "../Tags";
import {Header as SHeader, Label} from "semantic-ui-react";
import {Button, Modal, ModalContent} from "./Theme";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";

export const SearchSuggestionsContext = React.createContext({
    suggestionsResults: {},
    suggestions: {},
    suggestionsSums: {},
    handleResultSelect: null,
    resultRenderer: null,
    loading: false,
    searchStr: '',
    setSearchStr: null,
});


export const SearchSuggestionsProvider = (props) => {
    const value = useSearchSuggestions();

    return <SearchSuggestionsContext.Provider value={value}>
        {props.children}
    </SearchSuggestionsContext.Provider>
}

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

export function useSuggestions(searchStr) {
    const {data, sendRequest, loading} = useLatestRequest(500);

    React.useEffect(() => {
        if (!searchStr || searchStr.length === 0) {
            return;
        }

        // Use the `useLatestRequest` to handle user typing.
        sendRequest(async () => await searchSuggestions(searchStr));
    }, [searchStr, sendRequest]);

    return {suggestions: data, loading}
}


export function useSearchSuggestions(defaultSearchStr) {
    const navigate = useNavigate();
    const [searchStr, setSearchStr] = React.useState(defaultSearchStr || '');
    const {SingleTag, fuzzyMatchTagsByName} = React.useContext(TagsContext);
    const {suggestions, loading} = useSuggestions(searchStr);

    // The results that will be displayed by <Search>.
    const [suggestionsResults, setSuggestionsResults] = useState({});
    // The results summarized.
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

        const zimSum = newSuggestions.zimsEstimates.reduce((i, j) => i + j, 0);
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
        handleResultSelect,
        resultRenderer,
        loading
    }
}


export function useSearchEstimate(searchStr, tagNames) {
    const {data: filesData, sendRequest: sendFilesRequest, loading: loadingFiles} = useLatestRequest(250);
    const {data: zimsData, sendRequest: sendZimsRequest, loading: loadingZims} = useLatestRequest(250);

    // The estimates from the response.
    const [estimates, setEstimates] = React.useState({
        fileGroups: [],
        zims: [],
    });
    // The estimates summarized.
    const [estimatesSums, setEstimatesSums] = React.useState({
        fileGroups: 0,
        zims: 0,
    });

    React.useEffect(() => {
        // Handle results from `sendRequest`.
        if (_.isEmpty(filesData)) {
            return;
        }

        setEstimates({...estimates, fileGroups: filesData.fileGroups});
        setEstimatesSums({...estimatesSums, fileGroups: filesData.fileGroups});
    }, [JSON.stringify(filesData)]);

    React.useEffect(() => {
        sendFilesRequest(async () => await searchEstimateFiles(searchStr, tagNames));
    }, [searchStr, JSON.stringify(tagNames)], sendFilesRequest);

    React.useEffect(() => {
        // Handle results from `sendRequest`.
        if (_.isEmpty(zimsData)) {
            return;
        }

        setEstimates({...estimates, zimsEstimates: zimsData.zimsEstimates});
        setEstimatesSums({...estimatesSums, zims: zimsData.zimsEstimates.reduce((i, j) => i + j['estimate'], 0)});
    }, [JSON.stringify(zimsData)]);

    React.useEffect(() => {
        sendZimsRequest(async () => await searchEstimateZims(searchStr, tagNames));
    }, [searchStr, JSON.stringify(tagNames)], sendZimsRequest);

    return {
        estimates,
        estimatesSums,
        loading: loadingFiles || loadingZims,
    }
}


export function SearchView() {
    const {searchStr, activeTags} = useSearch();
    const {estimates, estimatesSums, loading} = useSearchEstimate(searchStr, activeTags);

    let filesTabName = <span>Files <Label>?</Label></span>;
    let zimsTabName = <span>Zims<Label>?</Label></span>;
    if (!_.isEmpty(estimatesSums)) {
        filesTabName = <span>Files <Label>{normalizeEstimate(estimatesSums.fileGroups)}</Label></span>;
        zimsTabName = <span>Zims <Label>{normalizeEstimate(estimatesSums.zims)}</Label></span>;
    }

    const links = [
        {text: filesTabName, to: '/search', key: 'filesSearch', end: true},
        {text: zimsTabName, to: '/search/zim', key: 'zimsSearch'},
    ]

    return <React.Fragment>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/*' element={<FilesSearchView/>}/>
            <Route path='/zim' exact element={<ZimSearchView estimates={estimates} loading={loading}/>}/>
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
