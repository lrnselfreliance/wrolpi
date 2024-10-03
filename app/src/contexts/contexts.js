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
    saveSettings: null,
    pending: false,
});

// `useQuery`
export const QueryContext = React.createContext({
    searchParams: null,
    setSearchParams: null,
    updateQuery: null,
    getLocationStr: null,
});

export const AppMedia = createMedia({
    breakpoints: {
        mobile: 0, tablet: 700, computer: 1024,
    }
});
export const mediaStyles = AppMedia.createMediaStyle();
export const {Media, MediaContextProvider} = AppMedia;
