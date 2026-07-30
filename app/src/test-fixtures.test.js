import React from 'react';
import fs from 'fs';
import path from 'path';
import {render} from '@testing-library/react';
import {QueryContext, SettingsContext, StatusContext, ThemeContext} from './contexts/contexts';
import {
    queryContextFixture,
    settingsContextFixture,
    statusContextFixture,
    themeContextFixture,
} from './test-fixtures';

/*
 * The fixtures are only worth having if they match what the app really carries.  A fixture
 * that has drifted is worse than none: the test passes, the component breaks in a browser,
 * and the fixture is the last place anyone looks.
 *
 * That is not hypothetical here.  The theme fixture supplied `i`, `s` and `t` holding
 * hardcoded Semantic greys for months after ThemeProvider stopped supplying them, and
 * FileBrowser was still reading `inverted` off the context and pasting it into a className --
 * so the tests agreed with the fixture, the fixture agreed with nothing, and the file
 * browser's footer stayed light in all three dark themes.
 *
 * Each context's `createContext` default is the declared shape; these hold the fixtures to it
 * key for key, in both directions.  A property added to a context and forgotten in a fixture
 * fails here, and so does one deleted from a context and left in a fixture.
 */

/** Read a context's default by consuming it with no provider above -- public API only. */
const defaultValueOf = (Context) => {
    let captured;
    const Probe = () => {
        captured = React.useContext(Context);
        return null;
    };
    render(<Probe/>);
    return captured;
};

describe('context fixtures match the contexts they stand in for', () => {
    const cases = [
        ['ThemeContext', ThemeContext, themeContextFixture],
        ['StatusContext', StatusContext, statusContextFixture],
        ['SettingsContext', SettingsContext, settingsContextFixture],
        ['QueryContext', QueryContext, queryContextFixture],
    ];

    cases.forEach(([name, Context, fixture]) => {
        it(`${name} and its fixture declare the same properties`, () => {
            expect(Object.keys(fixture()).sort()).toEqual(Object.keys(defaultValueOf(Context)).sort());
        });

        it(`${name}'s fixture supplies a function wherever the context does`, () => {
            // A callback stubbed as a value rather than a function turns into a "not a
            // function" crash the first time a component calls it, usually in an event
            // handler where the failure surfaces far from the fixture.
            const declared = defaultValueOf(Context);
            const supplied = fixture();
            Object.entries(declared)
                .filter(([, value]) => typeof value === 'function')
                .forEach(([key]) => expect(typeof supplied[key]).toBe('function'));
        });
    });
});

describe('fixtures cannot leak state between tests', () => {
    it('hands out a new object every call', () => {
        // Exported constants let one test mutate what the next one sees; every fixture is a
        // function for that reason, and this fails if one is quietly turned back into a
        // shared object.
        const first = settingsContextFixture();
        const second = settingsContextFixture();

        expect(first).not.toBe(second);
        expect(first.settings).not.toBe(second.settings);

        first.settings.wrol_mode = true;
        expect(second.settings.wrol_mode).toBe(false);
    });

    it('applies overrides without discarding the rest of the shape', () => {
        const settings = settingsContextFixture({pending: true});

        expect(settings.pending).toBe(true);
        expect(settings.settings.media_directory).toBe('/media/wrolpi');
    });
});

describe('specs still mocking a context module', () => {
    /*
     * A ratchet, not a prohibition.  Mocking a context module replaces every export it has,
     * providers included, so each spec that does it reinvents the pieces it still needs --
     * one of them supplies a `Media` that always reports desktop, which quietly leaves the
     * mobile branch of that component untested, and another hand-writes a context as a bare
     * `_currentValue` with no provider at all.
     *
     * These six can pass their contexts to render() instead.  The list is here so the count
     * can only fall: converting one means deleting its line, and a new spec reaching for the
     * old pattern fails this test rather than joining an unread pile.
     */
    const ALLOWED = [
        'components/collections/BatchReorganizeModal.test.js',
        'components/collections/CollectionEditForm.test.js',
        'components/collections/CollectionReorganizeModal.test.js',
        'components/collections/CollectionTable.test.js',
        'components/collections/CollectionTagModal.test.js',
        'hooks/customHooks.test.js',
    ];

    it('is only the specs already known to do it', () => {
        const offenders = [];
        const walk = (dir) => {
            for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) walk(full);
                else if (/\.test\.js$/.test(entry.name)) {
                    const source = fs.readFileSync(full, 'utf8');
                    if (/jest\.mock\('[^']*(contexts\/contexts|FileWorkerStatusContext|\/Tags)'/
                        .test(source)) {
                        offenders.push(path.relative(__dirname, full));
                    }
                }
            }
        };
        walk(__dirname);

        expect(offenders.sort()).toEqual(ALLOWED);
    });
});

describe('the Semantic theme compatibility props are gone for good', () => {
    it('no context, fixture, or component carries i/s/t/inverted from the theme', () => {
        /*
         * These four props are why this whole file exists.  They were removed from
         * ThemeProvider, but survived in the context default, in the test harness, and in one
         * component that read `inverted` and pasted the resulting `undefined` into a
         * className.  Nothing failed, because the fixture supplied what production did not.
         */
        const offenders = [];
        const walk = (dir) => {
            for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) walk(full);
                else if (/\.(js|jsx|ts|tsx)$/.test(entry.name)) {
                    const source = fs.readFileSync(full, 'utf8')
                        .replace(/\/\*[\s\S]*?\*\//g, '')
                        .replace(/^\s*\/\/.*$/gm, '');
                    // Destructuring any of them off ThemeContext, or a bare `inverted:` key
                    // in a context value.
                    if (/const\s*\{[^}]*\binverted\b[^}]*}\s*=\s*(React\.)?useContext\(\s*ThemeContext/
                        .test(source)) {
                        offenders.push(`${path.relative(__dirname, full)} reads theme.inverted`);
                    }
                }
            }
        };
        walk(__dirname);

        expect(offenders).toEqual([]);
    });
});
