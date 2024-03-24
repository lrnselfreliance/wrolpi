import React, {useState} from "react";
import {Route, Routes, useNavigate} from "react-router-dom";
import {FilesSearchView} from "./Files";
import {
    useLatestRequest,
    usePages,
    useSearchDateRange,
    useSearchFilter,
    useSearchModel,
    useSearchMonths,
    useSearchOrder,
    useSearchStr,
    useSearchTags,
    useSearchView
} from "../hooks/customHooks";
import {ZimSearchView} from "./Zim";
import {filesSearch, searchEstimateZims, searchSuggestions} from "../api";
import {filterToMimetypes, fuzzyMatch, normalizeEstimate, SearchResultsInput, TabLinks} from "./Common";
import _ from "lodash";
import {TagsContext} from "../Tags";
import {Button as SButton, Header as SHeader, Label} from "semantic-ui-react";
import {Modal, ModalContent} from "./Theme";
import {QueryContext, SearchGlobalContext} from "../contexts/contexts";
import {toast} from "react-semantic-toasts-2";

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

export const useSearchQuery = () => {
    // The URL query parameters used to filter FileGroups and Zims.

    const {clearQuery} = React.useContext(QueryContext);
    // q=...
    const {
        searchStr, setSearchStr, submitSearch, submitGlobalSearch,
        pendingSearchStr, setPendingSearchStr,
    } = useSearchStr();
    // month=1&month=2
    const {months, setMonths} = useSearchMonths();
    // fromDate=...&toDate=...
    const {dateRange, setDateRange} = useSearchDateRange();
    // tag=Name1&tag=Name2
    const {activeTags, setSearchTags, addTag, removeTag} = useSearchTags();
    // o=0&l=24
    const pages = usePages();
    // video, image, etc.
    const {filter, setFilter} = useSearchFilter();
    // archive/video/ebook/etc.
    const {model, setModel} = useSearchModel();
    // view=highlight
    const {view, setView} = useSearchView()
    // o=...
    const {order, setOrder} = useSearchOrder();

    // TODO global clear button does nothing

    // Shorthand for React.useEffect to detect when these values change.
    const effect = JSON.stringify({
        searchStr, months, dateRange, activeTags, pages: pages.effect, filter, model, view, order
    });

    const clearSearch = () => {
        clearQuery();
        setPendingSearchStr('');
    }

    return {
        searchStr, setSearchStr, clearSearch, pendingSearchStr, setPendingSearchStr, submitSearch, submitGlobalSearch,
        months, setMonths,
        dateRange, setDateRange,
        activeTags, setSearchTags, addTag, removeTag,
        pages,
        filter, setFilter,
        model, setModel,
        view, setView,
        order, setOrder,
        effect,
    }
}

export function SearchGlobalProvider({...props}) {
    const value = useSearchGlobal();
    return <SearchGlobalContext.Provider value={value}>
        {props.children}
    </SearchGlobalContext.Provider>
}

