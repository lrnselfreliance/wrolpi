import React from 'react';
import {fireEvent, render, screen} from '../test-utils';
import {SearchFilterButton} from './Files';
import {QueryContext} from '../contexts/contexts';

// Render SearchFilterButton with a controlled QueryContext so the search hooks
// (useSearchFilter/useSearchOrder/useSearchDate/useSearch) can read the URL
// query params without a real router/provider.
//
// `render` here comes from `../test-utils`, which already supplies MantineProvider
// (needed by components under src/components/ui, e.g. the Toggle/Switch) and a
// BrowserRouter, plus a default ThemeContext -- so only QueryContext needs wiring here.
function renderButton(props = {}, initialParams = {}, onUpdateQuery = null) {
    const params = new URLSearchParams(initialParams);

    function Wrapper({children}) {
        const [searchParams, setSearchParams] = React.useState(params);
        const updateQuery = (newParams) => {
            if (onUpdateQuery) {
                onUpdateQuery(newParams);
            }
            const next = new URLSearchParams(searchParams.toString());
            Object.entries(newParams).forEach(([k, v]) => {
                if (v === null || v === undefined) {
                    next.delete(k);
                } else if (Array.isArray(v)) {
                    next.delete(k);
                    v.forEach(i => next.append(k, String(i)));
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
    }

    return render(<Wrapper><SearchFilterButton {...props}/></Wrapper>);
}

const videoOrders = [
    {value: 'published_datetime', text: 'Published Date'},
    {value: 'size', text: 'Size'},
];

describe('SearchFilterButton', () => {
    it('renders a Filter button with no count badge when nothing is active', () => {
        renderButton({sorts: videoOrders});
        expect(screen.getByText('Filter')).toBeInTheDocument();
        // No active filters -> no numeric badge.
        expect(screen.queryByText('1')).toBeNull();
    });

    it('shows a count badge summing the active filters', () => {
        // order + filter + tag => count of 3.
        renderButton(
            {sorts: videoOrders, fileFilterOptions: [{value: 'video', text: 'Video'}]},
            {order: '-published_datetime', filter: 'video', tag: 'Food'},
        );
        expect(screen.getByText('3')).toBeInTheDocument();
    });

    it('opens the modal and only shows the sections enabled by props', async () => {
        renderButton({sorts: videoOrders});
        fireEvent.click(screen.getByText('Filter'));

        // Enabled sections.
        expect(await screen.findByText('Sort By')).toBeInTheDocument();
        expect(screen.getByText('Tags')).toBeInTheDocument();
        expect(screen.getByText('Results Per Page')).toBeInTheDocument();

        // Disabled sections (no fileFilterOptions, showDates defaults false).  Assert on the date range
        // 'From Year' label, since the 'Published Date' header text collides with a sort option label.
        expect(screen.queryByText('File Type')).toBeNull();
        expect(screen.queryByText('From Year')).toBeNull();
    });

    it('applies changes only on close, not as fields change', async () => {
        const spy = jest.fn();
        renderButton({sorts: videoOrders}, {}, spy);
        fireEvent.click(screen.getByText('Filter'));

        // Changing the sort field updates the draft but must NOT perform the search yet.
        fireEvent.click(await screen.findByText('Size'));
        expect(spy).not.toHaveBeenCalled();

        // Closing via Done commits the draft in a single query update.
        fireEvent.click(screen.getByText('Done'));
        expect(spy).toHaveBeenCalledTimes(1);
        expect(spy.mock.calls[0][0]).toMatchObject({order: '-size'});
    });

    it('Clear All resets results-per-page to the default on close', async () => {
        const spy = jest.fn();
        renderButton({sorts: videoOrders}, {l: '96'}, spy);
        fireEvent.click(screen.getByText('Filter'));
        fireEvent.click(await screen.findByText('Clear All'));
        fireEvent.click(screen.getByText('Done'));
        expect(spy).toHaveBeenCalledTimes(1);
        expect(spy.mock.calls[0][0]).toMatchObject({l: 24});
    });

    it('does not update the query when closed without changes', async () => {
        const spy = jest.fn();
        renderButton({sorts: videoOrders}, {}, spy);
        fireEvent.click(screen.getByText('Filter'));
        fireEvent.click(await screen.findByText('Done'));
        expect(spy).not.toHaveBeenCalled();
    });

    it('counts the censored filter and applies it on close when showCensored is set', async () => {
        const spy = jest.fn();
        renderButton({sorts: videoOrders, showCensored: true}, {}, spy);

        // No censored badge initially.
        expect(screen.queryByText('1')).toBeNull();

        fireEvent.click(screen.getByText('Filter'));
        // The Availability section/toggle is shown.
        expect(await screen.findByText('Availability')).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('toggle'));
        // Draft only — nothing applied yet.
        expect(spy).not.toHaveBeenCalled();

        fireEvent.click(screen.getByText('Done'));
        expect(spy).toHaveBeenCalledTimes(1);
        expect(spy.mock.calls[0][0]).toMatchObject({censored: 'true'});
    });

    it('does not show the Availability section unless showCensored is set', async () => {
        renderButton({sorts: videoOrders});
        fireEvent.click(screen.getByText('Filter'));
        await screen.findByText('Sort By');
        expect(screen.queryByText('Availability')).toBeNull();
    });

    it('shows a count badge when the censored filter is active in the URL', () => {
        renderButton({sorts: videoOrders, showCensored: true}, {censored: 'true'});
        expect(screen.getByText('1')).toBeInTheDocument();
    });

    it('counts the deep filter and applies it on close when showDeep is set', async () => {
        const spy = jest.fn();
        renderButton({sorts: videoOrders, showDeep: true}, {}, spy);

        // No deep badge initially.
        expect(screen.queryByText('1')).toBeNull();

        fireEvent.click(screen.getByText('Filter'));
        // The Search Depth section/toggle is shown.
        expect(await screen.findByText('Search Depth')).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('toggle'));
        // Draft only — nothing applied yet.
        expect(spy).not.toHaveBeenCalled();

        fireEvent.click(screen.getByText('Done'));
        expect(spy).toHaveBeenCalledTimes(1);
        expect(spy.mock.calls[0][0]).toMatchObject({deep: 'true'});
    });

    it('does not show the Search Depth section unless showDeep is set', async () => {
        renderButton({sorts: videoOrders});
        fireEvent.click(screen.getByText('Filter'));
        await screen.findByText('Sort By');
        expect(screen.queryByText('Search Depth')).toBeNull();
    });

    it('shows a count badge when the deep filter is active in the URL', () => {
        renderButton({sorts: videoOrders, showDeep: true}, {deep: 'true'});
        expect(screen.getByText('1')).toBeInTheDocument();
    });

    it('shows the File Type section when fileFilterOptions are provided', async () => {
        renderButton({
            sorts: videoOrders,
            fileFilterOptions: [{value: 'pdf', text: 'PDF'}, {value: 'epub', text: 'EPUB'}],
        });
        fireEvent.click(screen.getByText('Filter'));
        expect(await screen.findByText('File Type')).toBeInTheDocument();
        expect(screen.getByText('PDF')).toBeInTheDocument();
        expect(screen.getByText('EPUB')).toBeInTheDocument();
    });
});
