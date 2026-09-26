import React from 'react';
import {act, renderHook} from '@testing-library/react';
import {render, screen} from '../test-utils';
import {usePages, useDriveTemperature, useDriveHealth, useSearchChannels, useVideoExtras} from './customHooks';
import {getVideoComments, getVideoDescription, searchChannels} from '../api';
import {QueryContext, StatusContext} from '../contexts/contexts';
import {Paginator} from '../components/Common';

// Build a wrapper that provides a controlled QueryContext so usePages can read
// `o` and `l` from searchParams without a real router.
const makeWrapper = (initialParams = {}) => {
    const params = new URLSearchParams(initialParams);
    const Wrapper = ({children}) => {
        const [searchParams, setSearchParams] = React.useState(params);

        const updateQuery = (newParams) => {
            const next = new URLSearchParams(searchParams.toString());
            Object.entries(newParams).forEach(([k, v]) => {
                if (v === null || v === undefined) {
                    next.delete(k);
                } else {
                    next.set(k, String(v));
                }
            });
            setSearchParams(next);
        };

        return (
            <QueryContext.Provider value={{searchParams, updateQuery, getLocationStr: () => '/'}}>
                {children}
            </QueryContext.Provider>
        );
    };
    return Wrapper;
};

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getVideoComments: jest.fn(),
    getVideoDescription: jest.fn(),
    searchChannels: jest.fn(),
}));

// Mock Media so Paginator renders both mobile + tablet variants synchronously.
jest.mock('../contexts/contexts', () => {
    const actual = jest.requireActual('../contexts/contexts');
    return {
        ...actual,
        Media: ({children}) => <>{children}</>,
    };
});

describe('usePages.setTotal -> totalPages', () => {
    // These cases describe the contract: how many pages should the Paginator
    // render given a total result count and a per-page limit?
    const cases = [
        // [total, limit, expectedPages, label]
        [0, 24, 1, 'no results -> 1 page'],
        [1, 24, 1, 'fewer than one page'],
        [23, 24, 1, 'just under one page'],
        [24, 24, 1, 'exactly one page (BUG: reports 2)'],
        [25, 24, 2, 'one full page plus one'],
        [47, 24, 2, 'just under two pages'],
        [48, 24, 2, 'exactly two pages (BUG: reports 3)'],
        [49, 24, 3, 'just over two pages'],
        [72, 24, 3, 'exactly three pages (BUG: reports 4)'],
        [100, 24, 5, 'partial last page'],
        [144, 24, 6, 'exactly six pages (BUG: reports 7)'],
    ];

    test.each(cases)('total=%i limit=%i -> %i pages (%s)', (total, limit, expected) => {
        const wrapper = makeWrapper({l: String(limit)});
        const {result} = renderHook(() => usePages(limit), {wrapper});

        act(() => {
            result.current.setTotal(total);
        });

        expect(result.current.totalPages).toBe(expected);
    });

    test('the last reported page yields an offset within total (no empty trailing page)', () => {
        // This is the user-visible symptom: clicking the last page link should
        // produce an offset that the API can still satisfy.  When totalPages is
        // off-by-one, the last page maps to offset === total (or > total) and
        // the API returns zero rows.
        const total = 48;
        const limit = 24;
        const wrapper = makeWrapper({l: String(limit)});
        const {result} = renderHook(() => usePages(limit), {wrapper});

        act(() => {
            result.current.setTotal(total);
        });

        act(() => {
            result.current.setPage(result.current.totalPages);
        });

        // setPage stores (page - 1) * limit as `o` in the query.
        const lastOffset = (result.current.totalPages - 1) * limit;
        expect(lastOffset).toBeLessThan(total);
    });
});

