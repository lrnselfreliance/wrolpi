import fs from 'fs';
import path from 'path';
import baseline from './semantic-baseline.json';

/*
 * Semantic UI is gone, and this keeps it gone.
 *
 * It began as a ratchet: semantic-baseline.json listed the 75 files still importing
 * Semantic UI, the list only shrank, and adding a file to it failed the build.  The list
 * reached zero, the three packages are uninstalled, and the baseline is now an empty
 * array kept only so a reintroduction has to delete a file rather than edit one.
 *
 * The assertions below are cheap and each one caught something real during the migration,
 * so they stay: an import would now fail to resolve, but a `className="ui button"` or a
 * reach back through Theme.tsx would not, and neither would reinstalling a package.
 *
 * It is a test rather than an ESLint rule deliberately: `no-restricted-imports` would
 * either print dozens of warnings on every dev rebuild or fail the build outright, and CI
 * unsets CI= for its build step, so warnings there guard nothing.
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

    it('has no Semantic package installed', () => {
        /*
         * The three packages are uninstalled.  An import of a missing module fails loudly,
         * so this guards the quieter mistake: someone reinstalling one -- to "just use a
         * Semantic component for this one thing" -- which would drag the whole library and
         * its 300kB stylesheet back into the bundle.
         */
        const pkg = JSON.parse(
            fs.readFileSync(path.join(SRC, '..', 'package.json'), 'utf8'));
        const named = [...Object.keys(pkg.dependencies || {}),
            ...Object.keys(pkg.devDependencies || {})]
            .filter(name => /semantic/i.test(name));

        expect(named).toEqual([]);
    });

    it('keeps the baseline empty', () => {
        // The migration is finished; the file stays as an empty list so that putting a
        // name back requires a deliberate edit.
        expect(baseline).toEqual([]);
        expect(importers()).toEqual([]);
    });
});
