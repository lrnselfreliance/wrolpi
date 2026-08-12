import fs from 'fs';
import path from 'path';

/*
 * The document page's embedded viewer, and which of them is withheld in a filtering theme.
 *
 * This is the surface that measured 55% non-red pixels in night mode: a PDF is drawn by the
 * browser in its own out-of-process viewer, which the theme's SVG filter never reaches, so it
 * arrives in full color however the iframe is styled.  The EPUB viewer is a document of our own
 * and tints correctly, so gating it would hide something for no reason.
 *
 * Read off the source.  DocPage renders only after `useDoc` resolves a file group and reaches
 * the embed through several branches of file selection; a render test here would assert more
 * about the mocks than about the wiring.  ui.test.js covers what MediaGate itself does, and
 * FilePreview.test.js covers the same contract on the other embed surface.
 */

const source = fs.readFileSync(path.join(__dirname, 'Docs.js'), 'utf8');

describe('DocPage embed gating (source contract)', () => {
    it('wraps the embedded viewer in a MediaGate', () => {
        // The iframe must not be reachable without passing through the gate.
        const embed = source.match(/<MediaGate[^>]*>\s*<iframe/);

        expect(embed).not.toBeNull();
    });

    it('gates on the live filter state, not on the theme name', () => {
        /*
         * `mediaFilterEnabled` rather than `theme === 'night'`: a reader who turns night's
         * filter off has said they do not want this, and amber with its filter on has the same
         * unreachable PDF and does.
         */
        const gate = source.match(/<MediaGate[^>]*gated=\{([^}]*)\}/);

        expect(gate).not.toBeNull();
        expect(gate[1]).toContain('mediaFilterEnabled');
        expect(gate[1]).toContain('isPdf');
        // The theme's NAME must not appear in the condition.
        expect(gate[1]).not.toMatch(/theme\s*===/);
    });

    it('remounts the gate per document, so revealing one does not reveal the next', () => {
        // Selecting a different file reuses the same fiber otherwise, carrying `revealed` over.
        const gate = source.match(/<MediaGate([^>]*)>/);

        expect(gate[1]).toMatch(/key=\{/);
    });
});
