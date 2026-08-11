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
