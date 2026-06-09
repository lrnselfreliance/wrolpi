import {safeHref} from './Playlists';

// safeHref is the only thing standing between a stored playlist url item and an executable href,
// so every dangerous-scheme vector must return null.
describe('safeHref', () => {
    it('allows http(s) and relative WROLPi paths', () => {
        expect(safeHref('/map?lat=40.76&lon=-111.89&z=12')).toBe('/map?lat=40.76&lon=-111.89&z=12');
        expect(safeHref('/api/zim/1/entry/home')).toBe('/api/zim/1/entry/home');
        expect(safeHref('relative/path')).toBe('relative/path');
        expect(safeHref('http://example.com/page')).toBe('http://example.com/page');
        expect(safeHref('https://example.com/page')).toBe('https://example.com/page');
    });

    it('rejects empty values', () => {
        expect(safeHref('')).toBeNull();
        expect(safeHref(null)).toBeNull();
        expect(safeHref(undefined)).toBeNull();
    });

    it('rejects dangerous schemes', () => {
        expect(safeHref('javascript:alert(1)')).toBeNull();
        expect(safeHref('data:text/html,<script>alert(1)</script>')).toBeNull();
        expect(safeHref('vbscript:msgbox(1)')).toBeNull();
        expect(safeHref('blob:https://example.com/uuid')).toBeNull();
        expect(safeHref('file:///etc/passwd')).toBeNull();
    });

    it('rejects case and whitespace smuggling tricks', () => {
        expect(safeHref('JaVaScRiPt:alert(1)')).toBeNull();
        expect(safeHref(' javascript:alert(1)')).toBeNull();
        expect(safeHref('\tjavascript:alert(1)')).toBeNull();
        // The URL parser strips tab/newline anywhere, exactly as the browser does when resolving
        // the href -- so this must be detected as a javascript: URL and rejected.
        expect(safeHref('java\tscript:alert(1)')).toBeNull();
        expect(safeHref('java\nscript:alert(1)')).toBeNull();
    });

    it('treats percent-encoded schemes as harmless relative paths', () => {
        // Browsers do not percent-decode before scheme detection; this resolves as a relative
        // path, which is safe to keep.
        expect(safeHref('javascript%3Aalert(1)')).toBe('javascript%3Aalert(1)');
    });
});
