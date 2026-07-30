import React, {useContext} from 'react';
import {act, render, screen} from '@testing-library/react';
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
    const {theme, savedTheme, isDark, setTheme, cycleSavedTheme} = useContext(ThemeContext);
    return <>
        <span data-testid='theme'>{theme}</span>
        <span data-testid='saved'>{String(savedTheme)}</span>
        <span data-testid='dark'>{String(isDark)}</span>
        <button onClick={() => setTheme(nightTheme)}>night</button>
        <button onClick={() => setTheme(systemTheme)}>system</button>
        <button onClick={cycleSavedTheme}>cycle</button>
    </>
}

const renderProvider = () => render(<ThemeProvider><ThemeProbe/></ThemeProvider>);

const appliedTheme = () => document.documentElement.getAttribute('data-theme');

describe('ThemeProvider', () => {
    beforeEach(() => {
        prefersDark = false;
        localStorage.clear();
        document.documentElement.removeAttribute('data-theme');
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
