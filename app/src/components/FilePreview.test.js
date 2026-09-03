import {getSlicerURL, SLICERS} from "./FilePreview";

describe('getSlicerURL', () => {
    test('builds a slicer link with the absolute media URL encoded once', () => {
        const previewFile = {path: '3d printing/benchy.stl'};
        const url = getSlicerURL(previewFile, 'orcaslicer');
        expect(url).toEqual(
            `orcaslicer://open?file=${encodeURIComponent('http://localhost/media/3d%20printing/benchy.stl')}`);
    });

    test('prefers primary_path and encodes special characters', () => {
        const previewFile = {
            primary_path: 'models/Buckle #2 (v2)/buckle.3mf',
            path: 'models/Buckle #2 (v2)/buckle.stl',
        };
        const url = getSlicerURL(previewFile, 'bambustudio');
        expect(url).toEqual(
            `bambustudio://open?file=${encodeURIComponent('http://localhost/media/models/Buckle%20%232%20(v2)/buckle.3mf')}`);
    });

    test('PrusaSlicer is not offered because it only downloads from whitelisted domains', () => {
        expect(SLICERS.map(s => s.scheme)).not.toContain('prusaslicer');
    });
});

describe('PDF gating (source contract)', () => {
    /*
     * Which previews withhold their content in a filtering theme.
     *
     * A PDF is the only one that must: the browser draws it in its own out-of-process viewer,
     * which the theme's SVG filter never reaches, so it arrives in full color -- measured at
     * 39.8% non-red pixels inside the preview modal on a device in night mode.  Text and the
     * EPUB viewer are documents of our own and filter correctly, so gating them would hide
     * something for no reason.
     *
     * Read off the source rather than rendered: the modal builders are plain functions called
     * from an event handler, reached only through a file-click on a mounted browser page.  This
     * checks the wiring; ui.test.js checks that MediaGate itself behaves.
     */
    const fs = require('fs');
    const path = require('path');
    const source = fs.readFileSync(path.join(__dirname, 'FilePreview.js'), 'utf8');

    /** The `setModalContent(...)` line for the branch guarded by `mimetype.startsWith(x)`. */
    const branchCall = (mimetype) => {
        const at = source.indexOf(`mimetype.startsWith('${mimetype}')`);
        if (at < 0) return null;
        const rest = source.slice(at, at + 400);
        const call = rest.match(/setModalContent\([^\n]*/);
        return call ? call[0] : null;
    };

    test('the PDF preview is gated', () => {
        expect(branchCall('application/pdf')).toContain('gatePdf: true');
    });

    test.each([
        ['text/', 'text'],
        ['application/epub', 'the EPUB viewer'],
    ])('%s is not gated, because %s is filtered correctly', (mimetype) => {
        const call = branchCall(mimetype);

        // The premise: a branch that could not be found would vacuously "not be gated".
        expect(call).not.toBeNull();
        expect(call).not.toContain('gatePdf');
    });
});

describe('preview gate remounting (source contract)', () => {
    /*
     * A revealed PDF must not carry its reveal over to the next document.
     *
     * The effect that rebuilds a preview sets the modal to null and then to the new content in
     * a single pass, so React 18 batches both updates and reconciles rather than unmounting:
     * the MediaGate fiber survives across documents.  Without a key, a reader who revealed PDF
     * A and then opened PDF B would get B in full color with no prompt -- the flash the whole
     * feature exists to prevent.
     */
    const fs = require('fs');
    const path = require('path');
    const source = fs.readFileSync(path.join(__dirname, 'FilePreview.js'), 'utf8');

    test('the gate is keyed by the document URL', () => {
        const gate = source.match(/<MediaGate([^>]*)>/);

        expect(gate).not.toBeNull();
        expect(gate[1]).toMatch(/key=\{url\}/);
    });

    test('the rebuild really does batch, which is why the key is needed', () => {
        /*
         * The premise for the test above.  If the rebuild ever unmounted the modal between
         * documents, the key would be redundant -- and if this assertion stopped holding, the
         * reasoning in the comment above would be stale rather than merely belt-and-braces.
         */
        const effects = source.split('React.useEffect');
        const rebuild = effects.filter(body =>
            body.includes('setPreviewModal(null)') && body.includes('setModalContent('));

        expect(rebuild.length).toBeGreaterThan(0);
    });
});

describe('IframePreview color scheme', () => {
    /*
     * The previewed file is a bare document with no styles of its own, so it renders with the
     * browser's default stylesheet for whatever color-scheme the iframe element declares.  If
     * the scheme does not follow the theme, one combination is always unreadable: a dark page
     * scheme with a white iframe renders the browser's light text on white.
     */
    const {render} = require('@testing-library/react');
    const {ThemeContext} = require('../contexts/contexts');
    const {IframePreview} = require('./FilePreview');

    const renderWithTheme = (isDark) => render(
        <ThemeContext.Provider value={{isDark, mediaFilterEnabled: false}}>
            <IframePreview url='/media/config/wrolpi.yaml'/>
        </ThemeContext.Provider>
    );

    test('dark themes render the document dark with a dark background', () => {
        const {container} = renderWithTheme(true);
        const iframe = container.querySelector('iframe');
        expect(iframe.style.colorScheme).toEqual('dark');
    });

    test('the dark background is the theme panel color', () => {
        /*
         * Read off the source because jsdom's CSSOM drops var() declarations entirely, so a
         * rendered iframe in jsdom cannot show the background it gets in a real browser.
         */
        const fs = require('fs');
        const path = require('path');
        const source = fs.readFileSync(path.join(__dirname, 'FilePreview.js'), 'utf8');
        expect(source).toContain(`backgroundColor: isDark ? 'var(--panel)' : '#ffffff'`);
    });

    test('the light theme renders the document black-on-white', () => {
        const {container} = renderWithTheme(false);
        const iframe = container.querySelector('iframe');
        expect(iframe.style.colorScheme).toEqual('light');
        expect(iframe.style.backgroundColor).toEqual('rgb(255, 255, 255)');
    });
});
