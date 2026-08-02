import fs from 'fs';
import path from 'path';
import layers from 'protomaps-themes-base';
import {isDarkTheme, isMonochromeTheme, mapFlavor, mapSprite, themeNames} from './names';

/*
 * The map viewer draws its basemap with protomaps-themes-base, which takes a "flavor".
 *
 * MapViewer used to hand it the WROLPi theme name directly.  That worked while there were
 * two themes called `light` and `dark`, and broke the day night and amber arrived: protomaps
 * looks the flavor up in a record, finds nothing, and dereferences it anyway --
 * `TypeError: Cannot read properties of undefined (reading 'background')`, thrown before a
 * single tile is drawn, so /map was blank in two of the four themes.
 *
 * The flavor is also interpolated into a sprite URL, so it has to be a name we ship sprites
 * for, which is a smaller set again.  Both halves are checked against the real thing --
 * protomaps itself, and the sprites directory on disk -- rather than against a list repeated
 * here, because a list repeated here is exactly what would have passed in the first place.
 */

const SPRITES = path.join(__dirname, '../../../modules/map/static/sprites');

/** The sprite sets actually shipped, from disk. */
const spriteFlavors = () => [...new Set(fs.readdirSync(SPRITES)
    .map(file => file.replace(/(@2x)?\.(json|png)$/, '')))].sort();

describe('the map basemap flavor', () => {
    it('ships sprites for at least two flavors', () => {
        // The premise for every case below.  If the directory were empty or unreadable,
        // `toContain` would fail for the wrong reason and read as a mapping bug.
        expect(spriteFlavors().length).toBeGreaterThan(1);
    });

    it.each(themeNames)('maps %s to a flavor protomaps understands', (theme) => {
        const flavor = mapFlavor(theme);

        // protomaps itself is the authority, not a list copied into this file.  It throws on
        // an unknown flavor rather than returning nothing, which is the whole bug.
        const built = layers('src', flavor);
        expect(Array.isArray(built)).toBe(true);
        expect(built.length).toBeGreaterThan(0);
    });

    it.each(themeNames)('gives %s a sprite set we actually ship', (theme) => {
        /*
         * The sprite is a SEPARATE style property from the flavor; they only happened to
         * share a variable, which is what made a `black` basemap look impossible.  We ship
         * two sets, so this is the narrower constraint and it is checked against disk.
         */
        expect(spriteFlavors()).toContain(mapSprite(theme));
    });

    it.each(themeNames)('keeps %s on a basemap of its own brightness', (theme) => {
        /*
         * A dark theme must not get the light basemap.  Night and amber tint the canvas with
         * an SVG filter, but that only shifts hue -- a white slab filtered to red is a red
         * slab, and the point of night mode is not to put one of those on screen.
         */
        expect(mapFlavor(theme) === 'light').toBe(!isDarkTheme(theme));
    });
});

describe('the monochrome themes get an achromatic basemap', () => {
    /*
     * The reason night and amber take `black` rather than `dark`, and the thing that would
     * silently regress if someone "simplified" the mapping to `isDarkTheme ? dark : light`.
     *
     * Both media filters are a pure luminance projection -- the same `0.2126 0.7152 0.0722`
     * row -- so they keep brightness and discard hue.  A basemap that encodes anything in
     * hue loses it: `dark` marks water and parks with colour, and after filtering those
     * features sit at whatever brightness their hue happened to carry.  An achromatic
     * basemap has nothing to lose, so the designer's hierarchy arrives intact.
     */
    const chroma = (hex) => {
        const value = hex.replace('#', '');
        const [r, g, b] = [0, 2, 4].map(i => parseInt(value.slice(i, i + 2), 16));
        return Math.max(r, g, b) - Math.min(r, g, b);
    };

    /** Every literal hex a flavor paints with. */
    const paletteOf = (flavor) => layers('src', flavor).flatMap(layer =>
        ['background-color', 'fill-color', 'line-color']
            .map(key => layer.paint && layer.paint[key])
            .filter(value => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)));

    themeNames.filter(isMonochromeTheme).forEach((theme) => {
        it(`paints ${theme} with greys only`, () => {
            const palette = paletteOf(mapFlavor(theme));

            expect(palette.length).toBeGreaterThan(20);
            const hued = [...new Set(palette)].filter(hex => chroma(hex) > 0);
            expect(hued).toEqual([]);
        });
    });

    it('is a real constraint: the plain dark flavor is NOT achromatic', () => {
        // Without this the test above passes on any flavor at all and proves nothing about
        // the choice -- `black` would look unremarkable rather than deliberate.
        const hued = [...new Set(paletteOf('dark'))].filter(hex => chroma(hex) > 0);

        expect(hued.length).toBeGreaterThan(0);
    });
});
