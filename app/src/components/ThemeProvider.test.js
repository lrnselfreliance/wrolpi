import fs from 'fs';
import path from 'path';
import React, {useContext} from 'react';
import {act, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {ThemeContext} from '../contexts/contexts';
import {
    amberTheme,
    darkTheme,
    isDarkTheme,
    lightTheme,
    nightTheme,
    resolveTheme,
    systemTheme,
    ThemeProvider,
    themeSessionKey,
} from './Theme';
import {mediaFilterSessionKey, resolveMediaFilter, themeMediaFilter} from '../themes/names';
import {clearToasts, toast} from './ui';

// Lets a test drive `prefers-color-scheme` and assert on what the provider applied.
let prefersDark = false;

const mockMatchMedia = () => {
    const listeners = new Set();
    window.matchMedia = jest.fn().mockImplementation(query => ({
        matches: query === '(prefers-color-scheme: dark)' ? prefersDark : false,
        media: query,
        addEventListener: (_event, listener) => listeners.add(listener),
        removeEventListener: (_event, listener) => listeners.delete(listener),
        addListener: (listener) => listeners.add(listener),
        removeListener: (listener) => listeners.delete(listener),
        dispatchEvent: () => false,
    }));
    return {
        // Emulate the OS switching to dark/light while the app is open.
        change: (value) => {
            prefersDark = value;
            act(() => listeners.forEach(listener => listener({matches: value})));
        },
    };
};

function ThemeProbe() {
    const {
        theme, savedTheme, isDark, setTheme, cycleSavedTheme,
        mediaFilter, mediaFilterEnabled, setMediaFilterEnabled,
    } = useContext(ThemeContext);
    return <>
        <span data-testid='theme'>{theme}</span>
        <span data-testid='saved'>{String(savedTheme)}</span>
        <span data-testid='dark'>{String(isDark)}</span>
        <span data-testid='filter-offered'>{mediaFilter ? mediaFilter.id : 'none'}</span>
        <span data-testid='filter-on'>{String(mediaFilterEnabled)}</span>
        <button onClick={() => setTheme(nightTheme)}>night</button>
        <button onClick={() => setTheme(amberTheme)}>amber</button>
        <button onClick={() => setTheme(lightTheme)}>light</button>
        <button onClick={() => setTheme(systemTheme)}>system</button>
        <button onClick={cycleSavedTheme}>cycle</button>
        <button onClick={() => setMediaFilterEnabled(false)}>filter off</button>
        <button onClick={() => setMediaFilterEnabled(true)}>filter on</button>
    </>
}

const renderProvider = () => render(<ThemeProvider><ThemeProbe/></ThemeProvider>);

const appliedTheme = () => document.documentElement.getAttribute('data-theme');
const appliedFilter = () => document.documentElement.getAttribute('data-media-filter');

describe('ThemeProvider', () => {
    beforeEach(() => {
        prefersDark = false;
        localStorage.clear();
        document.documentElement.removeAttribute('data-theme');
        document.documentElement.removeAttribute('data-media-filter');
        mockMatchMedia();
    });

    it('applies the saved theme and stamps it on <html>', () => {
        localStorage.setItem(themeSessionKey, nightTheme);

        renderProvider();

        expect(screen.getByTestId('theme')).toHaveTextContent(nightTheme);
        expect(appliedTheme()).toBe(nightTheme);
    });

    it('falls back to the OS preference when no theme is saved', () => {
        prefersDark = true;

        renderProvider();

        expect(screen.getByTestId('theme')).toHaveTextContent(darkTheme);
        expect(screen.getByTestId('saved')).toHaveTextContent('null');
    });

    it('persists a chosen theme so it survives a reload', async () => {
        renderProvider();

        await userEvent.click(screen.getByRole('button', {name: 'night'}));

        expect(localStorage.getItem(themeSessionKey)).toBe(nightTheme);
        expect(appliedTheme()).toBe(nightTheme);
    });

    it('follows the OS preference while `system` is chosen', async () => {
        const media = mockMatchMedia();
        renderProvider();
        await userEvent.click(screen.getByRole('button', {name: 'system'}));

        media.change(true);

        expect(screen.getByTestId('theme')).toHaveTextContent(darkTheme);
        expect(appliedTheme()).toBe(darkTheme);
    });

    it('ignores the OS preference once a specific theme is chosen', async () => {
        const media = mockMatchMedia();
        renderProvider();
        await userEvent.click(screen.getByRole('button', {name: 'night'}));

        media.change(true);

        expect(screen.getByTestId('theme')).toHaveTextContent(nightTheme);
    });

    it('reports night and amber as dark themes', async () => {
        renderProvider();

        await userEvent.click(screen.getByRole('button', {name: 'night'}));

        expect(screen.getByTestId('dark')).toHaveTextContent('true');
    });

    it('cycles through every theme and back to system', async () => {
        renderProvider();
        const cycle = screen.getByRole('button', {name: 'cycle'});

        const seen = [];
        for (let index = 0; index < 5; index++) {
            await userEvent.click(cycle);
            seen.push(screen.getByTestId('saved').textContent);
        }

        expect(seen).toEqual([lightTheme, darkTheme, nightTheme, amberTheme, systemTheme]);
    });

    it('recovers from a theme name written by an older version', () => {
        localStorage.setItem(themeSessionKey, 'sepia');

        renderProvider();

        expect(screen.getByTestId('theme')).toHaveTextContent(lightTheme);
        expect(appliedTheme()).toBe(lightTheme);
    });
});

describe('ThemeProvider media filtering', () => {
    beforeEach(() => {
        prefersDark = false;
        localStorage.clear();
        document.documentElement.removeAttribute('data-theme');
        document.documentElement.removeAttribute('data-media-filter');
        mockMatchMedia();
    });

    it('filters media in night mode without being asked', async () => {
        // An unfiltered thumbnail undoes dark adaptation, so night starts filtered.
        renderProvider();

        await userEvent.click(screen.getByRole('button', {name: 'night'}));

        expect(appliedFilter()).toBe('night-red');
        expect(screen.getByTestId('filter-on')).toHaveTextContent('true');
    });

    it('leaves amber media alone until the user asks for it', async () => {
        renderProvider();

        await userEvent.click(screen.getByRole('button', {name: 'amber'}));

        expect(appliedFilter()).toBeNull();
        expect(screen.getByTestId('filter-offered')).toHaveTextContent('amber-mono');
    });

    it('applies no filter, and offers none, in a theme without one', async () => {
        renderProvider();

        await userEvent.click(screen.getByRole('button', {name: 'light'}));

        expect(appliedFilter()).toBeNull();
        expect(screen.getByTestId('filter-offered')).toHaveTextContent('none');
    });

    it('turns the filter off when the user says so, and persists it', async () => {
        renderProvider();
        await userEvent.click(screen.getByRole('button', {name: 'night'}));

        await userEvent.click(screen.getByRole('button', {name: 'filter off'}));

        expect(appliedFilter()).toBeNull();
        expect(JSON.parse(localStorage.getItem(mediaFilterSessionKey))).toEqual({night: false});
    });

    it('turns amber filtering on when the user asks', async () => {
        renderProvider();
        await userEvent.click(screen.getByRole('button', {name: 'amber'}));

        await userEvent.click(screen.getByRole('button', {name: 'filter on'}));

        expect(appliedFilter()).toBe('amber-mono');
    });

    it('keeps the choice separate for each theme', async () => {
        // Wanting amber's tint says nothing about wanting night's, and turning night's off
        // must not disarm a filter the user deliberately enabled elsewhere.
        renderProvider();
        await userEvent.click(screen.getByRole('button', {name: 'amber'}));
        await userEvent.click(screen.getByRole('button', {name: 'filter on'}));
        await userEvent.click(screen.getByRole('button', {name: 'night'}));

        await userEvent.click(screen.getByRole('button', {name: 'filter off'}));
        expect(appliedFilter()).toBeNull();

        await userEvent.click(screen.getByRole('button', {name: 'amber'}));
        expect(appliedFilter()).toBe('amber-mono');
    });

    it('restores the saved choice on the next load', () => {
        localStorage.setItem(themeSessionKey, nightTheme);
        localStorage.setItem(mediaFilterSessionKey, JSON.stringify({night: false}));

        renderProvider();

        expect(appliedFilter()).toBeNull();
    });

    it('falls back to the theme default when the stored settings are unusable', () => {
        localStorage.setItem(themeSessionKey, nightTheme);
        localStorage.setItem(mediaFilterSessionKey, 'not json');

        renderProvider();

        // Failing open would leave a user in the dark staring at a white thumbnail.
        expect(appliedFilter()).toBe('night-red');
    });

    it('ignores stored entries for themes that no longer exist', () => {
        localStorage.setItem(themeSessionKey, nightTheme);
        localStorage.setItem(mediaFilterSessionKey, JSON.stringify({sepia: true, night: false}));

        renderProvider();

        expect(appliedFilter()).toBeNull();
    });
});

describe('resolveMediaFilter', () => {
    it('gives every filtering theme a filter defined in MediaFilterDefs', () => {
        // A theme naming a filter that does not exist would silently filter nothing.
        const defs = fs.readFileSync(
            path.join(__dirname, '..', 'themes', 'MediaFilterDefs.tsx'), 'utf8');

        [nightTheme, amberTheme].forEach(theme => {
            const filter = themeMediaFilter(theme);
            expect(defs).toContain(`id='wrolpi-${filter.id}'`);
        });
    });

    it('honours an override in either direction', () => {
        expect(resolveMediaFilter(nightTheme, {})).toBe('night-red');
        expect(resolveMediaFilter(nightTheme, {night: false})).toBe('');
        expect(resolveMediaFilter(amberTheme, {})).toBe('');
        expect(resolveMediaFilter(amberTheme, {amber: true})).toBe('amber-mono');
        expect(resolveMediaFilter(lightTheme, {light: true})).toBe('');
    });
});

describe('theme helpers', () => {
    beforeEach(() => {
        prefersDark = false;
        mockMatchMedia();
    });

    it('resolves explicit theme names as themselves', () => {
        [lightTheme, darkTheme, nightTheme, amberTheme].forEach(theme => {
            expect(resolveTheme(theme)).toBe(theme);
        });
    });

    it('resolves `system` and null from the OS preference', () => {
        expect(resolveTheme(systemTheme)).toBe(lightTheme);
        expect(resolveTheme(null)).toBe(lightTheme);

        prefersDark = true;
        expect(resolveTheme(systemTheme)).toBe(darkTheme);
    });

    it('knows which themes are built on a dark background', () => {
        expect(isDarkTheme(lightTheme)).toBe(false);
        expect(isDarkTheme(darkTheme)).toBe(true);
        expect(isDarkTheme(nightTheme)).toBe(true);
        expect(isDarkTheme(amberTheme)).toBe(true);
    });
});

describe('the toast container ThemeProvider mounts', () => {
    /*
     * Observing the wiring rather than re-stating it.
     *
     * `toast.test.js` and `ui-layout.cy.js` each mount their own `<Notifications>` with the
     * position and limit they expect, so neither would notice if this file moved the container
     * back, changed its limit, or dropped it altogether -- and a missing container while
     * thirteen call sites keep firing is the failure that has already shipped once.  Those
     * suites test `toast()`; this tests that the app has somewhere to put what it produces.
     */

    beforeEach(() => {
        prefersDark = false;
        localStorage.clear();
        mockMatchMedia();
    });

    afterEach(() => act(() => clearToasts()));

    const notifications = () =>
        document.querySelectorAll('[class*="mantine-Notification-root"]');

    it('shows a toast raised by a call site', async () => {
        // The regression that already shipped: no container, thirteen call sites still firing,
        // nothing thrown and nothing shown.
        renderProvider();

        act(() => toast({title: 'Refresh started'}));

        expect(await screen.findByText('Refresh started')).toBeInTheDocument();
    });

    it('puts it in the top right', async () => {
        /*
         * Asserted through a real toast rather than by finding a container.  Mantine renders an
         * empty container for every position it supports, so querying for one returns whichever
         * comes first in the DOM -- `top-center` -- whatever the provider was configured with.
         */
        renderProvider();

        act(() => toast({title: 'Somewhere'}));
        const notification = await screen.findByText('Somewhere');

        expect(notification.closest('[class*="mantine-Notifications-root"]'))
            .toHaveAttribute('data-position', 'top-right');
    });

    it('shows five at once and queues the rest', async () => {
        /*
         * The user-visible behaviour, not the prop: Mantine's own default limit is also 5, so
         * this stays green if `limit={5}` is deleted from the provider.  It is here to catch a
         * limit being *raised* -- a background task that reports twenty times should not bury
         * the page -- rather than to prove the prop is present.
         */
        renderProvider();

        act(() => {
            for (let i = 1; i <= 7; i += 1) {
                toast({title: `Toast ${i}`});
            }
        });

        await waitFor(() => expect(notifications()).toHaveLength(5));
    });
});
