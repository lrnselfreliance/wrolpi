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

// Characters a URL parser strips or that split a URL in surprising places.  See the
// same rule in wrolpi/bookmarks.py; the two must agree.
// eslint-disable-next-line no-control-regex -- matching control characters is the point
const FORBIDDEN = /[\x00-\x20\x7f\\]/;
const PORT_FORM = /^(?:(https?):\/\/)?:(\d{1,5})(?=$|[/?#])(.*)$/i;
const PORT_FORM_START = /^(?:https?:\/\/)?:/i;

const NONE = {internal: false, href: null};

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
 *
 * Anything else, including a stored value the server would refuse today, resolves to a
 * null href and is rendered as text rather than a link: the form each value claims is
 * checked by parsing it, never by its prefix, because `//evil.com` starts like a path and
 * `:8096@evil.com` starts like a port, and a browser takes both off this host.
 */
export function resolveBookmarkUrl(url, location = window.location) {
    const value = (url || '').trim();
    if (!value || FORBIDDEN.test(value)) {
        return NONE;
    }
    const origin = `${location.protocol}//${location.host}`;

    if (PORT_FORM_START.test(value)) {
        const match = value.match(PORT_FORM);
        if (!match || match[3].includes('@')) {
            return NONE;
        }
        const [, scheme, port, tail] = match;
        // An IPv6 literal has to be bracketed to sit before a port.  Browsers report it
        // bracketed already; tests and older code may not.
        const bare = location.hostname.replace(/^\[|]$/g, '');
        const host = bare.includes(':') ? `[${bare}]` : bare;
        const href = `${scheme ? `${scheme.toLowerCase()}:` : location.protocol}//${host}:${port}${tail}`;
        const parsed = parse(href);
        if (!parsed || parsed.hostname !== host || parsed.port !== port) {
            return NONE;
        }
        return {internal: false, href};
    }

    if (value.startsWith('/')) {
        const parsed = parse(value, origin);
        if (value.startsWith('//') || !parsed || parsed.origin !== origin) {
            return NONE;
        }
        return {internal: true, href: value};
    }

    const parsed = parse(value);
    if (!parsed || (parsed.protocol !== 'http:' && parsed.protocol !== 'https:')) {
        return NONE;
    }
    return {internal: false, href: value};
}

function parse(value, base) {
    try {
        return new URL(value, base);
    } catch {
        return null;
    }
}
