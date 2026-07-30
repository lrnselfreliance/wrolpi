import { CSSProperties } from 'react';

// Theme values.  `night` and `amber` are explicit user choices only; neither is
// ever selected by `prefers-color-scheme`.
export type ThemeName = 'dark' | 'light' | 'night' | 'amber';
export type SavedThemeName = ThemeName | 'system' | null;

/**
 * A theme's media filter: images, video, PDFs, and canvases cannot consume theme
 * tokens, so a monochrome theme can remap them with an SVG color matrix instead.
 * The theme declares the filter and whether it starts on; the user decides.
 */
export interface ThemeMediaFilter {
    /** Matches a filter id in MediaFilterDefs, minus the `wrolpi-` prefix. */
    id: string;
    /** On unless the user says otherwise. */
    defaultOn: boolean;
    /** Label for the toggle, naming what the filter does. */
    label: string;
    description: string;
}

// Style objects used by theme
export interface InvertedProps {
    inverted?: boolean;
}

export interface StyleProps {
    style?: CSSProperties;
}

// ThemeContext value type
export interface ThemeContextValue {
    /** Current applied theme */
    theme: ThemeName;
    /** User's saved theme preference */
    savedTheme: SavedThemeName;
    /** True when the applied theme is built on a dark background */
    isDark: boolean;
    /** The media filter this theme offers, or undefined when it offers none */
    mediaFilter?: ThemeMediaFilter;
    /** True when that filter is currently being applied to media */
    mediaFilterEnabled: boolean;
    /** Turn the current theme's media filter on or off */
    setMediaFilterEnabled: (enabled: boolean) => void;
    /** Apply and save a theme (or 'system' to follow the OS preference) */
    setTheme: (value: SavedThemeName) => void;
    /** Set dark theme */
    setDarkTheme: (save?: boolean) => void;
    /** Set light theme */
    setLightTheme: (save?: boolean) => void;
    /** Cycle through theme options */
    cycleSavedTheme: (e?: React.MouseEvent) => void;
}
