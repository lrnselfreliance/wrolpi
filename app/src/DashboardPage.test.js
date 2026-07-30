import React from 'react';
import {render, screen} from './test-utils';
import {Getters, FlagsMessages} from './DashboardPage';
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
