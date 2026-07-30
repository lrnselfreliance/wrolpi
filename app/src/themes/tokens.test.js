import fs from 'fs';
import path from 'path';
import {themeNames, themeSessionKey} from '../components/Theme';

const readFile = (...parts) => fs.readFileSync(path.join(__dirname, ...parts), 'utf8');

const tokensCss = readFile('tokens.css');
const fontsCss = readFile('fonts.css');
const indexHtml = readFile('..', '..', 'public', 'index.html');

/** The custom properties declared in the block for one theme. */
const themeTokens = (theme) => {
    // Light doubles as the fallback, so its block is a grouped selector.
    const pattern = theme === 'light'
        ? /:root,\s*html\[data-theme="light"]\s*{([^}]*)}/
        : new RegExp(`html\\[data-theme="${theme}"]\\s*{([^}]*)}`);
    const match = tokensCss.match(pattern);
    expect(match).not.toBeNull();
    return new Set([...match[1].matchAll(/(--[\w-]+)\s*:/g)].map(m => m[1]));
};

describe('theme tokens', () => {
    it('declares a block for every theme', () => {
        themeNames.forEach(theme => expect(themeTokens(theme).size).toBeGreaterThan(0));
    });

    it('defines the same tokens in every theme', () => {
        // A token missing from one theme inherits the light value, which is how a stray
        // white or blue ends up in night mode.
        const light = themeTokens('light');
        themeNames.filter(theme => theme !== 'light').forEach(theme => {
            const missing = [...light].filter(token => !themeTokens(theme).has(token)
                // Fonts are a role assignment, not a color; only amber overrides one.
                && !token.startsWith('--font-'));
            expect({theme, missing}).toEqual({theme, missing: []});
        });
    });

    it('uses only red hues in the night theme', () => {
        // Night's whole purpose is that no non-red pixel reaches the eye.
        const hexes = [...tokensCss.match(/html\[data-theme="night"]\s*{([^}]*)}/)[1]
            .matchAll(/#([0-9a-f]{6})/gi)].map(m => m[1]);
        expect(hexes.length).toBeGreaterThan(10);
        hexes.forEach(hex => {
            const [r, g, b] = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16));
            expect({hex, redDominant: r >= g && r >= b, neutralGreenBlue: g === b}).toEqual(
                {hex, redDominant: true, neutralGreenBlue: true}
            );
        });
    });

    it('resolves fonts through role tokens only', () => {
        expect(fontsCss).toMatch(/--font-body:/);
        expect(fontsCss).toMatch(/--font-mono:/);
        // Nothing may hardcode a family: a theme swaps the role, not the rule.
        expect(tokensCss).toMatch(/font-family:\s*var\(--font-body\)/);
        expect(tokensCss).not.toMatch(/font-family:(?!\s*var\()/);
    });
});

describe('pre-paint theme script', () => {
    // The inline script in index.html duplicates the theme names and storage key so the
    // first paint matches the saved theme.  These assertions fail if either side is renamed.
    it('reads the same localStorage key as ThemeProvider', () => {
        expect(indexHtml).toContain(`localStorage.getItem('${themeSessionKey}')`);
    });

    it('recognizes every theme name', () => {
        themeNames.forEach(theme => expect(indexHtml).toContain(`'${theme}'`));
    });

    it('stamps data-theme before the bundle loads', () => {
        const head = indexHtml.slice(0, indexHtml.indexOf('</head>'));
        expect(head).toContain("document.documentElement.setAttribute('data-theme'");
    });
});
