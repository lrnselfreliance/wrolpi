/**
 * Test utilities: render helpers that supply what a component actually needs, and no more.
 *
 * Three tiers, because components differ in what they depend on and a single do-everything
 * wrapper hides that:
 *
 *   renderUI              components from src/components/ui.  Mantine's provider only.  These
 *                         take props and read no ambient state, which is enforced by the
 *                         guards in components/ui/ui.test.js.
 *   render                anything that reads a context.  Supplies the REAL providers holding
 *                         fixture values -- see test-fixtures.js -- so consumers run against
 *                         real data instead of a mocked module.
 *   mockModule            the last resort, for hooks that fetch.  Always spreads the actual
 *                         module, which hand-written jest.mock factories forget to do.
 *
 * The point of the middle tier is that `jest.mock('../../contexts/contexts')` should be
 * unnecessary.  Mocking that module replaces every export, including `Media` and the other
 * providers, so each spec that did it reinvented them slightly differently -- one of them
 * defaulting the responsive `Media` to desktop, which quietly left the mobile branch of that
 * component untested.
 */

import React from 'react';
import {render as rtlRender} from '@testing-library/react';
import {BrowserRouter} from 'react-router';
import {MantineProvider} from '@mantine/core';
import {
    MediaContextProvider,
    QueryContext,
    SettingsContext,
    StatusContext,
    ThemeContext,
} from './contexts/contexts';
import {cssVariablesResolver, mantineTheme} from './themes/mantine';
import {darkTheme, isDarkTheme, lightTheme} from './themes/names';
import {
    domainFixture,
    domainsFixture,
    queryContextFixture,
    settingsContextFixture,
    statusContextFixture,
    themeContextFixture,
} from './test-fixtures';

/*
 * Why this file imports only contexts/contexts, and nothing else of the app's.
 *
 * A first attempt had the harness import Tags.js and FileWorkerStatusContext.js so it could
 * supply those providers too.  That put both into the module graph of every spec that imports
 * the harness, ahead of the spec's own mocks, and broke eight suites in two different ways.
 * Where a spec mocked a module those files pull in, the component under test bound to a second
 * instance of it -- a different `jest.fn()` from the one the test configured, so a hook mocked
 * to return a value returned undefined, in a file the test never mentions.  Requiring them
 * lazily fixed that but not the mirror image of it: `useContext(TagsContext)` in a component
 * read a different TagsContext than the one the harness had required, so the provider was
 * ignored and the context default (`SingleTag: null`) won.
 *
 * The lesson is that a test harness must not change what a spec imports.  So this file owns
 * only the four contexts in contexts/contexts.js, and any other context is passed in by the
 * spec, which resolves it exactly as the component does:
 *
 *   import {TagsContext} from '../Tags';
 *   render(<Thing/>, {contexts: [[TagsContext, tagsContextFixture({tags})]]})
 *
 * A private mock context and re-exported `useFileWorkerStatus`/`useReorganizationStatus` also
 * used to live here.  They could never have worked: components import those hooks from
 * contexts/FileWorkerStatusContext, so a copy exported from the harness was read by nothing.
 */

/**
 * Render a component from src/components/ui.
 *
 * Mantine's provider and nothing else, matching what those components can rely on.  Reach for
 * this rather than the full harness when the component takes props and reads no context: a
 * test that supplies providers a component does not use conceals it starting to use one.
 */
export function renderUI(ui, {theme, ...renderOptions} = {}) {
    if (theme) document.documentElement.dataset.theme = theme;
    return rtlRender(
        <MantineProvider theme={mantineTheme} cssVariablesResolver={cssVariablesResolver}>
            {ui}
        </MantineProvider>,
        renderOptions,
    );
}

/**
 * Render anything that reads a context, with the real providers holding fixture values.
 *
 * Every context option takes overrides merged into that context's fixture, so a test states
 * only the part it cares about:
 *
 *   render(<Page/>, {settings: {wrol_mode: true}})
 *   render(<Page/>, {status: {status: statusFixture({flags: {db_up: false}})}})
 *   render(<Page/>, {tags: {tags: [tagFixture({name: 'Repair'})]}})
 *
 * @param {React.ReactElement} ui
 * @param {Object}  [options]
 * @param {boolean} [options.inverted]   render dark; sets the theme and Mantine's scheme together
 * @param {Object}  [options.theme]      ThemeContext overrides
 * @param {Object}  [options.status]     StatusContext overrides
 * @param {Object}  [options.settings]   SettingsContext overrides
 * @param {Object}  [options.query]      QueryContext overrides
 * @param {Array}   [options.contexts]   extra [Context, value] pairs the spec supplies itself,
 *                                       for contexts outside contexts/contexts.js -- see the
 *                                       note at the top of this file for why
 * @param {boolean} [options.withMedia]  wrap in MediaContextProvider (needs window.matchMedia)
 * @param {string}  [options.route]      point jsdom's location here before rendering
 * @param {Object}  [options.themeContext] deprecated alias for `theme`
 */
