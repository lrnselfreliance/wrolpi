import React from "react";
import {createMedia} from "@artsy/fresnel";

export const ThemeContext = React.createContext({theme: null, i: {}});

export const StatusContext = React.createContext({
    status: {},
    fetchStatus: null,
});

export const SettingsContext = React.createContext({
    settings: {},
    fetchSettings: null,
});

// Multiple providers for this context!
export const QueryContext = React.createContext({
    searchParams: null,
    setSearchParams: null,
    updateQuery: null,
    getLocationStr: null,
    clearQuery: null,
});

export const SearchGlobalContext = React.createContext({
    loading: false,
    pages: null,
    searchStr: null, setSearchStr: null, clearSearch: null, fetchSuggestions: null,
    pendingSearchStr: null, setPendingSearchStr: null, submitSearch: null,
    filter: null, setFilter: null,
    months: null, setMonths: null,
    dateRange: null, setDateRange: null,
    activeTags: null, setSearchTags: null, addTag: null, removeTag: null,
    model: null, setModel: null,
    view: null, setView: null,
    order: null, setOrder: null,
    suggestions: null, suggestionsResults: null, suggestionsSums: null,
    resultRenderer: null,
    getSearchResultsInput: null,
});

export const AppMedia = createMedia({
    breakpoints: {
        mobile: 0, tablet: 700, computer: 1024,
    }
});
export const mediaStyles = AppMedia.createMediaStyle();
export const {Media, MediaContextProvider} = AppMedia;
