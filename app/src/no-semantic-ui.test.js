import fs from 'fs';
import path from 'path';

/*
 * Semantic UI is gone, and this is what keeps it gone.
 *
 * It began as a ratchet: a JSON baseline listing the 75 files that still imported the
 * library, which was only ever allowed to shrink.  The list reached zero and the file has
 * been deleted with it; what is left is the part that still has teeth.
 *
 * An import of a missing module fails loudly on its own, so that is not really what this
 * guards.  It guards the quiet ways the library comes back: reinstalling a package to
 * "just use a Semantic component for this one thing", which drags a 300kB stylesheet into
 * the bundle with it, or writing `className="ui stackable grid"` in the belief that those
 * rules are still loaded, which they have not been since Phase 4 -- markup like that does
 * not error, it simply has no effect, and the layout quietly comes out wrong.
 *
 * It is a test rather than an ESLint rule deliberately: `no-restricted-imports` would
 * either print warnings on every dev rebuild or fail the build outright, and CI unsets CI=
 * for its build step, so warnings there guard nothing.
 *
 * New UI code imports from `src/components/ui`.
 */

const SRC = __dirname;
const REPO = path.join(SRC, '..');

/** Every source file under src/, excluding tests. */
const sourceFiles = (dir = SRC) => fs.readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    if (!/\.(js|jsx|ts|tsx)$/.test(entry.name)) return [];
    if (/\.(test|cy)\.(js|jsx|ts|tsx)$/.test(entry.name)) return [];
    return [path.relative(REPO, full)];
});

const filesMatching = (pattern) => sourceFiles()
    .filter(file => pattern.test(fs.readFileSync(path.join(REPO, file), 'utf8')))
    .sort();

describe('Semantic UI stays removed', () => {
    it('scans a source tree, so a clean result means something', () => {
        // Every assertion below is "this list is empty".  Without this one they would all
        // pass just as well if the walk found no files at all.
        expect(sourceFiles().length).toBeGreaterThan(100);
    });

    it('has no file importing Semantic UI', () => {
        expect(filesMatching(/from ['"](semantic-ui-react|semantic-ui-react\/)/)).toEqual([]);
    });

    it('has nobody left calling the Semantic toast library', () => {
        /*
         * A toast raised through react-semantic-toasts-2 needs `<SemanticToastContainer/>`
         * mounted, and that came out of App.js when App.js migrated.  So this import fails
         * in the way that is hardest to notice: no error, no warning, just a notification
         * the user is never shown.  Import `toast` from `src/components/ui` instead; it
         * takes the same options.
         */
        expect(filesMatching(/from ['"]react-semantic-toasts-2/)).toEqual([]);
    });

    it('has no file leaning on the Semantic stylesheet', () => {
        /*
         * `className="ui stackable grid"` and friends.  semantic.min.css is not loaded, so
         * a `ui ...` class name now styles nothing at all -- which is why this cannot be
         * left to the import check: nothing about it fails, the element simply loses the
         * layout its author expected.
         */
        expect(filesMatching(/className=["']ui /)).toEqual([]);
    });

    it('has no Semantic package installed', () => {
        const pkg = JSON.parse(fs.readFileSync(path.join(REPO, 'package.json'), 'utf8'));
        const named = [...Object.keys(pkg.dependencies || {}),
            ...Object.keys(pkg.devDependencies || {})]
            .filter(name => /semantic/i.test(name));

        expect(named).toEqual([]);
    });
});
