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

/*
 * Themes built on a single hue, which is the constraint the semantic roles exist for.
 *
 * These have no second colour to spend, so a role cannot be a hue there -- it has to be
 * a step on a brightness ramp, and `--orange` being byte-identical to `--text` in night
 * is what that costs when it is ignored.  Light and dark have hues and are free to use
 * them, so severity does NOT read as brightness there and must not be asserted to.
 *
 * The same set as `explicitOnlyThemes` today, deliberately named separately: one is about
 * how a theme is chosen, the other about what a theme has to work with.
 */
export const monochromeThemes: ThemeName[] = [nightTheme, amberTheme];

export const isMonochromeTheme = (theme: ThemeName): boolean =>
    monochromeThemes.includes(theme);

export const isDarkTheme = (theme: ThemeName): boolean => darkThemes.includes(theme);

/*
 * The basemap flavor for a theme.
 *
 * The map viewer draws with protomaps-themes-base, which takes a flavor of its own and is
 * NOT a place to pass a WROLPi theme name.  It looks the flavor up in a record and then
 * dereferences the result without checking, so an unknown name is not a fallback but a
 * `TypeError: Cannot read properties of undefined (reading 'background')` thrown before the
 * first tile -- which is what /map did in night and amber once those themes existed.
 *
 * The monochrome themes take `black`, which is protomaps' only ACHROMATIC dark flavor, and
 * that is the whole reason to prefer it.  Both media filters are a pure luminance
 * projection -- the same `0.2126 0.7152 0.0722` row -- so they keep brightness and throw
 * hue away.  Filtering `black` is therefore a hue rotation and nothing else: all thirteen
 * of its greys were authored as a monochrome hierarchy and every one survives.  `dark` has
 * nineteen colours but four of them are hued (water, parks, up to 25 chroma), and those
 * distinctions do not survive at all -- the features land at whatever brightness their hue
 * happened to carry rather than one anybody chose.  `black` is also half the light:
 * earth L0.007 against dark's L0.014, which is the point of a night-vision theme.
 *
 * `grayscale` is not an option despite the name -- it is a LIGHT theme (earth L0.604), and
 * a luminance filter turns a light map into a bright red one.
 */
export type MapFlavor = 'light' | 'dark' | 'black';

export const mapFlavor = (theme: ThemeName): MapFlavor => {
    if (isMonochromeTheme(theme)) return 'black';
    return isDarkTheme(theme) ? 'dark' : 'light';
};

/*
 * The sprite set for a theme, which is NOT the flavor.
 *
 * They are separate style properties and only happened to share a variable, which is what
 * made `black` look impossible: we ship two sprite sets, `light` and `dark`, so a style
 * naming `/map-assets/sprites/black` would load and then find no icons.  A `black` basemap
 * with `dark` icons is a perfectly ordinary style.
 */
export type MapSprite = 'light' | 'dark';

export const mapSprite = (theme: ThemeName): MapSprite =>
    isDarkTheme(theme) ? 'dark' : 'light';

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
