import React from 'react';
import {bestForeground, contrastRatio} from './contrast';


/*
 * The navigation bar's colours.
 *
 * The bar's background is the one colour in the interface the USER picks (Settings ->
 * navbar colour), and it is picked by hue name -- `violet`, `olive`, `brown` -- which each
 * theme then resolves to its own hex.  So the bar has a background the theme cannot know in
 * advance, and its links and status icons have to stay legible on all twelve of them in all
 * four themes: forty-eight combinations, not one.
 *
 * It used to draw them all with the single `--btn-text` token, which is white in light and
 * near-black in the other three.  Near-black on night's `--brown` (#451212) is 1.33:1 and on
 * amber's (#452708) 1.48:1 -- nine of night's twelve colours and seven of amber's sat below
 * 4.5:1, which is why the bar's icons were unreadable.  `--btn-text` is the right token for
 * a button, whose fill the theme chooses; it was never the right one here.
 *
 * So the foreground is MEASURED instead, against the background the theme actually resolved.
 * The two candidates are the theme's own `--black` and `--white` rather than literal black and
 * white, because a literal white pixel in night mode defeats the entire point of the mode --
 * night's "white" is #ff8a8a, a bright red, and amber's is #ffc875.
 *
 * Measuring at runtime rather than shipping a paired `--on-red`/`--on-olive` token for every
 * colour also means the custom YAML themes still ahead of us get this for free: a theme
 * supplies a palette, and the correct foreground for each entry falls out of it.
 */

/**
 * The colours offered for the bar, in picker order.
 *
 * The same keys as `semanticUIColorMap` in components/Vars.js, which maps them to the fixed
 * hexes used for the favicon and the mobile status bar (those are files and OS chrome, so
 * they cannot take a token).  navColors.test.js holds the two lists together.
 */
export const navColorNames: string[] = [
    'red', 'orange', 'yellow', 'olive', 'green', 'teal',
    'blue', 'violet', 'purple', 'pink', 'brown', 'grey',
];

export const defaultNavColor = 'violet';

export interface NavColors {
    /** CSS colour for the bar itself. */
    background: string;
    /** CSS colour its text and icons take. */
    color: string;
    /**
     * Measured contrast of `color` on `background`, or null when the tokens could not be
     * read and the pair below is the un-measured fallback.  Surfaced so /theme-sample can
     * show the number next to the sample.
     */
    ratio: number | null;
}

/**
 * The bar's colours, given a way to read theme tokens.
 *
 * Takes a reader rather than an element so it can be measured against the real palette in a
 * unit test without a browser -- the shipped tokens are parsed out of tokens.css and handed
 * in.  Forty-eight combinations is far too many to eyeball.
 */
export function navColorsFrom(read: (name: string) => string, navColor: string): NavColors {
    const name = navColorNames.includes(navColor) ? navColor : defaultNavColor;
    const background = read(`--${name}`);
    /*
     * `--btn-text` leads because it is the token this used to use unconditionally, so where
     * it was already the best choice nothing changes -- and in the monochrome themes it is
     * genuinely the darkest thing the theme has (night's is #0a0000 against a `--black` of
     * #2a0808), which makes it the right foreground for every bright bar.  It was never
     * wrong; it was just applied without looking at what it was being drawn on.
     */
    const candidates = [read('--btn-text'), read('--black'), read('--white')].filter(Boolean);

    if (!background || candidates.length === 0) {
        /*
         * No stylesheet to read: jsdom, or a very early render.  Fall back to the tokens
         * themselves so the bar is still painted by CSS and still changes with the theme --
         * this is the pre-measurement behaviour, and it is only ever wrong about the
         * foreground.
         */
        return {background: `var(--${name})`, color: 'var(--btn-text)', ratio: null};
    }

    const color = bestForeground(background, candidates) as string;
    return {background, color, ratio: contrastRatio(color, background)};
}

/** The bar's colours read from a live document. */
export function resolveNavColors(
    navColor: string,
    element: Element = document.documentElement,
): NavColors {
    const styles = window.getComputedStyle(element);
    return navColorsFrom(name => styles.getPropertyValue(name).trim(), navColor);
}

/**
 * The inline style for a bar painted in these colours.
 *
 * Shared by the real navigation bar and the /theme-sample gallery, so a sample cannot end
 * up demonstrating a bar the app does not actually draw.
 */
export function navBarStyle(colors: NavColors): React.CSSProperties {
    return {
        background: colors.background,
        color: colors.color,
        /*
         * The hotspot glyph stacks two icons, and the corner one paints a disc of its
         * surface behind itself.  The bar's colour is the user's choice, so it has to be
         * handed down rather than looked up from a token.
         */
        '--icon-stack-bg': colors.background,
    } as React.CSSProperties;
}

/**
 * The bar's colours, kept current as the theme changes.
 *
 * Watches the `data-theme` attribute rather than subscribing to ThemeContext, because the
 * attribute is what the tokens actually key off and it is stamped by ThemeProvider in an
 * effect of its own.  React runs child effects before parent effects, so a consumer that
 * re-read the tokens when the context value changed would read them one theme late -- and
 * the bar would sit on the previous theme's foreground until something else re-rendered it.
 *
 * The attribute is also stamped by the inline script in index.html before React loads, and
 * that is a change no context can report at all.
 */
export function useNavColors(navColor: string): NavColors {
    const [colors, setColors] = React.useState<NavColors>(
        () => navColorsFrom(() => '', navColor));

    React.useLayoutEffect(() => {
        const update = () => setColors(resolveNavColors(navColor));
        update();

        if (typeof MutationObserver !== 'function') {
            return;
        }
        const observer = new MutationObserver(update);
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['data-theme'],
        });
        return () => observer.disconnect();
    }, [navColor]);

    return colors;
}
