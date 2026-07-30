import fs from 'fs';
import path from 'path';
import baseline from './semantic-baseline.json';

/*
 * A ratchet for the Semantic UI removal.
 *
 * semantic-baseline.json lists every file that still imports Semantic UI (or the
 * Semantic-based toast library).  This test fails if a file not on that list
 * starts importing them, and asks for the list to shrink when a file stops.
 *
 * It replaces an ESLint rule deliberately: `no-restricted-imports` would either
 * print 75 warnings on every dev rebuild, or fail the build outright, and CI
 * already unsets CI= for the build step so warnings there guard nothing.
 *
 * The list has reached zero.  The test stays as a guard rather than being deleted: it now
 * asserts that nothing imports Semantic UI, nothing calls its toast library, nothing leans
 * on its stylesheet, and no migrated file reaches back through Theme.tsx.  It can go when
 * the packages themselves are uninstalled.
 */

const SRC = path.join(__dirname);
const LIBRARIES = /from ['"](semantic-ui-react|semantic-ui-react\/|react-semantic-toasts-2)/;

/** Every source file under src/, excluding tests. */
const sourceFiles = (dir = SRC) => fs.readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    if (!/\.(js|jsx|ts|tsx)$/.test(entry.name)) return [];
    if (/\.(test|cy)\.(js|jsx|ts|tsx)$/.test(entry.name)) return [];
    return [path.relative(path.join(SRC, '..'), full)];
});

const importers = () => sourceFiles()
    .filter(file => LIBRARIES.test(fs.readFileSync(path.join(SRC, '..', file), 'utf8')))
    .sort();

describe('Semantic UI removal', () => {
    it('has no new files importing Semantic UI', () => {
        const added = importers().filter(file => !baseline.includes(file));

        // New code must import from src/components/ui instead.  See ui-migration-plan.md.
        expect(added).toEqual([]);
    });

    it('keeps the baseline free of files that no longer import Semantic UI', () => {
        const current = importers();
        const stale = baseline.filter(file => !current.includes(file));

        // Migrating a file should also delete its line here, so the count means something.
        expect(stale).toEqual([]);
    });

    it('has nobody left calling the Semantic toast library', () => {
        /*
         * This one is a ratchet at zero, not a shrinking list.
         *
         * The Semantic toasts only appear if `<SemanticToastContainer/>` is mounted, and
         * that container came out of App.js when App.js migrated.  Any file that goes back
         * to importing `toast` from react-semantic-toasts-2 would therefore raise
         * notifications that silently never appear — no error, no warning, just a delete
         * or a failure the user is never told about.  Import `toast` from
         * `src/components/ui` instead; it takes the same options.
         */
        const TOASTS = /from ['"]react-semantic-toasts-2/;
        const importers = sourceFiles()
            .filter(file => TOASTS.test(fs.readFileSync(path.join(SRC, '..', file), 'utf8')));

        expect(importers).toEqual([]);
    });

    it('declares every migrated file that still leans on Semantic CSS classes', () => {
        /*
         * A file can stop importing semantic-ui-react and still depend on its stylesheet
         * by writing `className="ui stackable grid"`.  The import ratchet above cannot see
         * that, so when Phase 4 deletes semantic.min.css the layout would silently
         * collapse.  Anything on this list is a deliberate bridge that must be revisited
         * then; anything NOT on it is an accident.
         */
        // Empty, and it should stay that way: Semantic's stylesheet is no longer loaded,
        // so a `ui ...` class name now styles nothing at all.
        const allowed = [];

        const bridges = sourceFiles()
            .filter(file => !baseline.includes(file))
            .filter(file => /className=["']ui /.test(fs.readFileSync(path.join(SRC, '..', file), 'utf8')));

        expect(bridges.sort()).toEqual(allowed.sort());
    });

    it('lets no migrated file keep rendering Semantic through Theme.tsx', () => {
        /*
         * The import check above only sees `semantic-ui-react`.  `Theme.tsx` re-exports
         * Semantic-backed wrappers under friendly names, so a file could drop its direct
         * imports, leave the baseline, and still put Semantic components on screen —
         * which is exactly how a Semantic modal survived in the search shortcut long
         * after that file looked migrated.
         *
         * Theme.tsx also re-exports theme *names* (`themeChoices`, `darkTheme`, ...),
         * which are data and carry no markup; those come from `themes/names` instead, so
         * any import from Theme in a migrated file is a component import and a mistake.
         */
        const fromTheme = /from ['"](\.{1,2}\/)+Theme['"]/;
        const leaks = sourceFiles()
            .filter(file => !baseline.includes(file))
            .filter(file => !file.endsWith('components/Theme.tsx'))
            .filter(file => fromTheme.test(fs.readFileSync(path.join(SRC, '..', file), 'utf8')));

        expect(leaks).toEqual([]);
    });

    it('reports how much of the migration is left', () => {
        // Not an assertion so much as a progress readout in the test output.
        const remaining = importers().length;
        expect(remaining).toBeLessThanOrEqual(baseline.length);
        console.log(`Semantic UI: ${remaining} files remaining to migrate.`);
    });
});
