import React, {useEffect, useState} from 'react';
import {ThemeContext} from "../contexts/contexts";
import {MantineProvider} from "@mantine/core";
import {Notifications} from "@mantine/notifications";
import {cssVariablesResolver, mantineTheme} from "../themes/mantine";
import {
    amberTheme,
    darkTheme,
    defaultTheme,
    isDarkTheme,
    isThemeName,
    lightTheme,
    mediaFilterSessionKey,
    nightTheme,
    resolveMediaFilter,
    systemTheme,
    themeChoices,
    themeMediaFilter,
    themeNames,
    themeSessionKey,
} from "../themes/names";
import _ from "lodash";
import {ThemeContextValue, ThemeName, SavedThemeName} from "../types/theme";

// Theme names and picker choices live in themes/names, and are re-exported here because
// most call sites already import them from Theme.
export {
    amberTheme,
    darkTheme,
    defaultTheme,
    isDarkTheme,
    lightTheme,
    nightTheme,
    systemTheme,
    themeChoices,
    themeMediaFilter,
    themeNames,
    themeSessionKey,
};

/** Resolve the saved preference to the theme that should be applied right now. */
export const resolveTheme = (saved: SavedThemeName): ThemeName => {
    if (isThemeName(saved)) {
        return saved;
    }
    // `system`, null, or a value written by an older version.
    const prefersDark = typeof window.matchMedia === 'function'
        && window.matchMedia('(prefers-color-scheme: dark)').matches;
    return prefersDark ? darkTheme : lightTheme;
}

const readSavedTheme = (): SavedThemeName => {
    try {
        const value = localStorage.getItem(themeSessionKey);
        if (isThemeName(value) || value === systemTheme) {
            return value;
        }
    } catch (e) {
        // localStorage can throw when cookies/storage are blocked.
        console.error('Unable to read the saved theme', e);
    }
    return null;
}

/**
 * The user's per-theme media filter choices: `{night: false}` means "night, but
 * do not filter media".  A theme absent from the map follows its own default.
 */
const readMediaFilters = (): Partial<Record<ThemeName, boolean>> => {
    try {
        const raw = localStorage.getItem(mediaFilterSessionKey);
        if (raw) {
            const parsed = JSON.parse(raw);
            // Only keep known themes with boolean values; the rest is someone else's data.
            if (parsed && typeof parsed === 'object') {
                return Object.fromEntries(Object.entries(parsed)
                    .filter(([key, value]) => isThemeName(key) && typeof value === 'boolean'));
            }
        }
    } catch (e) {
        // Blocked storage, or a value an older version wrote.
        console.error('Unable to read the media filter settings', e);
    }
    return {};
}

interface ThemeProviderProps {
    children: React.ReactNode;
}

