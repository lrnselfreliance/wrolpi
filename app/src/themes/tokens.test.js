import fs from 'fs';
import path from 'path';
import {themeNames, themeSessionKey} from '../components/Theme';
import {mediaFilterSessionKey, themeMediaFilter} from './names';

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

    it('stamps the media filter before the bundle loads too', () => {
        // Otherwise night mode paints a screen of unfiltered thumbnails while the bundle
        // arrives, which costs the user the dark adaptation the theme exists to protect.
        const head = indexHtml.slice(0, indexHtml.indexOf('</head>'));
        expect(head).toContain("document.documentElement.setAttribute('data-media-filter'");
        expect(head).toContain(`localStorage.getItem('${mediaFilterSessionKey}')`);
    });

    it('duplicates the same filter ids and defaults the app uses', () => {
        // The script cannot import from names.ts, so it restates both.  These assertions
        // fail if a theme's filter id or default changes on only one side.
        themeNames.forEach(theme => {
            const filter = themeMediaFilter(theme);
            if (!filter) return;
            expect(indexHtml).toContain(`${theme}: '${filter.id}'`);
            expect(indexHtml).toContain(`${theme}: ${filter.defaultOn}`);
        });
    });
});

describe('media filter rules', () => {
    it('keys on the filter, not on the theme', () => {
        // Filtering is a per-theme setting the user controls, so a rule keyed on
        // `data-theme` could not be turned off.
        const filterRules = [...tokensCss.matchAll(/^html\[([^\]]+)][^{]*{\s*filter:/gm)]
            .map(match => match[1]);

        expect(filterRules.length).toBeGreaterThan(0);
        filterRules.forEach(selector => expect(selector).toMatch(/^data-media-filter=/));
    });

    it('has a rule for every filter a theme offers', () => {
        themeNames.forEach(theme => {
            const filter = themeMediaFilter(theme);
            if (!filter) return;
            expect(tokensCss).toContain(`html[data-media-filter="${filter.id}"]`);
            // Restated for native fullscreen, where an ancestor's filter stops applying.
            expect(tokensCss).toMatch(
                new RegExp(`html\\[data-media-filter="${filter.id}"] :fullscreen`));
        });
    });

    it('never filters an ancestor, only leaf media', () => {
        // A CSS filter creates a containing block, which would break `position: fixed`
        // descendants — the nav bar and every modal.
        expect(tokensCss).not.toMatch(/data-media-filter="[^"]+"]\s*{\s*filter:/);
    });
});
