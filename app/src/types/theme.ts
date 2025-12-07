import { CSSProperties } from 'react';

// Theme values
export type ThemeName = 'dark' | 'light';
export type SavedThemeName = ThemeName | 'system' | null;

// Style objects used by theme
export interface InvertedProps {
    inverted?: boolean;
}

export interface StyleProps {
    style?: CSSProperties;
}

// ThemeContext value type
export interface ThemeContextValue {
    /** Props for Semantic elements that support "inverted" */
    i: InvertedProps;
    /** Props to invert styles on elements */
    s: StyleProps;
    /** Props to invert text color */
    t: StyleProps;
    /** Class name string: 'inverted' or '' */
    inverted: string;
    /** Current applied theme */
    theme: ThemeName;
    /** User's saved theme preference */
    savedTheme: SavedThemeName;
    /** Set dark theme */
    setDarkTheme: (save?: boolean) => void;
    /** Set light theme */
    setLightTheme: (save?: boolean) => void;
    /** Cycle through theme options */
    cycleSavedTheme: (e?: React.MouseEvent) => void;
}