export const useSearchGlobal = () => {
    // Used to search Files and Zims.  Modifies URL query when user submits search.
    const emptySearch = false;

    const navigate = useNavigate();
    const {queryNavigate} = React.useContext(QueryContext);
    const {SingleTag, fuzzyMatchTagsByName} = React.useContext(TagsContext);

    const searchQuery = useSearchQuery();
    const {
        searchStr, clearSearch, pendingSearchStr, setPendingSearchStr, submitSearch, submitGlobalSearch,
        months, setMonths,
        dateRange, setDateRange,
        activeTags, setSearchTags, addTag, removeTag,
        pages,
        filter, setFilter,
        model,
        view, setView,
        order, setOrder,
    } = searchQuery;

    const [searchFiles, setSearchFiles] = useState(null);
    const headline = view === 'headline';

    const emptySuggestions = {
        fileGroups: [],
        channels: [],
        domains: [],
        zimsEstimates: [],
    }
    const [suggestions, setSuggestions] = React.useState(emptySuggestions);
    // fileGroups/channels/domains.
    const {data: filesData, sendRequest: sendFilesRequest, loading: filesLoading} = useLatestRequest(500);
    // Zims are slow, so they are separate.
    const {data: zimData, sendRequest: sendZimRequest, loading: zimLoading} = useLatestRequest(500);

    const fetchSuggestions = () => {
        if ((pendingSearchStr && pendingSearchStr.length > 0) || (activeTags && activeTags.length > 0)) {
            const mimetypes = filterToMimetypes(filter);
            sendFilesRequest(async () => await searchSuggestions(pendingSearchStr, activeTags, mimetypes, months, dateRange));
            sendZimRequest(async () => await searchEstimateZims(pendingSearchStr, activeTags));
        }
    }

    React.useEffect(() => {
        if (!_.isEmpty(filesData)) {
            setSuggestions({
                ...suggestions,
                channels: filesData.channels,
                fileGroups: filesData.fileGroups,
                domains: filesData.domains,
            });
        }
    }, [JSON.stringify(filesData)]);

    React.useEffect(() => {
        if (!_.isEmpty(zimData)) {
            setSuggestions({...suggestions, zimsEstimates: zimData.zimsEstimates});
        }
    }, [JSON.stringify(zimData)]);

    // The results that will be displayed by <Search>.
    const [suggestionsResults, setSuggestionsResults] = useState({});
    // The results summarized.
    const [suggestionsSums, setSuggestionsSums] = useState({});

    const noResults = [{title: 'No results'}];

    const normalizeSuggestionsResults = (newSuggestions) => {
        // Convert the suggestions from the Backend to what the Semantic <Search> expects.
        const lowerPendingStr = pendingSearchStr ? pendingSearchStr.toLowerCase() : '';

        let results = {};

        // Suggested results are ordered.
        if (newSuggestions.fileGroups > 0) {
            results.fileGroups = {
                name: 'Files', results: [
                    {
                        title: newSuggestions.fileGroups.toString(),
                        type: 'files',
                        // Add search query onto current location.
                        location: [{q: pendingSearchStr}, '/search'],
                    }
                ]
            };
        } else if (newSuggestions.fileGroups === 0) {
            // Tell the user there are no files.
            results.fileGroups = {name: 'Files', results: noResults};
        }

        const zimSum = newSuggestions.zimsEstimates && newSuggestions.zimsEstimates.length > 0
            ? newSuggestions.zimsEstimates.reduce((i, j) => i + j.estimate, 0)
            : null;
        if (newSuggestions && zimSum > 0) {
            results.zimsSum = {
                name: 'Zims', results: [
                    // Navigating to Zims is not relative. We don't want to keep filters or other extra params.
                    {
                        title: zimSum.toString(),
                        type: 'zims',
                        location: [{q: pendingSearchStr}, '/search/zim'],
                    }
                ],
            };
        } else if (newSuggestions && zimSum === 0) {
            results.zimsSum = {name: 'Zims', results: noResults};
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
                        location: [{domain: i.domain}, '/archive'],
                    }
                })
            }
        }

        // Match at most 5 Tags.
        const matchingTags = pendingSearchStr ? fuzzyMatchTagsByName(pendingSearchStr).slice(0, 5) : null;
        if (matchingTags && matchingTags.length > 0) {
            results.tags = {
                name: 'Tags', results: matchingTags.map(i => {
                    return {type: 'tag', title: i.name, location: [{tag: i.name}, '/search']}
                })
            }
        }

        const matchingApps = SUGGESTED_APPS.filter(i =>
            i.title.toLowerCase().includes(lowerPendingStr)
            || fuzzyMatch(i.title.toLowerCase(), lowerPendingStr));
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
    const handleResultSelect = ({result}) => {
        if (typeof result.location === 'string') {
            console.info(`queryNavigate string: ${result.location}`);
            navigate(result.location);
        } else if (Array.isArray(result.location) && result.location.length === 2) {
            console.info(`queryNavigate special: ${result.location}`);
            queryNavigate(result.location[0], result.location[1]);
        } else {
            console.error('No location to navigate');
        }
    }

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

    const fetchFiles = async () => {
        if (!emptySearch && !searchStr && !activeTags) {
            return;
        }
        const mimetypes = filterToMimetypes(filter);
        setSearchFiles(null);
        let fromYear;
        let toYear;
        if (dateRange) {
            fromYear = dateRange[0];
            toYear = dateRange[1];
        }
        try {
            let [file_groups, total] = await filesSearch(
                pages.offset, pages.limit, searchStr, mimetypes, model, activeTags, headline,
                months, fromYear, toYear);
            setSearchFiles(file_groups);
            pages.setTotal(total);
        } catch (e) {
            pages.setTotal(0);
            console.error(e);
            toast({
                type: 'error',
                title: 'Unexpected server response',
                description: 'Could not get files',
                time: 5000,
            });
        }
    }

    const localSetSearchStr = (newSearchStr) => {
        queryNavigate({q: newSearchStr, o: null});
    }

    return {
        loading: filesLoading || zimLoading,
        pages,
        searchStr, setSearchStr: localSetSearchStr, clearSearch,
        pendingSearchStr, setPendingSearchStr, submitSearch, submitGlobalSearch,
        filter, setFilter,
        months, setMonths,
        dateRange, setDateRange,
        activeTags, setSearchTags, addTag, removeTag,
        view, setView,
        order, setOrder,
        suggestions, suggestionsResults, suggestionsSums,
        searchFiles,
        resultRenderer,
        handleResultSelect,
        effect: searchQuery.effect,
        fetchSuggestions, fetchFiles,
    }
}


