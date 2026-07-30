import {SavedThemeName, ThemeName} from '../types/theme';

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
            'and maps are filtered to red as well.',
    },
    {
        value: amberTheme,
        text: 'Amber',
        icon: 'terminal',
        description: 'Monochrome amber, like a classic terminal.',
    },
];
