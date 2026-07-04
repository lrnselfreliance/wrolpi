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