export function renderWithProviders(
    ui,
    {
        inverted = false,
        theme = {},
        themeContext = {},
        status = {},
        settings = {},
        query = {},
        contexts = [],
        withMedia = false,
        route,
        ...renderOptions
    } = {}
) {
    // render() wraps content in a BrowserRouter rather than a MemoryRouter, so a test wanting
    // a particular URL has to put jsdom's location there first.  Several specs were doing
    // this by hand.
    if (route) window.history.pushState({}, '', route);

    /*
     * The theme decides the colour scheme, rather than the two being set independently.
     *
     * `inverted` used to drive Mantine's scheme on its own, so asking for night or amber
     * through the theme option produced a tree that reported a dark theme while Mantine
     * rendered its light one -- a combination production cannot reach.  A harness inventing
     * states the app never has is worse than one that is merely incomplete: what a test proves
     * about that tree is true of nothing.
     *
     * `isDark` follows from the theme name, but only as a default: a spec deliberately checking
     * what a component does when the two disagree can still say so.
     */
    const requestedTheme = theme.theme ?? themeContext.theme ?? (inverted ? darkTheme : lightTheme);
    const themeValue = themeContextFixture({
        theme: requestedTheme,
        isDark: isDarkTheme(requestedTheme),
        ...themeContext,
        ...theme,
    });
    // Every token table and the whole night-mode treatment key on this attribute, so a
    // component test that leaves it unset cannot exercise any of them.
    document.documentElement.dataset.theme = requestedTheme;
    const statusValue = statusContextFixture(status);
    const settingsValue = settingsContextFixture(settings);
    const queryValue = queryContextFixture(query);

    /*
     * One provider per context, skipping any a spec has mocked away.
     *
     * `jest.mock` on contexts/contexts replaces its exports, so a context can arrive here as
     * undefined -- and one spec passes a hand-written object with a `_currentValue` and no
     * `.Provider`, which works only because `useContext` reads that React internal.  Rendering
     * `undefined.Provider` fails with "element type is invalid" pointing at this wrapper rather
     * than at the mock responsible, which is a miserable trail to follow.  So the harness
     * degrades rather than demanding every spec convert at once.
     */
    const providers = [
        [StatusContext, statusValue],
        [SettingsContext, settingsValue],
        [QueryContext, queryValue],
        [ThemeContext, themeValue],
        ...contexts,
    ];

    function Wrapper({children}) {
        const withProviders = providers.reduceRight(
            (inner, [Context, value]) => (Context && Context.Provider
                ? <Context.Provider value={value}>{inner}</Context.Provider>
                : inner),
            children,
        );

        const content = (
            <BrowserRouter>
                {/* Configured exactly as ThemeProvider configures it: components from
                    src/components/ui render Mantine internals and need it in the tree. */}
                <MantineProvider
                    theme={mantineTheme}
                    cssVariablesResolver={cssVariablesResolver}
                    forceColorScheme={isDarkTheme(requestedTheme) ? 'dark' : 'light'}
                >
                    {withProviders}
                </MantineProvider>
            </BrowserRouter>
        );

        // Opt-in: MediaContextProvider needs window.matchMedia, and a component that does not
        // branch on breakpoint gains nothing from it.
        if (withMedia) {
            return <MediaContextProvider>{content}</MediaContextProvider>;
        }

        return content;
    }

    return rtlRender(ui, {wrapper: Wrapper, ...renderOptions});
}

/**
 * Replace named exports of a module, keeping every other export intact.
 *
 * Takes the module, which the spec resolves itself, not a path to it:
 *
 *   jest.mock('../hooks/customHooks', () =>
 *       require('../test-utils').mockModule(
 *           jest.requireActual('../hooks/customHooks'),
 *           {useDomains: () => mockUseDomains()},
 *       ));
 *
 * The point is the spread.  A factory written by hand returns only the keys it lists, so every
 * other export of that module becomes undefined -- one spec mocks six hooks out of customHooks
 * and blanks the rest, and the next hook a component under it starts calling fails as "not a
 * function" a long way from the cause.
 *
 * It first took a path and called `jest.requireActual` itself, which cannot work: the
 * specifier would resolve relative to THIS file rather than to the spec, so the documented
 * `'../hooks/customHooks'` pointed outside src altogether for any spec in a subdirectory.  The
 * helper had no caller, so nothing ever ran it.  Throwing on a string is deliberate -- silently
 * resolving to the wrong module is the failure that was there to begin with.
 */
