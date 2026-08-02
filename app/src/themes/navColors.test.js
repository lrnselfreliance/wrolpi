import fs from 'fs';
import path from 'path';
import {contrastRatio, isMeasurable} from './contrast';
import {defaultNavColor, navColorNames, navColorsFrom} from './navColors';
import {themeNames} from './names';
import {semanticUIColorMap} from '../components/Vars';

/*
 * The navbar foreground, measured against the palette that actually ships.
 *
 * The bar's background is the one colour a user picks by name, so there are twelve of them
 * per theme and forty-eight in total -- too many to eyeball, and the reason the bar drew
 * near-black text on night's #451212 for as long as it did.  The tokens are parsed out of
 * tokens.css rather than restated here: a list restated here is a list that agrees with
 * itself while disagreeing with the stylesheet.
 */

const tokensCss = fs.readFileSync(path.join(__dirname, 'tokens.css'), 'utf8');

/** Every `--name: #hex` declared in one theme's block. */
const paletteOf = (theme) => {
    const pattern = theme === 'light'
        ? /:root,\s*html\[data-theme="light"]\s*{([^}]*)}/
        : new RegExp(`html\\[data-theme="${theme}"]\\s*{([^}]*)}`);
    const match = tokensCss.match(pattern);
    if (!match) throw new Error(`tokens.css has no block for ${theme}`);
    return Object.fromEntries([...match[1].matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;/g)]
        .map(m => [m[1], m[2]]));
};

/** A token reader for one theme, as `navColorsFrom` expects. */
const readerFor = (theme) => {
    const palette = paletteOf(theme);
    return (name) => palette[name] || '';
};

/** Every (theme, navColor) pair, with what the bar resolves to. */
const everyCombination = () => themeNames.flatMap(theme => navColorNames.map((navColor) => {
    const read = readerFor(theme);
    return {theme, navColor, palette: paletteOf(theme), ...navColorsFrom(read, navColor)};
}));

describe('the navbar palette', () => {
    it('parses a palette for every theme', () => {
        // The premise for every case below.  Without it a broken parser reads as a
        // navbar that never fails, because there would be nothing to measure.
        themeNames.forEach((theme) => {
            const palette = paletteOf(theme);
            expect({theme, colors: Object.keys(palette).length > 15}).toEqual(
                {theme, colors: true});
        });
    });

    it('offers exactly the colours the favicon has an icon for', () => {
        /*
         * `semanticUIColorMap` supplies the fixed hexes for `/favicon-<colour>.svg` and the
         * `theme-color` meta tag -- a file on disk and OS chrome, neither of which can take a
         * token.  A colour offered here with no icon there falls back to violet, so the bar
         * and the browser tab would disagree.
         */
        expect([...navColorNames].sort()).toEqual(Object.keys(semanticUIColorMap).sort());
    });

    it('defaults to a colour it offers', () => {
        expect(navColorNames).toContain(defaultNavColor);
    });
});

describe('the navbar foreground', () => {
    /** The tokens the bar is allowed to draw its text in. */
    const candidatesOf = (palette) =>
        [palette['--btn-text'], palette['--black'], palette['--white']];

    it('takes a colour the theme itself supplies, never a literal black or white', () => {
        /*
         * A literal white pixel in night mode undoes the user's dark adaptation, which is the
         * one thing that theme exists to prevent.  Night's "white" is #ff8a8a and its "black"
         * is #2a0808; both are red, and both are among what this must choose between.
         */
        everyCombination().forEach(({theme, navColor, color, palette}) => {
            expect({theme, navColor, color}).toEqual({
                theme, navColor,
                color: candidatesOf(palette).includes(color)
                    ? color : `expected a theme token, got ${color}`,
            });
        });
    });

    it('picks the best of them, every time', () => {
        // The invariant.  A brightness threshold picks the worse option for every mid-tone,
        // and a mid-tone is exactly what a navbar colour is.
        everyCombination().forEach(({theme, navColor, background, color, palette}) => {
            const chosenRatio = contrastRatio(color, background);
            const rejected = candidatesOf(palette)
                .filter(candidate => candidate !== color)
                .map(candidate => contrastRatio(candidate, background));

            expect({theme, navColor, best: rejected.every(ratio => chosenRatio >= ratio)})
                .toEqual({theme, navColor, best: true});
        });
    });

    it('reports the ratio it measured', () => {
        everyCombination().forEach(({theme, navColor, background, color, ratio}) => {
            expect({theme, navColor, ratio: Number(ratio.toFixed(4))}).toEqual({
                theme, navColor, ratio: Number(contrastRatio(color, background).toFixed(4)),
            });
        });
    });

    it('never does worse than the --btn-text it replaced', () => {
        /*
         * The regression guard, and the whole claim of the change.  `--btn-text` is a single
         * value per theme, so it was right for whichever end of the palette it happened to
         * match and wrong for the other -- 1.33:1 on night's brown.
         */
        everyCombination().forEach(({theme, navColor, background, ratio, palette}) => {
            const before = contrastRatio(palette['--btn-text'], background);

            expect({theme, navColor, atLeastAsGood: ratio >= before - 0.001})
                .toEqual({theme, navColor, atLeastAsGood: true});
        });
    });

    it('lifts every combination clear of 3:1', () => {
        /*
         * 3:1 is the WCAG floor for large text and for graphical objects, which is what the
         * bar's icons are.  Twelve combinations were below it -- night's brown at 1.33:1 was
         * a glyph the same colour as the bar behind it.
         */
        const failing = everyCombination()
            .filter(({ratio}) => ratio < 3)
            .map(({theme, navColor, ratio}) => `${theme}/${navColor} ${ratio.toFixed(2)}`);

        expect(failing).toEqual([]);
    });

    it('is a real constraint: --btn-text does NOT clear 3:1', () => {
        /*
         * Without this the case above could pass on any mapping at all, including the one it
         * replaced, and would prove nothing.  Seventeen combinations sat below 4.5:1 with a
         * fixed foreground and twelve below 3:1.
         */
        const failing = everyCombination()
            .filter(({background, palette}) => contrastRatio(palette['--btn-text'], background) < 3);

        expect(failing.length).toBeGreaterThan(5);
    });
});

