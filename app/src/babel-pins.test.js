import fs from 'fs';
import path from 'path';

/*
 * The @babel core pipeline is pinned, and has to stay pinned.
 *
 * Floating it broke the React /map page: maplibre-gl's Web Worker is inlined into the
 * production bundle, Babel 7.29 transpiles it differently, and CRA's Terser mangle pass then
 * turns it into `ReferenceError: a is not defined`.  The worker's style-layer index never
 * builds, every vector source fails to parse, and the map renders blank with only the pins.
 *
 * Two properties make this worth a test rather than a comment:
 *
 *   - It is invisible to everything else we run.  The dev server is fine, the jest suite is
 *     fine, `npm run build` succeeds -- only the MINIFIED bundle is broken, and only on a page
 *     whose failure looks like missing map data rather than a JS error.
 *   - It has already regressed once by accident.  The pins were added deliberately, then
 *     removed as collateral when the Mantine commit rewrote `overrides` for TypeScript 5.
 *     Nothing failed, so nothing objected; the map survived on lockfile inertia alone until
 *     someone re-resolved it.
 *
 * Verified rather than assumed, on this tree: raising @babel/core to 7.29.7 and reinstalling
 * fails `npm run build` outright ("'opera_mobile' is not a valid target", from a
 * helper-compilation-targets that floated away from the browserslist data it was pinned
 * against).  Restoring these pins builds, and /map renders from the built bundle.
 */

const APP = path.join(__dirname, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(APP, 'package.json'), 'utf8'));
const lock = JSON.parse(fs.readFileSync(path.join(APP, 'package-lock.json'), 'utf8'));

/** The 16 packages that differ between the last-good tree and the one that broke the map. */
const PINNED = [
    '@babel/code-frame', '@babel/compat-data', '@babel/core', '@babel/generator',
    '@babel/helper-compilation-targets', '@babel/helper-globals', '@babel/helper-module-imports',
    '@babel/helper-module-transforms', '@babel/helper-string-parser',
    '@babel/helper-validator-identifier', '@babel/helper-validator-option', '@babel/helpers',
    '@babel/parser', '@babel/template', '@babel/traverse', '@babel/types',
];

describe('@babel pins', () => {
    it('names every package in the core pipeline', () => {
        /*
         * The whole pipeline, not just @babel/core.  Pinning core alone was tried when this was
         * first diagnosed and is not enough: the transform plugins resolve their own copies of
         * traverse/generator/types, so the new AST pipeline comes back in underneath a pinned
         * core.
         */
        const overrides = pkg.overrides || {};
        const missing = PINNED.filter(name => !overrides[name]);

        expect(missing).toEqual([]);
    });

    it('pins them to an exact version, not a range', () => {
        // `^7.20.12` is not a pin -- it resolves to 7.29 the moment anything re-resolves, which
        // is exactly the event this guards against.
        const loose = PINNED
            .map(name => [name, (pkg.overrides || {})[name]])
            .filter(([, spec]) => typeof spec !== 'string' || !/^\d+\.\d+\.\d+$/.test(spec));

        expect(loose).toEqual([]);
    });

    it('resolves every installed copy to the pinned version', () => {
        /*
         * The manifest is the intent; the lockfile is what actually gets installed.  npm nests
         * a second copy of a dependency whenever versions conflict, and a nested copy that
         * escaped the override would put the new pipeline back into the build while the
         * top-level entry still read correctly.
         *
         * So this walks EVERY path in the lockfile, not just `node_modules/<name>`.
         */
        const wanted = Object.fromEntries(PINNED.map(name => [name, pkg.overrides[name]]));
        const mismatched = [];
        let copies = 0;

        for (const [location, info] of Object.entries(lock.packages || {})) {
            for (const [name, version] of Object.entries(wanted)) {
                if (location === `node_modules/${name}` || location.endsWith(`/node_modules/${name}`)) {
                    copies += 1;
                    if (info.version !== version) {
                        mismatched.push(`${location}: ${info.version} (pinned ${version})`);
                    }
                }
            }
        }

        // The premise: a lockfile these names never matched would report nothing mismatched.
        expect(copies).toBeGreaterThan(100);
        expect(mismatched).toEqual([]);
    });
});