export function mockModule(actualModule, overrides) {
    if (typeof actualModule === 'string') {
        throw new Error(
            'mockModule takes the module, not a path: pass jest.requireActual(path) so the '
            + 'specifier resolves from your spec rather than from test-utils.js',
        );
    }
    return {...actualModule, ...overrides};
}

/*
 * The names the existing specs already import.  Both delegate to test-fixtures so a domain is
 * defined once rather than in two places free to disagree.
 */
export const createMockDomain = domainFixture;
export const createMockDomains = domainsFixture;

/**
 * Mock fetch implementation for API calls
 */
export function mockFetch(data, options = {}) {
    const {
        ok = true,
        status = 200,
        delay = 0,
    } = options;

    return jest.fn(() =>
        new Promise((resolve) => {
            setTimeout(() => {
                resolve({
                    ok,
                    status,
                    json: async () => data,
                    text: async () => JSON.stringify(data),
                });
            }, delay);
        })
    );
}

/**
 * Mock API error response
 */
export function mockFetchError(error = 'An error occurred', status = 400) {
    return jest.fn(() =>
        Promise.resolve({
            ok: false,
            status,
            json: async () => ({error}),
            text: async () => error,
        })
    );
}

/**
 * Wait for async updates to complete
 * Useful for testing loading states
 */
export async function waitForLoadingToFinish() {
    const {waitFor} = await import('@testing-library/react');
    await waitFor(() => {
    }, {timeout: 100});
}

/**
 * Test helper to render components in dark mode
 *
 * Usage:
 *   renderInDarkMode(<MyComponent />)
 *
 * Verify inverted styling is applied:
 *   const element = container.querySelector('.ui.segment.inverted');
 *   expect(element).toBeInTheDocument();
 */
export function renderInDarkMode(ui, options = {}) {
    return renderWithProviders(ui, {
        inverted: true,
        ...options
    });
}

/**
 * Test helper to render components in light mode
 * (This is the default, but provided for explicitness in tests)
 */
export function renderInLightMode(ui, options = {}) {
    return renderWithProviders(ui, {
        inverted: false,
        ...options
    });
}

/**
 * Creates a test-friendly form object using real useForm hook
 *
 * This uses the actual useForm implementation, making tests more reliable.
 * The form starts in a "ready" state with the provided data.
 *
 * Usage:
 *   const form = createTestForm({domain: 'test.com', directory: '/path'});
 *   render(<CollectionEditForm form={form} metadata={metadata} />);
 *
 *   // With overrides:
 *   const form = createTestForm(data, {overrides: {loading: true, disabled: true}});
 */
export function createTestForm(initialData = {}, config = {}) {
    // Return a plain object that mimics the useForm interface without actual React hooks
    // This avoids async state updates that cause act() warnings in tests
    const _ = require('lodash');
    const formData = {...initialData};

    const setValue = (path, newValue) => {
        _.set(formData, path, newValue);
    };

    const form = {
        formData,
        ready: true,
        loading: false,
        disabled: false,
        dirty: false,
        error: null,
        errors: {},
        // Methods that update formData directly
        patchFormData: jest.fn((updates) => {
            Object.assign(formData, updates);
        }),
        reset: jest.fn(() => {
            Object.keys(formData).forEach(key => delete formData[key]);
            Object.assign(formData, initialData);
        }),
        onSubmit: config.submitter || jest.fn(async () => initialData),
        // Input helpers
        setError: jest.fn(),
        setValidator: jest.fn(),
        setValidValue: jest.fn(),
        setRequired: jest.fn(),
        // Property getter for field values
        get: (path) => _.get(formData, path),
        setValue: jest.fn((path, value) => setValue(path, value)),
        // getCustomProps - mimics the real useForm method
        getCustomProps: ({name, path, required = false, type = 'text'}) => {
            path = path || name;
            const value = _.get(formData, path);

            const inputProps = {
                type,
                disabled: form.disabled,
                value: value !== undefined ? value : (type === 'array' ? [] : null),
                onChange: (newValue) => {
                    setValue(path, newValue);
                },
                'data-path': path,
            };

            const inputAttrs = {
                valid: true,
                path,
                localSetValue: (newValue) => setValue(path, newValue),
            };

            return [inputProps, inputAttrs];
        },
    };

    // Apply any overrides
    if (config.overrides) {
        Object.assign(form, config.overrides);
    }

    return form;
}

// Re-export everything from React Testing Library
export * from '@testing-library/react';

// Override the default render with our custom one
export {renderWithProviders as render};