describe('what measurement cannot fix', () => {
    /*
     * Ten of the forty-eight combinations still sit under 4.5:1, and no choice of
     * foreground will lift them, because the shortfall is in the BACKGROUND.
     *
     * A monochrome theme resolves all twelve colour names onto one red (or amber) ramp, and
     * six of night's land in the middle of it -- #b03030 is 3.27:1 from night's darkest red
     * and 2.52:1 from its brightest, so the best available option is the one this picks and
     * it is still short.  There is no foreground in a one-hue palette that reads on a
     * mid-tone of that same hue; the fix, if the residue matters, is to the palette.
     *
     * Recorded as a number rather than a comment so it cannot quietly grow.  /theme-sample
     * prints the measured ratio beside every sample, which is where this gets decided.
     */
    const belowAA = () => everyCombination()
        .filter(({ratio}) => ratio < 4.5)
        .map(({theme, navColor}) => `${theme}/${navColor}`);

    it('leaves ten combinations short of 4.5:1, all of them mid-tones', () => {
        expect(belowAA().sort()).toEqual([
            'amber/blue', 'amber/grey', 'amber/teal',
            'light/yellow',
            'night/blue', 'night/green', 'night/grey', 'night/pink', 'night/teal',
            'night/violet',
        ]);
    });

    it('holds the worst case above 3:1 -- night/green, at 3.27', () => {
        // Nothing is invisible any more, which is the bar this change had to clear.  The
        // number is here so that a palette edit which makes it worse has to say so.
        const worst = everyCombination().sort((a, b) => a.ratio - b.ratio)[0];

        expect({combination: `${worst.theme}/${worst.navColor}`, above3: worst.ratio > 3})
            .toEqual({combination: 'night/green', above3: true});
    });

    it('leaves none of them in dark, which has a full palette to draw on', () => {
        // The contrast with the monochrome themes, and the evidence that the shortfall is
        // the palette's rather than the mapping's.
        expect(belowAA().filter(name => name.startsWith('dark/'))).toEqual([]);
    });
});

describe('the bar the app actually renders', () => {
    /*
     * Nav.js draws two bars -- one for mobile, one for desktop -- and neither is reachable
     * from a test that could measure it.  <NavBar/> needs the settings, status and file-worker
     * contexts and a dozen polling hooks, and which of the two renders is decided by a media
     * query.  ui-layout.cy.js measures the gallery's bar instead, which is the same chrome
     * built with the same call; these hold Nav.js to that call, so a bar that stops going
     * through the measurement cannot pass by being untested.
     */
    const source = fs.readFileSync(
        path.join(__dirname, '../components/Nav.js'), 'utf8');

    it('styles both bars through navBarStyle', () => {
        const bars = [...source.matchAll(/className='wrolpi-navbar'[^>]*/g)].map(m => m[0]);

        // Mobile and desktop.  If this drops to one, the case below is covering half of
        // what it claims to.
        expect(bars.length).toBe(2);
        bars.forEach(bar => expect(bar).toContain('style={navBarStyle(navColors)}'));
    });

    it('never hardcodes the foreground on the bar again', () => {
        // What it did before: one token for forty-eight backgrounds.
        expect(source).not.toMatch(/color:\s*'var\(--btn-text\)'/);
    });
});

