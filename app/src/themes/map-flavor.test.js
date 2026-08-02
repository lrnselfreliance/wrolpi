import fs from 'fs';
import path from 'path';
import layers from 'protomaps-themes-base';
import {isDarkTheme, mapFlavor, themeNames} from './names';

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

    it.each(themeNames)('maps %s to a flavor we ship sprites for', (theme) => {
        // The flavor is interpolated into `/map-assets/sprites/<flavor>`, so a name protomaps
        // accepts is not enough -- `black` and `grayscale` are real flavors with no sprites.
        expect(spriteFlavors()).toContain(mapFlavor(theme));
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