export function ThemeProvider({children, ...props}: ThemeProviderProps) {
    if (!_.isEmpty(props)) {
        console.log(props);
        console.error('ThemeWrapper does not support props!');
    }

    // savedTheme is the user's preference: a theme name, `system`, or null (never chosen).
    const [savedTheme, setSavedTheme] = useState<SavedThemeName>(readSavedTheme);
    // theme is what is currently applied.
    const [theme, setThemeName] = useState<ThemeName>(() => resolveTheme(readSavedTheme()));

    // Which themes the user has turned media filtering on or off for.
    const [mediaFilters, setMediaFilters] = useState<Partial<Record<ThemeName, boolean>>>(
        readMediaFilters);

    // `data-theme` on <html> is what the token CSS keys off of.  index.html stamps it before
    // first paint from the same localStorage value, so the first render already matches.
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
    }, [theme]);

    // `data-media-filter` names the filter to apply, or is absent when nothing should be
    // filtered.  index.html stamps this too: a flash of unfiltered thumbnails before the
    // bundle arrives would cost the user the dark adaptation night mode exists to protect.
    useEffect(() => {
        const filter = resolveMediaFilter(theme, mediaFilters);
        if (filter) {
            document.documentElement.setAttribute('data-media-filter', filter);
        } else {
            document.documentElement.removeAttribute('data-media-filter');
        }
    }, [theme, mediaFilters]);

    // Follow the OS preference only while the user has not chosen a specific theme.
    useEffect(() => {
        if (isThemeName(savedTheme) || typeof window.matchMedia !== 'function') {
            return;
        }
        const query = window.matchMedia('(prefers-color-scheme: dark)');
        const onChange = () => setThemeName(resolveTheme(savedTheme));
        query.addEventListener('change', onChange);
        return () => query.removeEventListener('change', onChange);
    }, [savedTheme]);

    const saveTheme = (value: SavedThemeName) => {
        setSavedTheme(value);
        try {
            if (value === null) {
                localStorage.removeItem(themeSessionKey);
            } else {
                localStorage.setItem(themeSessionKey, value);
            }
        } catch (e) {
            console.error('Unable to save the theme', e);
        }
    }

    /** Apply and persist a theme.  Pass `system` to follow the OS preference. */
    const setTheme = (value: SavedThemeName) => {
        if (value !== systemTheme && value !== null && !isThemeName(value)) {
            console.error(`Unknown theme! ${value}`);
            return;
        }
        saveTheme(value);
        setThemeName(resolveTheme(value));
    }

    /**
     * Turn the current theme's media filter on or off.  Stored per theme, so a user who
     * wants amber's tint but not night's — or the reverse — gets both.
     */
    const setMediaFilterEnabled = (enabled: boolean) => {
        const next = {...mediaFilters, [theme]: enabled};
        setMediaFilters(next);
        try {
            localStorage.setItem(mediaFilterSessionKey, JSON.stringify(next));
        } catch (e) {
            console.error('Unable to save the media filter setting', e);
        }
    }

    // Retained for callers written against the old two-theme API.
    const setDarkTheme = (save = false) => {
        setThemeName(darkTheme);
        if (save) saveTheme(darkTheme);
    }

    const setLightTheme = (save = false) => {
        setThemeName(lightTheme);
        if (save) saveTheme(lightTheme);
    }

    const cycleSavedTheme = (e?: React.MouseEvent) => {
        // Cycle: System -> Light -> Dark -> Night -> Amber -> System
        if (e) {
            e.preventDefault();
        }
        const order: SavedThemeName[] = [systemTheme, ...themeNames];
        const current = order.indexOf(isThemeName(savedTheme) ? savedTheme : systemTheme);
        setTheme(order[(current + 1) % order.length]);
    }

    const dark = isDarkTheme(theme);

    const themeValue: ThemeContextValue = {
        theme,
        savedTheme,
        isDark: dark,
        // The filter this theme offers, if any, and whether it is currently applied.
        mediaFilter: themeMediaFilter(theme),
        mediaFilterEnabled: !!resolveMediaFilter(theme, mediaFilters),
        setMediaFilterEnabled,
        setTheme,
        setDarkTheme,
        setLightTheme,
        cycleSavedTheme,
    };

    // Mantine's own scheme decides the surfaces its internals use (overlays, scrollbars,
    // focus rings).  Night and amber are neither of its two schemes, so they ride on dark
    // and take their actual colors from our tokens.  This is the theme `base` flag.
    return <ThemeContext.Provider value={themeValue}>
        <MantineProvider
            theme={mantineTheme}
            cssVariablesResolver={cssVariablesResolver}
            forceColorScheme={dark ? 'dark' : 'light'}
        >
            {/*
              * Top right.  Bottom right put toasts over the sticky footer on the file browser
              * and over the player controls on a video, which are the two places a background
              * task is most likely to report while the user is doing something else.
              */}
            <Notifications position='top-right' limit={5}/>
            {children}
        </MantineProvider>
    </ThemeContext.Provider>
}
/*
 * The Semantic UI wrappers that used to live below this line are gone.
 *
 * They existed so call sites could get a themed Button, Segment, Modal and so on while
 * the app still rendered Semantic components; every one of those call sites now imports
 * from `src/components/ui` instead.  The dark-mode compatibility props they consumed --
 * `i`, `s`, `t`, `inverted` -- went with them: those carried hardcoded greys, which is
 * precisely what the token themes replaced.
 *
 * What remains is the part that was never about Semantic: the provider that resolves the
 * chosen theme, stamps `data-theme` and `data-media-filter` on <html>, persists both, and
 * hands Mantine our tokens.
 */