describe('when the tokens cannot be read', () => {
    /*
     * jsdom resolves no stylesheet, and neither does the first render before the document
     * has one.  The bar must still be painted by CSS then, and must still follow the theme --
     * falling through to an empty `background` would leave a transparent bar over the page.
     */
    it('falls back to the tokens themselves', () => {
        expect(navColorsFrom(() => '', 'olive')).toEqual({
            background: 'var(--olive)', color: 'var(--btn-text)', ratio: null,
        });
    });

    it('falls back for an unknown colour too', () => {
        // `nav_color` comes from a config file, which a user edits by hand.
        expect(navColorsFrom(() => '', 'chartreuse').background)
            .toEqual(`var(--${defaultNavColor})`);
    });

    it('resolves an unknown colour to the default when tokens ARE readable', () => {
        const read = readerFor('light');
        expect(navColorsFrom(read, 'chartreuse').background)
            .toEqual(paletteOf('light')[`--${defaultNavColor}`]);
    });
});

describe('a token this cannot measure', () => {
    /*
     * Every token in tokens.css is a hex, so this is about the custom YAML themes ahead of
     * us -- the first place a palette will be written by hand, and the first place something
     * other than a hex will appear.
     *
     * The failure it guards was silent and worse than doing nothing.  An unparseable colour
     * measured as luminance zero, indistinguishable from black, so the bar chose its
     * foreground against a colour the theme does not contain and then froze the wrong hex
     * into an inline style, where CSS could no longer correct it.  Falling back leaves the
     * bar painted by CSS: wrong about the foreground at worst, rather than about both.
     */
    const hexPalette = () => paletteOf('light');

    /** The light palette with one token rewritten into some other notation. */
    const readerWith = (overrides) => {
        const palette = {...hexPalette(), ...overrides};
        return (token) => palette[token] || '';
    };

    it('measures rgb() as readily as hex, since both are colours', () => {
        // `--violet` is #5c4fa8 in light.  The same colour, written the other way, must
        // produce the same answer rather than falling back.
        const asHex = navColorsFrom(readerFor('light'), 'violet');
        const asRgb = navColorsFrom(readerWith({'--violet': 'rgb(92, 79, 168)'}), 'violet');

        expect(asRgb.color).toEqual(asHex.color);
        expect(asRgb.ratio).toBeCloseTo(asHex.ratio, 4);
    });

    it('handles the modern space-separated form too', () => {
        const asHex = navColorsFrom(readerFor('light'), 'violet');
        const asRgb = navColorsFrom(readerWith({'--violet': 'rgb(92 79 168 / 1)'}), 'violet');

        expect(asRgb.ratio).toBeCloseTo(asHex.ratio, 4);
    });

    it('falls back rather than measuring a background it cannot read', () => {
        // `color-mix` is the shape a hand-written theme is most likely to reach for, and
        // resolving it needs a browser.
        const colors = navColorsFrom(
            readerWith({'--olive': 'color-mix(in srgb, #6f7a24 60%, white)'}), 'olive');

        expect(colors).toEqual({
            background: 'var(--olive)', color: 'var(--btn-text)', ratio: null,
        });
    });

    it('falls back when no candidate foreground can be read', () => {
        const colors = navColorsFrom(readerWith({
            '--btn-text': 'hsl(0 0% 100%)', '--black': 'rebeccapurple', '--white': 'hsl(0 0% 0%)',
        }), 'violet');

        expect(colors.ratio).toBeNull();
    });

    it('still measures when only SOME candidates are unreadable', () => {
        /*
         * The narrow case, and the reason the unreadable ones are filtered out rather than
         * the whole measurement abandoned.  A theme that writes one token oddly should not
         * lose the measurement for the other two.
         */
        const colors = navColorsFrom(
            readerWith({'--white': 'oklch(0.9 0.1 20)'}), 'violet');

        expect(colors.ratio).not.toBeNull();
        expect([hexPalette()['--btn-text'], hexPalette()['--black']]).toContain(colors.color);
    });

    it('is a real constraint: an unreadable colour is NOT treated as black', () => {
        /*
         * Without this the fallback could be removed and every case above would still pass
         * on `relativeLuminance` returning zero -- which is precisely the bug, because zero
         * is a legitimate luminance and nothing downstream could tell the two apart.
         */
        expect(contrastRatio('color-mix(in srgb, red, blue)', '#ffffff'))
            .toBeCloseTo(contrastRatio('#000000', '#ffffff'), 4);
        expect(isMeasurable('color-mix(in srgb, red, blue)')).toBe(false);
        expect(isMeasurable('#000000')).toBe(true);
    });
});
