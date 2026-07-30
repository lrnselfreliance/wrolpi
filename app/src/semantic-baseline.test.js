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
 * When the list reaches zero, delete this test, the JSON, and the dependencies.
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

    it('reports how much of the migration is left', () => {
        // Not an assertion so much as a progress readout in the test output.
        const remaining = importers().length;
        expect(remaining).toBeLessThanOrEqual(baseline.length);
        console.log(`Semantic UI: ${remaining} files remaining to migrate.`);
    });
});
