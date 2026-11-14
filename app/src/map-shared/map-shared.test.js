const fs = require('fs');
const path = require('path');

// The standalone map viewer (modules/map/static/index.html) has no build step: it loads copies of
// the shared overlay modules as they are.  The copies must be the modules.

const SHARED = __dirname;
const COPIES = path.join(__dirname, '../../../modules/map/static/js');
const MODULES = fs.readdirSync(SHARED).filter(name => name.endsWith('.js') && !name.endsWith('.test.js'));

describe('the shared map modules', () => {
    test('are the two the standalone viewer loads', () => {
        expect(MODULES.sort()).toEqual(['overlayStyle.js', 'overlays.js']);
    });

    test.each(MODULES)('%s is copied to the standalone viewer as it is (run `npm run sync:map-shared`)', (name) => {
        const copy = path.join(COPIES, name);
        expect(fs.existsSync(copy)).toBe(true);
        expect(fs.readFileSync(copy, 'utf8')).toBe(fs.readFileSync(path.join(SHARED, name), 'utf8'));
    });

    test.each(MODULES)('%s can be loaded by a browser: it imports only its neighbors, by file name', (name) => {
        const source = fs.readFileSync(path.join(SHARED, name), 'utf8');
        const imports = [...source.matchAll(/^\s*(?:import|export)\b[^;]*?\bfrom\s+["']([^"']+)["']/gm)].map(m => m[1]);
        for (const specifier of imports) {
            expect(specifier).toMatch(/^\.\/[A-Za-z]+\.js$/);
            expect(MODULES).toContain(specifier.slice(2));
        }
        // No `require`, and nothing of the app or of React.
        expect(source).not.toMatch(/\brequire\(/);
    });
});
