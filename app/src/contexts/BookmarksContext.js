import React, {createContext, useCallback, useContext, useEffect, useState} from 'react';
import {getBookmarks} from '../api';

/*
 * The user's bookmarks, shared by the navigation bar and the editor page.
 *
 * A context rather than a prop: the bar and the page are far apart in the tree, and an
 * edit on the page must show in the bar at once.  `bookmarks` is null until the first
 * fetch answers, so the bar can tell "not loaded yet" from "the user has none".
 */
export const BookmarksContext = createContext({bookmarks: null, error: null, refresh: async () => null});

export function BookmarksProvider({children}) {
    const [bookmarks, setBookmarks] = useState(null);
    const [error, setError] = useState(null);

    const refresh = useCallback(async () => {
        try {
            setBookmarks(await getBookmarks());
            setError(null);
        } catch (err) {
            setError(err);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return <BookmarksContext.Provider value={{bookmarks, error, refresh}}>
        {children}
    </BookmarksContext.Provider>;
}

export function useBookmarks() {
    return useContext(BookmarksContext);
}

export const isBookmarkDirectory = (node) => Array.isArray(node.children);

/**
 * Where a bookmark URL really points, from the browser's point of view.
 *
 * Three forms are accepted, and only the first is an in-app link:
 *   `/videos/channel/3`   a path on this WROLPi -> {internal: true, href: '/videos/channel/3'}
 *   `:8096/web`           a port on this host, using the page's scheme
 *   `http://:8096/web`    a port on this host, with its own scheme
 *   `https://example.com` anything else, verbatim
 *
 * The host-relative forms exist because a WROLPi is reached by LAN IP, by mDNS name, and
 * by its hotspot address, and a service running beside it is reached the same way.  A
 * bookmark with the hostname written in would work from only one of them.
 */
export function resolveBookmarkUrl(url, location = window.location) {
    const value = (url || '').trim();
    if (value.startsWith('/')) {
        return {internal: true, href: value};
    }
    const hostRelative = value.match(/^(?:(https?:)\/\/)?(:\d+.*)$/i);
    if (hostRelative) {
        const scheme = hostRelative[1] ? hostRelative[1].toLowerCase() : location.protocol;
        return {internal: false, href: `${scheme}//${location.hostname}${hostRelative[2]}`};
    }
    return {internal: false, href: value};
}