export function SearchView() {
    const {suggestions, suggestionsSums, loading} = React.useContext(SearchGlobalContext);

    const filesTabName = <span>Files <Label>{normalizeEstimate(suggestionsSums?.fileGroups)}</Label></span>;
    const zimsTabName = <span>Zims <Label>{normalizeEstimate(suggestionsSums?.zims)}</Label></span>;

    const links = [
        {text: filesTabName, to: '/search', key: 'filesSearch', end: true, replace: false},
        {text: zimsTabName, to: '/search/zim', key: 'zimsSearch', replace: false},
    ];

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
        pendingSearchStr, setPendingSearchStr, clearSearch, submitGlobalSearch,
        fetchSuggestions,
    } = React.useContext(SearchGlobalContext);
    const [open, setOpen] = React.useState(false);

    const localHandleResultSelect = (i) => {
        // Close modal when user selects a result.
        setOpen(false);
        handleResultSelect(i);
    }

    const localSubmitSearch = () => {
        // Close modal when user searches.  Use the global search page.
        submitGlobalSearch();
        setOpen(false);
    }

    React.useEffect(() => {
        // Fetch suggestions only when this modal is open and user is typing.
        if (open) {
            fetchSuggestions();
        }
    }, [pendingSearchStr]);

    return <React.Fragment>
        <SButton
            icon='search'
            color='blue'
            style={{padding: '0.6em', paddingBottom: '0.55em'}}
            onClick={() => setOpen(!open)}
        />
        <Modal open={open} onClose={() => setOpen(false)} centered={false}>
            <ModalContent>
                <SearchResultsInput clearable
                                    searchStr={pendingSearchStr}
                                    onChange={setPendingSearchStr}
                                    onSubmit={localSubmitSearch}
                                    onClear={clearSearch}
                                    size='large'
                                    placeholder='Search everywhere...'
                                    results={suggestionsResults}
                                    handleResultSelect={localHandleResultSelect}
                                    resultRenderer={resultRenderer}
                                    loading={loading}
                                    autoFocus={true}
                />
            </ModalContent>
        </Modal>
    </React.Fragment>
}