describe('useDriveTemperature', () => {
    const makeStatusWrapper = (status) => ({children}) => (
        <StatusContext.Provider value={{status}}>
            {children}
        </StatusContext.Provider>
    );

    test('selects the hottest drive and reads thresholds from the payload', () => {
        const status = {
            smart_stats: {
                drives: [
                    {device: 'sda', temperature: 51},
                    {device: 'sdb', temperature: 60},
                ],
                high_temperature: 55,
                critical_temperature: 65,
            },
        };
        const {result} = renderHook(() => useDriveTemperature(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.device).toBe('sdb');
        expect(result.current.temperature).toBe(60);
        expect(result.current.highTemperature).toBe(55);
        expect(result.current.criticalTemperature).toBe(65);
    });

    test('ignores drives without a numeric temperature', () => {
        const status = {
            smart_stats: {
                drives: [
                    {device: 'sda', temperature: null},
                    {device: 'sdb', temperature: 48},
                ],
                high_temperature: 55,
                critical_temperature: 65,
            },
        };
        const {result} = renderHook(() => useDriveTemperature(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.device).toBe('sdb');
        expect(result.current.temperature).toBe(48);
    });

    test('defaults to no warning and default thresholds when smart_stats is absent', () => {
        const {result} = renderHook(() => useDriveTemperature(),
            {wrapper: makeStatusWrapper({})});
        expect(result.current.device).toBeNull();
        expect(result.current.temperature).toBe(0);
        expect(result.current.highTemperature).toBe(55);
        expect(result.current.criticalTemperature).toBe(65);
    });

    test('returns no drive when none report a temperature', () => {
        const status = {
            smart_stats: {
                drives: [{device: 'sda', temperature: null}],
                high_temperature: 55,
                critical_temperature: 65,
            },
        };
        const {result} = renderHook(() => useDriveTemperature(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.device).toBeNull();
        expect(result.current.temperature).toBe(0);
    });
});

describe('useDriveHealth', () => {
    const makeStatusWrapper = (status) => ({children}) => (
        <StatusContext.Provider value={{status}}>
            {children}
        </StatusContext.Provider>
    );

    test('flags drives whose SMART assessment is FAIL', () => {
        const status = {
            smart_stats: {
                drives: [
                    {device: 'sda', assessment: 'PASS'},
                    {device: 'sdb', assessment: 'FAIL'},
                ],
            },
        };
        const {result} = renderHook(() => useDriveHealth(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.failing).toBe(true);
        expect(result.current.failingDevices).toEqual(['sdb']);
    });

    test('reports every failing drive', () => {
        const status = {
            smart_stats: {
                drives: [
                    {device: 'sda', assessment: 'FAIL'},
                    {device: 'sdb', assessment: 'FAIL'},
                ],
            },
        };
        const {result} = renderHook(() => useDriveHealth(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.failingDevices).toEqual(['sda', 'sdb']);
    });

    test('does not warn when all drives PASS', () => {
        const status = {
            smart_stats: {drives: [{device: 'sda', assessment: 'PASS'}]},
        };
        const {result} = renderHook(() => useDriveHealth(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.failing).toBe(false);
        expect(result.current.failingDevices).toEqual([]);
    });

    test('ignores drives with an unknown (null) assessment', () => {
        const status = {
            smart_stats: {drives: [{device: 'sda', assessment: null}]},
        };
        const {result} = renderHook(() => useDriveHealth(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.failing).toBe(false);
    });

    test('does not warn when smart_stats is absent', () => {
        const {result} = renderHook(() => useDriveHealth(),
            {wrapper: makeStatusWrapper({})});
        expect(result.current.failing).toBe(false);
        expect(result.current.failingDevices).toEqual([]);
    });

    test('surfaces WARN drives separately from FAIL', () => {
        const status = {
            smart_stats: {
                drives: [
                    {device: 'sda', health: 'PASS', assessment: 'PASS'},
                    {device: 'sdb', health: 'WARN', assessment: 'PASS'},
                    {device: 'sdc', health: 'FAIL', assessment: 'FAIL'},
                ],
            },
        };
        const {result} = renderHook(() => useDriveHealth(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.failingDevices).toEqual(['sdc']);
        expect(result.current.warning).toBe(true);
        expect(result.current.warningDevices).toEqual(['sdb']);
    });

    test('prefers derived health over raw assessment', () => {
        // A drive self-assessing PASS but with pending sectors is WARN.
        const status = {
            smart_stats: {drives: [{device: 'sda', health: 'WARN', assessment: 'PASS'}]},
        };
        const {result} = renderHook(() => useDriveHealth(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.failing).toBe(false);
        expect(result.current.warningDevices).toEqual(['sda']);
    });

    test('falls back to assessment when health is absent', () => {
        const status = {
            smart_stats: {drives: [{device: 'sda', assessment: 'FAIL'}]},
        };
        const {result} = renderHook(() => useDriveHealth(),
            {wrapper: makeStatusWrapper(status)});
        expect(result.current.failingDevices).toEqual(['sda']);
    });
});

describe('Paginator rendering', () => {
    test('renders exactly totalPages numbered page links (no phantom trailing link)', () => {
        // 48 results at 24 per page -> 2 pages.  If totalPages is 3, the pagination
        // will render an extra "3" link that fetches an empty page.
        render(
            <Paginator activePage={1} totalPages={2} onPageChange={() => {}}/>
        );

        // Page numbers render as <a> elements carrying the page text.
        // Tablet + mobile variants both render here because Media is mocked to
        // pass children through, so each numeric page appears at least once.
        expect(screen.queryAllByText('1').length).toBeGreaterThan(0);
        expect(screen.queryAllByText('2').length).toBeGreaterThan(0);
        expect(screen.queryByText('3')).toBeNull();
    });
});

describe('useVideoExtras', () => {
    // The description is fetched on its own, like comments: the Video payload no longer carries it,
    // so list pages never pay for it.
    test('fetches comments and description for a video', async () => {
        getVideoComments.mockResolvedValue({comments: [{id: 'c1', parent: 'root'}]});
        getVideoDescription.mockResolvedValue({description: 'hello'});
        const {result} = renderHook(() => useVideoExtras(7));
        await act(async () => {
        });
        expect(getVideoComments).toHaveBeenCalledWith(7);
        expect(getVideoDescription).toHaveBeenCalledWith(7);
        expect(result.current.comments).toEqual([{id: 'c1', parent: 'root'}]);
        expect(result.current.description).toBe('hello');
    });

    test('clears both when there is no video', () => {
        const {result} = renderHook(() => useVideoExtras(null));
        expect(result.current.comments).toBeNull();
        expect(result.current.description).toBeNull();
    });

    // State contract, matching the rest of the hooks: null = pending, undefined = error,
    // [] / '' = loaded and empty.  The page branches on these to choose between a placeholder,
    // an error, and "No comments have been downloaded".
    test('both are pending (null) until the responses arrive', () => {
        getVideoComments.mockReturnValue(new Promise(() => {
        }));
        getVideoDescription.mockReturnValue(new Promise(() => {
        }));
        const {result} = renderHook(() => useVideoExtras(7));
        expect(result.current.comments).toBeNull();
        expect(result.current.description).toBeNull();
    });

    test('a video with no comments or description loads as empty, not pending', async () => {
        // The API serializes a missing info_json field as null.
        getVideoComments.mockResolvedValue({comments: null});
        getVideoDescription.mockResolvedValue({description: null});
        const {result} = renderHook(() => useVideoExtras(7));
        await act(async () => {
        });
        expect(result.current.comments).toEqual([]);
        expect(result.current.description).toBe('');
    });

    test('a failed fetch yields undefined so the page can show an error instead of "no comments"', async () => {
        getVideoComments.mockRejectedValue(new Error('boom'));
        getVideoDescription.mockRejectedValue(new Error('boom'));
        const spy = jest.spyOn(console, 'error').mockImplementation(() => {
        });
        try {
            const {result} = renderHook(() => useVideoExtras(7));
            await act(async () => {
            });
            expect(result.current.comments).toBeUndefined();
            expect(result.current.description).toBeUndefined();
        } finally {
            spy.mockRestore();
        }
    });

    test('switching video resets both to pending before the new responses arrive', async () => {
        getVideoComments.mockResolvedValue({comments: [{id: 'c1', parent: 'root'}]});
        getVideoDescription.mockResolvedValue({description: 'first'});
        const {result, rerender} = renderHook(({id}) => useVideoExtras(id), {initialProps: {id: 7}});
        await act(async () => {
        });
        expect(result.current.description).toBe('first');

        // The next video's responses are slow: the previous video's data must not linger.
        getVideoComments.mockReturnValue(new Promise(() => {
        }));
        getVideoDescription.mockReturnValue(new Promise(() => {
        }));
        rerender({id: 8});
        expect(result.current.comments).toBeNull();
        expect(result.current.description).toBeNull();
    });

    test('a slow response for the previous video does not overwrite the current one', async () => {
        // Video 7's responses are slow; the user moves on to video 8 before they arrive.
        let resolveComments, resolveDescription;
        getVideoComments.mockReturnValueOnce(new Promise(res => resolveComments = res));
        getVideoDescription.mockReturnValueOnce(new Promise(res => resolveDescription = res));
        const {result, rerender} = renderHook(({id}) => useVideoExtras(id), {initialProps: {id: 7}});

        getVideoComments.mockResolvedValue({comments: [{id: 'c8', parent: 'root'}]});
        getVideoDescription.mockResolvedValue({description: 'eighth'});
        rerender({id: 8});
        await act(async () => {
        });
        expect(result.current.description).toBe('eighth');

        await act(async () => {
            resolveComments({comments: [{id: 'c7', parent: 'root'}]});
            resolveDescription({description: 'seventh'});
        });
        expect(result.current.comments).toEqual([{id: 'c8', parent: 'root'}]);
        expect(result.current.description).toBe('eighth');
    });

    test('returning to a video does not let its first, still-pending request land', async () => {
        // The route clears the video between pages, so the id goes 7 -> undefined -> 8 -> 7 while
        // the very first request for 7 is still in flight (the API timeout is a minute).
        let rejectComments, rejectDescription;
        getVideoComments.mockReturnValueOnce(new Promise((_, rej) => rejectComments = rej));
        getVideoDescription.mockReturnValueOnce(new Promise((_, rej) => rejectDescription = rej));
        const {result, rerender} = renderHook(({id}) => useVideoExtras(id), {initialProps: {id: 7}});

        rerender({id: undefined});
        getVideoComments.mockResolvedValue({comments: [{id: 'c8', parent: 'root'}]});
        getVideoDescription.mockResolvedValue({description: 'eighth'});
        rerender({id: 8});
        getVideoComments.mockResolvedValue({comments: [{id: 'c7b', parent: 'root'}]});
        getVideoDescription.mockResolvedValue({description: 'seventh again'});
        rerender({id: 7});
        await act(async () => {
        });
        expect(result.current.comments).toEqual([{id: 'c7b', parent: 'root'}]);
        expect(result.current.description).toBe('seventh again');

        // The first request finally times out.  Same id, but it is not the newest request.
        const spy = jest.spyOn(console, 'error').mockImplementation(() => {
        });
        try {
            await act(async () => {
                rejectComments(new Error('timeout'));
                rejectDescription(new Error('timeout'));
            });
        } finally {
            spy.mockRestore();
        }
        expect(result.current.comments).toEqual([{id: 'c7b', parent: 'root'}]);
        expect(result.current.description).toBe('seventh again');
    });

    test('a refetch after saving beats the initial description request still in flight', async () => {
        let resolveInitial;
        getVideoComments.mockResolvedValue({comments: []});
        getVideoDescription.mockReturnValueOnce(new Promise(res => resolveInitial = res));
        const {result} = renderHook(() => useVideoExtras(7));

        // The user edits and saves before the page's first description request returned.
        getVideoDescription.mockResolvedValue({description: 'edited'});
        await act(async () => {
            await result.current.fetchDescription();
        });
        expect(result.current.description).toBe('edited');

        await act(async () => {
            resolveInitial({description: 'pre-edit'});
        });
        expect(result.current.description).toBe('edited');
    });
});

describe('useSearchChannels', () => {
    // State contract: null = pending, undefined = fetch failed, [] = no channels.  The Other tab
    // shows "No Channels" only for the last of those; `loading` is true from the first render.
    beforeEach(() => searchChannels.mockReset());

    test('is loading with no channels on the first render', () => {
        searchChannels.mockReturnValue(new Promise(() => {
        }));
        const {result} = renderHook(() => useSearchChannels(['a']));
        expect(result.current.loading).toBe(true);
        expect(result.current.channels).toBeNull();
    });

    test('resolves to the channels and stops loading', async () => {
        searchChannels.mockResolvedValue({channels: [{id: 1, name: 'One'}]});
        const {result} = renderHook(() => useSearchChannels(['a']));
        await act(async () => {
        });
        expect(searchChannels).toHaveBeenCalledWith(['a']);
        expect(result.current.channels).toEqual([{id: 1, name: 'One'}]);
        expect(result.current.loading).toBe(false);
    });

    test('a failed fetch yields undefined, not "no channels"', async () => {
        // The api helper returns undefined on a non-OK response, which the hook cannot destructure.
        searchChannels.mockResolvedValue(undefined);
        const spy = jest.spyOn(console, 'error').mockImplementation(() => {
        });
        try {
            const {result} = renderHook(() => useSearchChannels(['a']));
            await act(async () => {
            });
            expect(result.current.channels).toBeUndefined();
            expect(result.current.loading).toBe(false);
        } finally {
            spy.mockRestore();
        }
    });

    test('a changed tag argument refetches and resets a loaded result to pending', async () => {
        // The Other tab passes the URL's tags on every render; the filter modal changes them in
        // place while the tab stays mounted.
        searchChannels.mockResolvedValue({channels: [{id: 1, name: 'Old'}]});
        const {result, rerender} = renderHook(({tags}) => useSearchChannels(tags), {initialProps: {tags: ['old']}});
        await act(async () => {
        });
        expect(result.current.channels).toEqual([{id: 1, name: 'Old'}]);
        expect(searchChannels).toHaveBeenCalledTimes(1);

        searchChannels.mockReturnValue(new Promise(() => {
        }));
        rerender({tags: ['new']});
        expect(searchChannels).toHaveBeenCalledTimes(2);
        expect(searchChannels).toHaveBeenLastCalledWith(['new']);
        expect(result.current.channels).toBeNull();
        expect(result.current.loading).toBe(true);
    });

    test('a new array with the same tags does not refetch', async () => {
        searchChannels.mockResolvedValue({channels: []});
        const {rerender} = renderHook(({tags}) => useSearchChannels(tags), {initialProps: {tags: ['a']}});
        await act(async () => {
        });
        rerender({tags: ['a']});
        await act(async () => {
        });
        expect(searchChannels).toHaveBeenCalledTimes(1);
    });

    test('a slow response for the old tags is dropped after the tags change', async () => {
        let resolveOld;
        searchChannels.mockReturnValueOnce(new Promise(res => resolveOld = res));
        const {result, rerender} = renderHook(({tags}) => useSearchChannels(tags), {initialProps: {tags: ['old']}});
        expect(result.current.loading).toBe(true);

        searchChannels.mockResolvedValue({channels: [{id: 2, name: 'New'}]});
        rerender({tags: ['new']});
        expect(result.current.channels).toBeNull();
        expect(result.current.loading).toBe(true);
        await act(async () => {
        });
        expect(result.current.channels).toEqual([{id: 2, name: 'New'}]);
        expect(result.current.loading).toBe(false);

        await act(async () => {
            resolveOld({channels: [{id: 1, name: 'Old'}]});
        });
        expect(result.current.channels).toEqual([{id: 2, name: 'New'}]);
        expect(result.current.loading).toBe(false);
    });
});
