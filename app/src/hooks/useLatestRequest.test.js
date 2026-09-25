import {act, renderHook} from '@testing-library/react';
import {useLatestRequest} from './customHooks';

// Invariants of useLatestRequest:
//  1. From the moment sendRequest is called until the latest request settles, `loading` is true.
//     Consumers branch on `loading` to decide between a spinner and an empty state, so a window
//     where data is null and loading is false renders "No results" for a search that has not run.
//  2. Only the latest request may write `data` or clear `loading`; a stale request that resolves
//     or rejects after a newer one was sent must not touch either.

const DELAY = 300;

// A fetch function whose promise the test settles by hand.
const deferred = () => {
    let resolve, reject;
    const promise = new Promise((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return {promise, resolve, reject, fn: jest.fn(() => promise)};
};

beforeEach(() => {
    jest.useFakeTimers();
    jest.spyOn(console, 'error').mockImplementation(() => {
    });
});

afterEach(() => {
    jest.useRealTimers();
    console.error.mockRestore();
});

describe('useLatestRequest loading window', () => {
    test('loading is true synchronously after sendRequest, before the debounce elapses', () => {
        const {result} = renderHook(() => useLatestRequest(DELAY));
        expect(result.current.loading).toBe(false);
        expect(result.current.data).toBeNull();

        const req = deferred();
        act(() => {
            result.current.sendRequest(req.fn);
        });

        // The debounce has not fired yet: the fetch has not been called, but the hook must
        // already report that a request is pending.
        expect(req.fn).not.toHaveBeenCalled();
        expect(result.current.loading).toBe(true);
        expect(result.current.data).toBeNull();
    });

    test('loading stays true through the debounce and the fetch, then data arrives', async () => {
        const {result} = renderHook(() => useLatestRequest(DELAY));
        const req = deferred();
        act(() => {
            result.current.sendRequest(req.fn);
        });

        act(() => {
            jest.advanceTimersByTime(DELAY);
        });
        expect(req.fn).toHaveBeenCalledTimes(1);
        expect(result.current.loading).toBe(true);

        await act(async () => {
            req.resolve({results: [1, 2]});
        });
        expect(result.current.loading).toBe(false);
        expect(result.current.data).toEqual({results: [1, 2]});
    });

    test('loading stays true when a second sendRequest resets the debounce', () => {
        const {result} = renderHook(() => useLatestRequest(DELAY));
        const first = deferred();
        const second = deferred();

        act(() => {
            result.current.sendRequest(first.fn);
        });
        act(() => {
            jest.advanceTimersByTime(DELAY - 1);
        });
        act(() => {
            result.current.sendRequest(second.fn);
        });
        act(() => {
            jest.advanceTimersByTime(DELAY - 1);
        });

        // Neither request has fired, and the user is still waiting.
        expect(first.fn).not.toHaveBeenCalled();
        expect(second.fn).not.toHaveBeenCalled();
        expect(result.current.loading).toBe(true);

        act(() => {
            jest.advanceTimersByTime(1);
        });
        expect(first.fn).not.toHaveBeenCalled();
        expect(second.fn).toHaveBeenCalledTimes(1);
        expect(result.current.loading).toBe(true);
    });
});

describe('useLatestRequest stale requests', () => {
    // Fire two requests so both fetches are in flight, returning their deferreds.
    const sendTwo = (result) => {
        const first = deferred();
        const second = deferred();
        act(() => {
            result.current.sendRequest(first.fn);
        });
        act(() => {
            jest.advanceTimersByTime(DELAY);
        });
        act(() => {
            result.current.sendRequest(second.fn);
        });
        act(() => {
            jest.advanceTimersByTime(DELAY);
        });
        expect(first.fn).toHaveBeenCalledTimes(1);
        expect(second.fn).toHaveBeenCalledTimes(1);
        return {first, second};
    };

    test('a stale request that resolves late does not overwrite newer data or clear loading', async () => {
        const {result} = renderHook(() => useLatestRequest(DELAY));
        const {first, second} = sendTwo(result);

        await act(async () => {
            first.resolve('stale');
        });
        expect(result.current.data).toBeNull();
        expect(result.current.loading).toBe(true);

        await act(async () => {
            second.resolve('latest');
        });
        expect(result.current.data).toBe('latest');
        expect(result.current.loading).toBe(false);
    });

    test('a stale request that rejects late does not clear newer data', async () => {
        const {result} = renderHook(() => useLatestRequest(DELAY));
        const {first, second} = sendTwo(result);

        await act(async () => {
            second.resolve('latest');
        });
        expect(result.current.data).toBe('latest');
        expect(result.current.loading).toBe(false);

        await act(async () => {
            first.reject(new Error('slow failure'));
        });
        expect(result.current.data).toBe('latest');
        expect(result.current.loading).toBe(false);
    });

    // Send A and let its fetch start, then send B and leave B's debounce pending.  B has claimed
    // "latest" the moment it was sent, so A is stale even though B has not fetched yet.
    const sendDuringFlight = (result) => {
        const first = deferred();
        const second = deferred();
        act(() => {
            result.current.sendRequest(first.fn);
        });
        act(() => {
            jest.advanceTimersByTime(DELAY);
        });
        expect(first.fn).toHaveBeenCalledTimes(1);
        act(() => {
            result.current.sendRequest(second.fn);
        });
        expect(second.fn).not.toHaveBeenCalled();
        return {first, second};
    };

    test.each([
        ['resolves', (req) => req.resolve('stale')],
        ['rejects', (req) => req.reject(new Error('slow failure'))],
    ])('an in-flight request that %s during a newer debounce neither writes data nor clears loading',
        async (_label, settle) => {
            const {result} = renderHook(() => useLatestRequest(DELAY));
            const {first, second} = sendDuringFlight(result);

            await act(async () => {
                settle(first);
            });
            expect(result.current.data).toBeNull();
            expect(result.current.loading).toBe(true);

            // B's debounce fires and B fetches; still loading until B settles.
            act(() => {
                jest.advanceTimersByTime(DELAY);
            });
            expect(second.fn).toHaveBeenCalledTimes(1);
            expect(result.current.loading).toBe(true);

            await act(async () => {
                second.resolve('latest');
            });
            expect(result.current.data).toBe('latest');
            expect(result.current.loading).toBe(false);
        });

    test('the latest request rejecting clears loading and data', async () => {
        const {result} = renderHook(() => useLatestRequest(DELAY));
        const req = deferred();
        act(() => {
            result.current.sendRequest(req.fn);
        });
        act(() => {
            jest.advanceTimersByTime(DELAY);
        });

        await act(async () => {
            req.reject(new Error('failure'));
        });
        expect(result.current.loading).toBe(false);
        expect(result.current.data).toBeNull();
    });
});

describe('useLatestRequest unmount', () => {
    test('a pending debounce does not fire after unmount', () => {
        const {result, unmount} = renderHook(() => useLatestRequest(DELAY));
        const req = deferred();
        act(() => {
            result.current.sendRequest(req.fn);
        });
        unmount();
        act(() => {
            jest.advanceTimersByTime(DELAY);
        });
        expect(req.fn).not.toHaveBeenCalled();
    });
});
