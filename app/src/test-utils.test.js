import React from 'react';
import {mockModule, render, renderUI, screen} from './test-utils';
import {ThemeContext} from './contexts/contexts';
import {amberTheme, darkTheme, lightTheme, nightTheme} from './themes/names';

/*
 * The harness itself needs tests.
 *
 * Both of these cover mistakes it shipped with.  `mockModule` had no caller at all, so its
 * documented usage was never once executed and could not have worked; and the theme option
 * moved ThemeContext without moving Mantine's color scheme, so asking for night produced a
 * tree that reported night and rendered light -- a state production never reaches, which is
 * the one thing a test harness must not invent.
 */

const ThemeProbe = () => {
    const {theme, isDark} = React.useContext(ThemeContext);
    return <div data-testid='probe'>{`${theme}:${isDark}`}</div>;
};

describe('render keeps the theme and the color scheme together', () => {
    // The dark-background themes, which is what Mantine has to be told about.  night and amber
    // are the interesting ones: neither is ever chosen by prefers-color-scheme, so nothing else
    // would put Mantine's own components on a dark scheme for them.
    [darkTheme, nightTheme, amberTheme].forEach((theme) => {
        it(`renders ${theme} as a dark scheme, and reports it as dark`, () => {
            render(<ThemeProbe/>, {theme: {theme}});

            expect(screen.getByTestId('probe')).toHaveTextContent(`${theme}:true`);
            expect(document.documentElement)
                .toHaveAttribute('data-mantine-color-scheme', 'dark');
        });

        it(`stamps data-theme for ${theme}, so CSS keyed on it applies`, () => {
            // Every token table and the whole night-mode treatment key on this attribute; a
            // component test that never sets it cannot exercise any of them.
            render(<ThemeProbe/>, {theme: {theme}});

            expect(document.documentElement).toHaveAttribute('data-theme', theme);
        });
    });

    it('renders light as a light scheme', () => {
        render(<ThemeProbe/>, {theme: {theme: lightTheme}});

        expect(screen.getByTestId('probe')).toHaveTextContent(`${lightTheme}:false`);
        expect(document.documentElement).toHaveAttribute('data-mantine-color-scheme', 'light');
    });

    it('still honours the older inverted flag', () => {
        render(<ThemeProbe/>, {inverted: true});

        expect(screen.getByTestId('probe')).toHaveTextContent(`${darkTheme}:true`);
        expect(document.documentElement).toHaveAttribute('data-mantine-color-scheme', 'dark');
    });

    it('lets a test contradict the theme deliberately', () => {
        // isDark is derived, not fixed: a spec checking what a component does when the two
        // disagree must still be able to say so.
        render(<ThemeProbe/>, {theme: {theme: nightTheme, isDark: false}});

        expect(screen.getByTestId('probe')).toHaveTextContent(`${nightTheme}:false`);
    });
});

describe('renderUI stamps the theme it is given', () => {
    it('sets data-theme so token-driven CSS resolves', () => {
        renderUI(<div data-testid='plain'>hi</div>, {theme: amberTheme});

        expect(document.documentElement).toHaveAttribute('data-theme', amberTheme);
    });
});

describe('mockModule', () => {
    /*
     * It takes the module, not a path to it.  Passing a path meant `jest.requireActual` ran
     * from inside test-utils.js and resolved the caller's relative specifier against the wrong
     * directory -- for a spec in components/ the documented `'../hooks/customHooks'` pointed
     * outside src entirely.  Handing over the module the spec already resolved cannot go wrong.
     */
    it('keeps every export the caller did not replace', () => {
        const actual = {useOne: () => 1, useTwo: () => 2, CONSTANT: 'x'};
        const replaced = () => 99;

        const result = mockModule(actual, {useTwo: replaced});

        expect(result.useOne()).toBe(1);
        expect(result.useTwo).toBe(replaced);
        expect(result.CONSTANT).toBe('x');
    });

    it('rejects a path, which cannot resolve from here', () => {
        // Failing loudly beats resolving to the wrong module or to nothing at all.
        expect(() => mockModule('../hooks/customHooks', {})).toThrow(/module.*not a path/i);
    });
});
