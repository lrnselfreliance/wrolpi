import fs from 'fs';
import path from 'path';

/*
 * Import cycles that a `const` export cannot survive.
 *
 * `Calculators.js` exports `useCalculators` as a `const` arrow function and imports the ten
 * calculators it renders.  Five of those reached back up to `Apps.js` for `ColoredInput`,
 * and `Apps.js` imports `CalculatorsPage` from `Calculators.js` -- so the hub was in a cycle
 * with its own leaves.
 *
 * Webpack compiles a `const` export to a live getter, and a getter read before the module
 * body reaches the declaration throws `ReferenceError: Cannot access 'useCalculators' before
 * initialization` rather than returning undefined.  With every module evaluated once, in
 * order, the cycle is harmless; it stops being harmless the moment anything re-executes a
 * module in the middle of it, which is exactly what react-refresh does on every save.  The
 * dashboard threw on arrival, repeatably, for the whole of an editing session.
 *
 * So this is a STATIC guard rather than a rendering test.  The failure needs a module to be
 * mid-evaluation when the getter is read, and no test can arrange that from the outside:
 * by the time a spec body runs, every module has finished.  Babel also papers over it --
 * jest would hand back `undefined` where webpack throws.  What is checkable, and what is
 * actually the defect, is the cycle.
 *
 * Scoped to the hubs below rather than the whole tree: `src/` has dozens of long-standing
 * cycles through `Common.js` and `api.js` that this PR is not untangling.  Add a module here
 * when it exports a `const` that others call.
 */

const SRC = __dirname;
const EXTENSIONS = ['.js', '.jsx', '.ts', '.tsx'];

/*
 * Modules that own a subtree and export a `const` into it.  Each must not be reachable from
 * anything it imports.
 */
const HUBS = ['components/Calculators.js'];

const resolve = (specifier, fromFile) => {
    if (!specifier.startsWith('.')) return null;  // A package, not our graph.
    const base = path.resolve(path.dirname(fromFile), specifier);
    const candidates = [
        base,
        ...EXTENSIONS.map(extension => base + extension),
        ...EXTENSIONS.map(extension => path.join(base, `index${extension}`)),
    ];
    const found = candidates.find(candidate =>
        fs.existsSync(candidate) && fs.statSync(candidate).isFile());
    return found && EXTENSIONS.includes(path.extname(found)) ? found : null;
};

/*
 * Static `import ... from '...'` and `export ... from '...'` only.  A dynamic `import()` is
 * deliberately excluded: it defers evaluation, which is one of the ways to BREAK a cycle.
 */
const IMPORT = /(?:^|\n)\s*(?:import|export)[\s\S]*?from\s+['"]([^'"]+)['"]/g;

const importsOf = (file) => {
    const source = fs.readFileSync(file, 'utf8');
    return [...source.matchAll(IMPORT)]
        .map(match => resolve(match[1], file))
        .filter(Boolean);
};

/** The shortest import path from `start` back to itself, or null if there is none. */
const findCycle = (start) => {
    const queue = importsOf(start).map(file => [file]);
    const seen = new Set([start]);
    while (queue.length) {
        const trail = queue.shift();
        const current = trail[trail.length - 1];
        if (current === start) return trail;
        if (seen.has(current)) continue;
        seen.add(current);
        for (const next of importsOf(current)) {
            // `start` is not in `seen`, so it is reachable again and closes the trail.
            if (!seen.has(next) || next === start) queue.push([...trail, next]);
        }
    }
    return null;
};

describe('import cycles', () => {
    it.each(HUBS)('%s is not reachable from its own imports', (hub) => {
        const start = path.join(SRC, hub);
        expect(fs.existsSync(start)).toBe(true);

        const cycle = findCycle(start);
        /*
         * The cycle itself is the assertion's value, not a message beside it -- jest's
         * `expect` takes no message argument, and the path is the only useful thing to
         * read when this fails.
         */
        const readable = cycle
            ? `${hub} is in an import cycle:\n  ${[hub, ...cycle.map(f => path.relative(SRC, f))]
                .join('\n  -> ')}`
            : null;

        expect(readable).toBeNull();
    });

    it('detects a cycle when there is one, and reports a real one', () => {
        /*
         * The walker checked against itself.  Without this, the guard above passes just as
         * happily when `findCycle` is broken and returns null for everything -- the failure
         * mode of every static check that has nothing to find.
         *
         * `Common.js` is a hub with long-standing cycles this PR is not untangling, so it is
         * a reliable positive.  The claim is about the walker's invariants rather than which
         * files it names, because naming a pair makes the test fail the day that pair is
         * legitimately untangled.
         */
        const start = path.join(SRC, 'components/Common.js');
        const cycle = findCycle(start);

        expect(cycle).not.toBeNull();
        // The trail closes on where it started.
        expect(cycle[cycle.length - 1]).toBe(start);
        // Every step is an import the walker did not invent.
        [start, ...cycle].forEach((file, index) => {
            if (index === cycle.length) return;
            expect(importsOf(file)).toContain(cycle[index]);
        });
    });
});
