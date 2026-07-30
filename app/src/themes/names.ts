import {SavedThemeName, ThemeMediaFilter, ThemeName} from '../types/theme';

/*
 * Theme names and the choices offered by the pickers.
 *
 * These live here rather than in components/Theme.tsx so the component library can
 * use them without importing that module, which still pulls in Semantic UI.
 */

export const darkTheme = 'dark';
export const lightTheme = 'light';
export const nightTheme = 'night';
export const amberTheme = 'amber';
export const defaultTheme = lightTheme;
export const systemTheme = 'system';
export const themeSessionKey = 'color-scheme';

/** Every theme a user can apply, in the order the pickers offer them. */
export const themeNames: ThemeName[] = [lightTheme, darkTheme, nightTheme, amberTheme];

/** Themes built on a dark background.  Semantic components are `inverted` in these. */
export const darkThemes: ThemeName[] = [darkTheme, nightTheme, amberTheme];

/** Themes a user must choose deliberately; `prefers-color-scheme` never picks them. */
export const explicitOnlyThemes: ThemeName[] = [nightTheme, amberTheme];

export const isDarkTheme = (theme: ThemeName): boolean => darkThemes.includes(theme);

export const isThemeName = (value: unknown): value is ThemeName =>
    themeNames.includes(value as ThemeName);

/*
 * Media filtering.
 *
 * Images, video, PDFs, embedded pages, and the map canvas cannot consume theme
 * tokens, so a monochrome theme can pass them through an SVG color matrix
 * instead (see MediaFilterDefs.tsx for the filters, tokens.css for the rule).
 *
 * A theme declares which filter it uses and whether it is on to begin with; the
 * user can then turn it on or off for that theme.  Night defaults to on — an
 * unfiltered thumbnail undoes dark adaptation, which is the whole point of the
 * mode — and amber defaults to off, since it is a look rather than a night-vision
 * aid.  Neither is forced: some users want their media tinted to match, some
 * want to see the actual image.
 *
 * The choice is stored per theme, so turning it off in amber does not disarm it
 * in night.
 */
export const themeMediaFilters: Partial<Record<ThemeName, ThemeMediaFilter>> = {
    [nightTheme]: {
        id: 'night-red',
        defaultOn: true,
        label: 'Filter media to red',
        description: 'Videos, images, documents, and maps are remapped to red. Turning this off '
            + 'shows their real colors, which will spoil your night vision.',
    },
    [amberTheme]: {
        id: 'amber-mono',
        defaultOn: false,
        label: 'Filter media to amber',
        description: 'Videos, images, documents, and maps are remapped to amber, matching the '
            + 'interface. Off by default so media keeps its real colors.',
    },
};

/** The filter a theme offers, or undefined when it has none to offer. */
export const themeMediaFilter = (theme: ThemeName): ThemeMediaFilter | undefined =>
    themeMediaFilters[theme];

export const mediaFilterSessionKey = 'media-filter';

/**
 * Resolve the filter id to stamp on `<html>` — '' when nothing should be filtered.
 *
 * `overrides` is the stored map of theme name to boolean; a theme missing from it
 * has never been changed and follows its own default.
 */
export const resolveMediaFilter = (
    theme: ThemeName,
    overrides: Partial<Record<ThemeName, boolean>>,
): string => {
    const filter = themeMediaFilters[theme];
    if (!filter) return '';
    const enabled = overrides[theme] ?? filter.defaultOn;
    return enabled ? filter.id : '';
}

export interface ThemeChoice {
    value: SavedThemeName;
    text: string;
    /** Semantic icon name; resolved to a Tabler component by the Icon shim. */
    icon: string;
    description: string;
}

/** Shared by the navigation bar picker and the Settings page, so the two cannot drift. */
export const themeChoices: ThemeChoice[] = [
    {
        value: systemTheme,
        text: 'System',
        icon: 'lightbulb outline',
        description: "Follow this device's light or dark preference.",
    },
    {value: lightTheme, text: 'Light', icon: 'sun', description: 'A light background.'},
    {value: darkTheme, text: 'Dark', icon: 'moon', description: 'A dark background.'},
    {
        value: nightTheme,
        text: 'Night',
        icon: 'eye',
        description: 'Red only, to preserve your night vision in the dark. Videos, documents, ' +
            'and maps are filtered to red as well, unless you turn that off.',
    },
    {
        value: amberTheme,
        text: 'Amber',
        icon: 'terminal',
        description: 'Monochrome amber, like a classic terminal. Media keeps its real colors '
            + 'unless you ask for it to be tinted too.',
    },
];
