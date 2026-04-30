import React from 'react';
import {act, renderHook} from '@testing-library/react';
import {render, screen} from '@testing-library/react';
import {usePages} from './customHooks';
import {QueryContext} from '../contexts/contexts';
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

describe('Paginator rendering', () => {
    test('renders exactly totalPages numbered page links (no phantom trailing link)', () => {
        // 48 results at 24 per page -> 2 pages.  If totalPages is 3, semantic-ui
        // will render an extra "3" link that fetches an empty page.
        render(
            <Paginator activePage={1} totalPages={2} onPageChange={() => {}}/>
        );

        // Semantic UI renders page numbers as <a> elements with the page text.
        // Tablet + mobile variants both render here because Media is mocked to
        // pass children through, so each numeric page appears at least once.
        expect(screen.queryAllByText('1').length).toBeGreaterThan(0);
        expect(screen.queryAllByText('2').length).toBeGreaterThan(0);
        expect(screen.queryByText('3')).toBeNull();
    });
});
