import React from 'react';
import {render, screen} from './test-utils';
import {DashboardStatus, Getters, FlagsMessages} from './DashboardPage';
import {SettingsContext, StatusContext} from './contexts/contexts';

// Replace DownloadMenu with a stub that records its props. The deep-link
// behavior under test is just "Getters reads URL params and forwards them
// to DownloadMenu" — we don't need the real downloader forms to verify that.
jest.mock('./components/Download', () => ({
    DownloadMenu: ({initialDownloader, initialUrls, disabled}) => (
        <div data-testid="download-menu">
            <span data-testid="initial-downloader">{initialDownloader || ''}</span>
            <span data-testid="initial-urls">{JSON.stringify(initialUrls || [])}</span>
            <span data-testid="disabled">{String(!!disabled)}</span>
        </div>
    ),
}));

jest.mock('./hooks/customHooks', () => ({
    ...jest.requireActual('./hooks/customHooks'),
    useWROLMode: () => false,
}));

function renderAtUrl(url) {
    // test-utils' render() wraps content in a BrowserRouter (not MemoryRouter),
    // so point the jsdom location at the desired URL before rendering.
    window.history.pushState({}, '', url);
    const status = {flags: {refresh_complete: true}};
    return render(
        <StatusContext.Provider value={{status}}>
            <Getters/>
        </StatusContext.Provider>
    );
}

describe('DashboardPage Getters deep-link', () => {
    it('does not auto-open the download modal without query params', () => {
        renderAtUrl('/');
        expect(screen.queryByTestId('download-menu')).toBeNull();
    });

    it('auto-opens the modal and forwards downloader as initialDownloader', async () => {
        renderAtUrl('/?downloader=archive&download_url=https%3A%2F%2Fexample.com%2Fpage');
        const menu = await screen.findByTestId('download-menu');
        expect(menu).toBeInTheDocument();
        expect(screen.getByTestId('initial-downloader').textContent).toBe('archive');
        expect(JSON.parse(screen.getByTestId('initial-urls').textContent))
            .toEqual(['https://example.com/page']);
    });

    it('forwards multiple download_url params as an array', async () => {
        renderAtUrl(
            '/?downloader=video' +
            '&download_url=https%3A%2F%2Fa.com' +
            '&download_url=https%3A%2F%2Fb.com'
        );
        await screen.findByTestId('download-menu');
        expect(screen.getByTestId('initial-downloader').textContent).toBe('video');
        expect(JSON.parse(screen.getByTestId('initial-urls').textContent))
            .toEqual(['https://a.com', 'https://b.com']);
    });

    it('also handles downloader=rss', async () => {
        renderAtUrl('/?downloader=rss&download_url=https%3A%2F%2Ffeed.example.com');
        await screen.findByTestId('download-menu');
        expect(screen.getByTestId('initial-downloader').textContent).toBe('rss');
    });
});

// The DownloadMenu's seed-object construction (joining initialUrls with
// newlines into the `download` prop's `urls` field) is exercised in the
// browser via manual verification, not unit-tested here — reaching into the
// per-form trees pulls in heavy fetch-driven components.

function renderFlagsMessages({flags = {}, settings = {}} = {}) {
    const status = {flags: {refresh_complete: true, db_up: true, have_internet: true, ...flags}};
    return render(
        <SettingsContext.Provider value={{settings, fetchSettings: () => {}}}>
            <StatusContext.Provider value={{status}}>
                <FlagsMessages/>
            </StatusContext.Provider>
        </SettingsContext.Provider>
    );
}

describe('DashboardPage no-drive-mounted banner', () => {
    it('shows the banner when media_mounted is false', () => {
        renderFlagsMessages({flags: {media_mounted: false}});
        expect(screen.getByText(/No drive mounted/i)).toBeInTheDocument();
        const link = screen.getByText(/Open the Controller/i);
        expect(link).toHaveAttribute('href', '/admin/controller');
    });

    it('hides the banner when media_mounted is true', () => {
        renderFlagsMessages({flags: {media_mounted: true}});
        expect(screen.queryByText(/No drive mounted/i)).toBeNull();
    });

    it('hides the banner when media_mounted is undefined (status not yet loaded)', () => {
        renderFlagsMessages();
        expect(screen.queryByText(/No drive mounted/i)).toBeNull();
    });
});

function renderDashboardStatus() {
    const status = {
        cpu_stats: {percent: 12, cores: 4},
        load_stats: {minute_1: 0.4, minute_5: 0.5, minute_15: 0.6},
        downloads: {pending: 3, disabled: false},
        nic_bandwidth_stats: {},
    };
    return render(
        <StatusContext.Provider value={{status}}>
            <DashboardStatus/>
        </StatusContext.Provider>
    );
}

describe('the dashboard status panel links without looking like a link', () => {
    /*
     * The whole panel is wrapped in a <Link> to /admin/status, which makes it an anchor --
     * and `a` takes `color: var(--blue)` with an underline on hover from tokens.css.  A
     * statistic's value sets no color of its own, so the load figures inherited that: three
     * blue numbers on a panel where nothing else is blue, underlining as a group when the
     * pointer crossed any part of the panel.
     *
     * `no-link-underscore card-link` is the pair already used wherever a link IS the
     * element's own text rather than a link through it -- every card title and meta line.
     * The pointer cursor is untouched: it comes from the UA stylesheet for `a[href]`, and
     * the affordance is the point of wrapping the panel at all.
     *
     * Colors are asserted in ui-layout.cy.js; jsdom does not resolve the custom property
     * these classes rely on.
     */
    it('dresses the status link as the panel\'s own text', () => {
        const {container} = renderDashboardStatus();

        const link = container.querySelector('a[href="/admin/status"]');
        expect(link).toBeInTheDocument();
        expect(link).toHaveClass('card-link');
        expect(link).toHaveClass('no-link-underscore');
    });

    it('does the same for the downloads link beneath it', () => {
        const {container} = renderDashboardStatus();

        const link = container.querySelector('a[href="/admin"]');
        expect(link).toBeInTheDocument();
        expect(link).toHaveClass('card-link');
        expect(link).toHaveClass('no-link-underscore');
    });

    it('leaves the load figures inside it, which is what went blue', () => {
        // The premise for the two assertions above: this link really does wrap statistics
        // whose value carries no color of its own, so it decides theirs.
        const {container} = renderDashboardStatus();

        const link = container.querySelector('a[href="/admin/status"]');
        const values = [...link.querySelectorAll('.wrolpi-statistic-value')];

        expect(values.length).toBeGreaterThanOrEqual(3);
        expect(values.map(value => value.textContent)).toEqual(
            expect.arrayContaining(['0.4', '0.5', '0.6']));
    });
});
