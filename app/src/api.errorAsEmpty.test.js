import {
    flasherSearch, getConfigBackups, getDownloaders, getInventoryBackups, getMapSearchStatus, searchMap,
} from './api';

// A helper that fails must say so.  These used to turn a non-OK response into an empty value
// ([], {dates: []}, {results: []}, ...), so every consumer rendered "nothing here" for a server
// error.  They now return undefined; an empty value only ever comes from the server.

jest.mock('./components/ui', () => ({
    ...jest.requireActual('./components/ui'),
    toast: jest.fn(),
}));

const response = (ok, body = {}) => {
    const r = {
        ok,
        status: ok ? 200 : 500,
        json: async () => body,
        text: async () => JSON.stringify(body),
    };
    r.clone = () => r;
    return r;
};

let originalFetch;
beforeEach(() => {
    originalFetch = global.fetch;
});
afterEach(() => {
    global.fetch = originalFetch;
});

const failWith = () => {
    global.fetch = jest.fn(() => Promise.resolve(response(false, {error: 'boom'})));
};
const succeedWith = (body) => {
    global.fetch = jest.fn(() => Promise.resolve(response(true, body)));
};

describe('on a non-OK response, the helper returns undefined', () => {
    test.each([
        ['getConfigBackups', () => getConfigBackups('wrolpi.yaml')],
        ['getInventoryBackups', () => getInventoryBackups('food')],
        ['getDownloaders', () => getDownloaders()],
        ['searchMap', () => searchMap('camp')],
        ['getMapSearchStatus', () => getMapSearchStatus()],
        ['flasherSearch', () => flasherSearch(null, null)],
    ])('%s', async (_name, call) => {
        failWith();
        expect(await call()).toBeUndefined();
    });
});

describe('a confirmed empty result is still empty', () => {
    test('getConfigBackups', async () => {
        succeedWith({dates: []});
        expect(await getConfigBackups('wrolpi.yaml')).toEqual({dates: []});
    });

    test('getInventoryBackups', async () => {
        succeedWith({dates: []});
        expect(await getInventoryBackups('food')).toEqual([]);
    });

    test('getDownloaders', async () => {
        succeedWith({downloaders: []});
        expect(await getDownloaders()).toEqual({downloaders: []});
    });

    test('searchMap', async () => {
        succeedWith({results: [], total: 0});
        expect(await searchMap('camp')).toEqual({results: [], total: 0});
    });

    test('getMapSearchStatus', async () => {
        succeedWith({indexed: [], missing: []});
        expect(await getMapSearchStatus()).toEqual({indexed: [], missing: []});
    });

    test('flasherSearch', async () => {
        succeedWith({file_groups: [], totals: {file_groups: 0}});
        expect(await flasherSearch(null, null)).toEqual([[], 0]);
    });
});
