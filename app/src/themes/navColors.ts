import React from 'react';
import {bestForeground, contrastRatio, isMeasurable} from './contrast';


/*
 * The navigation bar's colors.
 *
 * The bar's background is the one color in the interface the USER picks (Settings ->
 * navbar color), and it is picked by hue name -- `violet`, `olive`, `brown` -- which each
 * theme then resolves to its own hex.  So the bar has a background the theme cannot know in
 * advance, and its links and status icons have to stay legible on all twelve of them in all
 * four themes: forty-eight combinations, not one.
 *
 * It used to draw them all with the single `--btn-text` token, which is white in light and
 * near-black in the other three.  Near-black on night's `--brown` (#451212) is 1.33:1 and on
 * amber's (#452708) 1.48:1 -- nine of night's twelve colors and seven of amber's sat below
 * 4.5:1, which is why the bar's icons were unreadable.  `--btn-text` is the right token for
 * a button, whose fill the theme chooses; it was never the right one here.
 *
 * So the foreground is MEASURED instead, against the background the theme actually resolved.
 * The two candidates are the theme's own `--black` and `--white` rather than literal black and
 * white, because a literal white pixel in night mode defeats the entire point of the mode --
 * night's "white" is #ff8a8a, a bright red, and amber's is #ffc875.
 *
 * Measuring at runtime rather than shipping a paired `--on-red`/`--on-olive` token for every
 * color also means a theme only has to supply a palette: the correct foreground for each
 * entry falls out of it, with nothing extra to declare and nothing to keep in step.
 *
 * What is NOT measured, and should be: the warning indicators.  NavBar still picks their
 * color from `conflictingColors`, a hardcoded list of navbar names that swaps `yellow`/`red`
 * for `null`/`black` on the five bars those hues would blend into.  It is the same defect
 * this replaced -- a name list standing in for a measurement -- and it is worse than the one
 * fixed here rather than better: `--danger` and `--warning` measure 1.0-1.8:1 against the bar
 * in EVERY theme, light and dark included, because a red icon on a red bar is a red icon on a
 * red bar.  It is left alone deliberately, because the fix is not a better color.  Those
 * icons have to stay distinguishable from each other AND from the bar's own text, and in a
 * monochrome theme there is no third brightness to spend, so severity has to stop being a
 * hue -- a filled badge, or a shape.  That is a redesign of how severity reads, not a
 * substitution, and it is not this change.
 *
 * /theme-sample draws the indicators as they are, taking the measured bar color, which is
 * what the bar does when nothing is wrong.  It does not stage a fake overheating Pi to
 * exhibit a fault nobody has agreed how to fix.
 *
 * Two limits on the measuring that IS done here, both of which the custom YAML themes will
 * meet before anything else does.  A token has to be a color these measurements can read -- hex or `rgb()`; anything
 * else falls back to CSS rather than being measured (see navColorsFrom).  And re-measurement
 * is triggered by `data-theme` changing, which is how a theme is applied today; a future
 * editor that patches custom properties in place without touching the attribute would leave
 * the bar on the values it last measured (see useNavColors).
 */

/**
 * The colors offered for the bar, in picker order.
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
    /** CSS color for the bar itself. */
    background: string;
    /** CSS color its text and icons take. */
    color: string;
    /**
     * Measured contrast of `color` on `background`, or null when the tokens could not be
     * read and the pair below is the un-measured fallback.  Surfaced so /theme-sample can
     * show the number next to the sample.
     */
    ratio: number | null;
}

/**
 * The bar's colors, given a way to read theme tokens.
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

    const measurable = candidates.filter(isMeasurable);

    if (!isMeasurable(background) || measurable.length === 0) {
        /*
         * Nothing readable to measure, so measure nothing and let CSS do its job.
         *
         * Two cases reach here.  The ordinary one is that there is no stylesheet yet -- jsdom,
         * or a very early render -- and the reader returns empty strings.  The other is a
         * token this cannot parse: a hand-written theme writing `rgb(90 79 168)` or
         * `color-mix(...)` rather than a hex.  That one used to be silent and worse than
         * useless: an unparseable color measured as luminance zero, indistinguishable from
         * black, so the bar picked its foreground against a color the theme does not contain
         * and then froze the wrong hex into an inline style, where CSS could not correct it.
         *
         * Falling back to the tokens themselves is the pre-measurement behaviour: the bar is
         * painted by CSS, follows the theme, and is only ever wrong about the foreground --
         * which is a great deal better than being confidently wrong about both.
         */
        return {background: `var(--${name})`, color: 'var(--btn-text)', ratio: null};
    }

    const color = bestForeground(background, measurable) as string;
    return {background, color, ratio: contrastRatio(color, background)};
}

/** The bar's colors read from a live document. */
export function resolveNavColors(
    navColor: string,
    element: Element = document.documentElement,
): NavColors {
    const styles = window.getComputedStyle(element);
    return navColorsFrom(name => styles.getPropertyValue(name).trim(), navColor);
}

/**
 * The inline style for a bar painted in these colors.
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
         * surface behind itself.  The bar's color is the user's choice, so it has to be
         * handed down rather than looked up from a token.
         */
        '--icon-stack-bg': colors.background,
    } as React.CSSProperties;
}

/**
 * The bar's colors, kept current as the theme changes.
 *
 * Watches the `data-theme` attribute rather than subscribing to ThemeContext, because the
 * attribute is what the tokens actually key off and it is stamped by ThemeProvider in an
 * effect of its own.  React runs child effects before parent effects, so a consumer that
 * re-read the tokens when the context value changed would read them one theme late -- and
 * the bar would sit on the previous theme's foreground until something else re-rendered it.
 *
 * The attribute is also stamped by the inline script in index.html before React loads, and
 * that is a change no context can report at all.
 *
 * This assumes token VALUES only change when `data-theme` does, which holds for every way a
 * theme is applied today.  It will not hold for a custom-theme editor that rewrites custom
 * properties in place: the measured pair is a snapshot of hexes, so the bar would keep the
 * old one until the theme name or the chosen color changed.  When that editor exists it
 * should either re-stamp the attribute or announce the change for this to observe -- there
 * is no event for "a custom property was assigned" to watch instead.
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
